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
    _last_filtered_count: Optional[int] = field(default=None, repr=False)
    _last_filtered_params_hash: Optional[str] = field(default=None, repr=False)
    _prefetched_page: Optional[pd.DataFrame] = field(default=None, repr=False)
    _cached_fetch_df: Optional[pd.DataFrame] = field(default=None, repr=False)
    _cached_fetch_hash: Optional[str] = field(default=None, repr=False)

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
            # Fetch first page of data in the same call as metadata.
            # This eliminates the separate page_size=1 metadata call (~488ms saved).
            prefetch_size = self.app_config.table.default_rows_per_page if hasattr(self.app_config, 'table') else 50
            response = self._client.read(
                user=self._user,
                tab=self._tab,
                environment=self._environment,
                page=1,
                page_size=prefetch_size,
            )
            self._total_count = response.row_count if response.row_count is not None else (response.total_pages or 0)
            if response.columns:
                self._columns = list(response.columns)
            elif response.data:
                self._columns = list(response.data[0].keys())
            else:
                self._columns = []

            # Cache the first page so fetch_page(page=1, no filters) is free
            if response.data:
                df = pd.DataFrame(response.data)
                if not df.empty:
                    df["_mod_status"] = "unprocessed"
                self._prefetched_page = df
                self._last_filtered_count = self._total_count
                self._last_filtered_params_hash = self._params_hash_raw(None, None)

            print(f"[LpLimsDataProvider] {self._total_count} rows, {len(self._columns)} columns")
        except Exception as e:
            print(f"✗ LP LIMS metadata error: {e}")
            self._total_count = 0
            self._columns = []

    @staticmethod
    def _params_hash_raw(filters, status_filters) -> str:
        """Hash from raw filter dicts (no QueryParams object needed)."""
        import hashlib, json
        key = json.dumps({
            "filters": filters,
            "status_filters": status_filters,
        }, sort_keys=True, default=str)
        return hashlib.sha256(key.encode()).hexdigest()

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

    def _params_hash(self, params) -> str:
        """Cheap hash of filter-relevant params (excludes page/page_size/sort)."""
        return self._params_hash_raw(
            params.filters if params.filters else None,
            params.status_filters if hasattr(params, 'status_filters') else None,
        )

    def _full_params_hash(self, params) -> str:
        """Hash including page/page_size/sort — for exact request dedup."""
        import hashlib
        sort_col = params.sort_column if hasattr(params, 'sort_column') else None
        sort_asc = params.sort_ascending if hasattr(params, 'sort_ascending') else None
        key = repr((
            params.filters if params.filters else None,
            getattr(params, 'status_filters', None),
            params.page, params.page_size,
            sort_col, sort_asc,
        ))
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def fetch_page(self, params) -> pd.DataFrame:
        if not self._client:
            return pd.DataFrame()

        # Return cached data from get_filtered_count (if it fired first with same params)
        fph = self._full_params_hash(params)
        if self._cached_fetch_df is not None and self._cached_fetch_hash == fph:
            df = self._cached_fetch_df
            self._cached_fetch_df = None
            self._cached_fetch_hash = None
            print(f"[LpLimsDataProvider] Fetched {len(df)} rows (page {params.page}, from count-cache)")
            return df

        # Return prefetched first page if it matches (no filters, page 1, same size)
        if (self._prefetched_page is not None
            and params.page == 1
            and not params.filters
            and not getattr(params, 'sort_column', None)
            and not getattr(params, 'status_filters', None)):
            prefetch_size = self.app_config.table.default_rows_per_page if hasattr(self.app_config, 'table') else 50
            if params.page_size <= prefetch_size:
                df = self._prefetched_page.head(params.page_size).copy()
                self._prefetched_page = None  # One-shot: free memory after use
                print(f"[LpLimsDataProvider] Fetched {len(df)} rows (page 1, prefetched)")
                return df
            self._prefetched_page = None

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

            # Cache the filtered row_count from this response to avoid a separate count request
            if response.row_count is not None:
                derived_count = response.row_count
            elif response.total_pages is not None:
                tp = response.total_pages
                n_data = len(response.data) if response.data else 0
                if tp <= 1:
                    derived_count = n_data
                else:
                    derived_count = (tp - 1) * params.page_size + n_data
            else:
                derived_count = None

            if derived_count is not None:
                self._last_filtered_count = derived_count
                self._last_filtered_params_hash = self._params_hash(params)

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
        # Use cached count from fetch_page if filters haven't changed
        ph = self._params_hash(params)
        if self._last_filtered_count is not None and self._last_filtered_params_hash == ph:
            return self._last_filtered_count
        try:
            # Do a full-size fetch (not page_size=1) so we cache data for fetch_page too
            filters, tab_filters = self._build_filters(params)
            order_by, order_direction = self._sort_params(params)
            response = self._client.read(
                user=self._user,
                tab=self._tab,
                environment=self._environment,
                filters=filters if filters else None,
                tab_filters=tab_filters,
                page=params.page,
                page_size=params.page_size,
                order_by=order_by,
                order_direction=order_direction,
            )
            # Derive count: prefer row_count, else compute from total_pages + data length
            if response.row_count is not None:
                count = response.row_count
            elif response.total_pages is not None:
                tp = response.total_pages
                n_data = len(response.data) if response.data else 0
                if tp <= 1:
                    # Single page: data length IS the total
                    count = n_data
                else:
                    # Last page may be partial; this page gives us a full page_size worth
                    count = (tp - 1) * params.page_size + n_data
            else:
                count = len(response.data) if response.data else 0
            self._last_filtered_count = count
            self._last_filtered_params_hash = ph

            # Cache the fetched data so fetch_page doesn't repeat the request
            df = pd.DataFrame(response.data)
            if df.empty and response.columns:
                df = pd.DataFrame(columns=response.columns)
            if not df.empty:
                df["_mod_status"] = "unprocessed"
            self._cached_fetch_df = df
            self._cached_fetch_hash = self._full_params_hash(params)

            return count
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
