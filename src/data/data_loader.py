"""
Data Loader - Configurable data source handling for Epitopes Data Editor

Supports loading data from:
- CSV files
- JSON files
- REST APIs
- Databases (SQLite, PostgreSQL, etc.)
"""

import json
import os
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from ..config import AppConfig, DataSourceConfig, load_config


class DataLoader:
    """Configurable data loader supporting multiple source types."""
    
    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or load_config()
        self._df: Optional[pd.DataFrame] = None
        # Project root is parent of src/
        self._project_root = Path(__file__).parent.parent
    
    def load(self) -> pd.DataFrame:
        """Load data based on configuration."""
        source_config = self.config.data_source
        
        if source_config.source_type == "csv":
            self._df = self._load_csv(source_config)
        elif source_config.source_type == "json":
            self._df = self._load_json(source_config)
        elif source_config.source_type == "api":
            self._df = self._load_api(source_config)
        elif source_config.source_type == "database":
            self._df = self._load_database(source_config)
        else:
            raise ValueError(f"Unknown source type: {source_config.source_type}")
        
        # Apply type conversions
        self._df = self._apply_type_conversions(self._df, source_config)
        
        return self._df
    
    def _load_csv(self, config: DataSourceConfig) -> pd.DataFrame:
        """Load data from CSV file."""
        file_path = self._resolve_path(config.file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"CSV file not found: {file_path}")
        return pd.read_csv(file_path)
    
    def _load_json(self, config: DataSourceConfig) -> pd.DataFrame:
        """Load data from JSON file."""
        file_path = self._resolve_path(config.file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"JSON file not found: {file_path}")
        return pd.read_json(file_path, orient="records")
    
    def _load_api(self, config: DataSourceConfig) -> pd.DataFrame:
        """Load data from REST API."""
        import requests
        
        url = self._resolve_env_vars(config.api_url)
        headers = {k: self._resolve_env_vars(v) for k, v in config.api_headers.items()}
        
        response = requests.request(
            method=config.api_method,
            url=url,
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        # Handle nested data (e.g., {"data": [...], "meta": {...}})
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        
        return pd.DataFrame(data)
    
    def _load_database(self, config: DataSourceConfig) -> pd.DataFrame:
        """Load data from database."""
        import sqlalchemy
        
        conn_string = self._resolve_env_vars(config.db_connection_string)
        engine = sqlalchemy.create_engine(conn_string)
        
        if config.db_query:
            query = config.db_query
        elif config.db_table:
            query = f"SELECT * FROM {config.db_table}"
        else:
            raise ValueError("Either db_query or db_table must be specified")
        
        return pd.read_sql(query, engine)
    
    def _apply_type_conversions(self, df: pd.DataFrame, config: DataSourceConfig) -> pd.DataFrame:
        """Apply type conversions to columns."""
        for col in config.date_columns:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        
        for col in config.numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        
        return df
    
    def _resolve_path(self, path: Optional[str]) -> Path:
        """Resolve path relative to project root."""
        if path is None:
            raise ValueError("File path not configured")
        
        path = self._resolve_env_vars(path)
        p = Path(path)
        
        if not p.is_absolute():
            # Resolve relative to project root
            p = self._project_root / p
        
        return p
    
    def _resolve_env_vars(self, value: Optional[str]) -> Optional[str]:
        """Resolve environment variables in string (${VAR_NAME} syntax)."""
        if value is None:
            return None
        
        import re
        
        def replace_env(match):
            var_name = match.group(1)
            return os.environ.get(var_name, f"${{{var_name}}}")
        
        return re.sub(r'\$\{(\w+)\}', replace_env, value)
    
    @property
    def dataframe(self) -> Optional[pd.DataFrame]:
        """Get loaded dataframe."""
        return self._df


class PersistenceManager:
    """Configurable persistence manager for modifications and state."""
    
    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or load_config()
        # Project root is parent of src/
        self._project_root = Path(__file__).parent.parent
    
    def save_modifications_log(self, log: list[dict]) -> None:
        """Save modifications log."""
        ps = self.config.persistence
        
        if ps.persistence_type == "local":
            self._save_local_json(log, ps.modifications_log_path)
        elif ps.persistence_type == "api":
            self._save_api(log, ps.api_save_url, "modifications")
        elif ps.persistence_type == "database":
            self._save_database(log, "modifications_log")
    
    def load_modifications_log(self) -> list[dict]:
        """Load modifications log."""
        ps = self.config.persistence
        
        if ps.persistence_type == "local":
            return self._load_local_json(ps.modifications_log_path, default=[])
        elif ps.persistence_type == "api":
            return self._load_api(ps.api_save_url, "modifications")
        elif ps.persistence_type == "database":
            return self._load_database("modifications_log")
        
        return []
    
    def save_data_state(self, df: pd.DataFrame) -> None:
        """Save current data state."""
        ps = self.config.persistence
        
        if ps.persistence_type == "local":
            path = self._resolve_path(ps.data_state_path)
            df.to_json(path, orient="records", indent=2, default_handler=str)
        elif ps.persistence_type == "api":
            data = df.to_dict(orient="records")
            self._save_api(data, ps.api_save_url, "data_state")
    
    def load_data_state(self) -> Optional[pd.DataFrame]:
        """Load saved data state if exists."""
        ps = self.config.persistence
        
        if ps.persistence_type == "local":
            path = self._resolve_path(ps.data_state_path)
            if path and path.exists():
                try:
                    return pd.read_json(path, orient="records")
                except Exception:
                    return None
        
        return None
    
    def _save_local_json(self, data: Any, path: Optional[str]) -> None:
        """Save data to local JSON file."""
        if path is None:
            return
        
        file_path = self._resolve_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2, default=str)
    
    def _load_local_json(self, path: Optional[str], default: Any = None) -> Any:
        """Load data from local JSON file."""
        if path is None:
            return default
        
        file_path = self._resolve_path(path)
        if not file_path.exists():
            return default
        
        with open(file_path, "r") as f:
            return json.load(f)
    
    def _save_api(self, data: Any, url: Optional[str], endpoint: str) -> None:
        """Save data to API."""
        import requests
        
        if url is None:
            return
        
        full_url = f"{url}/{endpoint}" if not url.endswith(endpoint) else url
        headers = {k: self._resolve_env_vars(v) for k, v in self.config.persistence.api_headers.items()}
        headers["Content-Type"] = "application/json"
        
        response = requests.post(full_url, json=data, headers=headers, timeout=30)
        response.raise_for_status()
    
    def _load_api(self, url: Optional[str], endpoint: str) -> Any:
        """Load data from API."""
        import requests
        
        if url is None:
            return []
        
        full_url = f"{url}/{endpoint}" if not url.endswith(endpoint) else url
        headers = {k: self._resolve_env_vars(v) for k, v in self.config.persistence.api_headers.items()}
        
        response = requests.get(full_url, headers=headers, timeout=30)
        if response.status_code == 404:
            return []
        response.raise_for_status()
        return response.json()
    
    def _save_database(self, data: Any, table: str) -> None:
        """Save data to database."""
        import sqlalchemy
        
        conn_string = self._resolve_env_vars(self.config.persistence.db_connection_string)
        engine = sqlalchemy.create_engine(conn_string)
        
        df = pd.DataFrame(data) if isinstance(data, list) else data
        df.to_sql(table, engine, if_exists="replace", index=False)
    
    def _load_database(self, table: str) -> list[dict]:
        """Load data from database."""
        import sqlalchemy
        
        conn_string = self._resolve_env_vars(self.config.persistence.db_connection_string)
        engine = sqlalchemy.create_engine(conn_string)
        
        try:
            df = pd.read_sql(f"SELECT * FROM {table}", engine)
            return df.to_dict(orient="records")
        except Exception:
            return []
    
    def _resolve_path(self, path: Optional[str]) -> Optional[Path]:
        """Resolve path relative to project root."""
        if path is None:
            return None
        
        path = self._resolve_env_vars(path)
        p = Path(path)
        
        if not p.is_absolute():
            p = self._project_root / p
        
        return p
    
    def _resolve_env_vars(self, value: Optional[str]) -> Optional[str]:
        """Resolve environment variables in string."""
        if value is None:
            return None
        
        import re
        
        def replace_env(match):
            var_name = match.group(1)
            return os.environ.get(var_name, f"${{{var_name}}}")
        
        return re.sub(r'\$\{(\w+)\}', replace_env, value)


# =============================================================================
# Convenience functions for backward compatibility
# =============================================================================

_loader: Optional[DataLoader] = None
_persistence: Optional[PersistenceManager] = None


def get_data_loader() -> DataLoader:
    """Get singleton data loader instance."""
    global _loader
    if _loader is None:
        _loader = DataLoader()
    return _loader


def get_persistence_manager() -> PersistenceManager:
    """Get singleton persistence manager instance."""
    global _persistence
    if _persistence is None:
        _persistence = PersistenceManager()
    return _persistence


def load_data() -> pd.DataFrame:
    """Load data using configured source."""
    return get_data_loader().load()


def load_modifications_log() -> list[dict]:
    """Load modifications log from configured persistence."""
    return get_persistence_manager().load_modifications_log()


def save_modifications_log(log: list[dict]) -> None:
    """Save modifications log to configured persistence."""
    get_persistence_manager().save_modifications_log(log)


def save_data_state(df: pd.DataFrame) -> None:
    """Save data state to configured persistence."""
    get_persistence_manager().save_data_state(df)


def load_data_state() -> Optional[pd.DataFrame]:
    """Load data state from configured persistence."""
    return get_persistence_manager().load_data_state()
