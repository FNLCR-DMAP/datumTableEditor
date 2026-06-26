"""
Configuration Instance Loader

Provides on-demand config loading for widget instances.
Each widget can load its own config file independently.
"""

import json
import os
import hashlib
import re
import threading
import time as _time
import pandas as pd
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple

from .app_config_schema import AppConfig, load_config
from .sql_types import SqlIdentifier, SqlTableName, SqlLiteral, build_pk_json_expr, build_pk_array
from ..utils import tracker


# ---------------------------------------------------------------------------
# App-level shared data cache
# Shared across all sessions in the same worker process.  Keyed by the
# user-configured ``shared_cache_key``.  Each entry stores (DataFrame, timestamp).
# ---------------------------------------------------------------------------
_APP_CACHE: Dict[str, Tuple[pd.DataFrame, float]] = {}
_APP_CACHE_LOCK = threading.Lock()


def _app_cache_get(key: str, ttl: int) -> Optional[pd.DataFrame]:
    """Return a .copy() of the cached DataFrame if within TTL, else None."""
    with _APP_CACHE_LOCK:
        entry = _APP_CACHE.get(key)
        if entry is None:
            return None
        df, ts = entry
        if (_time.time() - ts) >= ttl:
            del _APP_CACHE[key]
            return None
        return df.copy()


def _app_cache_set(key: str, df: pd.DataFrame) -> None:
    """Store a .copy() of the DataFrame in the app cache."""
    with _APP_CACHE_LOCK:
        _APP_CACHE[key] = (df.copy(), _time.time())


def _app_cache_invalidate(key: str) -> None:
    """Remove a key from the app cache."""
    with _APP_CACHE_LOCK:
        _APP_CACHE.pop(key, None)


# ---------------------------------------------------------------------------
# Backward-compatible wrappers (kept for test imports and transition period)
# New code should use SqlIdentifier / SqlTableName / SqlLiteral directly.
# ---------------------------------------------------------------------------

def _format_table_name(table_name: str) -> str:
    """Format table name for SQL queries with proper PostgreSQL quoting.

    DEPRECATED — prefer SqlTableName(table_name) in new code.
    """
    return str(SqlTableName(table_name))


def _mods_index_name(table_name: str, suffix: str) -> str:
    """Return a deterministic index name for a mods table."""
    table_part = table_name.split(".")[-1]
    safe_base = re.sub(r"[^A-Za-z0-9_]+", "_", table_part).strip("_") or "mods"
    digest = hashlib.sha1(f"{table_name}:{suffix}".encode("utf-8")).hexdigest()[:8]
    fixed_len = len("idx__") + len(suffix) + 1 + len(digest)
    max_base_len = max(8, 63 - fixed_len)
    index_name = f"idx_{safe_base[:max_base_len]}_{suffix}_{digest}"
    return str(SqlIdentifier(index_name))


def _mods_index_statements(mods_table: str) -> List[str]:
    """Build indexes used by mods-log loading, status joins, and undo checks."""
    table_sql = SqlTableName(mods_table)
    specs = [
        ("rowpk_gin", "USING GIN (row_pk)", ""),
        ("created", "(created_at ASC, id ASC)", ""),
        ("active_latest", "(row_pk, created_at DESC, id DESC)", "WHERE undone = FALSE"),
        (
            "field_active",
            "(row_pk, column_name, created_at DESC, id DESC)",
            "WHERE undone = FALSE AND mod_type = 'field_modification'",
        ),
        (
            "status_created",
            "(mod_type, created_at ASC, id ASC)",
            "WHERE mod_type IN ('approval', 'rejection')",
        ),
    ]
    statements = []
    for suffix, definition, predicate in specs:
        stmt = f"CREATE INDEX IF NOT EXISTS {_mods_index_name(mods_table, suffix)} ON {table_sql} {definition}"
        if predicate:
            stmt = f"{stmt} {predicate}"
        statements.append(stmt)
    return statements


def _row_pk_json_values(row_pks: list) -> List[str]:
    """Serialize row primary-key dicts exactly as mods-table JSONB values."""
    values = []
    seen = set()
    for row_pk in row_pks or []:
        if not isinstance(row_pk, dict) or not row_pk:
            continue
        serializable_pk = {}
        for key, value in row_pk.items():
            if hasattr(value, "item"):
                value = value.item()
            else:
                try:
                    if pd.isna(value):
                        value = None
                except Exception:
                    pass
            serializable_pk[key] = value
        pk_json = json.dumps(serializable_pk, sort_keys=True)
        if pk_json not in seen:
            values.append(pk_json)
            seen.add(pk_json)
    return values


def _modifications_log_query(mods_table_sql, pk_array_sql: str = None) -> str:
    """Return log rows with approval/rejection batches grouped in SQL."""
    pk_filter = f" AND row_pk = ANY({pk_array_sql})" if pk_array_sql else ""
    return f"""
    WITH latest_field_mods AS (
        SELECT DISTINCT ON (row_pk, column_name)
               id,
               row_pk,
               column_name,
               old_value,
               new_value,
               mod_type,
               created_by,
               created_at,
               undone,
               NULL::jsonb AS grouped_row_pks,
               NULL::integer AS grouped_count,
               id AS sort_id
        FROM {mods_table_sql}
        WHERE mod_type = 'field_modification'
          AND undone = FALSE{pk_filter}
        ORDER BY row_pk, column_name, created_at DESC, id DESC
    ),
    other_non_status AS (
        SELECT id,
               row_pk,
               column_name,
               old_value,
               new_value,
               mod_type,
               created_by,
               created_at,
               undone,
               NULL::jsonb AS grouped_row_pks,
               NULL::integer AS grouped_count,
               id AS sort_id
        FROM {mods_table_sql}
        WHERE mod_type NOT IN ('approval', 'rejection', 'field_modification'){pk_filter}
    ),
    grouped_status AS (
        SELECT NULL::integer AS id,
               NULL::jsonb AS row_pk,
               '_status'::varchar AS column_name,
               NULL::text AS old_value,
               CASE WHEN mod_type = 'approval' THEN 'approved' ELSE 'rejected' END AS new_value,
               mod_type,
               NULL::varchar AS created_by,
               date_trunc('second', created_at) AS created_at,
               FALSE AS undone,
               jsonb_agg(row_pk ORDER BY id) AS grouped_row_pks,
               COUNT(*)::integer AS grouped_count,
               MIN(id) AS sort_id
        FROM {mods_table_sql}
        WHERE mod_type IN ('approval', 'rejection'){pk_filter}
        GROUP BY mod_type, date_trunc('second', created_at)
    )
    SELECT id,
           row_pk,
           column_name,
           old_value,
           new_value,
           mod_type,
           created_by,
           created_at,
           undone,
           grouped_row_pks,
           grouped_count
    FROM (
        SELECT * FROM latest_field_mods
        UNION ALL
        SELECT * FROM other_non_status
        UNION ALL
        SELECT * FROM grouped_status
    ) log_rows
    ORDER BY created_at ASC, sort_id ASC
    """


def _coerce_json(value, default):
    """Decode JSON strings returned by Datum while accepting native objects."""
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return default
    return value


def _coerce_grouped_row_pks(value) -> list:
    row_pks = _coerce_json(value, [])
    if not isinstance(row_pks, list):
        return []
    result = []
    for row_pk in row_pks:
        parsed = _coerce_json(row_pk, row_pk)
        if isinstance(parsed, dict) and parsed:
            result.append(parsed)
    return result


def _timestamp_for_log(value, truncate_seconds: bool = False):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        text_value = value.isoformat()
    else:
        text_value = str(value)
    return text_value[:19] if truncate_seconds else text_value


def _modification_rows_to_log(rows: list) -> List[Dict]:
    """Convert SQL result rows into the in-memory modifications log shape."""
    log = []
    for row in rows:
        mod_type = row.get("mod_type")
        grouped_row_pks = row.get("grouped_row_pks")
        if mod_type in ("approval", "rejection") and grouped_row_pks is not None:
            row_pks = _coerce_grouped_row_pks(grouped_row_pks)
            action = "approved" if mod_type == "approval" else "rejected"
            rows_key = "approved_rows" if mod_type == "approval" else "rejected_rows"
            count_key = "approved_row_count" if mod_type == "approval" else "rejected_row_count"
            log.append({
                "timestamp": _timestamp_for_log(row.get("created_at"), truncate_seconds=True),
                "type": mod_type,
                "details": {
                    "action": action,
                    rows_key: row_pks,
                    count_key: int(row.get("grouped_count") or len(row_pks)),
                }
            })
            continue

        row_pk = _coerce_json(row.get("row_pk"), {})
        if row_pk is None:
            row_pk = {}

        log.append({
            "db_id": row.get("id"),
            "timestamp": _timestamp_for_log(row.get("created_at")),
            "type": mod_type,
            "undone": row.get("undone", False),
            "details": {
                "row_pk": row_pk,
                "column": row.get("column_name"),
                "old_value": row.get("old_value"),
                "new_value": row.get("new_value"),
                "created_by": row.get("created_by")
            }
        })
    return log


def _escape_identifier(name: str) -> str:
    """Escape a SQL identifier for double-quote wrapping.

    DEPRECATED — prefer SqlIdentifier(name) in new code.
    Returns the escaped name WITHOUT outer quotes (for backward compat).
    """
    return SqlIdentifier(name).escaped


def _escape_literal(value) -> str:
    """Escape a value for direct SQL string literal interpolation.

    DEPRECATED — prefer SqlLiteral(value) in new code.
    """
    return str(SqlLiteral(value))


# Priority order for status reconciliation: higher number wins.
_STATUS_PRIORITY = {
    "unprocessed": 0,
    "edited": 1,
    "approved": 2,
    "rejected": 3,
}


def _normalize_mod_status(raw: str) -> str:
    """Map raw mod_type / _mod_status values to internal status keys."""
    s = raw.strip().lower()
    _MAP = {
        "field_modification": "edited",
        "approval": "approved",
        "rejection": "rejected",
    }
    return _MAP.get(s, s)


def _reconcile_status_df(df, status_col: str, status_values: dict,
                         pk_columns: list, update_fn) -> 'pd.DataFrame':
    """Data-table-wins reconciliation.

    The status column in the data table is authoritative.  If ``_mod_status``
    disagrees, overwrite ``_mod_status`` in the DataFrame to match the status
    column.  No DB writes are needed because the data table already holds the
    correct value.
    """
    if "_mod_status" not in df.columns or status_col not in df.columns:
        return df

    # Build reverse lookup: mapped DB value → internal key
    reverse_values = {}
    for key, val in status_values.items():
        reverse_values[key.lower()] = key.lower()
        reverse_values[val.lower()] = key.lower()

    for idx, row in df.iterrows():
        cur_raw = str(row.get(status_col, "")).strip().lower()
        cur_key = reverse_values.get(cur_raw, "unprocessed")

        mod_raw = str(row.get("_mod_status", "unprocessed")).strip().lower()
        mod_key = _normalize_mod_status(mod_raw)

        if cur_key != mod_key:
            # Data table wins — sync _mod_status in DataFrame only
            df.at[idx, "_mod_status"] = cur_key

    return df


def _build_mod_status_expr(status_column: str = None, status_labels: dict = None,
                           status_values: dict = None) -> str:
    """
    Build the SQL expression for _mod_status.
    
    When a status_column is configured, it is the single source of truth:
    edits, approvals, rejections, and undos all write to it, so the badge
    always mirrors the data table.  The mods-table CTE is only used as a
    fallback when no status_column exists.
    
    Args:
        status_column: Name of the status column in the data table
        status_labels: Dict mapping internal keys to display labels
        status_values: Dict mapping internal keys to DB-written values
    """
    if status_column:
        col = f'd.{SqlIdentifier(status_column)}'
        # Normalise the status column value → internal key
        when_clauses = []
        if status_labels:
            for internal_key, label in status_labels.items():
                if internal_key == "unprocessed":
                    continue
                safe_key = internal_key.lower()
                safe_label = label.lower()
                match_vals = {safe_key, safe_label}
                if status_values and internal_key in status_values:
                    match_vals.add(status_values[internal_key].lower())
                values = sorted(match_vals)
                in_list = ", ".join(str(SqlLiteral(v)) for v in values)
                when_clauses.append(
                    f"WHEN LOWER(CAST({col} AS TEXT)) IN ({in_list}) THEN {SqlLiteral(safe_key)}"
                )
        else:
            when_clauses.append(
                f"WHEN LOWER(CAST({col} AS TEXT)) IN ('approved', 'rejected', 'edited') "
                f"THEN LOWER(CAST({col} AS TEXT))"
            )
        case_expr = " ".join(when_clauses)
        return f"CASE {case_expr} ELSE 'unprocessed' END"
    
    # No status_column — derive status from the mods table CTE
    mod_when_clauses = [
        "WHEN ms.mod_type = 'approval' THEN 'approved'",
        "WHEN ms.mod_type = 'rejection' THEN 'rejected'",
        "WHEN ms.mod_type = 'field_modification' THEN 'edited'",
    ]
    if status_values:
        for internal_key, db_val in status_values.items():
            safe_val = db_val.lower()
            safe_key = internal_key.lower()
            if safe_val not in (safe_key, "approval", "rejection"):
                mod_when_clauses.append(
                    f"WHEN LOWER(CAST(ms.new_value AS TEXT)) = {SqlLiteral(safe_val)} THEN {SqlLiteral(safe_key)}"
                )
    mod_when_clauses.append("ELSE ms.mod_type")
    mod_normalize = f"CASE {' '.join(mod_when_clauses)} END"
    return f"COALESCE({mod_normalize}, 'unprocessed')"


def _build_mod_cte_and_join(mods_table_sql, pk_json_build: str, include_field_mods: bool = False):
    """Return (cte_clause, join_clause) to replace LATERAL JOIN with a CTE.

    The CTE materialises only the latest active modification per PK from the
    (small) mods table.  PostgreSQL uses a hash-join against the data table
    instead of a correlated sub-query per row.

    ``include_field_mods`` adds a second aggregate CTE used only by lazy page
    fetches to rebuild edited-cell border metadata.

    Usage::

        cte, join = _build_mod_cte_and_join(mods_table_sql, pk_json_build)
        query = f'''
            {cte}
            SELECT d.*, {mod_status_expr} AS _mod_status
            FROM {data_table_sql} d
            {join}
            {where_clause}
        '''
    """
    cte_clause = f"""WITH latest_mod AS (
                SELECT DISTINCT ON (lm.row_pk)
                       lm.row_pk,
                       lm.mod_type,
                       lm.new_value
                FROM {mods_table_sql} lm
                WHERE lm.undone = FALSE
                ORDER BY lm.row_pk, lm.created_at DESC
            )"""
    if include_field_mods:
        cte_clause += f""",
            field_mods AS (
                SELECT fm.row_pk AS fm_row_pk,
                       fm.column_name AS fm_column_name,
                       (array_agg(fm.old_value ORDER BY fm.created_at ASC))[1] AS fm_old_value,
                       (array_agg(fm.new_value ORDER BY fm.created_at DESC))[1] AS fm_new_value
                FROM {mods_table_sql} fm
                WHERE fm.mod_type = 'field_modification'
                  AND fm.undone = FALSE
                GROUP BY fm.row_pk, fm.column_name
            )"""
    join_clause = (
        f"LEFT JOIN latest_mod ms ON ms.row_pk = {pk_json_build}"
    )
    return cte_clause, join_clause


@dataclass
class QueryParams:
    """Parameters for database queries - filters, sort, pagination."""
    filters: Dict[str, Any] = field(default_factory=dict)  # column -> value(s)
    search_term: str = ""
    search_column: str = "all"  # "all" or specific column name
    sort_column: Optional[str | List[str]] = None
    sort_ascending: bool | List[bool] = True
    page: int = 1
    page_size: int = 300
    status_filters: List[str] = field(default_factory=lambda: ["unprocessed", "edited", "approved", "rejected"])


