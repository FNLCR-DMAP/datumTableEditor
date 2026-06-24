"""
Direct PostgreSQL adapter with the same execute_sql shape as DatumClient.
"""
from __future__ import annotations

import datetime as dt
import decimal
import os
import time
from typing import Any, Optional

import psycopg
from psycopg import sql as pg_sql
from psycopg.rows import dict_row

from .datum import PostgresSqlResponse, validate_sql_safety


_RETRYABLE_ERRORS = (
    psycopg.OperationalError,
    psycopg.InterfaceError,
    TimeoutError,
    OSError,
)


class PostgresClient:
    """Small direct PostgreSQL client for server-side SQL queries."""

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | str | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
        schema: str | None = None,
        dsn: str | None = None,
        connect_timeout: int = 5,
    ):
        self.host = host or os.environ.get("PG_HOST", "localhost")
        self.port = int(port or os.environ.get("PG_PORT", 5432))
        self.user = user or os.environ.get("PG_USER", "user")
        self.password = password if password is not None else os.environ.get("PG_PASSWORD", "")
        self.database = database or os.environ.get("PG_DATABASE", "postgres")
        self.schema = schema or os.environ.get("PG_SCHEMA")
        self.dsn = dsn or os.environ.get("PG_DSN") or os.environ.get("DATABASE_URL")
        self.connect_timeout = connect_timeout
        self._unreachable_count = 0

    @property
    def unreachable_count(self) -> int:
        """Number of consecutive retryable connection/query failures."""
        return self._unreachable_count

    def ping(self, database: str | None = None) -> bool:
        """Open a short PostgreSQL connection to verify connectivity."""
        try:
            connection = self.get_connection(database=database)
            connection.close()
            if self._unreachable_count > 0:
                print(f"[Postgres] Connection restored after {self._unreachable_count} failures")
            self._unreachable_count = 0
            return True
        except _RETRYABLE_ERRORS as e:
            self._unreachable_count += 1
            print(
                f"[Postgres] PING FAILED | unreachable_count={self._unreachable_count} | "
                f"host={self.host}:{self.port} database={database or self.database} | "
                f"error={type(e).__name__}: {e}"
            )
            return False

    def get_connection(self, database: str | None = None):
        """Create a new PostgreSQL connection."""
        if self.dsn:
            return psycopg.connect(
                self.dsn,
                dbname=database,
                connect_timeout=self.connect_timeout,
            )
        return psycopg.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            dbname=database or self.database,
            connect_timeout=self.connect_timeout,
        )

    def execute_sql(
        self,
        sql: str,
        database: Optional[str] = None,
        schema: Optional[str] = None,
        service_name: str | None = None,
    ) -> PostgresSqlResponse:
        """Execute SQL directly against PostgreSQL and return Datum-compatible data."""
        validate_sql_safety(sql)
        del service_name  # Kept for call-site compatibility with DatumClient.

        if not self.ping(database=database):
            raise psycopg.OperationalError(
                f"Cannot reach PostgreSQL (unreachable_count={self._unreachable_count}). "
                f"Host: {self.host}:{self.port}, database={database or self.database}"
            )

        last_err = None
        for attempt in range(1, 4):
            try:
                return self._execute_sql_once(sql=sql, database=database, schema=schema or self.schema)
            except _RETRYABLE_ERRORS as e:
                last_err = e
                self._unreachable_count += 1
                print(
                    f"[Postgres] Attempt {attempt}/3 failed | "
                    f"unreachable_count={self._unreachable_count} | "
                    f"host={self.host}:{self.port} database={database or self.database} | "
                    f"{type(e).__name__}: {e}"
                )
                if attempt < 3:
                    time.sleep(attempt)

        raise last_err

    def _execute_sql_once(
        self,
        *,
        sql: str,
        database: Optional[str] = None,
        schema: Optional[str] = None,
    ) -> PostgresSqlResponse:
        """Execute one SQL attempt against PostgreSQL."""
        connection = self.get_connection(database=database)
        try:
            with connection.cursor(row_factory=dict_row) as cursor:
                if schema:
                    cursor.execute(
                        pg_sql.SQL("SET search_path TO {}").format(pg_sql.Identifier(schema))
                    )

                cursor.execute(sql)
                if cursor.description:
                    rows = cursor.fetchall()
                    columns = [desc.name for desc in cursor.description]
                    data = [
                        {key: _json_safe(value) for key, value in dict(row).items()}
                        for row in rows
                    ]
                    row_count = len(data)
                else:
                    columns = []
                    data = []
                    row_count = cursor.rowcount if cursor.rowcount is not None else 0

                connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        return PostgresSqlResponse(
            description="Direct PostgreSQL SQL query",
            query=sql,
            row_count=row_count,
            columns=columns,
            data=data,
        )


def _json_safe(value: Any) -> Any:
    """Convert common PostgreSQL/Python values to JSON-safe values."""
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value