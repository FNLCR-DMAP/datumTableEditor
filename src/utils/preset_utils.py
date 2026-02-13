"""
Preset management utilities for column presets and active preset persistence.

Delegates all database operations to ConfigInstance, which already handles
both Datum (proxy) and direct (SQLAlchemy) modes with the correct connection.

The server passes its already-loaded ConfigInstance – no redundant config
loading, no hardcoded paths, no extra service objects.
"""

from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..config.config_instance import ConfigInstance


def _convert_presets_from_db(presets: list, default_columns: list) -> dict:
    """Convert DB preset rows to app format {name: {columns, widths}}.
    
    The "Default" preset always comes from config's default_columns,
    never from the database.  Only user-created presets are stored in DB.
    """
    result = {}
    for preset in presets:
        name = preset["preset_name"]
        if name == "Default":
            # Skip DB version – Default is always driven by config
            continue
        columns = preset["columns"]
        if isinstance(columns, dict) and "columns" in columns:
            result[name] = columns
        else:
            result[name] = {"columns": columns, "widths": {}}

    # Default always comes from config
    result["Default"] = {"columns": list(default_columns), "widths": {}}

    return result


def load_presets(
    config_instance: "ConfigInstance",
    default_columns: list,
) -> dict:
    """
    Load column presets.

    "Default" preset is always built from ``default_columns`` (the config
    file's ``table.default_columns``).  User-created presets are loaded
    from the database via *config_instance*.

    Args:
        config_instance: The server's ConfigInstance (handles datum/direct).
        default_columns: Columns for the Default preset (from config).

    Returns:
        Dictionary of preset names to preset data (columns and widths).
    """
    # Always start with Default from config
    result = {"Default": {"columns": list(default_columns), "widths": {}}}

    try:
        presets = config_instance.get_presets()
        print(f"[Preset] Loaded {len(presets)} user presets from DB "
              f"(table={config_instance._get_preset_table_name()}, "
              f"user={config_instance.username})")

        for preset in presets:
            name = preset["preset_name"]
            if name == "Default":
                continue  # Default comes from config, not DB
            columns = preset["columns"]
            if isinstance(columns, dict) and "columns" in columns:
                result[name] = columns
            else:
                result[name] = {"columns": columns, "widths": {}}
    except Exception as e:
        print(f"[preset_utils] load_presets failed: {e}")

    return result


def save_presets(
    config_instance: "ConfigInstance",
    presets_dict: dict,
) -> None:
    """
    Save user-created presets to database via ConfigInstance.

    The "Default" preset is never written to the database — it is
    always driven by ``table.default_columns`` in the config file.

    Args:
        config_instance: The server's ConfigInstance.
        presets_dict: Dictionary of preset names to preset data.
    """
    try:
        # Get existing user presets (skip Default)
        existing_presets = config_instance.get_presets()
        existing_user = {p["preset_name"] for p in existing_presets if p["preset_name"] != "Default"}

        new_user_names = {n for n in presets_dict if n != "Default"}

        # Delete removed user presets
        for name in existing_user - new_user_names:
            config_instance.delete_preset(name)

        # Also clean up any stale Default row that might exist from before
        for p in existing_presets:
            if p["preset_name"] == "Default":
                config_instance.delete_preset("Default")

        # Save/update user presets only
        for name in new_user_names:
            data = presets_dict[name]
            columns_data = data if isinstance(data, dict) else {"columns": data, "widths": {}}
            config_instance.save_preset(name, columns_data, is_default=False)

        print(f"[Preset] Saved {len(new_user_names)} user presets to DB")
    except Exception as e:
        print(f"[preset_utils] save_presets failed: {e}")


def load_active_preset(
    config_instance: "ConfigInstance",
) -> str:
    """
    Load the last active preset name from database.

    If a user preset is marked ``is_default=True`` in the DB, that name is
    returned.  Otherwise falls back to ``"Default"`` (the config-driven preset).

    Args:
        config_instance: The server's ConfigInstance.

    Returns:
        Name of the active preset, or "Default" if not found.
    """
    try:
        default_preset = config_instance.get_default_preset()
        if default_preset:
            return default_preset["preset_name"]
    except Exception as e:
        print(f"[preset_utils] load_active_preset failed: {e}")
    return "Default"


def save_active_preset(
    config_instance: "ConfigInstance",
    preset_name: str,
) -> None:
    """
    Save the active preset name to database.

    Only user presets (non-Default) are in the DB, so:
    - If *preset_name* is a user preset, mark it ``is_default=True``
      and clear the flag on all others.
    - If *preset_name* is ``"Default"``, clear all ``is_default`` flags
      so ``load_active_preset`` naturally falls back to ``"Default"``.

    Args:
        config_instance: The server's ConfigInstance.
        preset_name: Name of the preset to mark as active/default.
    """
    try:
        presets = config_instance.get_presets()
        for p in presets:
            if p["preset_name"] == "Default":
                continue  # shouldn't be in DB, but skip if it is
            want_default = (p["preset_name"] == preset_name)
            if p.get("is_default") != want_default:
                config_instance.save_preset(p["preset_name"], p["columns"], is_default=want_default)
        print(f"[Preset] Active preset set to: {preset_name}")
    except Exception as e:
        print(f"[preset_utils] save_active_preset failed: {e}")
