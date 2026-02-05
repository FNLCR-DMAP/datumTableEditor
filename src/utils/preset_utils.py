"""
Preset management utilities for column presets and active preset persistence.
"""

import json
from pathlib import Path


def load_presets(presets_file: Path, default_columns: list) -> dict:
    """
    Load column presets from file.
    
    Args:
        presets_file: Path to the presets JSON file
        default_columns: Default columns to use if file doesn't exist
        
    Returns:
        Dictionary of preset names to preset data (columns and widths)
    """
    if presets_file.exists():
        try:
            with open(presets_file) as f:
                preset_data = json.load(f)
                # Handle old format (list) and new format (dict with columns/widths)
                result = {}
                for name, value in preset_data.items():
                    if isinstance(value, list):
                        result[name] = {"columns": value, "widths": {}}
                    else:
                        result[name] = value
                return result
        except Exception:
            pass
    return {"Default": {"columns": list(default_columns), "widths": {}}}


def save_presets(presets_file: Path, presets_dict: dict) -> None:
    """
    Save column presets to file.
    
    Args:
        presets_file: Path to the presets JSON file
        presets_dict: Dictionary of preset names to preset data
    """
    with open(presets_file, "w") as f:
        json.dump(presets_dict, f, indent=2)


def load_active_preset(active_preset_file: Path) -> str:
    """
    Load the last active preset name from file.
    
    Args:
        active_preset_file: Path to the active preset JSON file
        
    Returns:
        Name of the active preset, or "Default" if not found
    """
    if active_preset_file.exists():
        try:
            with open(active_preset_file) as f:
                data = json.load(f)
                return data.get("active_preset", "Default")
        except Exception:
            pass
    return "Default"


def save_active_preset(active_preset_file: Path, preset_name: str) -> None:
    """
    Save the active preset name to file.
    
    Args:
        active_preset_file: Path to the active preset JSON file
        preset_name: Name of the preset to save as active
    """
    with open(active_preset_file, "w") as f:
        json.dump({"active_preset": preset_name}, f)
