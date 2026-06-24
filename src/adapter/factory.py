"""
Factory for creating the appropriate DataProvider based on config.

Usage:
    from src.adapter.factory import create_data_provider
    provider = create_data_provider(app_config, username, user_email)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config.app_config_schema import AppConfig
    from .provider import DataProvider


def create_data_provider(app_config: "AppConfig", username: str = "", user_email: str = "") -> "DataProvider":
    """Create the appropriate DataProvider based on database mode.

    Args:
        app_config: Application configuration
        username: Session username (sanitized) for table names
        user_email: Actual user email (for LP LIMS API)

    Returns:
        A DataProvider instance appropriate for the configured mode.
    """
    mode = app_config.database.mode

    if mode == "lp_lims":
        from .lp_lims_provider import LpLimsDataProvider
        return LpLimsDataProvider(app_config=app_config, user_email=user_email)
    else:
        # SQL modes (direct, postgres, datum) use the existing DataFetcher
        # (which implements the DataProvider protocol)
        from ..config.config_instance import DataFetcher
        return DataFetcher(app_config=app_config, username=username, user_email=user_email)
