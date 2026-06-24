"""
Adapter module for external data sources.

Architecture:
    DataProvider (Protocol) ← rendering layer depends on this only
    ├── LpLimsDataProvider  ← structured API (no SQL)
    └── DataFetcher         ← SQL-based (Datum proxy or direct SQLAlchemy)

    create_data_provider(app_config, ...) → DataProvider
"""

from .datum import DatumClient
from .factory import create_data_provider
from .lp_lims import LpLimsClient
from .lp_lims_provider import LpLimsDataProvider
from .provider import DataProvider

__all__ = [
    "DataProvider",
    "DatumClient",
    "LpLimsClient",
    "LpLimsDataProvider",
    "PostgresClient",
    "create_data_provider",
]


def __getattr__(name):
    """Lazily import optional adapters to avoid hard startup dependencies."""
    if name == "PostgresClient":
        from .postgres import PostgresClient
        return PostgresClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
