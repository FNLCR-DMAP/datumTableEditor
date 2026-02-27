"""
Query Builder for Epitopes Data Editor

Constructs parameterized SQL queries for:
- Filtering with multiple conditions
- Sorting
- Pagination with LIMIT/OFFSET (max 100 rows)
- JOIN with modifications table for status overlay
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

try:
    from sqlalchemy import text
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False


def quote_identifier(name: str) -> str:
    """
    Properly quote a PostgreSQL identifier, handling schema-qualified names.
    
    Examples:
        - "users" -> '"users"'
        - "epitopes.epitopes_data" -> '"epitopes"."epitopes_data"'
        - "public.my_table" -> '"public"."my_table"'
    """
    parts = name.split(".")
    return ".".join(f'"{part}"' for part in parts)


@dataclass
class FilterCondition:
    """A single filter condition."""
    column: str
    operator: Literal["=", "!=", ">", "<", ">=", "<=", "LIKE", "ILIKE", "IN", "NOT IN", "IS NULL", "IS NOT NULL"]
    value: Any = None
    
    def to_sql(self, param_prefix: str = "p") -> tuple[str, dict]:
        """
        Convert to SQL fragment and parameters.
        
        Returns:
            (sql_fragment, params_dict)
        """
        param_name = f"{param_prefix}_{self.column}"
        
        if self.operator in ("IS NULL", "IS NOT NULL"):
            return f'"{self.column}" {self.operator}', {}
        
        if self.operator in ("IN", "NOT IN"):
            # Handle list values
            if not isinstance(self.value, (list, tuple)):
                values = [self.value]
            else:
                values = list(self.value)
            placeholders = ", ".join(f":{param_name}_{i}" for i in range(len(values)))
            params = {f"{param_name}_{i}": v for i, v in enumerate(values)}
            return f'"{self.column}" {self.operator} ({placeholders})', params
        
        if self.operator in ("LIKE", "ILIKE"):
            return f'"{self.column}" {self.operator} :{param_name}', {param_name: f"%{self.value}%"}
        
        return f'"{self.column}" {self.operator} :{param_name}', {param_name: self.value}


@dataclass
class SortConfig:
    """Sort configuration."""
    column: str
    ascending: bool = True
    
    def to_sql(self) -> str:
        direction = "ASC" if self.ascending else "DESC"
        return f'"{self.column}" {direction}'


@dataclass
class QueryContext:
    """Complete query context for caching/comparison."""
    filters: list[FilterCondition] = field(default_factory=list)
    sort: Optional[SortConfig] = None
    
    def get_hash(self) -> str:
        """Generate hash for this context (for cache keys)."""
        data = {
            "filters": [(f.column, f.operator, str(f.value)) for f in self.filters],
            "sort": (self.sort.column, self.sort.ascending) if self.sort else None
        }
        return hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()[:12]
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, QueryContext):
            return False
        return self.get_hash() == other.get_hash()


class QueryBuilder:
    """Builds parameterized SQL queries."""
    
    MAX_ROWS_PER_PAGE = 100  # class-level default (overridable per instance)
    
    def __init__(
        self,
        data_table: str,
        mods_table: Optional[str] = None,
        primary_key: Optional[list[str]] = None,
        status_column: Optional[str] = None,
        max_rows_per_page: Optional[int] = None,
    ):
        self.data_table = data_table
        self.mods_table = mods_table
        if max_rows_per_page is not None:
            self.MAX_ROWS_PER_PAGE = max_rows_per_page
        self.primary_key = primary_key or ["id"]
        self.status_column = status_column
    
    def build_select_query(
        self,
        filters: Optional[list[FilterCondition]] = None,
        sort: Optional[SortConfig] = None,
        page: int = 1,
        limit: int = 25,
        include_mods_status: bool = True
    ) -> tuple[str, dict]:
        """
        Build a SELECT query with filters, sort, and pagination.
        
        Args:
            filters: List of filter conditions
            sort: Sort configuration
            page: Page number (1-indexed)
            limit: Rows per page (capped at MAX_ROWS_PER_PAGE)
            include_mods_status: Whether to include modification status from mods_table
            
        Returns:
            (sql_query, parameters_dict)
        """
        # Cap limit
        limit = min(limit, self.MAX_ROWS_PER_PAGE)
        offset = (page - 1) * limit
        
        # Build SELECT clause
        if include_mods_status and self.mods_table:
            select_clause = self._build_select_with_mods()
        else:
            select_clause = f'SELECT * FROM {quote_identifier(self.data_table)}'
        
        # Build WHERE clause
        params: dict[str, Any] = {}
        where_parts = []
        
        if filters:
            for i, f in enumerate(filters):
                sql_frag, fparams = f.to_sql(f"f{i}")
                where_parts.append(sql_frag)
                params.update(fparams)
        
        where_clause = ""
        if where_parts:
            where_clause = " WHERE " + " AND ".join(where_parts)
        
        # Build ORDER BY clause
        order_clause = ""
        if sort:
            order_clause = f" ORDER BY {sort.to_sql()}"
        elif self.primary_key:
            # Default sort by primary key
            pk_sort = ", ".join(f'"{pk}" ASC' for pk in self.primary_key)
            order_clause = f" ORDER BY {pk_sort}"
        
        # Build LIMIT/OFFSET
        limit_clause = f" LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset
        
        sql = select_clause + where_clause + order_clause + limit_clause
        return sql, params
    
    def build_count_query(
        self,
        filters: Optional[list[FilterCondition]] = None
    ) -> tuple[str, dict]:
        """
        Build a COUNT query with filters.
        
        Returns:
            (sql_query, parameters_dict)
        """
        params: dict[str, Any] = {}
        where_parts = []
        
        if filters:
            for i, f in enumerate(filters):
                sql_frag, fparams = f.to_sql(f"f{i}")
                where_parts.append(sql_frag)
                params.update(fparams)
        
        where_clause = ""
        if where_parts:
            where_clause = " WHERE " + " AND ".join(where_parts)
        
        sql = f'SELECT COUNT(*) FROM {quote_identifier(self.data_table)}' + where_clause
        return sql, params
    
    def _build_select_with_mods(self) -> str:
        """Build SELECT clause that includes modification status."""
        # Build PK match condition for subquery
        pk_conditions = " AND ".join(
            f'm.row_pk->>\'{pk}\' = d."{pk}"::text'
            for pk in self.primary_key
        )
        
        mods_table_quoted = quote_identifier(self.mods_table)
        data_table_quoted = quote_identifier(self.data_table)
        
        return f"""
        SELECT d.*,
            COALESCE(
                (SELECT m.mod_type 
                 FROM {mods_table_quoted} m 
                 WHERE {pk_conditions}
                   AND m.undone = FALSE
                 ORDER BY m.created_at DESC 
                 LIMIT 1),
                'unprocessed'
            ) AS _mod_status,
            (SELECT COUNT(*) 
             FROM {mods_table_quoted} m 
             WHERE {pk_conditions}
               AND m.undone = FALSE
               AND m.mod_type = 'field_modification'
            ) AS _mod_count
        FROM {data_table_quoted} d
        """
    
    def build_insert_modification(self) -> str:
        """Build INSERT statement for modifications table."""
        return f"""
        INSERT INTO {quote_identifier(self.mods_table)} 
            (row_pk, column_name, old_value, new_value, mod_type, created_by)
        VALUES 
            (:row_pk, :column_name, :old_value, :new_value, :mod_type, :created_by)
        RETURNING id
        """
    
    def build_undo_modification(self) -> str:
        """Build UPDATE statement to mark modification as undone."""
        return f"""
        UPDATE {quote_identifier(self.mods_table)}
        SET undone = TRUE
        WHERE id = :mod_id
        RETURNING id
        """
    
    def build_get_modifications_for_row(self) -> str:
        """Build query to get all modifications for a specific row."""
        return f"""
        SELECT * FROM {quote_identifier(self.mods_table)}
        WHERE row_pk = :row_pk
          AND undone = FALSE
        ORDER BY created_at DESC
        """
    
    def build_upsert_state(self, state_table: str) -> str:
        """Build UPSERT statement for UI state."""
        return f"""
        INSERT INTO {quote_identifier(state_table)} 
            (user_id, session_id, filters, sort_column, sort_ascending, 
             current_page, rows_per_page, column_preset, updated_at)
        VALUES 
            (:user_id, :session_id, :filters, :sort_column, :sort_ascending,
             :current_page, :rows_per_page, :column_preset, NOW())
        ON CONFLICT (user_id, session_id) 
        DO UPDATE SET
            filters = EXCLUDED.filters,
            sort_column = EXCLUDED.sort_column,
            sort_ascending = EXCLUDED.sort_ascending,
            current_page = EXCLUDED.current_page,
            rows_per_page = EXCLUDED.rows_per_page,
            column_preset = EXCLUDED.column_preset,
            updated_at = NOW()
        """
    
    def build_get_state(self, state_table: str) -> str:
        """Build query to get UI state."""
        return f"""
        SELECT * FROM {quote_identifier(state_table)}
        WHERE user_id = :user_id AND session_id = :session_id
        """


def parse_filter_from_dict(filter_dict: dict) -> FilterCondition:
    """
    Parse a filter condition from a dictionary.
    
    Expected format:
    {"column": "Status", "operator": "=", "value": "active"}
    """
    return FilterCondition(
        column=filter_dict["column"],
        operator=filter_dict.get("operator", "="),
        value=filter_dict.get("value")
    )


def parse_filters_from_list(filters: list[dict]) -> list[FilterCondition]:
    """Parse multiple filter conditions from a list of dicts."""
    return [parse_filter_from_dict(f) for f in filters]


def build_search_filter(
    search_term: str,
    columns: list[str],
    case_sensitive: bool = False
) -> list[FilterCondition]:
    """
    Build filter conditions for text search across multiple columns.
    
    Returns a list of OR conditions (caller should handle OR logic).
    """
    operator = "LIKE" if case_sensitive else "ILIKE"
    return [
        FilterCondition(column=col, operator=operator, value=search_term)
        for col in columns
    ]
