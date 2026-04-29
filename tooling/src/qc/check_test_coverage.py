#!/usr/bin/env python3
"""Cross-reference public functions in src/ against test files to find untested functions."""

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import load_qc_config, get_project_root, resolve_source_files, resolve_test_files


def collect_src_functions(root: Path, config: dict):
    """Collect all public functions/methods from src/ modules."""
    src_funcs = {}
    for f in resolve_source_files(root, config):
        funcs = _extract_functions(f)
        if funcs:
            src_funcs[str(f.relative_to(root))] = funcs
    return src_funcs


def _extract_functions(filepath):
    """Extract public function and method names from a Python file."""
    funcs = []
    try:
        tree = ast.parse(filepath.read_text())
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                funcs.append(node.name)
            elif isinstance(node, ast.ClassDef):
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, ast.FunctionDef) and not child.name.startswith("_"):
                        funcs.append(f"{node.name}.{child.name}")
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
    return funcs


def collect_test_identifiers(root: Path, config: dict):
    """Collect all identifiers referenced in test files."""
    test_names = set()
    for f in resolve_test_files(root, config):
        content = f.read_text()
        tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", content)
        test_names.update(tokens)
    return test_names


def main():
    root = get_project_root()
    config = load_qc_config()
    src_funcs = collect_src_functions(root, config)
    test_names = collect_test_identifiers(root, config)

    total = 0
    untested = 0

    print("=" * 70)
    print("FUNCTION TEST COVERAGE REPORT")
    print("=" * 70)

    for filepath in sorted(src_funcs.keys()):
        funcs = src_funcs[filepath]
        missing = []
        for fn in funcs:
            check_name = fn.split(".")[-1] if "." in fn else fn
            if check_name not in test_names:
                missing.append(fn)
        total += len(funcs)
        untested += len(missing)
        if missing:
            print(f"\n{filepath} ({len(funcs) - len(missing)}/{len(funcs)} tested):")
            for m in missing:
                print(f"  MISSING: {m}")
        else:
            print(f"\n{filepath} ({len(funcs)}/{len(funcs)} tested): ALL COVERED")

    print("\n" + "=" * 70)
    print(f"SUMMARY: {total} total public functions, {total - untested} referenced in tests, {untested} not referenced")
    if total > 0:
        print(f"Coverage: {(total - untested) / total * 100:.1f}%")
    print("=" * 70)


if __name__ == "__main__":
    main()
