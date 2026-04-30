"""Shared config loader for QC tools. Reads tooling/qc_config.json."""

import json
from pathlib import Path
from typing import List


def find_project_root() -> Path:
    """Walk up from this file to find the project root (contains qc_config.json)."""
    current = Path(__file__).resolve().parent
    for _ in range(10):
        if (current / "tooling" / "qc_config.json").exists():
            return current
        current = current.parent
    raise RuntimeError("Cannot find project root (no tooling/qc_config.json found)")


def load_qc_config() -> dict:
    """Load and return the universal QC config."""
    root = find_project_root()
    config_path = root / "tooling" / "qc_config.json"
    with open(config_path) as f:
        return json.load(f)


def get_project_root() -> Path:
    return find_project_root()


def resolve_source_files(root: Path, config: dict) -> List[Path]:
    """Resolve all Python source files from config paths."""
    py_cfg = config["python"]
    files = []

    for d in py_cfg["source_dirs"]:
        p = root / d
        if p.exists():
            for f in sorted(p.glob("*.py")):
                if f.name == "__init__.py":
                    continue
                files.append(f)

    for f in py_cfg["source_files"]:
        p = root / f
        if p.exists():
            files.append(p)

    return files


def resolve_all_python_files(root: Path, config: dict) -> List[Path]:
    """Resolve all Python files in the project (excluding tooling, caches, etc.)."""
    exclude = config["python"]["exclude_patterns"]
    files = []
    for py_file in root.rglob("*.py"):
        rel = str(py_file.relative_to(root))
        if any(pat.strip("*").strip(".") in rel for pat in exclude):
            continue
        files.append(py_file)
    return sorted(files)


def resolve_test_files(root: Path, config: dict) -> List[Path]:
    """Resolve all test files."""
    tests_dir = root / config["paths"]["tests_dir"]
    pattern = config["python"]["test_pattern"]
    return sorted(tests_dir.glob(pattern))


def get_output_dir(root: Path, config: dict) -> Path:
    """Get and ensure output directory exists."""
    out = root / config["paths"]["output_dir"]
    out.mkdir(exist_ok=True)
    return out
