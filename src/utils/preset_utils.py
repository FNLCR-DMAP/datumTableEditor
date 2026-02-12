"""
Preset management utilities for column presets and active preset persistence.

Supports database-backed storage via Datum mode or UserPresetsService.

Updated to support multiple widget instances with different table identifiers.
"""

import json
from pathlib import Path
from typing import Optional

# Try to import database service
try:
    from ..db import UserPresetsService
    DB_SERVICE_AVAILABLE = True
except ImportError:
    DB_SERVICE_AVAILABLE = False

# Cache for config and services (keyed by table_name)
_app_config_cache: Optional[dict] = None
_presets_service_cache: dict[str, "UserPresetsService"] = {}
_default_username = "default_user"


def _load_app_config() -> dict:
    """Load app_config.json and cache it."""
    global _app_config_cache
    if _app_config_cache is None:
        config_path = Path(__file__).parent.parent.parent / "app_config.json"
        if config_path.exists():
            with open(config_path) as f:
                _app_config_cache = json.load(f)
        else:
            _app_config_cache = {}
    return _app_config_cache


def _load_full_config():
    """Load config using the full schema loader (respects env vars).
    
    Note: We call load_config() with no arguments so it resolves the config
    path relative to its own __file__ location (project root), rather than
    depending on the current working directory (which differs on Posit Connect).
    """
    try:
        from ..config.app_config_schema import load_config
        return load_config()
    except Exception as e:
        print(f"[preset_utils] Could not load full config: {e}")
        return None


def _is_database_enabled() -> bool:
    """Check if database mode is enabled."""
    config = _load_app_config()
    return config.get("database", {}).get("enabled", False) and DB_SERVICE_AVAILABLE


def _get_presets_service(table_name: str = None) -> "UserPresetsService":
    """Get or create the presets service for a specific table.
    
    Args:
        table_name: Base table name to scope presets. If None, uses default.
    """
    global _presets_service_cache
    cache_key = table_name or "_default"
    if cache_key not in _presets_service_cache:
        _presets_service_cache[cache_key] = UserPresetsService(table_name=table_name)
    return _presets_service_cache[cache_key]


def _get_username() -> str:
    """Get the username for presets. Currently uses default."""
    # NOTE: This is now typically overridden by passing username from session.user
    config = _load_app_config()
    return config.get("presets", {}).get("default_user", _default_username)


def _is_datum_mode() -> bool:
    """Check if using Datum mode (using full config loader that respects env vars)."""
    # Use the full config loader which properly applies environment variable overrides
    full_config = _load_full_config()
    if full_config:
        mode = full_config.database.mode
        print(f"[Preset DEBUG] _is_datum_mode: mode='{mode}' (from full config loader)")
        return mode == "datum"
    
    # Fallback: check environment variable directly
    import os
    env_mode = os.environ.get("APP_DATABASE_MODE", "").lower()
    print(f"[Preset DEBUG] _is_datum_mode fallback: APP_DATABASE_MODE='{env_mode}'")
    return env_mode == "datum"


def _get_config_instance(username: str = None):
    """Get a ConfigInstance for Datum mode preset operations."""
    try:
        from ..config.config_instance import ConfigInstance
        user = username or _get_username()
        return ConfigInstance(config_path="app_config.json", username=user)
    except Exception as e:
        print(f"[preset_utils] Could not create ConfigInstance: {e}")
        return None


def load_presets(presets_file: Path, default_columns: list, table_name: str = None, username: str = None) -> dict:
    """
    Load column presets from database.
    
    Args:
        presets_file: Unused (kept for API compatibility)
        default_columns: Default columns to use if no presets exist
        table_name: Base table name to scope presets (for multi-widget support)
        username: Username for user-scoped presets (from Posit Connect session.user)
        
    Returns:
        Dictionary of preset names to preset data (columns and widths)
    """
    print(f"[Preset DEBUG] load_presets called - datum_mode: {_is_datum_mode()}, username: {username}")
    
    # Use ConfigInstance for Datum mode
    if _is_datum_mode():
        try:
            config_instance = _get_config_instance(username)
            if config_instance:
                print(f"[Preset DEBUG] Loading from Datum, preset_table: {config_instance._get_preset_table_name()}")
                presets = config_instance.get_presets()
                print(f"[Preset DEBUG] Got {len(presets) if presets else 0} presets from Datum")
                
                if not presets:
                    return {"Default": {"columns": list(default_columns), "widths": {}}}
                
                result = {}
                for preset in presets:
                    name = preset["preset_name"]
                    columns = preset["columns"]
                    if isinstance(columns, dict) and "columns" in columns:
                        result[name] = columns
                    else:
                        result[name] = {"columns": columns, "widths": {}}
                
                if "Default" not in result:
                    result["Default"] = {"columns": list(default_columns), "widths": {}}
                
                print(f"[Preset DEBUG] Returning presets: {list(result.keys())}")
                return result
        except Exception as e:
            print(f"[preset_utils] Datum load failed: {e}")
        return {"Default": {"columns": list(default_columns), "widths": {}}}
    
    if _is_database_enabled():
        try:
            service = _get_presets_service(table_name)
            # Use provided username or fall back to default
            user = username or _get_username()
            presets = service.get_presets(user)
            
            if not presets:
                # No presets in DB, return default
                return {"Default": {"columns": list(default_columns), "widths": {}}}
            
            # Convert from DB format to app format
            result = {}
            for preset in presets:
                name = preset["preset_name"]
                columns = preset["columns"]
                # Handle widths - stored in columns JSON or separately
                if isinstance(columns, dict) and "columns" in columns:
                    result[name] = columns
                else:
                    result[name] = {"columns": columns, "widths": {}}
            
            # Ensure Default preset exists
            if "Default" not in result:
                result["Default"] = {"columns": list(default_columns), "widths": {}}
            
            return result
        except Exception as e:
            print(f"[preset_utils] DB load failed: {e}")
    
    return {"Default": {"columns": list(default_columns), "widths": {}}}