@dataclass
class DataFetcher:
    """
    Handles on-demand data fetching from database with pagination.
    
    Instead of loading all data at startup, this fetches:
    - Row count on init (for pagination UI)
    - Page data on demand (with filters/sort/pagination)
    - All filtered data for export

    When ``set_table_override(table)`` is called (e.g. for synthesis mode),
    all runtime queries target the override table instead of
    ``app_config.database.data_table``.  Metadata introspection methods
    always use the original table.
    """
    app_config: AppConfig
    username: str = ""  # Session username (sanitized) for table names
    user_email: str = ""  # Actual user email for LP LIMS API
    _engine: Any = field(default=None, repr=False)
    _datum_client: Any = field(default=None, repr=False)
    _postgres_client: Any = field(default=None, repr=False)
    _lp_lims_client: Any = field(default=None, repr=False)
    _total_count: int = field(default=0, repr=False)
    _columns: List[str] = field(default_factory=list, repr=False)
    _column_types: Dict[str, str] = field(default_factory=dict, repr=False)
    _table_override: Optional[str] = field(default=None, repr=False)
    _query_override: Optional[str] = field(default=None, repr=False)

    @property
    def _lp_lims_user_email(self) -> str:
        """Return user email for LP LIMS API.
        
        Uses user_email field directly (actual email from Posit Connect),
        falls back to LP_LIMS_USER env var.
        """
        return self.user_email or os.environ.get("LP_LIMS_USER", "")
    
    @property
    def _is_datum(self) -> bool:
        """True when SQL should run through a Datum-compatible execute_sql client."""
        if self.app_config.database.mode == "postgres":
            if self._postgres_client is None:
                from ..adapter.postgres import PostgresClient
                self._postgres_client = PostgresClient(
                    **self._postgres_client_kwargs()
                )
            self._datum_client = self._postgres_client
            return True
        if self.app_config.database.mode != "datum":
            return False
        if self._datum_client is None:
            from ..adapter.datum import DatumClient
            base_url = os.environ.get("DATUM_BASE_URL", "") or self.app_config.database.datum_base_url or ""
            token = os.environ.get("DATUM_API_TOKEN", "") or self.app_config.database.datum_token or ""
            if not base_url:
                print(f"⚠ [DataFetcher] Datum mode but no base_url (env DATUM_BASE_URL and config datum_base_url both empty)")
                return False
            self._datum_client = DatumClient(base_url=base_url, token=token)
        return True

    def __post_init__(self):
        """Initialize database connection and get initial count."""
        self._init_connection()
        self._fetch_metadata()
    
    def _init_connection(self):
        """Initialize database connection based on mode."""
        if self.app_config.database.mode == "lp_lims":
            from ..adapter.lp_lims import LpLimsClient
            base_url = self.app_config.database.lp_lims_base_url or os.environ.get("LP_LIMS_BASE_URL", "")
            token = self.app_config.database.lp_lims_token or os.environ.get("LP_LIMS_API_TOKEN", "") or os.environ.get("DATUM_API_TOKEN", "")
            if base_url and token:
                self._lp_lims_client = LpLimsClient(base_url=base_url, token=token)
            else:
                print(f"⚠ LP LIMS mode: missing base_url={bool(base_url)} or token={bool(token)}")
        elif self.app_config.database.mode == "datum":
            from ..adapter.datum import DatumClient
            base_url = os.environ.get("DATUM_BASE_URL", "") or self.app_config.database.datum_base_url or ""
            token = os.environ.get("DATUM_API_TOKEN", "") or self.app_config.database.datum_token or ""
            if base_url:
                self._datum_client = DatumClient(base_url=base_url, token=token)
            else:
                print(f"⚠ [DataFetcher._init_connection] Datum mode but no base_url found")
        elif self.app_config.database.mode == "postgres":
            from ..adapter.postgres import PostgresClient
            self._postgres_client = PostgresClient(
                **self._postgres_client_kwargs()
            )
            self._datum_client = self._postgres_client
        else:
            from sqlalchemy import create_engine
            conn_string = self.app_config.database.connection_string
            if conn_string:
                self._engine = create_engine(conn_string)

    def _resolve_env_ref(self, env_name: Optional[Any], default_env_names: list[str] = None, default=None, cast=None):
        """Resolve a config value that names an environment variable."""
        names = []
        if env_name not in (None, ""):
            names.append(str(env_name))
        names.extend(default_env_names or [])
        for name in names:
            value = os.environ.get(name)
            if value not in (None, ""):
                return cast(value) if cast else value
        return default

    def _postgres_client_kwargs(self) -> dict:
        """Build PostgresClient kwargs from env-var-name config references."""
        return {
            "dsn": self._resolve_env_ref(self.app_config.database.postgres_dsn, ["PG_DSN", "DATABASE_URL"]),
            "host": self._resolve_env_ref(self.app_config.database.postgres_host, ["PG_HOST"]),
            "port": self._resolve_env_ref(self.app_config.database.postgres_port, ["PG_PORT"], cast=int),
            "user": self._resolve_env_ref(self.app_config.database.postgres_user, ["PG_USER"]),
            "password": self._resolve_env_ref(self.app_config.database.postgres_password, ["PG_PASSWORD"]),
            "database": self._resolve_env_ref(self.app_config.database.postgres_database, ["PG_DATABASE"]),
            "schema": self._resolve_env_ref(self.app_config.database.postgres_schema, ["PG_SCHEMA"]),
            "connect_timeout": self._resolve_env_ref(self.app_config.database.postgres_connect_timeout, ["PG_CONNECT_TIMEOUT"], default=5, cast=int),
        }

    @property
    def _effective_table(self) -> str:
        """Return override table if set, else the configured data_table."""
        return self._table_override or self.app_config.database.data_table

    @property
    def _source_sql(self) -> str:
        """Return the SQL FROM source for runtime queries."""
        if self._query_override:
            query = self._query_override.strip().rstrip(";")
            return f"({query})"
        return str(SqlTableName(self._effective_table))

    def set_table_override(self, table_name: str):
        """Point all runtime queries at *table_name* (e.g. a matview).

        Refreshes the row count and column metadata automatically.
        Modification tracking is suppressed while the override is active.
        """
        self._query_override = None
        self._table_override = table_name
        self._fetch_metadata()
        print(f"[DataFetcher] Table override → {table_name} ({self._total_count} rows, {len(self._columns)} cols)")

    def set_query_override(self, query: str):
        """Point runtime queries at a SQL subquery instead of a physical table."""
        self._table_override = None
        self._query_override = query.strip().rstrip(";")
        self._fetch_metadata()
        print(f"[DataFetcher] Query override → {self._total_count} rows, {len(self._columns)} cols")

    def clear_table_override(self):
        """Restore queries to the original data table."""
        self._table_override = None
        self._query_override = None
        self._fetch_metadata()
        print(f"[DataFetcher] Table override cleared → {self.app_config.database.data_table} ({self._total_count} rows, {len(self._columns)} cols)")

    # PostgreSQL types that are natively textual — no CAST needed for
    # string comparisons (=, IN, ILIKE, ~*).  Keeping them bare allows
    # PostgreSQL to use B-tree / GIN indexes on those columns.
    _TEXT_TYPES = frozenset({
        "text", "character varying", "varchar", "character", "char",
        "name", "citext", "bpchar",
    })

    # PostgreSQL types that represent date/time values
    _DATE_TYPES = frozenset({
        "date", "timestamp", "timestamp without time zone",
        "timestamp with time zone", "timestamptz",
    })

    def _fetch_metadata(self):
        """Fetch table row count, column names, and column types."""
        import time as _tm
        try:
            # LP LIMS mode: metadata comes from a single read call
            if self.app_config.database.mode == "lp_lims" and self._lp_lims_client:
                _t0 = _tm.time()
                response = self._lp_lims_client.read(
                    user=self._lp_lims_user_email,
                    tab=self.app_config.database.lp_lims_tab,
                    environment=self.app_config.database.lp_lims_environment,
                    page=1,
                    page_size=1,
                )
                # row_count may be None; use total_pages as fallback (when page_size=1, total_pages=row_count)
                self._total_count = response.row_count if response.row_count is not None else (response.total_pages or 0)
                # columns may be None; derive from first data row keys
                if response.columns:
                    self._columns = list(response.columns)
                elif response.data:
                    self._columns = list(response.data[0].keys())
                else:
                    self._columns = []
                self._column_types = {}  # LP LIMS doesn't expose column types
                print(f"[Timing] fetch_metadata (lp_lims): {(_tm.time() - _t0)*1000:.0f}ms")
                print(f"DataFetcher: LP LIMS has {self._total_count} rows, {len(self._columns)} columns")
                return

            data_table_sql = self._source_sql
            
            count_query = f"SELECT COUNT(*) as cnt FROM {data_table_sql}"
            columns_query = f"SELECT * FROM {data_table_sql} LIMIT 0"
            
            if self._is_datum:
                # Datum mode
                _t0 = _tm.time()
                with tracker.track_sql("fetch_metadata.count", count_query):
                    response = self._datum_client.execute_sql(
                        sql=count_query,
                        database=self.app_config.database.datum_database,
                        schema=self.app_config.database.datum_schema,
                        service_name=self.app_config.database.datum_service_name,
                    )
                self._total_count = int(response.data[0]["cnt"]) if response.data else 0
                print(f"[Timing] fetch_metadata.count: {(_tm.time() - _t0)*1000:.0f}ms")
                
                # Get columns
                _t0 = _tm.time()
                with tracker.track_sql("fetch_metadata.columns", columns_query):
                    response = self._datum_client.execute_sql(
                        sql=columns_query,
                        database=self.app_config.database.datum_database,
                        schema=self.app_config.database.datum_schema,
                        service_name=self.app_config.database.datum_service_name,
                    )
                # Use response.columns (always present) rather than
                # response.data[0].keys() which fails when LIMIT 0 returns no rows
                self._columns = list(response.columns) if response.columns else []
                # Fallback: try information_schema
                if not self._columns:
                    self._columns = self._get_columns_from_schema_datum()
                print(f"[Timing] fetch_metadata.columns: {(_tm.time() - _t0)*1000:.0f}ms")
                
                if self._query_override:
                    self._column_types = {}
                else:
                    # Fetch column types from information_schema
                    _t0 = _tm.time()
                    self._column_types = self._get_column_types_from_schema()
                    print(f"[Timing] fetch_metadata.types: {(_tm.time() - _t0)*1000:.0f}ms")
            else:
                # Direct SQLAlchemy mode
                from sqlalchemy import text
                _t0 = _tm.time()
                with self._engine.connect() as conn:
                    with tracker.track_sql("fetch_metadata.count", count_query):
                        result = conn.execute(text(count_query))
                        row = result.fetchone()
                        self._total_count = row[0] if row else 0
                    
                    # Get columns
                    with tracker.track_sql("fetch_metadata.columns", columns_query):
                        result = conn.execute(text(columns_query))
                        self._columns = list(result.keys())
                print(f"[Timing] fetch_metadata.sql: {(_tm.time() - _t0)*1000:.0f}ms")
                
                if self._query_override:
                    self._column_types = {}
                else:
                    # Fetch column types from information_schema
                    _t0 = _tm.time()
                    self._column_types = self._get_column_types_from_schema()
                    print(f"[Timing] fetch_metadata.types: {(_tm.time() - _t0)*1000:.0f}ms")
            
            text_cols = [c for c, t in self._column_types.items() if t in self._TEXT_TYPES]
            print(f"DataFetcher: Table has {self._total_count} rows, {len(self._columns)} columns ({len(text_cols)} text)")
            
        except Exception as e:
            print(f"✗ Error fetching metadata: {e}")
            self._total_count = 0
            self._columns = []
            self._column_types = {}

    def refresh_count(self):
        """Refresh only the row count — skip column/type introspection.

        Used on manual reload where the schema hasn't changed but the
        row count might have.
        """
        try:
            if self.app_config.database.mode == "lp_lims" and self._lp_lims_client:
                response = self._lp_lims_client.read(
                    user=self._lp_lims_user_email,
                    tab=self.app_config.database.lp_lims_tab,
                    environment=self.app_config.database.lp_lims_environment,
                    page=1,
                    page_size=1,
                )
                # row_count may be None; use total_pages as fallback (page_size=1)
                self._total_count = response.row_count if response.row_count is not None else (response.total_pages or 0)
            elif self._is_datum:
                data_table_sql = self._source_sql
                count_query = f"SELECT COUNT(*) as cnt FROM {data_table_sql}"
                response = self._datum_client.execute_sql(
                    sql=count_query,
                    database=self.app_config.database.datum_database,
                    schema=self.app_config.database.datum_schema,
                    service_name=self.app_config.database.datum_service_name,
                )
                self._total_count = int(response.data[0]["cnt"]) if response.data else 0
            else:
                data_table_sql = self._source_sql
                count_query = f"SELECT COUNT(*) as cnt FROM {data_table_sql}"
                from sqlalchemy import text
                with self._engine.connect() as conn:
                    result = conn.execute(text(count_query))
                    row = result.fetchone()
                    self._total_count = row[0] if row else 0
            print(f"DataFetcher: Refreshed count → {self._total_count} rows")
        except Exception as e:
            print(f"✗ Error refreshing count: {e}")

    # Backward-compat alias
    _refresh_count = refresh_count

    @property
    def _effective_status_column(self) -> Optional[str]:
        """Return status_column only if it actually exists in the table
        *and* the status filter feature is enabled.

        If the config says ``"Status"`` but the table has ``"status"``
        (or no such column at all), or ``enable_status_filter`` is
        ``False``, return None so that ``_build_mod_status_expr`` falls
        back to the simple ``COALESCE(ms.mod_type, 'unprocessed')`` path.
        """
        if self._skip_mods:
            return None
        col = getattr(self.app_config.database, "status_column", None)
        if col and col in self._columns:
            return col
        return None

    @property
    def _skip_mods(self) -> bool:
        """True when modification tracking is disabled or table override is active.

        When True, queries skip the LATERAL JOIN to the modifications
        table entirely, avoiding both the performance cost and any
        dependency on the mods table existing.

        Triggered by any of:
        - table override active (synthesis matview)
        - enable_status_filter = false
        - enable_approval_workflow = false
        """
        if self._table_override or self._query_override:
            return True
        if not getattr(self.app_config, "enable_approval_workflow", True):
            return True
        return not getattr(self.app_config, "enable_status_filter", True)
    
    @property
    def _select_columns(self) -> str:
        """Build an explicit column list for SELECT instead of ``d.*``.

        PostgreSQL ARRAY columns crash the Datum proxy during result
        serialisation.  Selecting columns explicitly with a ``CAST`` for
        array types avoids the 500 error.
        """
        if not self._columns:
            return "d.*"
        col_types = getattr(self, "_column_types", None) or {}
        parts = []
        _ARRAY_TYPES = frozenset({"array", "anyarray", "user-defined"})
        for col in self._columns:
            ctype = col_types.get(col, "").lower()
            ident = SqlIdentifier(col)
            if ctype.startswith("array") or ctype.endswith("[]") or ctype in _ARRAY_TYPES:
                parts.append(f"CAST(d.{ident} AS TEXT) AS {ident}")
            else:
                parts.append(f"d.{ident}")
        return ", ".join(parts)

    def _get_columns_from_schema_datum(self) -> List[str]:
        """Get column names from information_schema via Datum."""
        try:
            data_table = self._effective_table
            schema = "public"
            table_name = data_table
            if "." in data_table:
                schema, table_name = data_table.split(".", 1)
            
            query = f"""
            SELECT column_name FROM information_schema.columns 
            WHERE table_schema = {SqlLiteral(schema)} AND table_name = {SqlLiteral(table_name)}
            ORDER BY ordinal_position
            """
            response = self._datum_client.execute_sql(
                sql=query,
                database=self.app_config.database.datum_database,
                schema=self.app_config.database.datum_schema,
                service_name=self.app_config.database.datum_service_name,
            )
            return [row["column_name"] for row in response.data]
        except Exception as e:
            print(f"✗ Error getting columns from schema: {e}")
            return []

    def _get_column_types_from_schema(self) -> Dict[str, str]:
        """Fetch column name → data_type mapping from information_schema.

        Works for both Datum and direct SQLAlchemy modes.
        Returns a dict like {"Gene_names": "character varying", "Score": "integer", ...}.
        Falls back to an empty dict on error (all columns will CAST as before).
        """
        try:
            data_table = self._effective_table
            schema = "public"
            table_name = data_table
            if "." in data_table:
                schema, table_name = data_table.split(".", 1)

            query = f"""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = {SqlLiteral(schema)}
              AND table_name = {SqlLiteral(table_name)}
            ORDER BY ordinal_position
            """

            if self._is_datum:
                response = self._datum_client.execute_sql(
                    sql=query,
                    database=self.app_config.database.datum_database,
                    schema=self.app_config.database.datum_schema,
                    service_name=self.app_config.database.datum_service_name,
                )
                return {row["column_name"]: row["data_type"] for row in response.data}
            elif self._engine:
                from sqlalchemy import text as sa_text
                with self._engine.connect() as conn:
                    result = conn.execute(sa_text(query))
                    return {row[0]: row[1] for row in result.fetchall()}
        except Exception as e:
            print(f"⚠ Could not fetch column types (will CAST all): {e}")
        return {}

    def _is_text_column(self, column: str) -> bool:
        """Return True if *column* has a natively textual PostgreSQL type.

        When True the column can be compared as-is (no CAST needed),
        which allows PostgreSQL to use existing B-tree indexes.
        """
        return self._column_types.get(column, "").lower() in self._TEXT_TYPES

    def is_date_column(self, column: str) -> bool:
        """Return True if *column* has a date/timestamp PostgreSQL type."""
        return self._column_types.get(column, "").lower() in self._DATE_TYPES

    @property
    def date_columns(self) -> set:
        """Return the set of column names that have date/timestamp types."""
        return {c for c, t in self._column_types.items() if t.lower() in self._DATE_TYPES}

    def _coerce_date_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert known date/timestamp columns to pandas datetime dtype.

        The Datum API returns JSON where date/timestamp values may arrive
        as epoch milliseconds (numbers) rather than ISO strings.  Without
        this coercion ``_format_cell_value`` sees them as ints/floats and
        displays the raw number instead of a human-readable date.
        """
        if not getattr(self, "_column_types", None):
            return df
        for col in self.date_columns:
            if col not in df.columns:
                continue
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                continue  # already datetime
            try:
                # date-only columns should not carry UTC timezone
                col_type = self._column_types.get(col, "").lower()
                is_date_only = (col_type == "date")
                if pd.api.types.is_numeric_dtype(df[col]):
                    # Whole column is numeric → epoch milliseconds from the API
                    df[col] = pd.to_datetime(df[col], unit="ms", errors="coerce", utc=not is_date_only)
                    if is_date_only:
                        df[col] = df[col].dt.normalize()
                else:
                    # Object/string column — coerce to numeric first; if most
                    # values convert, treat as epoch-ms, otherwise ISO-parse.
                    numeric = pd.to_numeric(df[col], errors="coerce")
                    non_null = df[col].dropna()
                    if non_null.empty:
                        continue
                    numeric_ratio = numeric.notna().sum() / max(non_null.shape[0], 1)
                    if numeric_ratio > 0.5:
                        df[col] = pd.to_datetime(numeric, unit="ms", errors="coerce", utc=not is_date_only)
                        if is_date_only:
                            df[col] = df[col].dt.normalize()
                    else:
                        df[col] = pd.to_datetime(df[col], errors="coerce", utc=not is_date_only)
            except Exception:
                pass  # leave as-is if conversion fails
        return df

    def _col_expr(self, col_ident: SqlIdentifier, column: str) -> str:
        """Return the SQL expression for *column* in a WHERE condition.

        - Text columns:  ``"col_name"``          (index-friendly)
        - Other columns:  ``CAST("col_name" AS TEXT)``  (safe, universal)
        """
        if self._is_text_column(column):
            return str(col_ident)
        return f'CAST({col_ident} AS TEXT)'
    
    def get_unique_values(self, column: str, limit: int = 5000) -> List[str]:
        """Fetch distinct values for a column from the database.
        
        Used by the filter UI to populate dropdown options in lazy loading mode.
        """
        try:
            # LP LIMS mode: fetch a page of data and extract unique values
            if self.app_config.database.mode == "lp_lims" and self._lp_lims_client:
                response = self._lp_lims_client.read(
                    user=self._lp_lims_user_email,
                    tab=self.app_config.database.lp_lims_tab,
                    environment=self.app_config.database.lp_lims_environment,
                    page=1,
                    page_size=min(limit, 10000),
                )
                values = set()
                for row in response.data:
                    val = row.get(column)
                    if val is not None and str(val).strip():
                        values.add(str(val))
                return sorted(values)[:limit]

            data_table_sql = self._source_sql
            col_ident = SqlIdentifier(column)
            query = f'SELECT DISTINCT {col_ident} FROM {data_table_sql} WHERE {col_ident} IS NOT NULL ORDER BY {col_ident} LIMIT {limit}'
            
            if self._is_datum:
                response = self._datum_client.execute_sql(
                    sql=query,
                    database=self.app_config.database.datum_database,
                    schema=self.app_config.database.datum_schema,
                    service_name=self.app_config.database.datum_service_name,
                )
                return [str(row[column]) for row in response.data]
            elif self._engine:
                from sqlalchemy import text
                with self._engine.connect() as conn:
                    result = conn.execute(text(query))
                    return [str(row[0]) for row in result.fetchall()]
        except Exception as e:
            print(f"[DataFetcher] Error getting unique values for {column}: {e}")
        return []

    def get_value_counts(self, column: str, limit: int = 50, filters: dict | None = None) -> List[Tuple[str, int]]:
        """Fetch value counts for a column ordered by frequency (descending).

        Returns list of (value, count) tuples.  NULL values are returned as
        the string ``"No value"``.

        Args:
            column: Column name to count values for.
            limit: Max distinct values to return.
            filters: Optional column filter dict (same format as active_filters)
                     to restrict which rows are counted.
        """
        try:
            # LP LIMS mode: fetch data and compute value counts locally
            if self.app_config.database.mode == "lp_lims" and self._lp_lims_client:
                response = self._lp_lims_client.read(
                    user=self._lp_lims_user_email,
                    tab=self.app_config.database.lp_lims_tab,
                    environment=self.app_config.database.lp_lims_environment,
                    page=1,
                    page_size=10000,
                )
                from collections import Counter
                counter = Counter()
                for row in response.data:
                    val = row.get(column)
                    key = str(val).strip() if val is not None and str(val).strip() else "No value"
                    counter[key] += 1
                return counter.most_common(limit)

            data_table_sql = self._source_sql
            col_ident = SqlIdentifier(column)

            # Build optional WHERE clause from filters
            where_clause = ""
            sql_params = {}
            if filters:
                # Normalize newline-delimited strings to lists (same as _build_query_params)
                norm = {}
                for k, v in filters.items():
                    if isinstance(v, dict) and "op" in v:
                        norm[k] = v
                    elif v and str(v).strip() and v != "all":
                        vals = [x.strip() for x in str(v).split("\n") if x.strip()]
                        if vals:
                            norm[k] = vals if len(vals) > 1 else vals[0]
                if norm:
                    dummy_params = QueryParams(filters=norm)
                    where_clause, sql_params = self._build_where_clause(dummy_params, use_params=not self._is_datum)

            query = (
                f"SELECT COALESCE(CAST({col_ident} AS TEXT), 'No value') AS val, "
                f"COUNT(*) AS cnt "
                f"FROM {data_table_sql} "
                f"{where_clause} "
                f"GROUP BY val ORDER BY cnt DESC LIMIT {int(limit)}"
            )

            if self._is_datum:
                response = self._datum_client.execute_sql(
                    sql=query,
                    database=self.app_config.database.datum_database,
                    schema=self.app_config.database.datum_schema,
                    service_name=self.app_config.database.datum_service_name,
                )
                return [(str(row["val"]), int(row["cnt"])) for row in response.data]
            elif self._engine:
                from sqlalchemy import text
                with self._engine.connect() as conn:
                    result = conn.execute(text(query), sql_params)
                    return [(str(row[0]), int(row[1])) for row in result.fetchall()]
        except Exception as e:
            print(f"[DataFetcher] Error getting value counts for {column}: {e}")
        return []

    @property
    def total_count(self) -> int:
        """Total row count in the table (unfiltered)."""
        return self._total_count
    
    @property
    def columns(self) -> List[str]:
        """Column names in the table."""
        return self._columns.copy()
    
    def _escape_sql_value(self, value: Any) -> str:
        """Escape a value for direct SQL interpolation (for Datum mode).
        
        Delegates to SqlLiteral for type-safe escaping.
        """
        return str(SqlLiteral(value))
    
    def _build_where_clause(self, params: QueryParams, use_params: bool = True) -> Tuple[str, Dict[str, Any]]:
        """
        Build WHERE clause from query parameters.
        
        Filter values can be:
          - A string or list of strings: exact match (= / IN)
          - An operator dict {"op": "...", "value": ...}: rich operator
            Supported ops: in, not_in, contains, not_contains, between, value_range, gt, gte, lt, lte, last_n_days, not_empty, is_null, regex
        
        Args:
            params: Query parameters
            use_params: If True, use parameterized queries (:param). 
                       If False, interpolate values directly (for Datum).
        """
        conditions = []
        sql_params = {}
        param_idx = 0
        
        # Column filters
        for col, value in params.filters.items():
            if value is None or value == "" or value == []:
                continue
            
            # Type-safe column identifier — produces "col_name" via __str__
            col_ident = SqlIdentifier(col)
            
            # ── Operator dict filter ──
            if isinstance(value, dict) and "op" in value:
                op = value.get("op", "in")
                fval = value.get("value")
                col_e = self._col_expr(col_ident, col)
                
                # Skip if value is empty/blank (no constraint)
                if op not in ("not_empty", "is_null"):
                    if fval is None or fval == "" or fval == []:
                        continue
                    if isinstance(fval, list) and all(
                        v is None or (isinstance(v, str) and v.strip() == "") for v in fval
                    ):
                        continue
                
                if op in ("in", "is"):
                    vals = fval if isinstance(fval, list) else [fval]
                    if use_params:
                        placeholders = ", ".join(f":p{param_idx + i}" for i in range(len(vals)))
                        conditions.append(f'{col_e} IN ({placeholders})')
                        for i, v in enumerate(vals):
                            sql_params[f"p{param_idx + i}"] = str(v)
                        param_idx += len(vals)
                    else:
                        placeholders = ", ".join(str(SqlLiteral(str(v))) for v in vals)
                        conditions.append(f'{col_e} IN ({placeholders})')
                
                elif op in ("not_in", "is not"):
                    vals = fval if isinstance(fval, list) else [fval]
                    if use_params:
                        placeholders = ", ".join(f":p{param_idx + i}" for i in range(len(vals)))
                        conditions.append(f'{col_e} NOT IN ({placeholders})')
                        for i, v in enumerate(vals):
                            sql_params[f"p{param_idx + i}"] = str(v)
                        param_idx += len(vals)
                    else:
                        placeholders = ", ".join(str(SqlLiteral(str(v))) for v in vals)
                        conditions.append(f'{col_e} NOT IN ({placeholders})')
                
                elif op == "contains":
                    targets = fval if isinstance(fval, list) else [fval]
                    targets = [t for t in targets if t is not None and str(t).strip()]
                    if targets:
                        if use_params:
                            parts = []
                            for t in targets:
                                parts.append(f'{col_e} ILIKE :p{param_idx}')
                                sql_params[f"p{param_idx}"] = f"%{t}%"
                                param_idx += 1
                            conditions.append(f'({" OR ".join(parts)})' if len(parts) > 1 else parts[0])
                        else:
                            parts = [f'{col_e} ILIKE {SqlLiteral(f"%{t}%")}' for t in targets]
                            conditions.append(f'({" OR ".join(parts)})' if len(parts) > 1 else parts[0])
                
                elif op == "not_contains":
                    targets = fval if isinstance(fval, list) else [fval]
                    targets = [t for t in targets if t is not None and str(t).strip()]
                    if targets:
                        if use_params:
                            parts = []
                            for t in targets:
                                parts.append(f'{col_e} NOT ILIKE :p{param_idx}')
                                sql_params[f"p{param_idx}"] = f"%{t}%"
                                param_idx += 1
                            conditions.append(f'({" AND ".join(parts)})' if len(parts) > 1 else parts[0])
                        else:
                            parts = [f'{col_e} NOT ILIKE {SqlLiteral(f"%{t}%")}' for t in targets]
                            conditions.append(f'({" AND ".join(parts)})' if len(parts) > 1 else parts[0])
                
                elif op in ("between", "value_range"):
                    if isinstance(fval, list) and len(fval) == 2:
                        lo_raw, hi_raw = fval
                        lo_none = lo_raw is None or str(lo_raw).strip() == ""
                        hi_none = hi_raw is None or str(hi_raw).strip() == ""
                        if lo_none and hi_none:
                            # Both bounds absent — no constraint
                            pass
                        elif hi_none:
                            # Only lower bound → >=
                            if use_params:
                                conditions.append(f'{col_e} >= :p{param_idx}')
                                sql_params[f"p{param_idx}"] = str(lo_raw)
                                param_idx += 1
                            else:
                                conditions.append(f'{col_e} >= {SqlLiteral(str(lo_raw))}')
                        elif lo_none:
                            # Only upper bound → <=
                            if use_params:
                                conditions.append(f'{col_e} <= :p{param_idx}')
                                sql_params[f"p{param_idx}"] = str(hi_raw)
                                param_idx += 1
                            else:
                                conditions.append(f'{col_e} <= {SqlLiteral(str(hi_raw))}')
                        else:
                            # Both bounds present — closed range
                            if use_params:
                                conditions.append(f'{col_e} BETWEEN :p{param_idx} AND :p{param_idx + 1}')
                                sql_params[f"p{param_idx}"] = str(lo_raw)
                                sql_params[f"p{param_idx + 1}"] = str(hi_raw)
                                param_idx += 2
                            else:
                                conditions.append(f'{col_e} BETWEEN {SqlLiteral(str(lo_raw))} AND {SqlLiteral(str(hi_raw))}')
                
                elif op in ("gt", "gte", "lt", "lte"):
                    sql_op = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[op]
                    if use_params:
                        conditions.append(f'{col_e} {sql_op} :p{param_idx}')
                        sql_params[f"p{param_idx}"] = str(fval)
                        param_idx += 1
                    else:
                        conditions.append(f'{col_e} {sql_op} {SqlLiteral(str(fval))}')
                
                elif op == "last_n_days":
                    raw = fval[0] if isinstance(fval, list) else fval
                    n = int(raw) if raw is not None else 7
                    if use_params:
                        conditions.append(f'CAST({col_ident} AS DATE) >= (CURRENT_DATE - :p{param_idx} * INTERVAL \'1 day\')')
                        sql_params[f"p{param_idx}"] = n
                        param_idx += 1
                    else:
                        conditions.append(f'CAST({col_ident} AS DATE) >= (CURRENT_DATE - INTERVAL \'{n} days\')')
                
                elif op == "not_empty":
                    if use_params:
                        conditions.append(f'({col_ident} IS NOT NULL AND {col_e} != :p{param_idx})')
                        sql_params[f"p{param_idx}"] = ""
                        param_idx += 1
                    else:
                        conditions.append(f'({col_ident} IS NOT NULL AND {col_e} != \'\')')
                
                elif op == "is_null":
                    if use_params:
                        conditions.append(f'({col_ident} IS NULL OR {col_e} = :p{param_idx})')
                        sql_params[f"p{param_idx}"] = ""
                        param_idx += 1
                    else:
                        conditions.append(f'({col_ident} IS NULL OR {col_e} = \'\')') 
                
                elif op == "regex":
                    if use_params:
                        conditions.append(f'{col_e} ~* :p{param_idx}')
                        sql_params[f"p{param_idx}"] = str(fval)
                        param_idx += 1
                    else:
                        conditions.append(f'{col_e} ~* {SqlLiteral(str(fval))}')
                
                continue
            
            # ── Simple value filter (original behavior) ──
            col_e = self._col_expr(col_ident, col)
            if isinstance(value, list):
                # IN clause for multi-select
                if use_params:
                    placeholders = ", ".join(f":p{param_idx + i}" for i in range(len(value)))
                    conditions.append(f'{col_e} IN ({placeholders})')
                    for i, v in enumerate(value):
                        sql_params[f"p{param_idx + i}"] = str(v)
                    param_idx += len(value)
                else:
                    placeholders = ", ".join(str(SqlLiteral(str(v))) for v in value)
                    conditions.append(f'{col_e} IN ({placeholders})')
            else:
                # Exact match
                if use_params:
                    conditions.append(f'{col_e} = :p{param_idx}')
                    sql_params[f"p{param_idx}"] = str(value)
                    param_idx += 1
                else:
                    conditions.append(f'{col_e} = {SqlLiteral(str(value))}')
        
        # Search term (ILIKE across searchable columns)
        if params.search_term:
            searchable_cols = self.app_config.query.searchable_columns or self._columns
            if params.search_column != "all" and params.search_column in self._columns:
                searchable_cols = [params.search_column]
            
            search_conditions = []
            if use_params:
                for col in searchable_cols:
                    col_ident = SqlIdentifier(col)
                    col_e = self._col_expr(col_ident, col)
                    search_conditions.append(f'{col_e} ILIKE :search_term')
                if search_conditions:
                    conditions.append(f"({' OR '.join(search_conditions)})")
                    sql_params["search_term"] = f"%{params.search_term}%"
            else:
                escaped_term = SqlLiteral(f"%{params.search_term}%")
                for col in searchable_cols:
                    col_ident = SqlIdentifier(col)
                    col_e = self._col_expr(col_ident, col)
                    search_conditions.append(f'{col_e} ILIKE {escaped_term}')
                if search_conditions:
                    conditions.append(f"({' OR '.join(search_conditions)})")
        
        where_clause = ""
        if conditions:
            where_clause = " WHERE " + " AND ".join(conditions)
        
        return where_clause, sql_params
    
    def _build_status_filter_clause(self, params: QueryParams) -> str:
        """Build status filter clause using modification status."""
        labels = getattr(self.app_config, 'status_labels', None) or {}
        all_keys = set(labels.keys()) or {"unprocessed", "edited", "approved", "rejected"}
        if not params.status_filters or set(params.status_filters) == all_keys:
            return ""
        
        # Whitelist: only allow configured status keys
        safe_statuses = [s for s in params.status_filters if s in all_keys]
        if not safe_statuses:
            return ""
        
        # Status is computed via LATERAL JOIN, filter on _mod_status
        statuses = ", ".join(str(SqlLiteral(s)) for s in safe_statuses)
        return f" AND _mod_status IN ({statuses})"
    
    def get_status_counts(self, params: QueryParams = None) -> dict:
        """Get overall status distribution counts from DB.
        
        Args:
            params: Optional query params for filters (excluding status filter).
                    If None, counts across all rows.
        
        Returns:
            Dict like {"unprocessed": N, "edited": N, "approved": N, "rejected": N}

        Optimisation:  Uses a CTE to materialise only the latest mod per
        PK from the (small) mods table, then LEFT JOINs it to the data
        table.  PostgreSQL picks a hash-join strategy because the CTE is
        tiny (dozens of rows).  This gives the same correct COALESCE
        semantics as the per-row LATERAL but runs in a single scan of the
        data table instead of a correlated sub-query per row.
        """
        counts = {"unprocessed": 0, "edited": 0, "approved": 0, "rejected": 0}

        # When status tracking is off, everything is "unprocessed"
        if self._skip_mods:
            counts["unprocessed"] = self._total_count
            return counts

        try:
            mods_table = self.app_config.database.mods_table
            pk_columns = self.app_config.table.primary_key
            data_table_sql = self._source_sql
            mods_table_sql = SqlTableName(mods_table)
            
            is_datum = self._is_datum

            # Build WHERE clause from filters (but ignore status_filters)
            where_clause = ""
            sql_params = {}
            if params:
                where_clause, sql_params = self._build_where_clause(params, use_params=not is_datum)

            pk_json_build = build_pk_json_expr(pk_columns)

            # ── Resolve status config ────────────────────────────────
            status_labels = getattr(self.app_config, "status_labels", None)
            status_values = getattr(self.app_config, "status_values", None)
            status_col = self._effective_status_column

            # ── Build status expression ────────────────────────────
            if status_col:
                # status_column is the source of truth — no mods table needed
                col_ident = SqlIdentifier(status_col)
                when_parts = []
                if status_labels:
                    for internal_key, label in status_labels.items():
                        if internal_key == "unprocessed":
                            continue
                        match_vals = {internal_key.lower(), label.lower()}
                        if status_values and internal_key in status_values:
                            match_vals.add(status_values[internal_key].lower())
                        in_list = ", ".join(str(SqlLiteral(v)) for v in sorted(match_vals))
                        when_parts.append(
                            f"WHEN LOWER(CAST(d.{col_ident} AS TEXT)) IN ({in_list}) THEN {SqlLiteral(internal_key.lower())}"
                        )
                else:
                    when_parts.append(
                        f"WHEN LOWER(CAST(d.{col_ident} AS TEXT)) IN ('approved', 'rejected', 'edited') "
                        f"THEN LOWER(CAST(d.{col_ident} AS TEXT))"
                    )
                status_expr = f"CASE {' '.join(when_parts)} ELSE 'unprocessed' END"

                query = f"""
                SELECT
                    {status_expr} AS _status,
                    COUNT(*) AS cnt
                FROM {data_table_sql} d
                {where_clause}
                GROUP BY 1
                """
            else:
                # No status_column — use mods table CTE
                mod_when_clauses = [
                    "WHEN lm.mod_type = 'approval' THEN 'approved'",
                    "WHEN lm.mod_type = 'rejection' THEN 'rejected'",
                    "WHEN lm.mod_type = 'field_modification' THEN 'edited'",
                ]
                if status_values:
                    for internal_key, db_val in status_values.items():
                        safe_val = db_val.lower()
                        safe_key = internal_key.lower()
                        if safe_val not in (safe_key, "approval", "rejection"):
                            mod_when_clauses.append(
                                f"WHEN LOWER(CAST(lm.new_value AS TEXT)) = {SqlLiteral(safe_val)} THEN {SqlLiteral(safe_key)}"
                            )
                mod_when_clauses.append("ELSE lm.mod_type")
                mod_normalize = f"CASE {' '.join(mod_when_clauses)} END"

                query = f"""
                WITH latest_mod AS (
                    SELECT DISTINCT ON (lm.row_pk)
                           lm.row_pk,
                           lm.mod_type,
                           lm.new_value
                    FROM {mods_table_sql} lm
                    WHERE lm.undone = FALSE
                    ORDER BY lm.row_pk, lm.created_at DESC
                )
                SELECT
                    COALESCE({mod_normalize}, 'unprocessed') AS _status,
                    COUNT(*) AS cnt
                FROM {data_table_sql} d
                LEFT JOIN latest_mod lm ON lm.row_pk = {pk_json_build}
                {where_clause}
                GROUP BY 1
                """

            if is_datum:
                with tracker.track_sql("get_status_counts", query):
                    response = self._datum_client.execute_sql(
                        sql=query,
                        database=self.app_config.database.datum_database,
                        schema=self.app_config.database.datum_schema,
                        service_name=self.app_config.database.datum_service_name,
                    )
                for row in response.data:
                    s = row.get("_status", "")
                    if s in counts:
                        counts[s] = int(row.get("cnt", 0))
            else:
                from sqlalchemy import text
                with self._engine.connect() as conn:
                    with tracker.track_sql("get_status_counts", query):
                        result = conn.execute(text(query), sql_params)
                        for row in result.fetchall():
                            s = row[0] or ""
                            if s in counts:
                                counts[s] = int(row[1])

        except Exception as e:
            print(f"✗ Error getting status counts: {e}")
        return counts

    def _has_status_filter(self, params: QueryParams) -> bool:
        """Return True if the user has narrowed the status checkboxes."""
        if self._skip_mods:
            return False
        if not params.status_filters:
            return False
        labels = getattr(self.app_config, 'status_labels', None) or {}
        all_keys = set(labels.keys()) or {"unprocessed", "edited", "approved", "rejected"}
        return set(params.status_filters) != all_keys

    def _build_order_clause(self, params: QueryParams) -> str:
        """Build ORDER BY clause supporting single or multi-column sort."""
        pk_columns = self.app_config.table.primary_key
        cols = params.sort_column
        asc = params.sort_ascending
        if not cols:
            for pk_col in pk_columns:
                if pk_col in self._columns:
                    return f'ORDER BY {SqlIdentifier(pk_col)} ASC'
            if self._columns:
                return f'ORDER BY {SqlIdentifier(self._columns[0])} ASC'
            return ""
        if isinstance(cols, str):
            cols = [cols]
        if isinstance(asc, bool):
            asc = [asc] * len(cols)
        # Pad ascending list if shorter than columns
        while len(asc) < len(cols):
            asc.append(True)
        parts = []
        for c, a in zip(cols, asc):
            if c in self._columns:
                direction = "ASC" if a else "DESC"
                parts.append(f'{SqlIdentifier(c)} {direction}')
        if not parts:
            for pk_col in pk_columns:
                if pk_col in self._columns:
                    return f'ORDER BY {SqlIdentifier(pk_col)} ASC'
            if self._columns:
                return f'ORDER BY {SqlIdentifier(self._columns[0])} ASC'
            return ""
        return f'ORDER BY {", ".join(parts)}'

    def get_filtered_count(self, params: QueryParams) -> int:
        """Get count of rows matching the current filters.

        Optimisation layers (fastest first):
          1. No filters, no search, no status filter → return cached _total_count
          2. Column/search filters but no status filter → simple COUNT on data
             table with WHERE clause (no join to mods table)
          3. Status filter active → CTE + LEFT JOIN (hash-join on tiny mods CTE)
        """
        try:
            # LP LIMS mode: use the API's row_count with filters
            is_lp_lims = self.app_config.database.mode == "lp_lims" and self._lp_lims_client
            if is_lp_lims:
                filters, tab_filters = self._build_lp_lims_filters(params)
                response = self._lp_lims_client.read(
                    user=self._lp_lims_user_email,
                    tab=self.app_config.database.lp_lims_tab,
                    environment=self.app_config.database.lp_lims_environment,
                    filters=filters if filters else None,
                    tab_filters=tab_filters,
                    page=1,
                    page_size=1,
                )
                # row_count may be None; use total_pages as fallback (page_size=1)
                return response.row_count if response.row_count is not None else (response.total_pages or 0)

            data_table_sql = self._source_sql

            is_datum = self._is_datum
            where_clause, sql_params = self._build_where_clause(params, use_params=not is_datum)

            needs_status = self._has_status_filter(params)
            has_filters = bool(where_clause.strip())

            # ── Fast path 1: no filters at all → cached total ────────────
            if not has_filters and not needs_status:
                return self._total_count

            # ── Fast path 2: column/search filters only (no status) ──────
            if not needs_status:
                query = f"SELECT COUNT(*) as cnt FROM {data_table_sql} d {where_clause}"
            else:
                # ── Status filter path: CTE + LEFT JOIN ──────────────────
                mods_table = self.app_config.database.mods_table
                pk_columns = self.app_config.table.primary_key
                mods_table_sql = SqlTableName(mods_table)
                pk_json_build = build_pk_json_expr(pk_columns)
                cte, join = _build_mod_cte_and_join(mods_table_sql, pk_json_build)

                query = f"""
                {cte}
                SELECT COUNT(*) as cnt FROM (
                    SELECT
                           {_build_mod_status_expr(self._effective_status_column, getattr(self.app_config, "status_labels", None), getattr(self.app_config, "status_values", None))} AS _mod_status
                    FROM {data_table_sql} d
                    {join}
                    {where_clause}
                ) subq
                WHERE 1=1 {self._build_status_filter_clause(params)}
                """

            if is_datum:
                with tracker.track_sql("get_filtered_count", query):
                    response = self._datum_client.execute_sql(
                        sql=query,
                        database=self.app_config.database.datum_database,
                        schema=self.app_config.database.datum_schema,
                        service_name=self.app_config.database.datum_service_name,
                    )
                return int(response.data[0]["cnt"]) if response.data else 0
            else:
                from sqlalchemy import text
                with self._engine.connect() as conn:
                    with tracker.track_sql("get_filtered_count", query):
                        result = conn.execute(text(query), sql_params)
                        row = result.fetchone()
                    return row[0] if row else 0
                    
        except Exception as e:
            print(f"✗ Error getting filtered count: {e}")
            return 0
    
    def fetch_page(self, params: QueryParams) -> pd.DataFrame:
        """
        Fetch a page of data with filters, sort, and pagination.
        
        This is the main method called when displaying data.
        """
        try:
            # LP LIMS mode: delegate filtering/pagination to the API
            is_lp_lims = self.app_config.database.mode == "lp_lims" and self._lp_lims_client
            if is_lp_lims:
                return self._fetch_page_lp_lims(params)

            mods_table = self.app_config.database.mods_table
            pk_columns = self.app_config.table.primary_key
            data_table_sql = self._source_sql
            mods_table_sql = SqlTableName(mods_table)
            
            # Use parameterized queries for SQLAlchemy, interpolated for Datum
            is_datum = self._is_datum
            where_clause, sql_params = self._build_where_clause(params, use_params=not is_datum)
            
            order_clause = self._build_order_clause(params)
            
            # Pagination
            offset = (params.page - 1) * params.page_size
            limit_clause = f"LIMIT {params.page_size} OFFSET {offset}"
            
            # Build query with mod status
            pk_json_build = build_pk_json_expr(pk_columns)
            status_filter = self._build_status_filter_clause(params)
            
            cols = self._select_columns
            if self._skip_mods:
                mod_status_select = "" if "_mod_status" in self._columns else ", 'unprocessed' AS _mod_status"
                # No modification tracking — simple SELECT, no LATERAL JOIN
                query = f"""
                SELECT {cols}{mod_status_select}
                FROM {data_table_sql} d
                {where_clause}
                {order_clause}
                {limit_clause}
                """
            else:
                # CTE materialises the tiny mods table; hash-join replaces
                # the expensive per-row LATERAL sub-query.
                cte, join = _build_mod_cte_and_join(
                    mods_table_sql, pk_json_build, include_field_mods=True
                )
                inner_query = f"""
                SELECT {cols}, 
                       {_build_mod_status_expr(self._effective_status_column, getattr(self.app_config, "status_labels", None), getattr(self.app_config, "status_values", None))} AS _mod_status,
                           (SELECT json_agg(json_build_object('column_name', fm.fm_column_name, 'old_value', fm.fm_old_value, 'new_value', fm.fm_new_value))
                        FROM field_mods fm WHERE fm.fm_row_pk = {pk_json_build}) AS _field_mods
                FROM {data_table_sql} d
                {join}
                {where_clause}
                """
                
                query = f"""
                {cte}
                SELECT * FROM ({inner_query}) subq
                WHERE 1=1 {status_filter}
                {order_clause}
                {limit_clause}
                """
            
            print(f"[DataFetcher] Fetching page {params.page}, size {params.page_size}, offset {offset}")
            
            if is_datum:
                with tracker.track_sql("fetch_page", query):
                    response = self._datum_client.execute_sql(
                        sql=query,
                        database=self.app_config.database.datum_database,
                        schema=self.app_config.database.datum_schema,
                        service_name=self.app_config.database.datum_service_name,
                    )
                df = pd.DataFrame(response.data)
                df = self._coerce_date_columns(df)
            else:
                from sqlalchemy import text
                with self._engine.connect() as conn:
                    with tracker.track_sql("fetch_page", query):
                        result = conn.execute(text(query), sql_params)
                        rows = result.fetchall()
                        columns = result.keys()
                df = pd.DataFrame(rows, columns=columns)
            
            # Apply field modifications
            df = self._apply_field_modifications(df)
            df = self._reconcile_status_column(df)
            
            print(f"[DataFetcher] Fetched {len(df)} rows")
            return df
            
        except Exception as e:
            print(f"[X] Error fetching page: {e}")
            import traceback
            traceback.print_exc()
            return pd.DataFrame()
    
    def fetch_all_filtered(self, params: QueryParams) -> pd.DataFrame:
        """
        Fetch ALL data matching current filters (no pagination).
        
        Used for export functionality.
        """
        try:
            # LP LIMS mode: fetch with max page_size (no true "all" endpoint)
            is_lp_lims = self.app_config.database.mode == "lp_lims" and self._lp_lims_client
            if is_lp_lims:
                filters, tab_filters = self._build_lp_lims_filters(params)
                order_by = None
                order_direction = None
                if params.sort_column:
                    if isinstance(params.sort_column, list):
                        order_by = params.sort_column[0]
                        asc = params.sort_ascending[0] if isinstance(params.sort_ascending, list) else params.sort_ascending
                    else:
                        order_by = params.sort_column
                        asc = params.sort_ascending if isinstance(params.sort_ascending, bool) else True
                    order_direction = "asc" if asc else "desc"
                response = self._lp_lims_client.read(
                    user=self._lp_lims_user_email,
                    tab=self.app_config.database.lp_lims_tab,
                    environment=self.app_config.database.lp_lims_environment,
                    filters=filters,
                    tab_filters=tab_filters,
                    page=1,
                    page_size=10000,
                    order_by=order_by,
                    order_direction=order_direction,
                )
                df = pd.DataFrame(response.data)
                if not df.empty:
                    df["_mod_status"] = "unprocessed"
                print(f"[DataFetcher] LP LIMS export fetched {len(df)} rows")
                return df

            mods_table = self.app_config.database.mods_table
            pk_columns = self.app_config.table.primary_key
            data_table_sql = self._source_sql
            mods_table_sql = SqlTableName(mods_table)
            
            # Use parameterized queries for SQLAlchemy, interpolated for Datum
            is_datum = self._is_datum
            where_clause, sql_params = self._build_where_clause(params, use_params=not is_datum)
            
            order_clause = self._build_order_clause(params)
            
            # Build query with mod status (NO LIMIT for export)
            pk_json_build = build_pk_json_expr(pk_columns)
            status_filter = self._build_status_filter_clause(params)
            
            cols = self._select_columns
            if self._skip_mods:
                mod_status_select = "" if "_mod_status" in self._columns else ", 'unprocessed' AS _mod_status"
                query = f"""
                SELECT {cols}{mod_status_select}
                FROM {data_table_sql} d
                {where_clause}
                {order_clause}
                """
            else:
                cte, join = _build_mod_cte_and_join(mods_table_sql, pk_json_build)
                inner_query = f"""
                SELECT {cols}, 
                       {_build_mod_status_expr(self._effective_status_column, getattr(self.app_config, "status_labels", None), getattr(self.app_config, "status_values", None))} AS _mod_status
                FROM {data_table_sql} d
                {join}
                {where_clause}
                """
                
                query = f"""
                {cte}
                SELECT * FROM ({inner_query}) subq
                WHERE 1=1 {status_filter}
                {order_clause}
                """
            
            print(f"[DataFetcher] Fetching ALL filtered data for export...")
            
            if is_datum:
                with tracker.track_sql("fetch_all_filtered", query):
                    response = self._datum_client.execute_sql(
                        sql=query,
                        database=self.app_config.database.datum_database,
                        schema=self.app_config.database.datum_schema,
                        service_name=self.app_config.database.datum_service_name,
                    )
                df = pd.DataFrame(response.data)
                df = self._coerce_date_columns(df)
            else:
                from sqlalchemy import text
                with self._engine.connect() as conn:
                    with tracker.track_sql("fetch_all_filtered", query):
                        result = conn.execute(text(query), sql_params)
                        rows = result.fetchall()
                        columns = result.keys()
                df = pd.DataFrame(rows, columns=columns)
            
            # Apply field modifications
            df = self._apply_field_modifications(df)
            df = self._reconcile_status_column(df)
            
            print(f"[DataFetcher] Fetched {len(df)} rows for export")
            return df
            
        except Exception as e:
            print(f"[X] Error fetching all filtered: {e}")
            import traceback
            traceback.print_exc()
            return pd.DataFrame()

    # ------------------------------------------------------------------
    # LP LIMS helpers
    # ------------------------------------------------------------------

    def _build_lp_lims_filters(self, params: QueryParams) -> tuple:
        """Convert QueryParams.filters to LP LIMS filter structures.

        Returns a tuple of (filters_dict, tab_filters) where:
        - filters_dict: {"column_name": ["value1", "value2"]} for simple IN filters
        - tab_filters: TabFilters object for date ranges, exclusions, etc.

        LP LIMS expects date "between" (or "value_range") as tab_filters.date_ranges with
        start/end in YYYY-MM-DD format.
        """
        from ..adapter.lp_lims import TabFilters, DateRangeFilter

        if not params.filters:
            return None, None

        result: Dict[str, List[str]] = {}
        date_ranges = []

        for col, val in params.filters.items():
            if val is None:
                continue
            if isinstance(val, dict):
                op = val.get("op", "in")
                inner = val.get("value")

                if op in ("between", "value_range") and isinstance(inner, list):
                    # Route to tab_filters.date_ranges
                    start = inner[0] if len(inner) > 0 and inner[0] else None
                    end = inner[1] if len(inner) > 1 and inner[1] else None
                    date_ranges.append(DateRangeFilter(column=col, start=start, end=end))
                elif op == "not_in" and isinstance(inner, list):
                    # Exclusions could be routed to tab_filters.exclusions
                    # For now, skip — LP LIMS generic filters don't support NOT IN
                    pass
                else:
                    # Default: treat as IN filter
                    if isinstance(inner, list):
                        result[col] = [str(v) for v in inner if v is not None]
                    elif inner is not None:
                        result[col] = [str(inner)]
            elif isinstance(val, list):
                result[col] = [str(v) for v in val]
            else:
                result[col] = [str(val)]

        filters_dict = result if result else None
        tab_filters = TabFilters(date_ranges=date_ranges) if date_ranges else None
        return filters_dict, tab_filters

    def _fetch_page_lp_lims(self, params: QueryParams) -> pd.DataFrame:
        """Fetch a page of data from LP LIMS API."""
        filters, tab_filters = self._build_lp_lims_filters(params)

        # Map sort params
        order_by = None
        order_direction = None
        if params.sort_column:
            if isinstance(params.sort_column, list):
                order_by = params.sort_column[0]
                asc = params.sort_ascending[0] if isinstance(params.sort_ascending, list) else params.sort_ascending
            else:
                order_by = params.sort_column
                asc = params.sort_ascending if isinstance(params.sort_ascending, bool) else True
            order_direction = "asc" if asc else "desc"

        response = self._lp_lims_client.read(
            user=self._lp_lims_user_email,
            tab=self.app_config.database.lp_lims_tab,
            environment=self.app_config.database.lp_lims_environment,
            filters=filters,
            tab_filters=tab_filters,
            page=params.page,
            page_size=params.page_size,
            order_by=order_by,
            order_direction=order_direction,
        )

        df = pd.DataFrame(response.data)
        if df.empty and response.columns:
            df = pd.DataFrame(columns=response.columns)

        # Add synthetic _mod_status column (LP LIMS is read-only)
        if not df.empty:
            df["_mod_status"] = "unprocessed"

        print(f"[DataFetcher] LP LIMS fetched {len(df)} rows (page {params.page})")
        return df

    def _reconcile_status_column(self, df: pd.DataFrame) -> pd.DataFrame:
        """Sync the status column with _mod_status for rows where they disagree."""
        status_col = self._effective_status_column
        if not status_col:
            return df
        status_values = getattr(self.app_config, "status_values", {})
        if not isinstance(status_values, dict):
            return df
        pk_columns = self.app_config.table.primary_key
        return _reconcile_status_df(df, status_col, status_values, pk_columns,
                                    self._update_status_in_db)

    def _update_status_in_db(self, row_pk: dict, column: str, value: str):
        """Issue an UPDATE to the data table for a single row's status column."""
        db_mode = self.app_config.database.mode
        data_table = self._active_table_name
        pk_columns = self.app_config.table.primary_key

        if self._is_datum:
            where_parts = []
            for pk_col in pk_columns:
                if pk_col in row_pk:
                    pk_val = SqlLiteral(row_pk[pk_col])
                    where_parts.append(f"{SqlIdentifier(pk_col)} = {pk_val}")
            if not where_parts:
                return
            sql = (
                f"UPDATE {SqlTableName(data_table)} "
                f"SET {SqlIdentifier(column)} = {SqlLiteral(value)} "
                f"WHERE {' AND '.join(where_parts)}"
            )
            self._datum_client.execute_sql(
                sql=sql,
                database=self.app_config.database.datum_database,
                schema=self.app_config.database.datum_schema,
                service_name=self.app_config.database.datum_service_name,
            )
        else:
            engine = self._get_engine()
            if engine is None:
                return
            from sqlalchemy import text
            where_parts = []
            params = {"new_value": value}
            for i, pk_col in enumerate(pk_columns):
                if pk_col in row_pk:
                    where_parts.append(f"{SqlIdentifier(pk_col)} = :pk_{i}")
                    params[f"pk_{i}"] = row_pk[pk_col]
            if not where_parts:
                return
            sql = (
                f"UPDATE {SqlTableName(data_table)} "
                f"SET {SqlIdentifier(column)} = :new_value "
                f"WHERE {' AND '.join(where_parts)}"
            )
            with engine.connect() as conn:
                conn.execute(text(sql), params)
                conn.commit()

    def _apply_field_modifications(self, df: pd.DataFrame) -> pd.DataFrame:
        """Reconcile field modifications: data table wins.
        
        Since edits write directly to the data table, the SELECT already
        contains the correct values.  This method queries the mods table to
        detect disagreements and fixes them so the mod table stays consistent.
        The DataFrame is NEVER overwritten — the data table is the source of truth.
        """
        if df.empty or self._skip_mods:
            return df
        
        try:
            mods_table = self.app_config.database.mods_table
            pk_columns = self.app_config.table.primary_key
            mods_table_sql = SqlTableName(mods_table)
            
            # Build PK index for row lookups
            pk_index = {}
            for idx, row in df.iterrows():
                pk_dict = {pk: row[pk] for pk in pk_columns if pk in df.columns}
                serializable_pk = {}
                for k, v in pk_dict.items():
                    if hasattr(v, 'item'):
                        serializable_pk[k] = v.item()
                    elif pd.isna(v):
                        serializable_pk[k] = None
                    else:
                        serializable_pk[k] = v
                pk_json = json.dumps(serializable_pk, sort_keys=True)
                if pk_json not in pk_index:
                    pk_index[pk_json] = []
                pk_index[pk_json].append(idx)
            
            # Use pre-fetched _field_mods column if available (merged CTE)
            if "_field_mods" in df.columns:
                mods = []
                for idx, row in df.iterrows():
                    fm = row["_field_mods"]
                    if fm is None or (isinstance(fm, float) and pd.isna(fm)):
                        continue
                    if isinstance(fm, str):
                        fm = json.loads(fm)
                    if not isinstance(fm, list):
                        continue
                    pk_dict = {pk: row[pk] for pk in pk_columns if pk in df.columns}
                    serializable_pk = {}
                    for k, v in pk_dict.items():
                        if hasattr(v, 'item'):
                            serializable_pk[k] = v.item()
                        elif pd.isna(v):
                            serializable_pk[k] = None
                        else:
                            serializable_pk[k] = v
                    pk_json = json.dumps(serializable_pk, sort_keys=True)
                    for m in fm:
                        mods.append({
                            "row_pk": pk_json,
                            "column_name": m["column_name"],
                            "old_value": m.get("old_value"),
                            "new_value": m["new_value"],
                        })
                df = df.drop(columns=["_field_mods"])
            else:
                # Fallback: separate query (used by fetch_all_filtered / skip_mods paths)
                pk_values = list(pk_index.keys())
                if not pk_values:
                    return df
                pk_array_expr = build_pk_array(pk_values)
                mods_query = f"""
                  SELECT row_pk,
                      column_name,
                      (array_agg(old_value ORDER BY created_at ASC))[1] AS old_value,
                      (array_agg(new_value ORDER BY created_at DESC))[1] AS new_value
                FROM {mods_table_sql}
                WHERE mod_type = 'field_modification' 
                  AND undone = FALSE
                  AND row_pk = ANY({pk_array_expr})
                  GROUP BY row_pk, column_name
                """
                
                if self._is_datum:
                    response = self._datum_client.execute_sql(
                        sql=mods_query,
                        database=self.app_config.database.datum_database,
                        schema=self.app_config.database.datum_schema,
                        service_name=self.app_config.database.datum_service_name,
                    )
                    mods = response.data
                else:
                    from sqlalchemy import text
                    with self._engine.connect() as conn:
                        result = conn.execute(text(mods_query))
                        mods = [dict(row._mapping) for row in result.fetchall()]
            
            # Detect disagreements — data table wins, don't overwrite df
            self.edited_cells = {}
            disagreements = []  # [(pk_json, col, data_table_value)]
            seen = set()  # Track (pk_json, col) to only record latest disagreement
            for mod in mods:
                row_pk = mod["row_pk"]
                if isinstance(row_pk, dict):
                    row_pk_dict = row_pk
                    pk_json = json.dumps(row_pk, sort_keys=True)
                elif isinstance(row_pk, str):
                    try:
                        row_pk_dict = json.loads(row_pk)
                        pk_json = json.dumps(row_pk_dict, sort_keys=True)
                    except (json.JSONDecodeError, TypeError):
                        row_pk_dict = {}
                        pk_json = row_pk
                else:
                    row_pk_dict = row_pk if isinstance(row_pk, dict) else {}
                    pk_json = json.dumps(row_pk, sort_keys=True)
                
                if pk_json in pk_index:
                    col = mod["column_name"]
                    mod_val = mod["new_value"]
                    old_value = mod.get("old_value")
                    idx = pk_index[pk_json][0]
                    if col in df.columns:
                        actual = df.at[idx, col]
                        actual_str = str(actual) if pd.notna(actual) else ""
                        mod_str = str(mod_val) if mod_val is not None else ""
                        if row_pk_dict:
                            pk_tuple = tuple(sorted((k, str(v)) for k, v in row_pk_dict.items()))
                            self.edited_cells[(pk_tuple, col)] = {"original": old_value, "current": actual_str}
                        cell_key = (pk_json, col)
                        if actual_str != mod_str:
                            if cell_key not in seen:
                                disagreements.append((pk_json, col, actual_str))
                                seen.add(cell_key)
            
            # Fix mod table for any disagreements
            if disagreements:
                self._fix_mod_disagreements(disagreements, mods_table_sql)
            
            return df
            
        except Exception as e:
            print(f"✗ Error applying field modifications: {e}")
            return df

    def _fix_mod_disagreements(self, disagreements: list,
                               mods_table_sql: SqlTableName):
        """Update the latest mod record's new_value to match the data table."""
        for pk_json, col, data_val in disagreements:
            sql = (
                f"UPDATE {mods_table_sql} "
                f"SET new_value = {SqlLiteral(data_val)} "
                f"WHERE id = ("
                f"  SELECT id FROM {mods_table_sql} "
                f"  WHERE row_pk = {SqlLiteral(pk_json)}::jsonb "
                f"    AND column_name = {SqlLiteral(col)} "
                f"    AND mod_type = 'field_modification' "
                f"    AND undone = FALSE "
                f"  ORDER BY created_at DESC LIMIT 1"
                f")"
            )
            try:
                if self._is_datum:
                    self._datum_client.execute_sql(
                        sql=sql,
                        database=self.app_config.database.datum_database,
                        schema=self.app_config.database.datum_schema,
                        service_name=self.app_config.database.datum_service_name,
                    )
                elif self._engine:
                    from sqlalchemy import text as sa_text
                    with self._engine.connect() as conn:
                        conn.execute(sa_text(sql))
                        conn.commit()
            except Exception as e:
                print(f"[Reconcile] Failed to fix mod for {col}: {e}")


