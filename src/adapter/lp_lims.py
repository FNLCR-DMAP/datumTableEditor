from __future__ import annotations

import time
from typing import Any, Dict, List, Literal, Optional

import requests
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------

class DateRangeFilter(BaseModel):
    """Date range filter for a specific column."""
    column: str = Field(..., description="Column name to filter on (must be in ALLOWED_DATE_COLUMNS).")
    start: Optional[str] = Field(default=None, description="Start date inclusive, YYYY-MM-DD.")
    end: Optional[str] = Field(default=None, description="End date inclusive, YYYY-MM-DD.")


class SelectionFilter(BaseModel):
    """Multi-value selection filter (IN clause)."""
    column: str = Field(..., description="Column name to filter on.")
    values: List[str] = Field(..., description="Allowed values for the column.")


class ExclusionFilter(BaseModel):
    """Multi-value exclusion filter (NOT IN clause)."""
    column: str = Field(..., description="Column name to exclude on.")
    values: List[str] = Field(..., description="Values to exclude.")


class IncompleteFilter(BaseModel):
    """Filter to rows where any specified column has NULL, empty, or NA value."""
    columns: List[str] = Field(..., description="Columns to check for missing values.")


class TabFilters(BaseModel):
    """Tab-specific filters applied server-side before pagination."""
    date_ranges: Optional[List[DateRangeFilter]] = None
    selections: Optional[List[SelectionFilter]] = None
    exclusions: Optional[List[ExclusionFilter]] = None
    incomplete_only: Optional[IncompleteFilter] = None


class GenericReadRequest(BaseModel):
    """
    Request model for generic read operations against LP LIMS.

    Supports data retrieval where access is controlled based on user email
    and tab selection. Filters enable server-side filtering; pagination and
    sorting are handled via dedicated fields.
    """
    user: str = Field(..., min_length=1, description="User email address requesting the data.")
    tab: str = Field(..., min_length=1, description="Tab identifier specifying which data view to retrieve.")
    environment: str = Field(..., min_length=1, description="Target environment (dev, test, prod).")
    filters: Optional[Dict[str, List[str]]] = Field(
        default=None,
        description="Optional filter constraints. Keys are column names; values are lists of allowed values.",
    )
    tab_filters: Optional[TabFilters] = Field(
        default=None,
        description="Tab-specific filters including date ranges, selections, exclusions.",
    )
    page: int = Field(default=1, ge=1, description="Page number (1-indexed).")
    page_size: Optional[int] = Field(default=None, ge=1, le=10000, description="Page size for pagination.")
    order_by: Optional[str] = Field(default=None, description="Column name to order by.")
    order_direction: Optional[Literal["asc", "desc"]] = Field(default=None, description="Sort direction.")


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------

class GenericReadResponse(BaseModel):
    """
    Response from LP LIMS generic read endpoint.

    Returns tabular data with columns and rows suitable for table rendering.
    """
    columns: List[str] = Field(..., description="List of column names in the result set.")
    data: List[Dict[str, Any]] = Field(..., description="Result rows as an array of objects.")
    row_count: int = Field(..., description="Total number of rows matching the query (for pagination).")
    page: int = Field(default=1, description="Current page number.")
    page_size: Optional[int] = Field(default=None, description="Page size used.")


# ---------------------------------------------------------------------------
# SDK Client
# ---------------------------------------------------------------------------

class LpLimsClient:
    """
    Client for the LP LIMS read-only data API.

    This adapter supports only read operations. Data is retrieved via a
    GenericReadRequest POST body with column-based filters, tab filters,
    pagination, and sorting.

    Args:
        base_url: LP LIMS API base URL.
        token: Bearer token for authentication.
        timeout: Request timeout in seconds.
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

    def read(
        self,
        user: str,
        tab: str,
        environment: str,
        filters: Optional[Dict[str, List[str]]] = None,
        tab_filters: Optional[TabFilters] = None,
        page: int = 1,
        page_size: Optional[int] = None,
        order_by: Optional[str] = None,
        order_direction: Optional[Literal["asc", "desc"]] = None,
    ) -> GenericReadResponse:
        """
        Fetch data from LP LIMS using the generic read endpoint.

        Args:
            user: User email for access control.
            tab: Tab identifier for the data view.
            environment: Target environment (dev/test/prod).
            filters: Column-name → allowed-values mapping.
            tab_filters: Tab-specific filters (date ranges, selections, etc.).
            page: Page number (1-indexed).
            page_size: Number of rows per page.
            order_by: Column to sort by.
            order_direction: Sort direction (asc/desc).

        Returns:
            GenericReadResponse with columns, data, row_count, and pagination info.
        """
        request = GenericReadRequest(
            user=user,
            tab=tab,
            environment=environment,
            filters=filters,
            tab_filters=tab_filters,
            page=page,
            page_size=page_size,
            order_by=order_by,
            order_direction=order_direction,
        )

        url = f"{self.base_url}/read"
        body = request.model_dump(exclude_none=True)

        t0 = time.perf_counter()
        resp = self._session.post(url, json=body, timeout=self.timeout)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        resp.raise_for_status()

        result = GenericReadResponse.model_validate(resp.json())
        print(
            f"[LpLims] POST /read (tab={tab}, page={page}) "
            f"→ {resp.status_code} in {elapsed_ms:.0f}ms | {result.row_count} rows"
        )
        return result