def save_presets(presets_file: Path, presets_dict: dict, table_name: str = None, username: str = None) -> None:
    """
    Save column presets to database.
    
    Args:
        presets_file: Unused (kept for API compatibility)
        presets_dict: Dictionary of preset names to preset data
        table_name: Base table name to scope presets (for multi-widget support)
        username: Username for user-scoped presets (from Posit Connect session.user)
    """
    # Use ConfigInstance for Datum mode
    if _is_datum_mode():
        try:
            config_instance = _get_config_instance(username)
            if config_instance:
                # Get existing presets to find deleted ones
                existing_presets = config_instance.get_presets()
                existing = {p["preset_name"] for p in existing_presets}
                
                # Find current default
                current_default = None
                for p in existing_presets:
                    if p.get("is_default"):
                        current_default = p["preset_name"]
                        break
                
                new_names = set(presets_dict.keys())
                
                # Delete removed presets
                for name in existing - new_names:
                    config_instance.delete_preset(name)
                
                # If current default was deleted, set new default
                if current_default and current_default not in new_names:
                    current_default = "Default" if "Default" in new_names else next(iter(new_names), None)
                
                # Save/update all presets
                for name, data in presets_dict.items():
                    columns_data = data if isinstance(data, dict) else {"columns": data, "widths": {}}
                    is_default = (name == current_default) if current_default else (name == "Default")
                    config_instance.save_preset(name, columns_data, is_default=is_default)
                
                return
        except Exception as e:
            print(f"[preset_utils] Datum save failed: {e}")
        return
    
    if _is_database_enabled():
        try:
            service = _get_presets_service(table_name)
            # Use provided username or fall back to default
            user = username or _get_username()
            
            # Get existing presets to find deleted ones and preserve default
            existing_presets = service.get_presets(user)
            existing = {p["preset_name"] for p in existing_presets}
            
            # Find current default preset name
            current_default = None
            for p in existing_presets:
                if p.get("is_default"):
                    current_default = p["preset_name"]
                    break
            
            new_names = set(presets_dict.keys())
            
            # Delete removed presets
            for name in existing - new_names:
                service.delete_preset(username, name)
            
            # If current default was deleted, set new default to "Default" or first preset
            if current_default and current_default not in new_names:
                current_default = "Default" if "Default" in new_names else next(iter(new_names), None)
            
            # Save/update all presets (preserve existing default)
            for name, data in presets_dict.items():
                # Store columns and widths together
                columns_data = data if isinstance(data, dict) else {"columns": data, "widths": {}}
                # Only set is_default=True for the current default, False otherwise
                is_default = (name == current_default) if current_default else (name == "Default")
                service.save_preset(username, name, columns_data, is_default=is_default)
            
            return
        except Exception as e:
            print(f"[preset_utils] DB save failed: {e}")
    
    print("[preset_utils] WARNING: No database backend available, presets not saved")


def load_active_preset(active_preset_file: Path, table_name: str = None, username: str = None) -> str:
    """
    Load the last active preset name from database.
    
    Args:
        active_preset_file: Unused (kept for API compatibility)
        table_name: Base table name to scope presets (for multi-widget support)
        username: Username for user-scoped presets (from Posit Connect session.user)
        
    Returns:
        Name of the active preset, or "Default" if not found
    """
    # Use ConfigInstance for Datum mode
    if _is_datum_mode():
        try:
            config_instance = _get_config_instance(username)
            if config_instance:
                default_preset = config_instance.get_default_preset()
                if default_preset:
                    return default_preset["preset_name"]
            return "Default"
        except Exception as e:
            print(f"[preset_utils] Datum load active preset failed: {e}")
        return "Default"
    
    if _is_database_enabled():
        try:
            service = _get_presets_service(table_name)
            user = username or _get_username()
            default_preset = service.get_default_preset(user)
            if default_preset:
                return default_preset["preset_name"]
            return "Default"
        except Exception as e:
            print(f"[preset_utils] DB load active preset failed: {e}")
    
    return "Default"


def save_active_preset(active_preset_file: Path, preset_name: str, table_name: str = None, username: str = None) -> None:
    """
    Save the active preset name to database.
    
    Args:
        active_preset_file: Unused (kept for API compatibility)
        preset_name: Name of the preset to save as active
        table_name: Base table name to scope presets (for multi-widget support)
        username: Username for user-scoped presets (from Posit Connect session.user)
    """
    # Use ConfigInstance for Datum mode - set the preset as default
    if _is_datum_mode():
        try:
            config_instance = _get_config_instance(username)
            if config_instance:
                # Get existing presets and update defaults
                presets = config_instance.get_presets()
                for p in presets:
                    # Clear old default, set new default
                    is_default = (p["preset_name"] == preset_name)
                    if p.get("is_default") != is_default:
                        config_instance.save_preset(p["preset_name"], p["columns"], is_default=is_default)
                return
        except Exception as e:
            print(f"[preset_utils] Datum save active preset failed: {e}")
        return
    
    if _is_database_enabled():
        try:
            service = _get_presets_service(table_name)
            user = username or _get_username()
            service.set_default(user, preset_name)
            return
        except Exception as e:
            print(f"[preset_utils] DB save active preset failed: {e}")
    
    print("[preset_utils] WARNING: No database backend available, active preset not saved")
