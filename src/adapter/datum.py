from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Literal

import requests
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# SQL Safety Gate – blocks destructive DDL/DML at the adapter boundary
# ---------------------------------------------------------------------------

class DestructiveSqlError(Exception):
    """Raised when SQL contains a blocked destructive operation."""
    pass


# Allowed statement types that the app legitimately sends through Datum.
# Anything not matching these prefixes (after stripping BEGIN/COMMIT wrappers)
# is rejected.
_ALLOWED_STATEMENT_PREFIXES = re.compile(
    r"^\s*"
    r"(?:BEGIN|COMMIT|ROLLBACK"
    r"|WITH"
    r"|SELECT"
    r"|INSERT\s+INTO"
    r"|UPDATE"
    r"|CREATE\s+(?:TABLE|SCHEMA|INDEX|MATERIALIZED\s+VIEW)\s+IF\s+NOT\s+EXISTS"
    r"|CREATE\s+(?:TABLE|SCHEMA|INDEX|MATERIALIZED\s+VIEW)"
    r"|CREATE\s+OR\s+REPLACE\s+VIEW"
    r"|REFRESH\s+MATERIALIZED\s+VIEW"
    r"|COMMENT\s+ON\s+(?:TABLE|MATERIALIZED\s+VIEW)"
    r")"
    r"\b",
    re.IGNORECASE,
)

# Patterns that are ALWAYS blocked, regardless of statement type.
# These catch destructive DDL even if somehow embedded.
_BLOCKED_PATTERNS = re.compile(
    r"\b(?:"
    r"DROP\s+(?:TABLE|SCHEMA|DATABASE|INDEX|VIEW|FUNCTION|TRIGGER|SEQUENCE|TYPE)"
    r"|TRUNCATE"
    r"|ALTER\s+TABLE\s+\S+\s+DROP"
    r"|ALTER\s+TABLE\s+\S+\s+RENAME"
    r"|DELETE\s+FROM"
    r")\b",
    re.IGNORECASE,
)


def validate_sql_safety(sql: str) -> None:
    """
    Validate that a SQL string does not contain destructive operations.
    
    Raises DestructiveSqlError if the SQL contains blocked patterns like
    DROP TABLE, TRUNCATE, ALTER TABLE ... DROP, etc.
    
    This is a defense-in-depth gate at the adapter layer. It does NOT
    replace proper escaping — it catches catastrophic mistakes.
    """
    if not sql or not sql.strip():
        return  # empty SQL is harmless (will fail at DB level)
    
    # 1. Check for unconditionally blocked destructive patterns
    match = _BLOCKED_PATTERNS.search(sql)
    if match:
        raise DestructiveSqlError(
            f"Blocked destructive SQL operation: '{match.group().strip()}' "
            f"in query: {sql[:120]}..."
        )
    
    # 2. Verify each statement starts with an allowed prefix.
    #    Split on ';' to handle multi-statement strings (BEGIN; ...; COMMIT;)
    for stmt in sql.split(';'):
        stripped = stmt.strip()
        if not stripped:
            continue  # trailing semicolons produce empty segments
        if not _ALLOWED_STATEMENT_PREFIXES.match(stripped):
            raise DestructiveSqlError(
                f"SQL statement not in allowlist: '{stripped[:80]}...'"
            )


# ---------------------------------------------------------------------------
# Core proxy models (what Datum actually sends/receives)
# ---------------------------------------------------------------------------

class DatumProxyRequest(BaseModel):
    """
    Generic request envelope to the Datum proxy endpoint.

    This is what you POST to /datum/proxy_request.
    """
    service_name: str
    endpoint_name: str
    path: str
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"]
    # NOTE: body is a JSON string because the current proxy expects it that way.
    # The SDK will accept a dict and encode it for you.
    body: str


class DatumProxyResponse(BaseModel):
    """
    Generic response envelope returned by the Datum proxy endpoint.
    """
    service_name: str
    endpoint_name: str
    path: str
    method: str
    status: int
    headers: Dict[str, Any]
    body: str  # JSON string from the upstream service


# ---------------------------------------------------------------------------
# PostgreSQL SQL API Models (postgres_sql service)
# ---------------------------------------------------------------------------

