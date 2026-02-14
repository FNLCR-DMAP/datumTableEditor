#!/usr/bin/env python3
"""Cross-reference public functions in src/ against test files to find untested functions."""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent


def collect_src_functions():
    """Collect all public functions/methods from src/ modules."""
    src_dirs = ["src/utils", "src/db", "src/config", "src/processing", "src/data", "src/adapter"]
    src_files_extra = ["src/server.py", "src/ui.py"]
    src_funcs = {}

    for d in src_dirs:
        p = ROOT / d
        if not p.exists():
            continue
        for f in sorted(p.glob("*.py")):
            if f.name == "__init__.py":
                continue
            funcs = _extract_functions(f)
            if funcs:
                src_funcs[str(f.relative_to(ROOT))] = funcs

    for fp in src_files_extra:
        f = ROOT / fp
        if f.exists():
            funcs = _extract_functions(f)
            if funcs:
                src_funcs[str(f.relative_to(ROOT))] = funcs

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


def collect_test_identifiers():
    """Collect all identifiers referenced in test files."""
    test_names = set()
    tests_dir = ROOT / "tests"
    for f in sorted(tests_dir.glob("test_*.py")):
        content = f.read_text()
        tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", content)
        test_names.update(tokens)
    return test_names


def main():
    src_funcs = collect_src_functions()
    test_names = collect_test_identifiers()

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