@dataclass
class ConfigInstance:
    """
    Holds all configuration and data for a single widget instance.
    
    This allows multiple widgets to have independent configs and data.
    """
    config_path: str
    username: str = "default_user"  # User identifier (sanitized) for user-scoped state
    user_email: str = ""  # Actual user email for LP LIMS API
    app_config: AppConfig = field(default=None)
    df: pd.DataFrame = field(default=None)
    all_columns: List[str] = field(default_factory=list)
    display_columns: List[str] = field(default_factory=list)
    data_dir: Path = field(default=None)
    modifications_log_path: Path = field(default=None)
    _state_table_checked: bool = field(default=False, repr=False)
    _state_table_available: bool = field(default=False, repr=False)
    _mods_table_checked: bool = field(default=False, repr=False)
    _preset_table_checked: bool = field(default=False, repr=False)
    _preset_legacy_mode: Optional[bool] = field(default=None, repr=False)  # None=unchecked, True=old per-user table, False=new shared table
    _engine: Any = field(default=None, repr=False)
    _postgres_client: Any = field(default=None, repr=False)
    _mods_log_cache: List[Dict] = field(default=None, repr=False)  # Cache for modifications log
    _mods_log_cache_time: float = field(default=0, repr=False)  # Cache timestamp
    _mods_log_pk_cache: List[Dict] = field(default=None, repr=False)  # Cache for scoped modifications log
    _mods_log_pk_cache_key: Tuple[str, ...] = field(default=None, repr=False)
    _mods_log_pk_cache_time: float = field(default=0, repr=False)
    _data_cache: pd.DataFrame = field(default=None, repr=False)  # Cache for data
    _data_cache_time: float = field(default=0, repr=False)  # Data cache timestamp
    _data_fetcher: Any = field(default=None, repr=False)  # DataProvider (lazy loading)
    _schemas_verified: set = field(default_factory=set, repr=False)  # Schemas already confirmed to exist
    _data_table_checked: bool = field(default=False, repr=False)  # Data table existence verified
    _synthesis_exists_cache: Optional[bool] = field(default=None, repr=False)  # Cached synthesis table existence
    _synthesis_age_cache: Optional[float] = field(default=None, repr=False)  # Cached synthesis age (minutes)
    _synthesis_age_cache_time: float = field(default=0, repr=False)  # When cache was populated
    
    @property
    def _effective_status_column(self) -> Optional[str]:
        """Return status_column only if it actually exists in the table
        *and* the status filter feature is enabled.

        Mirrors DataFetcher._effective_status_column so that
        _load_from_database / _load_from_datum can reference it on self.

        During initial load, all_columns is empty — return None to use
        safe fallback (trusting the config value risks case mismatches).
        """
        if self._skip_mods:
            return None
        col = getattr(self.app_config.database, "status_column", None)
        if not col:
            return None
        # Lazy mode — DataFetcher already knows the schema
        if self._data_fetcher is not None:
            return self._data_fetcher._effective_status_column
        # Columns already populated (reload / cache refresh)
        if self.all_columns and col in self.all_columns:
            return col
        # Initial load — columns unknown yet; return None to use safe fallback
        return None

    @property
    def _skip_mods(self) -> bool:
        """True when modification tracking is disabled.

        Returns True when either enable_status_filter or
        enable_approval_workflow is False.
        """
        if not getattr(self.app_config, "enable_approval_workflow", True):
            return True
        return not getattr(self.app_config, "enable_status_filter", True)

    @property
    def _lp_lims_user_email(self) -> str:
        """Return user email for LP LIMS API.
        
        Uses user_email field directly (actual email from Posit Connect),
        falls back to LP_LIMS_USER env var.
        """
        return self.user_email or os.environ.get("LP_LIMS_USER", "")

    def __post_init__(self):
        """Load config and data after initialization."""
        self._load_all()
    
    def _get_engine(self):
        """Get or create a cached SQLAlchemy engine."""
        if self._engine is None:
            from sqlalchemy import create_engine
            conn_string = self.app_config.database.connection_string
            if conn_string:
                self._engine = create_engine(conn_string)
        return self._engine

    def _resolve_env_ref(self, env_name: Optional[Any], default_env_names: list[str] = None, default=None, cast=None):
        """Resolve a config value that names an environment variable."""
        names = []
        if env_name not in (None, ""):
            names.append(str(env_name))
        names.extend(default_env_names or [])
        for name in names:
            value = os.environ.get(name)
            if value not in (None, ""):
                return cast(value) if cast else value
        return default

    def _postgres_client_kwargs(self) -> dict:
        """Build PostgresClient kwargs from env-var-name config references."""
        return {
            "dsn": self._resolve_env_ref(self.app_config.database.postgres_dsn, ["PG_DSN", "DATABASE_URL"]),
            "host": self._resolve_env_ref(self.app_config.database.postgres_host, ["PG_HOST"]),
            "port": self._resolve_env_ref(self.app_config.database.postgres_port, ["PG_PORT"], cast=int),
            "user": self._resolve_env_ref(self.app_config.database.postgres_user, ["PG_USER"]),
            "password": self._resolve_env_ref(self.app_config.database.postgres_password, ["PG_PASSWORD"]),
            "database": self._resolve_env_ref(self.app_config.database.postgres_database, ["PG_DATABASE"]),
            "schema": self._resolve_env_ref(self.app_config.database.postgres_schema, ["PG_SCHEMA"]),
            "connect_timeout": self._resolve_env_ref(self.app_config.database.postgres_connect_timeout, ["PG_CONNECT_TIMEOUT"], default=5, cast=int),
        }

    def _get_postgres_client(self):
        """Get or create a cached direct Postgres execute_sql client."""
        if self._postgres_client is None:
            from ..adapter.postgres import PostgresClient
            self._postgres_client = PostgresClient(**self._postgres_client_kwargs())
        return self._postgres_client

    def _uses_execute_sql_client(self) -> bool:
        """True when synthesis SQL should use a Datum-compatible execute_sql client."""
        return self.app_config.database.mode in ("datum", "postgres")

    def _execute_client_sql(self, sql: str):
        """Execute SQL through Datum or direct Postgres clients."""
        if self.app_config.database.mode == "postgres":
            return self._get_postgres_client().execute_sql(sql=sql)

        from ..adapter.datum import DatumClient
        base_url = self.app_config.database.datum_base_url or os.environ.get("DATUM_BASE_URL", "")
        token = self.app_config.database.datum_token or os.environ.get("DATUM_API_TOKEN", "")
        client = DatumClient(base_url=base_url, token=token)
        return client.execute_sql(
            sql=sql,
            database=self.app_config.database.datum_database,
            schema=self.app_config.database.datum_schema,
            service_name=self.app_config.database.datum_service_name,
        )

    def _execute_synthesis_sql(self, sql: str):
        """Execute synthesis SQL through Datum or direct Postgres clients."""
        return self._execute_client_sql(sql)
    
    def _load_all(self):
        """Load configuration and data."""
        import time as _t
        _t0 = _t.time()

        # Determine project root from config path
        config_file = Path(self.config_path)
        if not config_file.is_absolute():
            config_file = Path.cwd() / config_file
        
        project_root = config_file.parent
        
        # Load app config
        self.app_config = load_config(
            str(config_file).strip(),
            username=self.username
        )
        _t1 = _t.time()
        print(f"[Timing] load_config: {(_t1 - _t0)*1000:.0f}ms")
        
        # Setup paths (don't create at init - filesystem may be read-only)
        self.data_dir = project_root / "data"
        # Note: Directory created lazily when needed for exports
        
        # When synthesis is enabled with a query, skip loading the base table
        # entirely.  The server layer will load the synthesis result table or
        # trigger generation instead.
        if (getattr(self.app_config, 'enable_synthesis', False)
                and getattr(self.app_config.synthesis, 'query', '')):
            self.df = pd.DataFrame()
            self.all_columns = []
            self.display_columns = []
            self.modifications_log_path = self.data_dir / "modifications_log.json"
            print(f"[Synthesis] Skipping base table load — synthesis mode active")
            return

        # Check if lazy loading is enabled
        if self.app_config.database.lazy_loading:
            # Lazy loading mode: only get metadata, fetch data on demand
            from ..adapter.factory import create_data_provider
            self._data_fetcher = create_data_provider(
                app_config=self.app_config,
                username=self.username,
                user_email=self.user_email,
            )
            self.all_columns = self._data_fetcher.columns
            # Create empty DataFrame with correct columns
            self.df = pd.DataFrame(columns=self.all_columns)
            print(f"📊 Lazy loading enabled: {self._data_fetcher.total_count} total rows, fetching on demand")
        else:
            # Traditional mode: load all data at startup
            _t2 = _t.time()
            self.df = self._load_data()
            _t3 = _t.time()
            print(f"[Timing] _load_data: {(_t3 - _t2)*1000:.0f}ms ({len(self.df)} rows)")
            self.all_columns = list(self.df.columns)
        
        self.display_columns = self._get_display_columns()
        
        # Modifications log path (for reference only)
        self.modifications_log_path = self.data_dir / "modifications_log.json"
        print(f"[Timing] _load_all total: {(_t.time() - _t0)*1000:.0f}ms")
    
    @property
    def data_fetcher(self):
        """Get the DataProvider for lazy loading mode."""
        return self._data_fetcher
    
    @property
    def is_lazy_loading(self) -> bool:
        """Check if lazy loading is enabled."""
        return self._data_fetcher is not None

    def activate_synthesis_fetcher(self, matview_table: str):
        """Create (or reconfigure) a DataFetcher pointing at *matview_table*.

        Called when entering synthesis mode so that SQL-level filtering,
        sorting and pagination target the materialized view instead of
        the original data table.

        If a DataFetcher already exists it simply gets a table override.
        If not (synthesis skipped lazy-loading init), one is created now
        with the matview as the initial table.
        """
        if self._data_fetcher is None:
            # Bootstrap a new DataFetcher.  Set _table_override *before*
            # _fetch_metadata so introspection (count, columns, types) reads
            # from the matview, not the (possibly non-existent) base table.
            fetcher = DataFetcher.__new__(DataFetcher)
            fetcher.app_config = self.app_config
            fetcher.username = self.username
            fetcher.user_email = self.user_email
            fetcher._engine = None
            fetcher._datum_client = None
            fetcher._postgres_client = None
            fetcher._lp_lims_client = None
            fetcher._total_count = 0
            fetcher._columns = []
            fetcher._column_types = {}
            fetcher._table_override = matview_table
            fetcher._query_override = None
            fetcher._init_connection()
            fetcher._fetch_metadata()          # introspects matview
            self._data_fetcher = fetcher
            # Populate columns if not already set (synthesis skipped base table)
            if not self.all_columns and fetcher._columns:
                self.all_columns = fetcher._columns.copy()
                self.display_columns = fetcher._columns.copy()
            # Row count already correct — override was in place during init
            print(f"[DataFetcher] Created for synthesis → {matview_table} ({fetcher._total_count} rows)")
        else:
            self._data_fetcher.set_table_override(matview_table)

    def activate_synthesis_query_fetcher(self, synthesis_query: str):
        """Create/reconfigure a DataFetcher that pages over a synthesis SQL query."""
        if self._data_fetcher is None:
            fetcher = DataFetcher.__new__(DataFetcher)
            fetcher.app_config = self.app_config
            fetcher.username = self.username
            fetcher.user_email = self.user_email
            fetcher._engine = None
            fetcher._datum_client = None
            fetcher._postgres_client = None
            fetcher._lp_lims_client = None
            fetcher._total_count = 0
            fetcher._columns = []
            fetcher._column_types = {}
            fetcher._table_override = None
            fetcher._query_override = synthesis_query.strip().rstrip(";")
            fetcher._init_connection()
            fetcher._fetch_metadata()
            self._data_fetcher = fetcher
        else:
            self._data_fetcher.set_query_override(synthesis_query)

        if self._data_fetcher._columns:
            self.all_columns = self._data_fetcher._columns.copy()
            self.display_columns = self._data_fetcher._columns.copy()
            self.df = pd.DataFrame(columns=self.all_columns)
        print(f"[DataFetcher] Created for synthesis query ({self._data_fetcher.total_count} rows)")

    def deactivate_synthesis_fetcher(self):
        """Restore the DataFetcher to the original data table (or remove it)."""
        if self._data_fetcher is not None:
            if self.app_config.database.lazy_loading:
                # Original config uses lazy loading — just clear the override
                self._data_fetcher.clear_table_override()
            else:
                # Original config doesn't use lazy loading — remove fetcher
                self._data_fetcher = None
    
    @property
    def total_row_count(self) -> int:
        """Get total row count (from fetcher in lazy mode, from df otherwise)."""
        if self._data_fetcher:
            return self._data_fetcher.total_count
        return len(self.df) if self.df is not None else 0
        
        # Modifications log path (for reference only)
        self.modifications_log_path = self.data_dir / "modifications_log.json"
    
    def ensure_data_dir(self) -> bool:
        """
        Ensure data directory exists for file exports.
        Returns True if directory exists/created, False if filesystem is read-only.
        """
        try:
            self.data_dir.mkdir(exist_ok=True)
            return True
        except OSError:
            # Read-only filesystem (e.g., RStudio Connect)
            return False

    def _load_data(self) -> pd.DataFrame:
        """Load data from database with caching.

        Cache layers (checked in order):
        1. App-level shared cache (``shared_cache_key``) — survives across sessions
        2. Per-instance cache (``_data_cache``) — 30-second TTL per session
        3. Fresh DB query
        """
        import time
        cache_ttl = 30  # Per-instance cache TTL

        # ── Layer 1: app-level shared cache ──
        db = getattr(self.app_config, "database", None) if self.app_config else None
        shared_key = getattr(db, "shared_cache_key", None) if db else None
        shared_ttl = getattr(db, "shared_cache_ttl", 300) if db else 300
        if shared_key:
            shared_df = _app_cache_get(shared_key, shared_ttl)
            if shared_df is not None:
                print(f"[Cache] App-level HIT for key={shared_key}")
                # Also populate per-instance cache
                self._data_cache = shared_df.copy()
                self._data_cache_time = time.time()
                return shared_df

        # ── Layer 2: per-instance cache ──
        if self._data_cache is not None and (time.time() - self._data_cache_time) < cache_ttl:
            return self._data_cache.copy()

        # ── Layer 3: fresh DB query ──
        if self.app_config.database.mode == "lp_lims":
            df = self._load_from_lp_lims()
        elif self._uses_execute_sql_client():
            df = self._load_from_datum()
        else:
            df = self._load_from_database()

        # Populate per-instance cache
        self._data_cache = df.copy()
        self._data_cache_time = time.time()

        # Populate app-level cache
        if shared_key:
            _app_cache_set(shared_key, df)
            print(f"[Cache] App-level SET for key={shared_key}")

        return df

    def invalidate_data_cache(self):
        """Invalidate both per-instance and app-level shared caches."""
        self._data_cache = None
        self._data_cache_time = 0
        db = getattr(self.app_config, "database", None) if self.app_config else None
        shared_key = getattr(db, "shared_cache_key", None) if db else None
        if shared_key:
            _app_cache_invalidate(shared_key)
            print(f"[Cache] App-level INVALIDATE for key={shared_key}")

    def _ensure_data_table_exists(self) -> bool:
        """
        Ensure the data_table exists. If not and source_table is configured,
        create data_table as a copy of source_table.
        Returns True if data_table exists (or was created), False otherwise.
        Only runs the probe query once per session.
        """
        if self._data_table_checked:
            return True
        if self._uses_execute_sql_client():
            return self._ensure_data_table_exists_datum()
        
        try:
            from sqlalchemy import text
            
            data_table = self.app_config.database.data_table
            source_table = self.app_config.database.source_table
            data_table_sql = SqlTableName(data_table)
            
            engine = self._get_engine()
            if engine is None:
                return False
            
            # Check if data_table exists
            with engine.connect() as conn:
                # Parse schema.table to check existence properly
                if '.' in data_table:
                    schema, table_name = data_table.split('.', 1)
                    check_sql = text("""
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.tables 
                            WHERE table_schema = :schema AND table_name = :table
                        )
                    """)
                    result = conn.execute(check_sql, {"schema": schema, "table": table_name})
                else:
                    check_sql = text("""
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.tables 
                            WHERE table_name = :table
                        )
                    """)
                    result = conn.execute(check_sql, {"table": data_table})
                
                table_exists = result.scalar()
            
            if table_exists:
                self._data_table_checked = True
                return True
            
            # Table doesn't exist - check if we have a source table to copy from
            if not source_table:
                print(f"⚠ Data table {data_table_sql} does not exist and no source_table configured")
                return False
            
            source_table_sql = SqlTableName(source_table)
            print(f"📋 Creating {data_table_sql} as copy of {source_table_sql}...")
            
            with engine.connect() as conn:
                # Create schema if needed (once per schema per process)
                if '.' in data_table:
                    schema = data_table.split('.', 1)[0]
                    if schema not in self._schemas_verified:
                        schema_sql = SqlIdentifier(schema)
                        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS {schema_sql}'))
                        self._schemas_verified.add(schema)
                
                # Create data_table as a copy of source_table (structure + data)
                conn.execute(text(f'CREATE TABLE {data_table_sql} AS SELECT * FROM {source_table_sql}'))
                conn.commit()
            
            print(f"✓ Created {data_table_sql} from {source_table_sql}")
            self._data_table_checked = True
            return True
            
        except Exception as e:
            print(f"✗ Error ensuring data table exists: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _ensure_data_table_exists_datum(self) -> bool:
        """Ensure data_table exists via Datum-compatible execute_sql client."""
        try:
            data_table = self.app_config.database.data_table
            source_table = self.app_config.database.source_table
            data_table_sql = SqlTableName(data_table)
            
            # Check if data_table exists by trying to select from it
            try:
                self._execute_client_sql(f'SELECT 1 FROM {data_table_sql} LIMIT 1')
                self._data_table_checked = True
                return True  # Table exists
            except Exception:
                pass  # Table doesn't exist, continue
            
            # Table doesn't exist - check if we have a source table to copy from
            if not source_table:
                print(f"⚠ Data table {data_table_sql} does not exist and no source_table configured")
                return False
            
            source_table_sql = SqlTableName(source_table)
            print(f"📋 Creating {data_table_sql} as copy of {source_table_sql} via Datum...")
            
            # Create schema if needed (once per schema per process)
            if '.' in data_table:
                schema = data_table.split('.', 1)[0]
                if schema not in self._schemas_verified:
                    schema_sql = SqlIdentifier(schema)
                    try:
                        self._execute_client_sql(f'CREATE SCHEMA IF NOT EXISTS {schema_sql}')
                    except Exception:
                        pass  # Schema may already exist
                    self._schemas_verified.add(schema)
            
            # Create data_table as a copy of source_table
            self._execute_client_sql(f'CREATE TABLE {data_table_sql} AS SELECT * FROM {source_table_sql}')
            
            print(f"✓ Created {data_table_sql} from {source_table_sql} via execute_sql client")
            self._data_table_checked = True
            return True
            
        except Exception as e:
            print(f"✗ Error ensuring data table exists via execute_sql client: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _load_from_database(self) -> pd.DataFrame:
        """Load data from PostgreSQL database with modification status."""
        try:
            # Ensure data table exists (copy from source_table if needed)
            self._ensure_data_table_exists()
            # Ensure modifications table exists (data query joins against it for _mod_status)
            if not self._skip_mods:
                self._ensure_mods_table_exists()
            
            from sqlalchemy import text
            
            data_table = self.app_config.database.data_table
            mods_table = self.app_config.database.mods_table
            pk_columns = self.app_config.table.primary_key
            
            engine = self._get_engine()
            if engine is None:
                raise ValueError(
                    f"Database connection_string is None. "
                    f"Config path: {self.config_path}, "
                    f"Mode: {self.app_config.database.mode}, "
                    f"Enabled: {self.app_config.database.enabled}"
                )
            
            data_table_sql = SqlTableName(data_table)
            mods_table_sql = SqlTableName(mods_table)
            
            # OPTIMIZED: Use a single JOIN with DISTINCT ON instead of correlated subquery
            # This is much faster as the database can use indexes on mods_table
            pk_json_build = build_pk_json_expr(pk_columns)
            
            # Apply max_rows limit if configured
            max_rows = self.app_config.database.max_rows
            limit_clause = f"LIMIT {max_rows}" if max_rows else ""
            
            if self._skip_mods:
                query = f"""
                SELECT d.*, 'unprocessed' AS _mod_status
                FROM {data_table_sql} d
                ORDER BY d.{SqlIdentifier(pk_columns[0])}
                {limit_clause}
                """
            else:
                cte, join = _build_mod_cte_and_join(mods_table_sql, pk_json_build)
                query = f"""
                {cte}
                SELECT d.*, 
                       {_build_mod_status_expr(self._effective_status_column, getattr(self.app_config, "status_labels", None), getattr(self.app_config, "status_values", None))} AS _mod_status
                FROM {data_table_sql} d
                {join}
                ORDER BY d.{SqlIdentifier(pk_columns[0])}
                {limit_clause}
                """
            
            with engine.connect() as conn:
                result = conn.execute(text(query))
                rows = result.fetchall()
                columns = result.keys()
            
            df = pd.DataFrame(rows, columns=columns)
            
            # Apply field modifications to the data (also optimized)
            df = self._apply_field_modifications(df, engine)
            df = self._reconcile_status_column(df)
            
            return df
        except Exception as e:
            print(f"✗ Error loading from database: {e}")
            return pd.DataFrame()
    
    def _reconcile_status_column(self, df: pd.DataFrame) -> pd.DataFrame:
        """Sync the status column with _mod_status for rows where they disagree."""
        status_col = self._effective_status_column
        if not status_col:
            return df
        status_values = getattr(self.app_config, "status_values", {})
        if not isinstance(status_values, dict):
            return df
        pk_columns = self.app_config.table.primary_key
        return _reconcile_status_df(df, status_col, status_values, pk_columns,
                                    self.update_data_in_db)

    def _apply_field_modifications(self, df: pd.DataFrame, engine) -> pd.DataFrame:
        """Reconcile field modifications: data table wins.
        
        Since edits write directly to the data table, the SELECT already
        holds the correct values.  This method queries the mods table to
        track which cells were edited, but NEVER overwrites the DataFrame.
        If a mod record's new_value disagrees with the data table, the mod
        record is updated to match.
        """
        try:
            from sqlalchemy import text
            
            if df.empty:
                self.edited_cells = {}
                return df
            
            if self._skip_mods:
                self.edited_cells = {}
                return df
            
            mods_table = self.app_config.database.mods_table
            pk_columns = self.app_config.table.primary_key
            mods_table_sql = SqlTableName(mods_table)
            
            # Build list of PKs from current dataframe
            pk_values = []
            pk_index = {}
            for idx, row in df.iterrows():
                pk_dict = {pk: row[pk] for pk in pk_columns if pk in df.columns}
                serializable_pk = {}
                for k, v in pk_dict.items():
                    if hasattr(v, 'item'):
                        serializable_pk[k] = v.item()
                    elif pd.isna(v):
                        serializable_pk[k] = None
                    else:
                        serializable_pk[k] = v
                pk_json = json.dumps(serializable_pk, sort_keys=True)
                pk_values.append(pk_json)
                if pk_json not in pk_index:
                    pk_index[pk_json] = []
                pk_index[pk_json].append(idx)
            
            if not pk_values:
                self.edited_cells = {}
                return df
            
            pk_array = build_pk_array(pk_values)
            
            mods_query = f"""
            SELECT row_pk, column_name, old_value, new_value 
            FROM {mods_table_sql}
            WHERE mod_type = 'field_modification' 
              AND undone = FALSE
              AND row_pk = ANY({pk_array})
            ORDER BY created_at ASC
            """
            
            with engine.connect() as conn:
                result = conn.execute(text(mods_query))
                mods_data = result.fetchall()
            
            self.edited_cells = {}
            disagreements = []  # [(pk_json, col, data_table_value)]
            seen = set()
            
            if mods_data:
                for mod in mods_data:
                    row_pk = mod[0]
                    if isinstance(row_pk, str):
                        row_pk = json.loads(row_pk)
                    col_name = mod[1]
                    old_value = mod[2]
                    new_value = mod[3]
                    
                    if col_name in df.columns:
                        pk_json = json.dumps(row_pk, sort_keys=True)
                        row_indices = pk_index.get(pk_json, [])
                        
                        if row_indices:
                            pk_tuple = tuple(sorted((k, str(v)) for k, v in row_pk.items()))
                            cell_key = (pk_tuple, col_name)
                            
                            # Use the data table value as "current"
                            idx = row_indices[0]
                            actual = df.at[idx, col_name]
                            actual_str = str(actual) if pd.notna(actual) else ""
                            
                            if cell_key not in self.edited_cells:
                                self.edited_cells[cell_key] = {
                                    "original": old_value,
                                    "current": actual_str
                                }
                            else:
                                self.edited_cells[cell_key]["current"] = actual_str
                            
                            # Detect disagreement — data table wins
                            mod_str = str(new_value) if new_value is not None else ""
                            disagree_key = (pk_json, col_name)
                            if actual_str != mod_str and disagree_key not in seen:
                                disagreements.append((pk_json, col_name, actual_str))
                                seen.add(disagree_key)
                            
                            # DON'T overwrite df — data table is source of truth
            
            # Fix mod table for any disagreements
            if disagreements:
                self._fix_mod_disagreements(disagreements, mods_table_sql, engine)
            
            return df
        except Exception as e:
            print(f"⚠ Could not apply field modifications: {e}")
            self.edited_cells = {}
            return df

    def _fix_mod_disagreements(self, disagreements: list,
                               mods_table_sql: SqlTableName, engine):
        """Update the latest mod record's new_value to match the data table."""
        from sqlalchemy import text as sa_text
        for pk_json, col, data_val in disagreements:
            sql = (
                f"UPDATE {mods_table_sql} "
                f"SET new_value = {SqlLiteral(data_val)} "
                f"WHERE id = ("
                f"  SELECT id FROM {mods_table_sql} "
                f"  WHERE row_pk = {SqlLiteral(pk_json)}::jsonb "
                f"    AND column_name = {SqlLiteral(col)} "
                f"    AND mod_type = 'field_modification' "
                f"    AND undone = FALSE "
                f"  ORDER BY created_at DESC LIMIT 1"
                f")"
            )
            try:
                with engine.connect() as conn:
                    conn.execute(sa_text(sql))
                    conn.commit()
            except Exception as e:
                print(f"[Reconcile] Failed to fix mod for {col}: {e}")
    
    def get_edited_cells(self) -> dict:
        """Return dict of edited cells: {(pk_tuple, col_name): {"original": val, "current": val}}"""
        return getattr(self, 'edited_cells', {})
    
    def is_cell_edited(self, row_pk: dict, col_name: str) -> bool:
        """Check if a specific cell has been edited using its PK."""
        pk_tuple = tuple(sorted((k, str(v)) for k, v in row_pk.items()))
        return (pk_tuple, col_name) in getattr(self, 'edited_cells', {})
    
    def get_original_value(self, row_pk: dict, col_name: str) -> str:
        """Get the original value for an edited cell, or None if not edited."""
        pk_tuple = tuple(sorted((k, str(v)) for k, v in row_pk.items()))
        cell_info = getattr(self, 'edited_cells', {}).get((pk_tuple, col_name))
        if cell_info:
            return cell_info.get("original")
        return None
    
    def _load_from_datum(self) -> pd.DataFrame:
        """Load data via Datum-compatible execute_sql client."""
        try:
            # Ensure data table exists (copy from source_table if needed)
            self._ensure_data_table_exists()
            # Ensure modifications table exists (data query joins against it for _mod_status)
            if not self._skip_mods:
                self._ensure_mods_table_exists()

            data_table = self.app_config.database.data_table
            mods_table = self.app_config.database.mods_table
            pk_columns = self.app_config.table.primary_key
            data_table_sql = SqlTableName(data_table)
            mods_table_sql = SqlTableName(mods_table)
            
            # OPTIMIZED: Use LATERAL JOIN instead of correlated subquery
            pk_json_build = build_pk_json_expr(pk_columns)
            
            # Apply max_rows limit if configured
            max_rows = self.app_config.database.max_rows
            limit_clause = f"LIMIT {max_rows}" if max_rows else ""
            
            # Use explicit columns when available (avoids ARRAY crash in Datum proxy)
            cols = self._data_fetcher._select_columns if self._data_fetcher else "d.*"
            
            if self._skip_mods:
                query = f"""
                SELECT {cols}, 'unprocessed' AS _mod_status
                FROM {data_table_sql} d
                ORDER BY d.{SqlIdentifier(pk_columns[0])}
                {limit_clause}
                """
            else:
                cte, join = _build_mod_cte_and_join(mods_table_sql, pk_json_build)
                query = f"""
                {cte}
                SELECT {cols}, 
                       {_build_mod_status_expr(self._effective_status_column, getattr(self.app_config, "status_labels", None), getattr(self.app_config, "status_values", None))} AS _mod_status
                FROM {data_table_sql} d
                {join}
                ORDER BY d.{SqlIdentifier(pk_columns[0])}
                {limit_clause}
                """
            
            response = self._execute_client_sql(query)
            
            df = pd.DataFrame(response.data)

            # Coerce date/timestamp columns from epoch-ms to datetime
            if self._data_fetcher:
                df = self._data_fetcher._coerce_date_columns(df)
            
            if not self._skip_mods:
                # Clean up any corrupted modifications before applying
                self._cleanup_corrupted_modifications_datum()
            
            # Apply field modifications to the data (also optimized)
            df = self._apply_field_modifications_datum(df, None)
            df = self._reconcile_status_column(df)
            
            return df
        except Exception as e:
            print(f"✗ Error loading from execute_sql client: {e}")
            return pd.DataFrame()

    def _load_from_lp_lims(self) -> pd.DataFrame:
        """Load data via LP LIMS read-only API."""
        try:
            from ..adapter.lp_lims import LpLimsClient

            base_url = self.app_config.database.lp_lims_base_url or os.environ.get("LP_LIMS_BASE_URL", "")
            token = self.app_config.database.lp_lims_token or os.environ.get("LP_LIMS_API_TOKEN", "") or os.environ.get("DATUM_API_TOKEN", "")

            if not base_url or not token:
                raise ValueError("LP LIMS mode requires lp_lims_base_url and token (LP_LIMS_API_TOKEN or DATUM_API_TOKEN)")

            client = LpLimsClient(base_url=base_url, token=token)
            max_rows = self.app_config.database.max_rows

            response = client.read(
                user=self._lp_lims_user_email,
                tab=self.app_config.database.lp_lims_tab,
                environment=self.app_config.database.lp_lims_environment,
                page=1,
                page_size=max_rows or 10000,
            )

            df = pd.DataFrame(response.data)
            if not df.empty:
                df["_mod_status"] = "unprocessed"

            return df
        except Exception as e:
            print(f"✗ Error loading from LP LIMS: {e}")
            return pd.DataFrame()

    def _apply_field_modifications_datum(self, df: pd.DataFrame, client) -> pd.DataFrame:
        """Reconcile field modifications via Datum proxy: data table wins.
        
        Since edits write directly to the data table, the SELECT already
        holds the correct values.  This method queries the mods table to
        track which cells were edited, but NEVER overwrites the DataFrame.
        If a mod record's new_value disagrees with the data table, the mod
        record is updated to match.
        """
        try:
            if df.empty:
                self.edited_cells = {}
                return df
            
            if self._skip_mods:
                self.edited_cells = {}
                return df
            
            mods_table = self.app_config.database.mods_table
            pk_columns = self.app_config.table.primary_key
            mods_table_sql = SqlTableName(mods_table)
            
            pk_values = []
            pk_index = {}
            for idx, row in df.iterrows():
                pk_dict = {pk: row[pk] for pk in pk_columns if pk in df.columns}
                serializable_pk = {}
                for k, v in pk_dict.items():
                    if hasattr(v, 'item'):
                        serializable_pk[k] = v.item()
                    elif pd.isna(v):
                        serializable_pk[k] = None
                    else:
                        serializable_pk[k] = v
                pk_json = json.dumps(serializable_pk, sort_keys=True)
                pk_values.append(pk_json)
                if pk_json not in pk_index:
                    pk_index[pk_json] = []
                pk_index[pk_json].append(idx)
            
            if not pk_values:
                self.edited_cells = {}
                return df
            
            pk_array = build_pk_array(pk_values)
            
            mods_query = f"""
            SELECT row_pk, column_name, old_value, new_value 
            FROM {mods_table_sql}
            WHERE mod_type = 'field_modification' 
              AND undone = FALSE
              AND row_pk = ANY({pk_array})
            ORDER BY created_at ASC
            """
            
            response = self._execute_client_sql(mods_query)
            
            self.edited_cells = {}
            disagreements = []
            seen = set()
            
            if response.data:
                for mod in response.data:
                    row_pk_raw = mod.get("row_pk", {})
                    row_pk = row_pk_raw
                    if isinstance(row_pk, str):
                        row_pk = json.loads(row_pk)
                    col_name = mod.get("column_name")
                    old_value = mod.get("old_value")
                    new_value = mod.get("new_value")
                    
                    if not row_pk:
                        continue
                    
                    if col_name in df.columns:
                        pk_json = json.dumps(row_pk, sort_keys=True)
                        row_indices = pk_index.get(pk_json, [])
                        
                        if row_indices:
                            pk_tuple = tuple(sorted((k, str(v)) for k, v in row_pk.items()))
                            cell_key = (pk_tuple, col_name)
                            
                            # Use the data table value as "current"
                            idx = row_indices[0]
                            actual = df.at[idx, col_name]
                            actual_str = str(actual) if pd.notna(actual) else ""
                            
                            if cell_key not in self.edited_cells:
                                self.edited_cells[cell_key] = {
                                    "original": old_value,
                                    "current": actual_str
                                }
                            else:
                                self.edited_cells[cell_key]["current"] = actual_str
                            
                            # Detect disagreement — data table wins
                            mod_str = str(new_value) if new_value is not None else ""
                            disagree_key = (pk_json, col_name)
                            if actual_str != mod_str and disagree_key not in seen:
                                disagreements.append((pk_json, col_name, actual_str))
                                seen.add(disagree_key)
                            
                            # DON'T overwrite df — data table is source of truth
            
            # Fix mod table for any disagreements
            if disagreements:
                self._fix_mod_disagreements_datum(disagreements, mods_table_sql, client)
            
            mod_count = len(self.edited_cells)
            if mod_count > 0:
                print(f"✓ Tracked {mod_count} edited cells (data table authoritative)")
            
            return df
        except Exception as e:
            print(f"⚠ Could not apply field modifications via Datum: {e}")
            self.edited_cells = {}
            return df

    def _fix_mod_disagreements_datum(self, disagreements: list,
                                     mods_table_sql: SqlTableName, client):
        """Update the latest mod record's new_value to match the data table."""
        for pk_json, col, data_val in disagreements:
            sql = (
                f"UPDATE {mods_table_sql} "
                f"SET new_value = {SqlLiteral(data_val)} "
                f"WHERE id = ("
                f"  SELECT id FROM {mods_table_sql} "
                f"  WHERE row_pk = {SqlLiteral(pk_json)}::jsonb "
                f"    AND column_name = {SqlLiteral(col)} "
                f"    AND mod_type = 'field_modification' "
                f"    AND undone = FALSE "
                f"  ORDER BY created_at DESC LIMIT 1"
                f")"
            )
            try:
                self._execute_client_sql(sql)
            except Exception as e:
                print(f"[Reconcile] Failed to fix mod for {col}: {e}")

    def _get_display_columns(self) -> List[str]:
        """Get default display columns from configuration."""
        if self.app_config.table.default_columns:
            return [col for col in self.app_config.table.default_columns if col in self.df.columns]
        return self.all_columns[:12]  # Default to first 12 columns
    
    def load_modifications_log(
        self,
        force_refresh: bool = False,
        row_pks: list = None,
    ) -> List[Dict]:
        """
        Load modifications log from database with caching.
        
        Args:
            force_refresh: If True, bypass cache and reload from DB
            row_pks: Optional list of row PK dicts to load only those rows' mods
        """
        # When approval workflow is disabled, skip all mods DB queries
        if self._skip_mods:
            return []
        
        import time
        
        # Use cached data if available and not expired (cache for 5 seconds)
        cache_ttl = 5.0
        pk_json_values = None
        if row_pks is not None:
            pk_json_values = _row_pk_json_values(row_pks)
            if not pk_json_values:
                return []
            scoped_key = tuple(sorted(pk_json_values))
            if (
                not force_refresh
                and getattr(self, "_mods_log_pk_cache", None) is not None
                and getattr(self, "_mods_log_pk_cache_key", None) == scoped_key
                and time.time() - getattr(self, "_mods_log_pk_cache_time", 0) < cache_ttl
            ):
                return self._mods_log_pk_cache
            if self._uses_execute_sql_client():
                result = self._load_modifications_from_datum(pk_json_values=pk_json_values)
            else:
                result = self._load_modifications_from_db(pk_json_values=pk_json_values)
            self._mods_log_pk_cache = result
            self._mods_log_pk_cache_key = scoped_key
            self._mods_log_pk_cache_time = time.time()
            return result

        if not force_refresh and self._mods_log_cache is not None:
            if time.time() - self._mods_log_cache_time < cache_ttl:
                return self._mods_log_cache
        
        # Load from database
        if self._uses_execute_sql_client():
            result = self._load_modifications_from_datum()
        else:
            result = self._load_modifications_from_db()
        
        # Update cache
        self._mods_log_cache = result
        self._mods_log_cache_time = time.time()
        
        return result
    
    def invalidate_mods_cache(self):
        """Invalidate the modifications log cache (call after making changes)."""
        self._mods_log_cache = None
        self._mods_log_cache_time = 0
        self._mods_log_pk_cache = None
        self._mods_log_pk_cache_key = None
        self._mods_log_pk_cache_time = 0

    def _ensure_mods_table_exists(self) -> bool:
        """Create the modifications table if it doesn't exist. Only runs once per instance."""
        # Skip if already checked this session
        if self._mods_table_checked:
            return True
        
        if self._uses_execute_sql_client():
            return self._ensure_mods_table_exists_datum()
        
        try:
            from sqlalchemy import text
            
            mods_table = self.app_config.database.mods_table
            
            # Parse schema.table format
            if '.' in mods_table:
                schema, table_name = mods_table.split('.', 1)
                schema_sql = str(SqlIdentifier(schema))
                table_sql = SqlTableName(mods_table)
            else:
                schema = None
                schema_sql = None
                table_sql = SqlTableName(mods_table)
            
            engine = self._get_engine()
            if engine is None:
                return False
            
            with engine.connect() as conn:
                # Create schema if needed (once per schema per process)
                if schema_sql and schema not in self._schemas_verified:
                    conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS {schema_sql}'))
                    self._schemas_verified.add(schema)
                
                # Create table if not exists
                conn.execute(text(f'''
                    CREATE TABLE IF NOT EXISTS {table_sql} (
                        id SERIAL PRIMARY KEY,
                        row_pk JSONB NOT NULL,
                        column_name VARCHAR(255) NOT NULL,
                        old_value TEXT,
                        new_value TEXT,
                        mod_type VARCHAR(50) NOT NULL,
                        undone BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT NOW(),
                        created_by VARCHAR(255)
                    )
                '''))
                conn.commit()
                for index_sql in _mods_index_statements(mods_table):
                    try:
                        conn.execute(text(index_sql))
                        conn.commit()
                    except Exception as idx_e:
                        conn.rollback()
                        print(f"⚠ Could not create mods index: {idx_e}")
            self._mods_table_checked = True
            print(f"✓ Modifications table {table_sql} ensured")
            return True
        except Exception as e:
            print(f"⚠ Could not create mods table: {e}")
            return False

    def _ensure_mods_table_exists_datum(self) -> bool:
        """Create modifications table via Datum-compatible execute_sql client."""
        try:
            mods_table = self.app_config.database.mods_table
            mods_table_sql = SqlTableName(mods_table)
            
            # Parse schema for CREATE SCHEMA
            schema_sql = None
            schema_name = None
            if '.' in mods_table:
                schema_name = mods_table.split('.', 1)[0]
                schema_sql = str(SqlIdentifier(schema_name))
            
            # Create schema if needed (once per schema per process)
            if schema_sql and schema_name not in self._schemas_verified:
                try:
                    self._execute_client_sql(f'CREATE SCHEMA IF NOT EXISTS {schema_sql}')
                except Exception:
                    pass  # Schema may already exist
                self._schemas_verified.add(schema_name)
            
            # Create table if not exists - DDL auto-commits
            self._execute_client_sql(
                f'''
                    CREATE TABLE IF NOT EXISTS {mods_table_sql} (
                        id SERIAL PRIMARY KEY,
                        row_pk JSONB NOT NULL,
                        column_name VARCHAR(255) NOT NULL,
                        old_value TEXT,
                        new_value TEXT,
                        mod_type VARCHAR(50) NOT NULL,
                        undone BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT NOW(),
                        created_by VARCHAR(255)
                    )
                '''
            )
            for index_sql in _mods_index_statements(mods_table):
                try:
                    self._execute_client_sql(index_sql)
                except Exception as idx_e:
                    print(f"⚠ Could not create mods index via execute_sql client: {idx_e}")
            
            self._mods_table_checked = True
            print(f"✓ Modifications table {mods_table_sql} ensured via execute_sql client")
            return True
        except Exception as e:
            print(f"⚠ Could not create mods table via execute_sql client: {e}")
            return False

    # ------------------------------------------------------------------
    # Synthesis (long-running transform with TTL cache)
    # ------------------------------------------------------------------

    def get_synthesis_table_name(self) -> str:
        """Return the fully-qualified name for the synthesis result table.

        The table is shared across all users (no per-user suffix).
        """
        prefix = self.app_config.synthesis.result_table_prefix or "_synthesis_result"
        # If the data_table has a schema prefix, reuse it
        data_table = self.app_config.database.data_table
        if "." in data_table:
            schema = data_table.split(".", 1)[0]
            return f"{schema}.{prefix}"
        return prefix

    def _get_synthesis_age_minutes(self) -> Optional[float]:
        """Return age of the cached synthesis table in minutes, or None if missing.

        The creation timestamp is stored as a ``COMMENT ON TABLE``.
        Uses a cached epoch to avoid repeating the DB query on every call.
        """
        import time as _time

        # If we have a cached creation epoch, compute age from it directly
        if self._synthesis_age_cache_time > 0:
            return (_time.time() - self._synthesis_age_cache_time) / 60.0

        result_table = self.get_synthesis_table_name()
        result_table_sql = SqlTableName(result_table)
        use_execute_sql = self._uses_execute_sql_client()

        # Parse schema/table for obj_description lookup
        if "." in result_table:
            schema_part, table_part = result_table.split(".", 1)
        else:
            schema_part, table_part = "public", result_table

        comment_query = (
            f"SELECT obj_description(c.oid) "
            f"FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            f"WHERE n.nspname = {SqlLiteral(schema_part)} "
            f"AND c.relname = {SqlLiteral(table_part)}"
        )

        try:
            if use_execute_sql:
                response = self._execute_synthesis_sql(comment_query)
                rows = response.data
                if not rows:
                    return None
                comment = rows[0].get("obj_description")
            else:
                from sqlalchemy import text
                engine = self._get_engine()
                with engine.connect() as conn:
                    result = conn.execute(text(comment_query))
                    row = result.fetchone()
                    comment = row[0] if row else None

            if not comment or not comment.startswith("synthesis_created_at:"):
                return None
            created_epoch = float(comment.split(":", 1)[1])
            # Cache the creation epoch so future calls skip the DB query
            self._synthesis_age_cache_time = created_epoch
            return (_time.time() - created_epoch) / 60.0
        except Exception:
            return None

    def run_synthesis(self, force: bool = False) -> pd.DataFrame:
        """Return the synthesis result, creating the view if needed.

        In ``"query"`` mode, the SQL is executed directly and rows returned
        as a DataFrame — no view is created, no TTL caching.

        In ``"view"`` mode (default):
          1. Check if the synthesis view already exists.
          2. If exists and ``force=False`` → check TTL.
             a. If within TTL → read (cache hit).
             b. If expired → CREATE OR REPLACE VIEW + re-stamp.
          3. If exists and ``force=True`` → recreate unconditionally.
          4. If missing → CREATE OR REPLACE VIEW AS + stamp COMMENT.

        Returns ``(df, was_cached)`` tuple.
        """
        import time as _time

        synthesis_query = self.app_config.synthesis.query
        if not synthesis_query:
            raise ValueError("No synthesis query configured")

        # Direct query mode — no view creation
        if self.app_config.synthesis.mode == "query":
            if self.app_config.database.lazy_loading:
                self.activate_synthesis_query_fetcher(synthesis_query)
                return pd.DataFrame(columns=self.all_columns), False
            return self._run_synthesis_direct_query(synthesis_query)

        result_table = self.get_synthesis_table_name()
        result_table_sql = SqlTableName(result_table)
        ttl = self.app_config.synthesis.ttl_minutes
        use_execute_sql = self._uses_execute_sql_client()

        if self.check_synthesis_table_exists():
            age = self._get_synthesis_age_minutes()
            # Stamp comment if missing (pre-existing table)
            if age is None:
                self._stamp_synthesis_comment(result_table_sql, _time.time())
                age = 0.0

            needs_refresh = force or (ttl > 0 and age > ttl)

            if not needs_refresh:
                print(f"[Synthesis] Cache hit — matview exists ({age:.0f} min old)")
                return self._read_synthesis_table(result_table), True

            # Recreate the view
            reason = "forced" if force else f"expired ({age:.0f} min > {ttl} min TTL)"
            start = _time.time()
            print(f"[Synthesis] Recreating view ({reason}) → {result_table_sql} ...")
            self._refresh_synthesis(result_table_sql, use_execute_sql, synthesis_query)
            self._stamp_synthesis_comment(result_table_sql, _time.time())
            self._synthesis_exists_cache = True
            self._synthesis_age_cache_time = _time.time()
            elapsed = _time.time() - start
            print(f"[Synthesis] View recreated in {elapsed:.1f}s")
            return self._read_synthesis_table(result_table), False

        # View doesn't exist — create it
        schema_sql = None
        if "." in result_table:
            schema = result_table.split(".", 1)[0]
            schema_sql = str(SqlIdentifier(schema))

        start = _time.time()
        print(f"[Synthesis] View missing — creating → {result_table_sql} ...")

        if use_execute_sql:
            self._run_synthesis_datum(result_table_sql, schema_sql, synthesis_query)
        else:
            self._run_synthesis_direct(result_table_sql, schema_sql, synthesis_query)

        self._stamp_synthesis_comment(result_table_sql, _time.time())
        self._synthesis_exists_cache = True
        self._synthesis_age_cache_time = _time.time()

        elapsed = _time.time() - start
        print(f"[Synthesis] View created in {elapsed:.1f}s")

        return self._read_synthesis_table(result_table), False

    def _stamp_synthesis_comment(self, result_table_sql, epoch: float):
        """Store creation timestamp as COMMENT ON VIEW for TTL checking."""
        # Update in-memory cache immediately
        self._synthesis_age_cache_time = epoch
        comment = f"synthesis_created_at:{epoch}"
        stmt = f"COMMENT ON VIEW {result_table_sql} IS {SqlLiteral(comment)}"
        try:
            if self._uses_execute_sql_client():
                self._execute_synthesis_sql(stmt)
            else:
                from sqlalchemy import text
                engine = self._get_engine()
                with engine.connect() as conn:
                    conn.execute(text(stmt))
                    conn.commit()
        except Exception as e:
            print(f"[Synthesis] Warning: could not stamp comment: {e}")

    def _run_synthesis_direct(self, result_table_sql, schema_sql, synthesis_query):
        """Create the synthesis view via direct SQLAlchemy."""
        from sqlalchemy import text

        engine = self._get_engine()
        if engine is None:
            raise RuntimeError("No database engine available")

        with engine.connect() as conn:
            if schema_sql:
                # Extract raw schema name for the verified cache
                schema_name = str(result_table_sql).split('"')[1] if '.' in str(result_table_sql) else None
                if schema_name and schema_name not in self._schemas_verified:
                    conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema_sql}"))
                    self._schemas_verified.add(schema_name)
            conn.execute(text(f"CREATE OR REPLACE VIEW {result_table_sql} AS ({synthesis_query})"))
            conn.commit()

    def _run_synthesis_datum(self, result_table_sql, schema_sql, synthesis_query):
        """Create the synthesis view via Datum-compatible execute_sql client."""

        if schema_sql:
            # Only issue CREATE SCHEMA once per schema per process
            schema_name = result_table_sql._raw.split('.', 1)[0] if '.' in str(result_table_sql) else None
            if schema_name and schema_name not in self._schemas_verified:
                try:
                    self._execute_synthesis_sql(f"CREATE SCHEMA IF NOT EXISTS {schema_sql}")
                except Exception:
                    pass
                self._schemas_verified.add(schema_name)

        self._execute_synthesis_sql(f"CREATE OR REPLACE VIEW {result_table_sql} AS ({synthesis_query})")

    def _refresh_synthesis(self, result_table_sql, use_execute_sql: bool, synthesis_query: str):
        """Recreate the synthesis view (CREATE OR REPLACE VIEW) with the latest query."""
        stmt = f"CREATE OR REPLACE VIEW {result_table_sql} AS ({synthesis_query})"
        if use_execute_sql:
            self._execute_synthesis_sql(stmt)
        else:
            from sqlalchemy import text
            engine = self._get_engine()
            with engine.connect() as conn:
                conn.execute(text(stmt))
                conn.commit()

    def _read_synthesis_table(self, result_table: str) -> pd.DataFrame:
        """Read the full synthesis result table into a DataFrame."""
        result_table_sql = SqlTableName(result_table)
        query = f"SELECT * FROM {result_table_sql}"

        if self._uses_execute_sql_client():
            response = self._execute_synthesis_sql(query)
            return pd.DataFrame(response.data)
        else:
            from sqlalchemy import text
            engine = self._get_engine()
            with engine.connect() as conn:
                result = conn.execute(text(query))
                rows = result.fetchall()
                columns = list(result.keys())
            return pd.DataFrame(rows, columns=columns)

    def _run_synthesis_direct_query(self, synthesis_query: str):
        """Execute synthesis SQL directly and return rows as DataFrame.

        No view is created — data is fetched on each run and held in memory.
        Sorting/filtering happens on the fly in the application layer.

        Returns ``(df, was_cached=False)`` tuple.
        """
        import time as _time

        use_execute_sql = self._uses_execute_sql_client()
        start = _time.time()
        print(f"[Synthesis] Direct query mode — executing SQL ...")

        if use_execute_sql:
            response = self._execute_synthesis_sql(synthesis_query)
            df = pd.DataFrame(response.data)
        else:
            from sqlalchemy import text
            engine = self._get_engine()
            with engine.connect() as conn:
                result = conn.execute(text(synthesis_query))
                rows = result.fetchall()
                columns = list(result.keys())
            df = pd.DataFrame(rows, columns=columns)

        elapsed = _time.time() - start
        print(f"[Synthesis] Direct query returned {len(df):,} rows in {elapsed:.1f}s")
        return df, False

    def check_synthesis_table_exists(self) -> bool:
        """Return True if the synthesis result table exists (regardless of TTL).

        Result is cached after the first successful check.  Invalidated
        when ``run_synthesis()`` creates the table.
        """
        if self._synthesis_exists_cache is not None:
            return self._synthesis_exists_cache
        result_table = self.get_synthesis_table_name()
        result_table_sql = SqlTableName(result_table)
        try:
            if self._uses_execute_sql_client():
                self._execute_synthesis_sql(f"SELECT 1 FROM {result_table_sql} LIMIT 1")
                self._synthesis_exists_cache = True
                return True
            else:
                from sqlalchemy import text
                engine = self._get_engine()
                with engine.connect() as conn:
                    conn.execute(text(f"SELECT 1 FROM {result_table_sql} LIMIT 1"))
                self._synthesis_exists_cache = True
                return True
        except Exception:
            self._synthesis_exists_cache = False
            return False

    def _load_modifications_from_datum(self, pk_json_values: list = None) -> List[Dict]:
        """Load modifications via Datum-compatible execute_sql client."""
        try:
            # Ensure modifications table exists first
            self._ensure_mods_table_exists()
            mods_table = self.app_config.database.mods_table
            mods_table_sql = _format_table_name(mods_table)
            
            pk_array_sql = build_pk_array(pk_json_values) if pk_json_values else None
            query = _modifications_log_query(mods_table_sql, pk_array_sql=pk_array_sql)
            
            scope = f" for {len(pk_json_values)} PKs" if pk_json_values else ""
            print(f"[Datum DEBUG] Loading modifications{scope} from {mods_table_sql}, database={self.app_config.database.datum_database}, schema={self.app_config.database.datum_schema}")
            
            with tracker.track_sql("load_modifications.datum", query):
                response = self._execute_client_sql(query)
            
            print(f"[Datum DEBUG] Loaded {len(response.data)} modification log rows")
            # Show latest few IDs to verify new entries
            if response.data:
                latest_ids = [r.get("id") for r in response.data if r.get("id") is not None][-5:]
                print(f"[Datum DEBUG] Latest 5 modification IDs: {latest_ids}")
            
            result = _modification_rows_to_log(response.data)
            print(f"[Datum DEBUG] Parsed {len(result)} modifications")
            return result
        except Exception as e:
            print(f"✗ Error loading modifications from execute_sql client: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _load_modifications_from_db(self, pk_json_values: list = None) -> List[Dict]:
        """Load modifications from database."""
        try:
            # Ensure modifications table exists first
            self._ensure_mods_table_exists()
            
            from sqlalchemy import text
            
            mods_table = self.app_config.database.mods_table
            
            engine = self._get_engine()
            if engine is None:
                return []
            
            table_sql = _format_table_name(mods_table)
            pk_array_sql = build_pk_array(pk_json_values) if pk_json_values else None
            load_mods_sql = _modifications_log_query(table_sql, pk_array_sql=pk_array_sql)
            with engine.connect() as conn:
                with tracker.track_sql("load_modifications", load_mods_sql):
                    result = conn.execute(text(load_mods_sql))
                    rows = result.mappings().all()
            
            return _modification_rows_to_log(rows)
        except Exception as e:
            print(f"✗ Error loading modifications: {e}")
            return []
    
    def _aggregate_approval_rejection_entries(self, log: list) -> list:
        """Group approval/rejection entries by timestamp."""
        from collections import defaultdict
        
        result = []
        approval_groups = defaultdict(list)
        rejection_groups = defaultdict(list)
        
        for entry in log:
            mod_type = entry.get("type")
            if mod_type == "approval":
                ts = entry.get("timestamp", "")[:19]
                row_pk = entry.get("details", {}).get("row_pk", {})
                if row_pk:
                    approval_groups[ts].append({"entry": entry, "row_pk": row_pk})
            elif mod_type == "rejection":
                ts = entry.get("timestamp", "")[:19]
                row_pk = entry.get("details", {}).get("row_pk", {})
                if row_pk:
                    rejection_groups[ts].append({"entry": entry, "row_pk": row_pk})
            else:
                result.append(entry)
        
        for ts, items in approval_groups.items():
            result.append({
                "timestamp": ts,
                "type": "approval",
                "details": {
                    "action": "approved",
                    "approved_rows": [item["row_pk"] for item in items],
                    "approved_row_count": len(items),
                }
            })
        
        for ts, items in rejection_groups.items():
            result.append({
                "timestamp": ts,
                "type": "rejection",
                "details": {
                    "action": "rejected",
                    "rejected_rows": [item["row_pk"] for item in items],
                    "rejected_row_count": len(items),
                }
            })
        
        result.sort(key=lambda x: x.get("timestamp", ""))
        return result
    
    def reload_data(self) -> pd.DataFrame:
        """Reload data from database (bypasses all caches)."""
        self.invalidate_data_cache()
        self.df = self._load_data()
        self.all_columns = list(self.df.columns)
        return self.df
    
    def save_modification_to_db(self, row_pk: dict, column: str, old_value, new_value, mod_type: str = "field_modification"):
        """Save a single modification to the database using this config instance."""
        db_mode = self.app_config.database.mode
        print(f"[Datum DEBUG] save_modification_to_db called: mode={db_mode}, pk={row_pk}, col={column}")
        
        if self._uses_execute_sql_client():
            return self._save_modification_to_datum(row_pk, column, old_value, new_value, mod_type)
        
        # Ensure modifications table exists first
        self._ensure_mods_table_exists()
        
        print(f"[Datum DEBUG] Using direct SQLAlchemy mode (not datum)")
        try:
            from sqlalchemy import text
            
            mods_table = self.app_config.database.mods_table
            
            engine = self._get_engine()
            if engine is None:
                return None
            
            table_sql = _format_table_name(mods_table)
            
            insert_sql = f'''
                        INSERT INTO {table_sql} 
                            (row_pk, column_name, old_value, new_value, mod_type, created_by)
                        VALUES 
                            (:row_pk, :column_name, :old_value, :new_value, :mod_type, :created_by)
                        RETURNING id
                    '''
            with engine.connect() as conn:
                with tracker.track_sql("save_modification", insert_sql):
                    result = conn.execute(
                        text(insert_sql),
                        {
                            "row_pk": json.dumps(row_pk),
                            "column_name": column,
                            "old_value": str(old_value) if old_value is not None else None,
                            "new_value": str(new_value) if new_value is not None else None,
                            "mod_type": mod_type,
                            "created_by": self.username
                        }
                    )
                    mod_id = result.scalar()
                conn.commit()
                
                # Invalidate cache after successful insert
                self.invalidate_mods_cache()
                
                return mod_id
        except Exception as e:
            print(f"✗ Error saving modification to DB: {e}")
            return None
    
    def _save_modification_to_datum(self, row_pk: dict, column: str, old_value, new_value, mod_type: str):
        """Save modification via Datum-compatible execute_sql client."""
        try:
            # Ensure modifications table exists first
            self._ensure_mods_table_exists()
            mods_table = self.app_config.database.mods_table
            mods_table_sql = SqlTableName(mods_table)
            
            old_val_str = str(old_value) if old_value is not None else None
            new_val_str = str(new_value) if new_value is not None else None
            
            # Convert numpy/pandas types to native Python types for JSON serialization
            serializable_pk = {}
            for k, v in row_pk.items():
                if hasattr(v, 'item'):  # numpy scalar
                    serializable_pk[k] = v.item()
                elif pd.isna(v):
                    serializable_pk[k] = None
                else:
                    serializable_pk[k] = v
            
            # Type-safe escaping via SqlLiteral — replaces manual .replace() chains
            row_pk_json_lit = SqlLiteral(json.dumps(serializable_pk, sort_keys=True))
            column_lit = SqlLiteral(column)
            old_val_lit = SqlLiteral(old_val_str)
            new_val_lit = SqlLiteral(new_val_str)
            
            # Whitelist mod_type values
            allowed_mod_types = {"field_modification", "status_change", "approval", "rejection"}
            safe_mod_type = mod_type if mod_type in allowed_mod_types else "field_modification"
            
            # INSERT with explicit BEGIN/COMMIT for Datum proxy transaction safety
            sql = f'''
                BEGIN;
                INSERT INTO {mods_table_sql} 
                    (row_pk, column_name, old_value, new_value, mod_type)
                VALUES 
                    ({row_pk_json_lit}::jsonb, {column_lit}, 
                     {old_val_lit}, 
                     {new_val_lit}, 
                     {SqlLiteral(safe_mod_type)})
                RETURNING id;
                COMMIT;
            '''
            
            print(f"[Datum DEBUG] Saving modification: pk={row_pk_json_lit}, col={column}, old={old_val_str[:50] if old_val_str else None}..., new={new_val_str[:50] if new_val_str else None}...")
            print(f"[Datum DEBUG] INSERT SQL table: {mods_table_sql}, database: {self.app_config.database.datum_database}, schema: {self.app_config.database.datum_schema}")
            print(f"[Datum DEBUG] Full SQL: {sql}")
            
            with tracker.track_sql("save_modification.datum", sql):
                response = self._execute_client_sql(sql)
            
            if response.data:
                mod_id = response.data[0].get("id")
                
                # Invalidate cache after successful insert
                self.invalidate_mods_cache()
                
                return mod_id
            print(f"[Datum] ⚠ No id returned from INSERT")
            return None
        except Exception as e:
            print(f"✗ Error saving modification via execute_sql client: {e}")
            import traceback
            traceback.print_exc()
            return None

    def mark_modification_undone_in_db(self, mod_id: int):
        """Mark a modification as undone in the database."""
        if self._uses_execute_sql_client():
            return self._mark_modification_undone_datum(mod_id)
        
        try:
            from sqlalchemy import text
            
            mods_table = self.app_config.database.mods_table
            
            engine = self._get_engine()
            if engine is None:
                return False
            
            table_sql = _format_table_name(mods_table)
            
            with engine.connect() as conn:
                conn.execute(
                    text(f'UPDATE {table_sql} SET undone = TRUE WHERE id = :mod_id'),
                    {"mod_id": mod_id}
                )
                conn.commit()
                
                # Invalidate cache after successful update
                self.invalidate_mods_cache()
                
                return True
        except Exception as e:
            print(f"✗ Error marking modification undone: {e}")
            return False
    
    def _mark_modification_undone_datum(self, mod_id: int):
        """Mark modification undone via Datum-compatible execute_sql client."""
        try:
            # Validate mod_id is an integer to prevent SQL injection
            mod_id = int(mod_id)
            mods_table = self.app_config.database.mods_table
            mods_table_sql = _format_table_name(mods_table)
            
            self._execute_client_sql(f'BEGIN; UPDATE {mods_table_sql} SET undone = TRUE WHERE id = {mod_id}; COMMIT;')
            
            # Invalidate cache after successful update
            self.invalidate_mods_cache()
            
            return True
        except Exception as e:
            print(f"✗ Error marking modification undone via execute_sql client: {e}")
            return False

    def cleanup_corrupted_modifications(self):
        """
        Delete modifications with empty row_pk from database.
        These records are corrupted and will cause all rows to be updated.
        """
        if self._uses_execute_sql_client():
            return self._cleanup_corrupted_modifications_datum()
        return 0
    
    def _cleanup_corrupted_modifications_datum(self):
        """Clean up corrupted modifications via Datum-compatible execute_sql client."""
        try:
            mods_table = self.app_config.database.mods_table
            mods_table_sql = _format_table_name(mods_table)
            
            # First count how many will be deleted
            count_sql = f"""
                SELECT COUNT(*) as cnt FROM {mods_table_sql}
                WHERE mod_type = 'field_modification'
                  AND (row_pk IS NULL OR row_pk = '{{}}'::jsonb)
            """
            count_response = self._execute_client_sql(count_sql)
            count = count_response.data[0].get("cnt", 0) if count_response.data else 0
            
            if count > 0:
                # Delete corrupted records with explicit BEGIN/COMMIT
                delete_sql = f"""
                    BEGIN;
                    DELETE FROM {mods_table_sql}
                    WHERE mod_type = 'field_modification'
                      AND (row_pk IS NULL OR row_pk = '{{}}'::jsonb);
                    COMMIT;
                """
                self._execute_client_sql(delete_sql)
                print(f"✓ Cleaned up {count} corrupted field_modification records with empty row_pk")
            
            return count
        except Exception as e:
            print(f"✗ Error cleaning up corrupted modifications via execute_sql client: {e}")
            return 0

    def update_data_in_db(self, row_pk: dict, column: str, new_value):
        """Update the actual data in the database."""
        if self._uses_execute_sql_client():
            return self._update_data_in_datum(row_pk, column, new_value)
        
        try:
            from sqlalchemy import text
            
            data_table = self.app_config.database.data_table
            pk_columns = self.app_config.table.primary_key
            
            engine = self._get_engine()
            if engine is None:
                return False
            
            # Build WHERE clause from PK
            where_parts = []
            params = {"new_value": new_value}
            for i, pk_col in enumerate(pk_columns):
                if pk_col in row_pk:
                    pk_col_sql = SqlIdentifier(pk_col)
                    where_parts.append(f'{pk_col_sql} = :pk_{i}')
                    params[f"pk_{i}"] = row_pk[pk_col]
            
            if not where_parts:
                return False
            
            where_clause = " AND ".join(where_parts)
            table_sql = _format_table_name(data_table)
            column_sql = SqlIdentifier(column)
            
            with engine.connect() as conn:
                conn.execute(
                    text(f'UPDATE {table_sql} SET {column_sql} = :new_value WHERE {where_clause}'),
                    params
                )
                conn.commit()
                return True
        except Exception as e:
            print(f"✗ Error updating data in DB: {e}")
            return False
    
    def _update_data_in_datum(self, row_pk: dict, column: str, new_value):
        """Update data via Datum-compatible execute_sql client."""
        try:
            data_table = self.app_config.database.data_table
            pk_columns = self.app_config.table.primary_key
            
            # Build WHERE clause from PK — type-safe escaping
            where_parts = []
            for pk_col in pk_columns:
                if pk_col in row_pk:
                    col_ident = SqlIdentifier(pk_col)
                    pk_val_lit = SqlLiteral(row_pk[pk_col])
                    where_parts.append(f'{col_ident} = {pk_val_lit}')
            
            if not where_parts:
                return False
            
            where_clause = " AND ".join(where_parts)
            col_ident = SqlIdentifier(column)
            new_val_lit = SqlLiteral(new_value)
            data_table_sql = SqlTableName(data_table)
            
            self._execute_client_sql(f'BEGIN; UPDATE {data_table_sql} SET {col_ident} = {new_val_lit} WHERE {where_clause}; COMMIT;')
            return True
        except Exception as e:
            print(f"✗ Error updating data via execute_sql client: {e}")
            return False

    def save_cell_edit_to_db(self, row_pk: dict, column: str, old_value, new_value, status_col: str = None, status_value=None):
        """Persist one cell edit and its optional status sync in a single DB transaction."""
        if self._uses_execute_sql_client():
            return self._save_cell_edit_to_datum(row_pk, column, old_value, new_value, status_col, status_value)
        return False

    def _save_cell_edit_to_datum(self, row_pk: dict, column: str, old_value, new_value, status_col: str = None, status_value=None):
        """Persist a cell edit via Datum-compatible execute_sql client."""
        try:
            self._ensure_mods_table_exists()
            data_table_sql = SqlTableName(self.app_config.database.data_table)
            mods_table_sql = SqlTableName(self.app_config.database.mods_table)
            pk_columns = self.app_config.table.primary_key

            where_parts = []
            for pk_col in pk_columns:
                if pk_col in row_pk:
                    where_parts.append(f'{SqlIdentifier(pk_col)} = {SqlLiteral(row_pk[pk_col])}')
            if not where_parts:
                return False
            where_sql = " AND ".join(where_parts)

            serializable_pk = {}
            for key, value in row_pk.items():
                if hasattr(value, 'item'):
                    serializable_pk[key] = value.item()
                elif pd.isna(value):
                    serializable_pk[key] = None
                else:
                    serializable_pk[key] = value

            pk_lit = SqlLiteral(json.dumps(serializable_pk, sort_keys=True))
            column_lit = SqlLiteral(column)
            old_value_lit = SqlLiteral(str(old_value) if old_value is not None else None)
            new_value_lit = SqlLiteral(str(new_value) if new_value is not None else None)

            stmts = [
                "BEGIN;",
                f"UPDATE {data_table_sql} SET {SqlIdentifier(column)} = {SqlLiteral(new_value)} WHERE {where_sql};",
                f"INSERT INTO {mods_table_sql} (row_pk, column_name, old_value, new_value, mod_type)"
                f" VALUES ({pk_lit}::jsonb, {column_lit}, {old_value_lit}, {new_value_lit}, {SqlLiteral('field_modification')});",
            ]

            if status_col and status_value is not None and status_col != column:
                status_col_lit = SqlLiteral(status_col)
                status_value_lit = SqlLiteral(str(status_value))
                stmts.extend([
                    f"UPDATE {data_table_sql} SET {SqlIdentifier(status_col)} = {SqlLiteral(status_value)} WHERE {where_sql};",
                    f"INSERT INTO {mods_table_sql} (row_pk, column_name, old_value, new_value, mod_type)"
                    f" VALUES ({pk_lit}::jsonb, {status_col_lit}, NULL, {status_value_lit}, {SqlLiteral('field_modification')});",
                ])

            stmts.append("COMMIT;")
            sql = "\n".join(stmts)

            with tracker.track_sql("cell_edit.datum", sql):
                self._execute_client_sql(sql)

            self.invalidate_mods_cache()
            return True
        except Exception as e:
            print(f"✗ Error saving cell edit via execute_sql client: {e}")
            import traceback
            traceback.print_exc()
            return False

    def batch_save_status(self, entries: list):
        """Batch-save approval/rejection status changes in a single transaction.

        Each entry is a dict with keys:
            row_pk: dict of PK column → value
            status_value: the value to write to the status column
            mod_type: "approval" or "rejection"
            assignments: optional list of (column, value) tuples for approval_assignment

        This replaces N individual save_modification_to_db + update_data_in_db calls
        with a single multi-statement transaction.
        """
        if not entries:
            return

        db_mode = self.app_config.database.mode
        if self._uses_execute_sql_client():
            return self._batch_save_status_datum(entries)
        return self._batch_save_status_sqlalchemy(entries)

    def _batch_save_status_sqlalchemy(self, entries: list):
        """Execute batch status save via direct SQLAlchemy in a single transaction."""
        from sqlalchemy import text

        self._ensure_mods_table_exists()

        engine = self._get_engine()
        if engine is None:
            return

        mods_table = self.app_config.database.mods_table
        data_table = self.app_config.database.data_table
        pk_columns = self.app_config.table.primary_key
        status_col = getattr(self.app_config.database, "status_column", None)
        mods_table_sql = _format_table_name(mods_table)
        data_table_sql = _format_table_name(data_table)

        with engine.connect() as conn:
            for entry in entries:
                row_pk = entry["row_pk"]
                status_value = entry["status_value"]
                mod_type = entry["mod_type"]
                assignments = entry.get("assignments", [])

                # INSERT mod record for _status
                conn.execute(
                    text(f'''INSERT INTO {mods_table_sql}
                        (row_pk, column_name, old_value, new_value, mod_type, created_by)
                        VALUES (:row_pk, :col, NULL, :new_val, :mod_type, :user)'''),
                    {"row_pk": json.dumps(row_pk), "col": "_status",
                     "new_val": status_value, "mod_type": mod_type, "user": self.username}
                )

                # UPDATE data table status column
                if status_col:
                    where_parts = []
                    params = {"new_value": status_value}
                    for i, pk_col in enumerate(pk_columns):
                        if pk_col in row_pk:
                            where_parts.append(f'{SqlIdentifier(pk_col)} = :pk_{i}')
                            params[f"pk_{i}"] = row_pk[pk_col]
                    if where_parts:
                        col_sql = SqlIdentifier(status_col)
                        where_sql = " AND ".join(where_parts)
                        conn.execute(
                            text(f'UPDATE {data_table_sql} SET {col_sql} = :new_value WHERE {where_sql}'),
                            params
                        )
                    # Also insert a field_modification record for status column
                    conn.execute(
                        text(f'''INSERT INTO {mods_table_sql}
                            (row_pk, column_name, old_value, new_value, mod_type, created_by)
                            VALUES (:row_pk, :col, NULL, :new_val, :mod_type, :user)'''),
                        {"row_pk": json.dumps(row_pk), "col": status_col,
                         "new_val": status_value, "mod_type": "field_modification", "user": self.username}
                    )

                # Approval assignments (source → target column copies)
                for tgt_col, tgt_val in assignments:
                    where_parts = []
                    params = {"new_value": tgt_val}
                    for i, pk_col in enumerate(pk_columns):
                        if pk_col in row_pk:
                            where_parts.append(f'{SqlIdentifier(pk_col)} = :pk_{i}')
                            params[f"pk_{i}"] = row_pk[pk_col]
                    if where_parts:
                        col_sql = SqlIdentifier(tgt_col)
                        where_sql = " AND ".join(where_parts)
                        conn.execute(
                            text(f'UPDATE {data_table_sql} SET {col_sql} = :new_value WHERE {where_sql}'),
                            params
                        )
                    conn.execute(
                        text(f'''INSERT INTO {mods_table_sql}
                            (row_pk, column_name, old_value, new_value, mod_type, created_by)
                            VALUES (:row_pk, :col, NULL, :new_val, :mod_type, :user)'''),
                        {"row_pk": json.dumps(row_pk), "col": tgt_col,
                         "new_val": tgt_val, "mod_type": "field_modification", "user": self.username}
                    )

            conn.commit()

        self.invalidate_mods_cache()
        print(f"[Batch] Saved {len(entries)} status changes in single transaction")

    def _batch_save_status_datum(self, entries: list):
        """Execute batch status save via Datum-compatible execute_sql client."""
        try:
            mods_table = self.app_config.database.mods_table
            data_table = self.app_config.database.data_table
            pk_columns = self.app_config.table.primary_key
            status_col = getattr(self.app_config.database, "status_column", None)
            mods_table_sql = SqlTableName(mods_table)
            data_table_sql = SqlTableName(data_table)

            stmts = ["BEGIN;"]

            for entry in entries:
                row_pk = entry["row_pk"]
                status_value = entry["status_value"]
                mod_type = entry["mod_type"]
                assignments = entry.get("assignments", [])

                # Serialize PK for jsonb
                serializable_pk = {}
                for k, v in row_pk.items():
                    if hasattr(v, 'item'):
                        serializable_pk[k] = v.item()
                    elif pd.isna(v):
                        serializable_pk[k] = None
                    else:
                        serializable_pk[k] = v

                pk_lit = SqlLiteral(json.dumps(serializable_pk, sort_keys=True))
                status_lit = SqlLiteral(status_value)
                allowed_mod_types = {"approval", "rejection", "field_modification"}
                safe_mod_type = mod_type if mod_type in allowed_mod_types else "field_modification"

                # INSERT mod record
                stmts.append(
                    f"INSERT INTO {mods_table_sql} (row_pk, column_name, old_value, new_value, mod_type)"
                    f" VALUES ({pk_lit}::jsonb, {SqlLiteral('_status')}, NULL, {status_lit}, {SqlLiteral(safe_mod_type)});"
                )

                # UPDATE data table status column
                if status_col:
                    where_parts = []
                    for pk_col in pk_columns:
                        if pk_col in row_pk:
                            where_parts.append(f'{SqlIdentifier(pk_col)} = {SqlLiteral(row_pk[pk_col])}')
                    if where_parts:
                        where_sql = " AND ".join(where_parts)
                        stmts.append(
                            f"UPDATE {data_table_sql} SET {SqlIdentifier(status_col)} = {status_lit} WHERE {where_sql};"
                        )
                    stmts.append(
                        f"INSERT INTO {mods_table_sql} (row_pk, column_name, old_value, new_value, mod_type)"
                        f" VALUES ({pk_lit}::jsonb, {SqlLiteral(status_col)}, NULL, {status_lit}, {SqlLiteral('field_modification')});"
                    )

                # Approval assignments
                for tgt_col, tgt_val in assignments:
                    tgt_val_lit = SqlLiteral(tgt_val)
                    where_parts = []
                    for pk_col in pk_columns:
                        if pk_col in row_pk:
                            where_parts.append(f'{SqlIdentifier(pk_col)} = {SqlLiteral(row_pk[pk_col])}')
                    if where_parts:
                        where_sql = " AND ".join(where_parts)
                        stmts.append(
                            f"UPDATE {data_table_sql} SET {SqlIdentifier(tgt_col)} = {tgt_val_lit} WHERE {where_sql};"
                        )
                    stmts.append(
                        f"INSERT INTO {mods_table_sql} (row_pk, column_name, old_value, new_value, mod_type)"
                        f" VALUES ({pk_lit}::jsonb, {SqlLiteral(tgt_col)}, NULL, {tgt_val_lit}, {SqlLiteral('field_modification')});"
                    )

            stmts.append("COMMIT;")
            sql = "\n".join(stmts)

            with tracker.track_sql("batch_save_status.datum", sql):
                self._execute_client_sql(sql)

            self.invalidate_mods_cache()
            print(f"[Batch] Saved {len(entries)} status changes via execute_sql client in single transaction")
        except Exception as e:
            print(f"✗ Error in batch status save via execute_sql client: {e}")
            import traceback
            traceback.print_exc()

    def _ensure_state_table_exists(self) -> bool:
        """Create the UI state table if it doesn't exist. Only runs once per instance."""
        if not self.app_config.state.persist_state:
            return True
        if self.app_config.read_only:
            return False
        # Skip if already checked this session (success or failure)
        if self._state_table_checked:
            return self._state_table_available
        
        if self._uses_execute_sql_client():
            return self._ensure_state_table_exists_datum()
        
        try:
            from sqlalchemy import text
            
            state_table = self.app_config.database.state_table
            
            # Parse schema.table format
            if '.' in state_table:
                schema, table_name = state_table.split('.', 1)
                schema_sql = str(SqlIdentifier(schema))
                table_sql = SqlTableName(state_table)
            else:
                schema = None
                schema_sql = None
                table_sql = SqlTableName(state_table)
            
            engine = self._get_engine()
            if engine is None:
                return False
            
            with engine.connect() as conn:
                # Create schema if needed (once per schema per process)
                if schema_sql and schema not in self._schemas_verified:
                    conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS {schema_sql}'))
                    self._schemas_verified.add(schema)
                
                # Create table if not exists
                conn.execute(text(f'''
                    CREATE TABLE IF NOT EXISTS {table_sql} (
                        id SERIAL PRIMARY KEY,
                        user_id VARCHAR(255),
                        session_id VARCHAR(255),
                        filters JSONB,
                        sort_column VARCHAR(255),
                        sort_ascending BOOLEAN DEFAULT TRUE,
                        current_page INT DEFAULT 1,
                        rows_per_page INT DEFAULT 25,
                        column_preset VARCHAR(255),
                        updated_at TIMESTAMP DEFAULT NOW(),
                        UNIQUE(user_id, session_id)
                    )
                '''))
                conn.commit()
            self._state_table_checked = True
            self._state_table_available = True
            return True
        except Exception as e:
            print(f"⚠ Could not create state table: {e}")
            self._state_table_checked = True
            self._state_table_available = False
            return False

    def _ensure_state_table_exists_datum(self) -> bool:
        """Create UI state table via Datum-compatible execute_sql client."""
        try:
            state_table = self.app_config.database.state_table
            state_table_sql = SqlTableName(state_table)
            
            # Parse schema for CREATE SCHEMA
            schema_sql = None
            schema_name = None
            if '.' in state_table:
                schema_name = state_table.split('.', 1)[0]
                schema_sql = str(SqlIdentifier(schema_name))
            
            # Create schema if needed (once per schema per process)
            if schema_sql and schema_name not in self._schemas_verified:
                try:
                    self._execute_client_sql(f'CREATE SCHEMA IF NOT EXISTS {schema_sql}')
                except Exception:
                    pass  # Schema may already exist
                self._schemas_verified.add(schema_name)
            
            # Create table if not exists - DDL auto-commits
            self._execute_client_sql(
                f'''
                    CREATE TABLE IF NOT EXISTS {state_table_sql} (
                        id SERIAL PRIMARY KEY,
                        user_id VARCHAR(255),
                        session_id VARCHAR(255),
                        filters JSONB,
                        sort_column VARCHAR(255),
                        sort_ascending BOOLEAN DEFAULT TRUE,
                        current_page INT DEFAULT 1,
                        rows_per_page INT DEFAULT 25,
                        column_preset VARCHAR(255),
                        updated_at TIMESTAMP DEFAULT NOW(),
                        UNIQUE(user_id, session_id)
                    )
                '''
            )
            
            self._state_table_checked = True
            self._state_table_available = True
            return True
        except Exception as e:
            print(f"⚠ Could not create state table via execute_sql client: {e}")
            self._state_table_checked = True
            self._state_table_available = False
            return False

    def save_ui_state(
        self,
        sort_column: str = None,
        sort_ascending: bool = True,
        current_page: int = 1,
        rows_per_page: int = 25,
        filters: dict = None,
        column_preset: str = None,
        **kwargs  # Ignore extra args for compatibility
    ) -> bool:
        """Save UI state to database for this config instance."""
        if not self.app_config.state.persist_state:
            return False
        if self.app_config.read_only:
            return False
        if self._uses_execute_sql_client():
            return self._save_ui_state_datum(
                sort_column, sort_ascending, current_page, 
                rows_per_page, filters, column_preset
            )
        
        # Ensure state table exists first
        if not self._ensure_state_table_exists():
            return False
        
        try:
            from sqlalchemy import text
            
            state_table = self.app_config.database.state_table
            state_table_sql = _format_table_name(state_table)
            
            engine = self._get_engine()
            if engine is None:
                return False
            
            # Serialize filters as JSON
            filters_json = json.dumps(filters) if filters else None
            
            with engine.connect() as conn:
                # Use upsert pattern
                upsert_sql = f'''
                        INSERT INTO {state_table_sql} 
                            (user_id, session_id, sort_column, sort_ascending, 
                             current_page, rows_per_page, filters, column_preset, updated_at)
                        VALUES 
                            (:user_id, :session_id, :sort_column, :sort_ascending,
                             :current_page, :rows_per_page, :filters, :column_preset, NOW())
                        ON CONFLICT (user_id, session_id) 
                        DO UPDATE SET
                            sort_column = :sort_column,
                            sort_ascending = :sort_ascending,
                            current_page = :current_page,
                            rows_per_page = :rows_per_page,
                            filters = :filters,
                            column_preset = :column_preset,
                            updated_at = NOW()
                    '''
                with tracker.track_sql("save_ui_state", upsert_sql):
                    conn.execute(
                        text(upsert_sql),
                        {
                            "user_id": self.username,
                            "session_id": "default_session",
                            "sort_column": sort_column,
                            "sort_ascending": sort_ascending,
                            "current_page": current_page,
                            "rows_per_page": rows_per_page,
                            "filters": filters_json,
                            "column_preset": column_preset
                        }
                    )
                conn.commit()
                return True
        except Exception as e:
            print(f"⚠ Could not save UI state: {e}")
            return False

    def _save_ui_state_datum(
        self,
        sort_column: str,
        sort_ascending: bool,
        current_page: int,
        rows_per_page: int,
        filters: dict,
        column_preset: str
    ) -> bool:
        """Save UI state via Datum-compatible execute_sql client."""
        # Ensure state table exists first
        if not self._ensure_state_table_exists():
            return False
        
        try:
            state_table = self.app_config.database.state_table
            state_table_sql = SqlTableName(state_table)
            
            # Type-safe escaping via SqlLiteral
            filters_json_lit = SqlLiteral(json.dumps(filters)) if filters else SqlLiteral(None)
            sort_col_lit = SqlLiteral(sort_column)
            preset_lit = SqlLiteral(column_preset)
            user_lit = SqlLiteral(self.username)
            safe_page = int(current_page)
            safe_rows = int(rows_per_page)
            sort_asc_lit = SqlLiteral(bool(sort_ascending))
            
            sql = f'''
                BEGIN;
                INSERT INTO {state_table_sql} 
                    (user_id, session_id, sort_column, sort_ascending, 
                     current_page, rows_per_page, filters, column_preset, updated_at)
                VALUES 
                    ({user_lit}, 'default_session', {sort_col_lit}, {sort_asc_lit},
                     {safe_page}, {safe_rows}, {filters_json_lit}::jsonb, {preset_lit}, NOW())
                ON CONFLICT (user_id, session_id) 
                DO UPDATE SET
                    sort_column = {sort_col_lit},
                    sort_ascending = {sort_asc_lit},
                    current_page = {safe_page},
                    rows_per_page = {safe_rows},
                    filters = {filters_json_lit}::jsonb,
                    column_preset = {preset_lit},
                    updated_at = NOW();
                COMMIT;
            '''
            
            self._execute_client_sql(sql)
            return True
        except Exception as e:
            print(f"⚠ Could not save UI state via execute_sql client: {e}")
            return False

    def _apply_ui_state_policy(self, state: Dict, default_state: Dict) -> Dict:
        """Apply state persistence feature flags after loading saved UI state."""
        if not self.app_config.state.persist_page:
            state["current_page"] = default_state["current_page"]
            state["rows_per_page"] = default_state["rows_per_page"]
        return state
    
    def load_ui_state(self) -> Dict:
        """Load UI state from database for this config instance."""
        default_state = {
            "sort_column": self.app_config.table.default_sort_column,
            "sort_ascending": self.app_config.table.default_sort_ascending,
            "current_page": 1,
            "rows_per_page": self.app_config.table.default_rows_per_page,
            "filters": {},
            "column_preset": None
        }
        
        if not self.app_config.state.persist_state:
            return default_state
        
        if self.app_config.read_only:
            return default_state
        
        if self._uses_execute_sql_client():
            return self._load_ui_state_datum(default_state)
        
        # Ensure state table exists first
        if not self._ensure_state_table_exists():
            return default_state
        
        try:
            from sqlalchemy import text
            
            state_table = self.app_config.database.state_table
            state_table_sql = _format_table_name(state_table)
            
            engine = self._get_engine()
            if engine is None:
                return default_state
            
            with engine.connect() as conn:
                load_sql = f'''
                        SELECT sort_column, sort_ascending, current_page, 
                               rows_per_page, filters, column_preset
                        FROM {state_table_sql}
                        WHERE user_id = :user_id AND session_id = :session_id
                    '''
                with tracker.track_sql("load_ui_state", load_sql):
                    result = conn.execute(
                        text(load_sql),
                        {"user_id": self.username, "session_id": "default_session"}
                    )
                    row = result.fetchone()
            
            if row:
                filters = row[4]
                if isinstance(filters, str):
                    filters = json.loads(filters)
                elif filters is None:
                    filters = {}
                
                loaded_state = {
                    "sort_column": row[0] or default_state["sort_column"],
                    "sort_ascending": row[1] if row[1] is not None else default_state["sort_ascending"],
                    "current_page": row[2] or default_state["current_page"],
                    "rows_per_page": row[3] or default_state["rows_per_page"],
                    "filters": filters,
                    "column_preset": row[5]
                }
                return self._apply_ui_state_policy(loaded_state, default_state)
        except Exception as e:
            print(f"⚠ Could not load UI state: {e}")
        
        return default_state

    def _load_ui_state_datum(self, default_state: Dict) -> Dict:
        """Load UI state via Datum-compatible execute_sql client."""
        # Ensure state table exists first
        if not self._ensure_state_table_exists():
            return default_state
        
        try:
            state_table = self.app_config.database.state_table
            state_table_sql = SqlTableName(state_table)
            user_lit = SqlLiteral(self.username)
            
            response = self._execute_client_sql(
                f'''
                    SELECT sort_column, sort_ascending, current_page, 
                           rows_per_page, filters, column_preset
                    FROM {state_table_sql}
                    WHERE user_id = {user_lit} AND session_id = 'default_session'
                '''
            )
            
            if response.data and len(response.data) > 0:
                row = response.data[0]
                filters = row.get("filters", {})
                if isinstance(filters, str):
                    filters = json.loads(filters)
                elif filters is None:
                    filters = {}
                
                loaded_state = {
                    "sort_column": row.get("sort_column") or default_state["sort_column"],
                    "sort_ascending": row.get("sort_ascending") if row.get("sort_ascending") is not None else default_state["sort_ascending"],
                    "current_page": row.get("current_page") or default_state["current_page"],
                    "rows_per_page": row.get("rows_per_page") or default_state["rows_per_page"],
                    "filters": filters,
                    "column_preset": row.get("column_preset")
                }
                return self._apply_ui_state_policy(loaded_state, default_state)
        except Exception as e:
            print(f"⚠ Could not load UI state via execute_sql client: {e}")
        
        return default_state

    # =========================================================================
    # Preset Management (Datum-aware)
    # =========================================================================
    
    def _get_legacy_preset_table_name(self) -> str:
        """Generate the old per-user preset table name: {data_table_base}_{username}_column_presets"""
        data_table = self.app_config.database.data_table
        if '.' in data_table:
            base_name = data_table.split('.')[-1]
        else:
            base_name = data_table
        safe_username = "".join(c if c.isalnum() else "_" for c in self.username).lower()
        if '.' in data_table:
            schema = data_table.split('.')[0]
            return f"{schema}.{base_name}_{safe_username}_column_presets"
        return f"{base_name}_{safe_username}_column_presets"

    def _get_new_preset_table_name(self) -> str:
        """Generate the new shared preset table name: {data_table_base}_column_presets"""
        data_table = self.app_config.database.data_table
        if '.' in data_table:
            base_name = data_table.split('.')[-1]
        else:
            base_name = data_table
        if '.' in data_table:
            schema = data_table.split('.')[0]
            return f"{schema}.{base_name}_column_presets"
        return f"{base_name}_column_presets"

    def _get_preset_table_name(self) -> str:
        """Return the active preset table name (legacy per-user or new shared).
        
        On first call, checks if the old per-user table exists. If yes, uses it (legacy mode).
        Otherwise uses the new shared table with a username column.
        """
        if self._preset_legacy_mode is None:
            self._detect_preset_legacy_mode()
        if self._preset_legacy_mode:
            return self._get_legacy_preset_table_name()
        return self._get_new_preset_table_name()

    def _detect_preset_legacy_mode(self) -> None:
        """Detect whether the old per-user preset table exists."""
        if self._uses_execute_sql_client():
            self._detect_preset_legacy_mode_datum()
            return
        try:
            from sqlalchemy import inspect as sa_inspect
            engine = self._get_engine()
            if engine is None:
                self._preset_legacy_mode = False
                return
            inspector = sa_inspect(engine)
            legacy_table = self._get_legacy_preset_table_name()
            # Strip schema for inspector lookup
            check_schema = None
            check_table = legacy_table
            if '.' in legacy_table:
                check_schema = legacy_table.split('.')[0]
                check_table = legacy_table.split('.')[1]
            existing = inspector.get_table_names(schema=check_schema)
            self._preset_legacy_mode = check_table in existing
        except Exception:
            self._preset_legacy_mode = False

    def _detect_preset_legacy_mode_datum(self) -> None:
        """Detect legacy preset table via Datum-compatible execute_sql client."""
        try:
            legacy_table = self._get_legacy_preset_table_name()
            legacy_table_sql = _format_table_name(legacy_table)
            # Try a lightweight query against the legacy table
            self._execute_client_sql(f'SELECT 1 FROM {legacy_table_sql} LIMIT 1')
            self._preset_legacy_mode = True
        except Exception:
            self._preset_legacy_mode = False
    
    def _ensure_preset_table_exists(self) -> bool:
        """Create the preset table if it doesn't exist. Only runs once per instance."""
        if not self.app_config.table.presets_enabled:
            return True
        # Skip if already checked this session
        if self._preset_table_checked:
            return True
        
        # Legacy mode: old per-user table already exists, no creation needed
        if self._preset_legacy_mode is None:
            self._detect_preset_legacy_mode()
        if self._preset_legacy_mode:
            self._preset_table_checked = True
            return True
        
        if self._uses_execute_sql_client():
            return self._ensure_preset_table_exists_datum()
        
        try:
            from sqlalchemy import text
            
            preset_table = self._get_preset_table_name()
            preset_table_sql = _format_table_name(preset_table)
            
            engine = self._get_engine()
            if engine is None:
                return False
            
            with engine.connect() as conn:
                conn.execute(text(f'''
                    CREATE TABLE IF NOT EXISTS {preset_table_sql} (
                        id SERIAL PRIMARY KEY,
                        username VARCHAR(255) NOT NULL,
                        preset_name VARCHAR(255) NOT NULL,
                        columns JSONB NOT NULL,
                        is_default BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE (username, preset_name)
                    )
                '''))
                conn.commit()
            self._preset_table_checked = True
            return True
        except Exception as e:
            print(f"⚠ Could not create preset table: {e}")
            return False
    
    def _ensure_preset_table_exists_datum(self) -> bool:
        """Create preset table via Datum-compatible execute_sql client."""
        try:
            preset_table = self._get_preset_table_name()
            preset_table_sql = _format_table_name(preset_table)
            
            self._execute_client_sql(
                f'''
                    CREATE TABLE IF NOT EXISTS {preset_table_sql} (
                        id SERIAL PRIMARY KEY,
                        username VARCHAR(255) NOT NULL,
                        preset_name VARCHAR(255) NOT NULL,
                        columns JSONB NOT NULL,
                        is_default BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE (username, preset_name)
                    )
                '''
            )
            self._preset_table_checked = True
            return True
        except Exception as e:
            print(f"⚠ Could not create preset table via execute_sql client: {e}")
            return False
    
    def save_preset(self, preset_name: str, columns: Any, is_default: bool = False) -> Optional[int]:
        """Save a column preset."""
        if not self.app_config.table.presets_enabled:
            return None
        self._ensure_preset_table_exists()
        
        if self._uses_execute_sql_client():
            return self._save_preset_datum(preset_name, columns, is_default)
        
        try:
            from sqlalchemy import text
            
            preset_table = self._get_preset_table_name()
            preset_table_sql = _format_table_name(preset_table)
            
            engine = self._get_engine()
            if engine is None:
                return None
            
            with engine.connect() as conn:
                if self._preset_legacy_mode:
                    if is_default:
                        conn.execute(text(f'UPDATE {preset_table_sql} SET is_default = FALSE WHERE is_default = TRUE'))
                    result = conn.execute(
                        text(f'''
                            INSERT INTO {preset_table_sql} (preset_name, columns, is_default, updated_at)
                            VALUES (:preset_name, :columns, :is_default, CURRENT_TIMESTAMP)
                            ON CONFLICT (preset_name) 
                            DO UPDATE SET 
                                columns = EXCLUDED.columns,
                                is_default = EXCLUDED.is_default,
                                updated_at = CURRENT_TIMESTAMP
                            RETURNING id
                        '''),
                        {
                            "preset_name": preset_name,
                            "columns": json.dumps(columns),
                            "is_default": is_default
                        }
                    )
                else:
                    if is_default:
                        conn.execute(text(f'UPDATE {preset_table_sql} SET is_default = FALSE WHERE username = :username AND is_default = TRUE'),
                                     {"username": self.username})
                    result = conn.execute(
                        text(f'''
                            INSERT INTO {preset_table_sql} (username, preset_name, columns, is_default, updated_at)
                            VALUES (:username, :preset_name, :columns, :is_default, CURRENT_TIMESTAMP)
                            ON CONFLICT (username, preset_name) 
                            DO UPDATE SET 
                                columns = EXCLUDED.columns,
                                is_default = EXCLUDED.is_default,
                                updated_at = CURRENT_TIMESTAMP
                            RETURNING id
                        '''),
                        {
                            "username": self.username,
                            "preset_name": preset_name,
                            "columns": json.dumps(columns),
                            "is_default": is_default
                        }
                    )
                preset_id = result.scalar()
                conn.commit()
                return preset_id
        except Exception as e:
            print(f"⚠ Could not save preset: {e}")
            return None
    
    def _save_preset_datum(self, preset_name: str, columns: Any, is_default: bool) -> Optional[int]:
        """Save preset via Datum-compatible execute_sql client."""
        try:
            preset_table = self._get_preset_table_name()
            preset_table_sql = _format_table_name(preset_table)
            columns_json_lit = SqlLiteral(json.dumps(columns))
            preset_name_lit = SqlLiteral(preset_name)
            
            if self._preset_legacy_mode:
                if is_default:
                    self._execute_client_sql(f'BEGIN; UPDATE {preset_table_sql} SET is_default = FALSE WHERE is_default = TRUE; COMMIT;')
                sql = f'''
                        BEGIN;
                        INSERT INTO {preset_table_sql} (preset_name, columns, is_default, updated_at)
                        VALUES ({preset_name_lit}, {columns_json_lit}::jsonb, {str(is_default).upper()}, CURRENT_TIMESTAMP)
                        ON CONFLICT (preset_name) 
                        DO UPDATE SET 
                            columns = EXCLUDED.columns,
                            is_default = EXCLUDED.is_default,
                            updated_at = CURRENT_TIMESTAMP
                        RETURNING id;
                        COMMIT;
                    '''
            else:
                username_lit = SqlLiteral(self.username)
                if is_default:
                    self._execute_client_sql(f'BEGIN; UPDATE {preset_table_sql} SET is_default = FALSE WHERE username = {username_lit} AND is_default = TRUE; COMMIT;')
                sql = f'''
                        BEGIN;
                        INSERT INTO {preset_table_sql} (username, preset_name, columns, is_default, updated_at)
                        VALUES ({username_lit}, {preset_name_lit}, {columns_json_lit}::jsonb, {str(is_default).upper()}, CURRENT_TIMESTAMP)
                        ON CONFLICT (username, preset_name) 
                        DO UPDATE SET 
                            columns = EXCLUDED.columns,
                            is_default = EXCLUDED.is_default,
                            updated_at = CURRENT_TIMESTAMP
                        RETURNING id;
                        COMMIT;
                    '''
            
            response = self._execute_client_sql(sql)
            
            if response.data:
                return response.data[0].get("id")
            return None
        except Exception as e:
            print(f"⚠ Could not save preset via execute_sql client: {e}")
            return None
    
    def get_presets(self) -> List[Dict]:
        """Load all presets for the current user."""
        if not self.app_config.table.presets_enabled:
            return []
        self._ensure_preset_table_exists()
        
        if self._uses_execute_sql_client():
            return self._get_presets_datum()
        
        try:
            from sqlalchemy import text
            
            preset_table = self._get_preset_table_name()
            preset_table_sql = _format_table_name(preset_table)
            
            engine = self._get_engine()
            if engine is None:
                return []
            
            with engine.connect() as conn:
                if self._preset_legacy_mode:
                    result = conn.execute(text(f'''
                        SELECT id, preset_name, columns, is_default, created_at, updated_at
                        FROM {preset_table_sql}
                        ORDER BY preset_name
                    '''))
                else:
                    result = conn.execute(text(f'''
                        SELECT id, preset_name, columns, is_default, created_at, updated_at
                        FROM {preset_table_sql}
                        WHERE username = :username
                        ORDER BY preset_name
                    '''), {"username": self.username})
                
                presets = []
                for row in result:
                    presets.append({
                        "id": row[0],
                        "preset_name": row[1],
                        "columns": row[2],
                        "is_default": row[3],
                        "created_at": row[4].isoformat() if row[4] else None,
                        "updated_at": row[5].isoformat() if row[5] else None
                    })
                return presets
        except Exception as e:
            print(f"⚠ Could not load presets: {e}")
            return []
    
    def _get_presets_datum(self) -> List[Dict]:
        """Load presets via Datum-compatible execute_sql client."""
        try:
            preset_table = self._get_preset_table_name()
            preset_table_sql = _format_table_name(preset_table)
            
            if self._preset_legacy_mode:
                query = f'''
                        SELECT id, preset_name, columns, is_default, created_at, updated_at
                        FROM {preset_table_sql}
                        ORDER BY preset_name
                    '''
            else:
                username_lit = SqlLiteral(self.username)
                query = f'''
                        SELECT id, preset_name, columns, is_default, created_at, updated_at
                        FROM {preset_table_sql}
                        WHERE username = {username_lit}
                        ORDER BY preset_name
                    '''
            
            response = self._execute_client_sql(query)
            
            presets = []
            for row in response.data:
                columns = row.get("columns", {})
                if isinstance(columns, str):
                    columns = json.loads(columns)
                presets.append({
                    "id": row.get("id"),
                    "preset_name": row.get("preset_name"),
                    "columns": columns,
                    "is_default": row.get("is_default", False),
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("updated_at")
                })
            return presets
        except Exception as e:
            print(f"⚠ Could not load presets via execute_sql client: {e}")
            return []
    
    def delete_preset(self, preset_name: str) -> bool:
        """Delete a preset by name."""
        if not self.app_config.table.presets_enabled:
            return False
        if self._uses_execute_sql_client():
            return self._delete_preset_datum(preset_name)
        
        try:
            from sqlalchemy import text
            
            preset_table = self._get_preset_table_name()
            preset_table_sql = _format_table_name(preset_table)
            
            engine = self._get_engine()
            if engine is None:
                return False
            
            with engine.connect() as conn:
                if self._preset_legacy_mode:
                    result = conn.execute(
                        text(f'DELETE FROM {preset_table_sql} WHERE preset_name = :preset_name'),
                        {"preset_name": preset_name}
                    )
                else:
                    result = conn.execute(
                        text(f'DELETE FROM {preset_table_sql} WHERE username = :username AND preset_name = :preset_name'),
                        {"username": self.username, "preset_name": preset_name}
                    )
                conn.commit()
                return result.rowcount > 0
        except Exception as e:
            print(f"⚠ Could not delete preset: {e}")
            return False
    
    def _delete_preset_datum(self, preset_name: str) -> bool:
        """Delete preset via Datum-compatible execute_sql client."""
        try:
            preset_table = self._get_preset_table_name()
            preset_table_sql = _format_table_name(preset_table)
            preset_name_lit = SqlLiteral(preset_name)
            
            if self._preset_legacy_mode:
                sql = f"BEGIN; DELETE FROM {preset_table_sql} WHERE preset_name = {preset_name_lit}; COMMIT;"
            else:
                username_lit = SqlLiteral(self.username)
                sql = f"BEGIN; DELETE FROM {preset_table_sql} WHERE username = {username_lit} AND preset_name = {preset_name_lit}; COMMIT;"
            
            self._execute_client_sql(sql)
            return True
        except Exception as e:
            print(f"⚠ Could not delete preset via execute_sql client: {e}")
            return False
    
    def get_default_preset(self) -> Optional[Dict]:
        """Get the default preset for current user."""
        if not self.app_config.table.presets_enabled:
            return None
        presets = self.get_presets()
        for p in presets:
            if p.get("is_default"):
                return p
        return None


def load_config_instance(config_path: str = "app_config.json", username: str = "default_user", user_email: str = "") -> ConfigInstance:
    """
    Load a configuration instance for a widget.
    
    Args:
        config_path: Path to the config JSON file
        username: Username for user-scoped state (from Posit Connect session.user)
        user_email: Actual user email for LP LIMS API
        
    Returns:
        ConfigInstance with loaded config and data
    """
    return ConfigInstance(config_path=config_path, username=username, user_email=user_email)


def load_config_only(config_path: str = "app_config.json") -> 'AppConfig':
    """Load only the AppConfig (no DB queries, no data, no engine).

    This is used by the UI layer which only needs feature flags, titles,
    column lists etc. — never actual row data.  Avoids the heavy
    ``_load_all()`` path that fires DB queries for every tab at import time.

    Returns:
        AppConfig dataclass instance
    """
    from .app_config_schema import load_config

    config_file = Path(config_path)
    if not config_file.is_absolute():
        config_file = Path.cwd() / config_file

    return load_config(str(config_file).strip())