class PostgresSqlRequest(BaseModel):
    """
    Request body for the PostgreSQL SQL API endpoint.
    
    POST /sql
    Service: postgres_sql (postgres_sql_api_001)
    """
    sql: str = Field(
        ...,
        description="Arbitrary SQL statement to execute against PostgreSQL.",
        examples=["SELECT COUNT(*) AS total_records FROM demo.users"]
    )
    database: Optional[str] = Field(
        default=None,
        description="Optional PostgreSQL database name. If omitted, uses service default."
    )
    schema_: Optional[str] = Field(
        default=None,
        alias="schema",
        description="Optional PostgreSQL schema name to set as search_path."
    )

    class Config:
        populate_by_name = True


class PostgresSqlResponse(BaseModel):
    """
    Response from the PostgreSQL SQL API endpoint.
    
    Returns fully materialized results with columns, data, and row_count.
    """
    description: str = Field(
        ...,
        description="Human-readable description of the query."
    )
    query: str = Field(
        ...,
        description="The SQL statement that was executed."
    )
    row_count: int = Field(
        ...,
        description="Number of rows returned in the data array."
    )
    columns: List[str] = Field(
        ...,
        description="List of column names in the result set."
    )
    data: List[Dict[str, Any]] = Field(
        ...,
        description="Result rows as an array of objects (records)."
    )


# ---------------------------------------------------------------------------
# SDK Client
# ---------------------------------------------------------------------------

class DatumClient:
    """
    Thin SDK client for the Datum service platform.

    - base_url: e.g. "https://appshare-dev.cancer.gov/datum"
    - token:    your DATUM_API_TOKEN
    """

    def __init__(self, base_url: str, token: str, timeout: float = 60.0, connect_timeout: float = 2.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = (connect_timeout, timeout)
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            }
        )

    # -----------------------
    # Internal helper
    # -----------------------
    def _call_proxy(
        self,
        service_name: str,
        endpoint_name: str,
        path: str,
        method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"],
        body_obj: Dict[str, Any],
    ) -> DatumProxyResponse:
        """
        Build a DatumProxyRequest, send it to /proxy_request,
        and parse the DatumProxyResponse.
        """
        # The proxy currently expects `body` to be a JSON string,
        # so we encode the inner body dict here.
        req_envelope = DatumProxyRequest(
            service_name=service_name,
            endpoint_name=endpoint_name,
            path=path,
            method=method,
            body=json.dumps(body_obj),
        )

        url = f"{self.base_url}/proxy_request"
        t0 = time.perf_counter()
        resp = self._session.post(
            url,
            data=req_envelope.model_dump_json(),
            timeout=self.timeout,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        resp.raise_for_status()

        result = DatumProxyResponse.model_validate(resp.json())
        # Truncate body preview for readability
        sql_preview = body_obj.get("sql", "")[:80] if isinstance(body_obj, dict) else ""
        print(f"[Datum] {method} {path} ({service_name}/{endpoint_name}) → {resp.status_code} in {elapsed_ms:.0f}ms | {sql_preview}")
        return result

    # -----------------------
    # PostgreSQL SQL API
    # -----------------------
    def execute_sql(
        self,
        sql: str,
        database: Optional[str] = None,
        schema: Optional[str] = None,
        service_name: str = "postgres_sql",
    ) -> PostgresSqlResponse:
        """
        Execute arbitrary SQL against the PostgreSQL service via Datum proxy.
        
        Args:
            sql: SQL statement to execute
            database: Optional database name (default: service default)
            schema: Optional schema name for search_path
            service_name: Datum service name (default: postgres_sql)
            
        Returns:
            PostgresSqlResponse with columns, data, and row_count
        """
        # Safety gate: reject destructive SQL before it leaves the process
        validate_sql_safety(sql)
        
        request = PostgresSqlRequest(sql=sql, database=database, schema_=schema)
        body_dict = request.model_dump(by_alias=True, exclude_none=True)
        
        proxy_resp = self._call_proxy(
            service_name=service_name,
            endpoint_name="sql",
            path="/sql",
            method="POST",
            body_obj=body_dict,
        )
        
        if proxy_resp.status != 200:
            raise RuntimeError(
                f"PostgreSQL SQL API error: status={proxy_resp.status}, body={proxy_resp.body}"
            )
        
        # Parse the inner response body
        return PostgresSqlResponse.model_validate(json.loads(proxy_resp.body))

