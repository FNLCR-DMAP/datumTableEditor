"""
DataProvider Protocol — the rendering layer's API for data acquisition.

All data adapters (SQLAlchemy direct, direct psycopg PostgreSQL, Datum, LP LIMS)
implement this protocol.
The server/rendering layer only depends on this interface, never on
concrete adapter internals.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple, runtime_checkable

import pandas as pd


@runtime_checkable
class DataProvider(Protocol):
    """Protocol that all data adapters must implement.

    The rendering layer (server.py) consumes ONLY this interface.
    """

    # ── Properties ──────────────────────────────────────────────────────
    @property
    def total_count(self) -> int:
        """Total unfiltered row count."""
        ...

    @property
    def columns(self) -> List[str]:
        """Column names in the table."""
        ...

    @property
    def date_columns(self) -> set:
        """Set of column names that are date/timestamp type."""
        ...

    # ── Query methods ───────────────────────────────────────────────────
    def fetch_page(self, params: "QueryParams") -> pd.DataFrame:
        """Fetch a single page of filtered/sorted data."""
        ...

    def get_filtered_count(self, params: "QueryParams") -> int:
        """Count rows matching current filters."""
        ...

    def fetch_all_filtered(self, params: "QueryParams") -> pd.DataFrame:
        """Fetch ALL matching rows (for export)."""
        ...

    def get_unique_values(self, column: str, limit: int = 5000) -> List[str]:
        """Distinct values for a column (filter dropdowns)."""
        ...

    def get_value_counts(self, column: str, limit: int = 50, filters: dict | None = None) -> List[Tuple[str, int]]:
        """Value frequency for a column (facet panels)."""
        ...

    def get_status_counts(self, params: "QueryParams") -> dict:
        """Status distribution: {status_key: count}."""
        ...

    # ── Lifecycle ───────────────────────────────────────────────────────
    def refresh_count(self) -> None:
        """Refresh only the row count (e.g. after data reload)."""
        ...

    def set_table_override(self, table_name: str) -> None:
        """Redirect queries to a different table (e.g. synthesis matview)."""
        ...

    def clear_table_override(self) -> None:
        """Restore queries to the original table."""
        ...

    def is_date_column(self, column: str) -> bool:
        """Check if a specific column is date/timestamp type."""
        ...
