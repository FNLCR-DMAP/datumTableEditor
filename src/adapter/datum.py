from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Literal

import requests
from pydantic import BaseModel, Field


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

    def __init__(self, base_url: str, token: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
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
        resp = self._session.post(
            url,
            data=req_envelope.model_dump_json(),
            timeout=self.timeout,
        )
        resp.raise_for_status()

        # Parse the outer Datum envelope
        return DatumProxyResponse.model_validate(resp.json())

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
        request = PostgresSqlRequest(sql=sql, database=database, schema_=schema)
        body_dict = request.model_dump(by_alias=True, exclude_none=True)
        
        # Debug: log the actual request being sent
        is_insert = sql.strip().upper().startswith("INSERT")
        if is_insert or "modifications" in sql.lower():
            print(f"DEBUG Datum request - service: {service_name}, body: {body_dict}")
        
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
        
        # Debug: log raw response for modifications queries
        if is_insert or "modifications" in sql.lower():
            print(f"DEBUG Datum response - status: {proxy_resp.status}, body_preview: {proxy_resp.body[:500] if len(proxy_resp.body) > 500 else proxy_resp.body}")
        
        # Parse the inner response body
        return PostgresSqlResponse.model_validate(json.loads(proxy_resp.body))

