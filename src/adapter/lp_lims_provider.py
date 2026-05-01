"""
LP LIMS DataProvider — structured API-based data provider.

This provider talks to the LP LIMS read-only API via POST requests.
No SQL is generated; filtering/pagination is handled server-side by the API.
"""
from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .lp_lims import DateRangeFilter, LpLimsClient, TabFilters
from .provider import DataProvider


# Simple TTL cache entry
@dataclass
class _CacheEntry:
    value: Any
    timestamp: float


_CACHE_TTL_SECONDS = 300  # 5 minutes


@dataclass
class LpLimsDataProvider:
    """DataProvider implementation for LP LIMS read-only API.

    Implements the DataProvider protocol using structured POST requests
    to the LP LIMS generic-read endpoint. No SQL generation needed.
    """

    app_config: Any  # AppConfig
    user_email: str = ""
    _client: LpLimsClient = field(default=None, repr=False)
    _total_count: int = field(default=0, repr=False)
    _columns: List[str] = field(default_factory=list, repr=False)
    _unique_values_cache: Dict[str, _CacheEntry] = field(default_factory=dict, repr=False)
    _value_counts_cache: Dict[str, _CacheEntry] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        base_url = self.app_config.database.lp_lims_base_url or os.environ.get("LP_LIMS_BASE_URL", "")
        token = self.app_config.database.lp_lims_token or os.environ.get("LP_LIMS_API_TOKEN", "") or os.environ.get("DATUM_API_TOKEN", "")
        if base_url and token:
            self._client = LpLimsClient(base_url=base_url, token=token)
        else:
            print(f"⚠ LP LIMS mode: missing base_url={bool(base_url)} or token={bool(token)}")
        self._fetch_metadata()

    # ── Properties ──────────────────────────────────────────────────────

    @property
    def _user(self) -> str:
        return self.user_email or os.environ.get("LP_LIMS_USER", "")

    @property
    def _tab(self) -> str:
        return self.app_config.database.lp_lims_tab

    @property
    def _environment(self) -> str:
        return self.app_config.database.lp_lims_environment

    @property
    def total_count(self) -> int:
        return self._total_count

    @property
    def columns(self) -> List[str]:
        return self._columns.copy()

    @property
    def date_columns(self) -> set:
        # LP LIMS doesn't expose column types; return empty set
        return set()

    def is_date_column(self, column: str) -> bool:
        return False

    # ── Lifecycle ───────────────────────────────────────────────────────

    def _fetch_metadata(self):
        if not self._client:
            return
        try:
            response = self._client.read(
                user=self._user,
                tab=self._tab,
                environment=self._environment,
                page=1,
                page_size=1,
            )
            self._total_count = response.row_count if response.row_count is not None else (response.total_pages or 0)
            if response.columns:
                self._columns = list(response.columns)
            elif response.data:
                self._columns = list(response.data[0].keys())
            else:
                self._columns = []
            print(f"[LpLimsDataProvider] {self._total_count} rows, {len(self._columns)} columns")
        except Exception as e:
            print(f"✗ LP LIMS metadata error: {e}")
            self._total_count = 0
            self._columns = []

    def refresh_count(self) -> None:
        if not self._client:
            return
        try:
            response = self._client.read(
                user=self._user,
                tab=self._tab,
                environment=self._environment,
                page=1,
                page_size=1,
            )
            self._total_count = response.row_count if response.row_count is not None else (response.total_pages or 0)
            print(f"[LpLimsDataProvider] Refreshed count → {self._total_count}")
        except Exception as e:
            print(f"✗ LP LIMS refresh count error: {e}")

    def set_table_override(self, table_name: str) -> None:
        # LP LIMS doesn't support table overrides
        pass

    def clear_table_override(self) -> None:
        pass

    # ── Filter translation ──────────────────────────────────────────────

    def _build_filters(self, params) -> Tuple[Optional[Dict], Optional[TabFilters]]:
        """Convert QueryParams.filters to LP LIMS structures."""
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

                if op == "between" and isinstance(inner, list):
                    start = inner[0] if len(inner) > 0 and inner[0] else None
                    end = inner[1] if len(inner) > 1 and inner[1] else None
                    date_ranges.append(DateRangeFilter(column=col, start=start, end=end))
                elif op == "not_in" and isinstance(inner, list):
                    pass  # LP LIMS doesn't support NOT IN
                else:
                    if isinstance(inner, list):
                        cleaned = [str(v) for v in inner if v is not None and str(v).strip()]
                        if cleaned:
                            result[col] = cleaned
                    elif inner is not None and str(inner).strip():
                        result[col] = [str(inner)]
            elif isinstance(val, list):
                cleaned = [str(v) for v in val if v is not None and str(v).strip()]
                if cleaned:
                    result[col] = cleaned
            elif val is not None and str(val).strip():
                result[col] = [str(val)]

        filters_dict = result if result else None
        tab_filters = TabFilters(date_ranges=date_ranges) if date_ranges else None
        return filters_dict, tab_filters

    def _sort_params(self, params) -> Tuple[Optional[str], Optional[str]]:
        """Extract sort column/direction from QueryParams."""
        if not params.sort_column:
            return None, None
        if isinstance(params.sort_column, list):
            order_by = params.sort_column[0]
            asc = params.sort_ascending[0] if isinstance(params.sort_ascending, list) else params.sort_ascending
        else:
            order_by = params.sort_column
            asc = params.sort_ascending if isinstance(params.sort_ascending, bool) else True
        return order_by, "asc" if asc else "desc"

    # ── Query methods ───────────────────────────────────────────────────

    def fetch_page(self, params) -> pd.DataFrame:
        if not self._client:
            return pd.DataFrame()
        try:
            filters, tab_filters = self._build_filters(params)
            order_by, order_direction = self._sort_params(params)

            response = self._client.read(
                user=self._user,
                tab=self._tab,
                environment=self._environment,
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
            if not df.empty:
                df["_mod_status"] = "unprocessed"

            print(f"[LpLimsDataProvider] Fetched {len(df)} rows (page {params.page})")
            return df
        except Exception as e:
            print(f"✗ LP LIMS fetch_page error: {e}")
            import traceback
            traceback.print_exc()
            return pd.DataFrame()

    def get_filtered_count(self, params) -> int:
        if not self._client:
            return 0
        try:
            filters, tab_filters = self._build_filters(params)
            response = self._client.read(
                user=self._user,
                tab=self._tab,
                environment=self._environment,
                filters=filters if filters else None,
                tab_filters=tab_filters,
                page=1,
                page_size=1,
            )
            return response.row_count if response.row_count is not None else (response.total_pages or 0)
        except Exception as e:
            print(f"✗ LP LIMS get_filtered_count error: {e}")
            return 0

    def fetch_all_filtered(self, params) -> pd.DataFrame:
        if not self._client:
            return pd.DataFrame()
        try:
            filters, tab_filters = self._build_filters(params)
            order_by, order_direction = self._sort_params(params)

            response = self._client.read(
                user=self._user,
                tab=self._tab,
                environment=self._environment,
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
            print(f"[LpLimsDataProvider] Export fetched {len(df)} rows")
            return df
        except Exception as e:
            print(f"✗ LP LIMS fetch_all_filtered error: {e}")
            return pd.DataFrame()

    def get_unique_values(self, column: str, limit: int = 5000) -> List[str]:
        import time
        cache_key = f"{column}:{limit}"
        cached = self._unique_values_cache.get(cache_key)
        if cached and (time.time() - cached.timestamp) < _CACHE_TTL_SECONDS:
            return cached.value

        if not self._client:
            return []
        try:
            response = self._client.read(
                user=self._user,
                tab=self._tab,
                environment=self._environment,
                page=1,
                page_size=min(limit, 10000),
            )
            values = set()
            for row in response.data:
                val = row.get(column)
                if val is not None and str(val).strip():
                    values.add(str(val))
            result = sorted(values)[:limit]
            self._unique_values_cache[cache_key] = _CacheEntry(value=result, timestamp=time.time())
            return result
        except Exception as e:
            print(f"✗ LP LIMS get_unique_values error: {e}")
            return []

    def get_value_counts(self, column: str, limit: int = 50) -> List[Tuple[str, int]]:
        import time
        cache_key = f"{column}:{limit}"
        cached = self._value_counts_cache.get(cache_key)
        if cached and (time.time() - cached.timestamp) < _CACHE_TTL_SECONDS:
            return cached.value

        if not self._client:
            return []
        try:
            response = self._client.read(
                user=self._user,
                tab=self._tab,
                environment=self._environment,
                page=1,
                page_size=10000,
            )
            counter = Counter()
            for row in response.data:
                val = row.get(column)
                key = str(val).strip() if val is not None and str(val).strip() else "No value"
                counter[key] += 1
            result = counter.most_common(limit)
            self._value_counts_cache[cache_key] = _CacheEntry(value=result, timestamp=time.time())
            return result
        except Exception as e:
            print(f"✗ LP LIMS get_value_counts error: {e}")
            return []

    def get_status_counts(self, params=None) -> dict:
        # LP LIMS is read-only; all rows are "unprocessed"
        return {"unprocessed": self._total_count, "edited": 0, "approved": 0, "rejected": 0}
