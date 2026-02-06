#!/usr/bin/env python3
"""
Generate server_function_qc.json by analyzing Python files in src/utils/ and server.py.
Detects unused functions across the entire codebase.
"""

import ast
import json
from pathlib import Path
from typing import Set, Dict, List, Tuple


def get_functions_from_file(filepath: Path) -> List[str]:
    """Extract all function names defined in a Python file."""
    try:
        with open(filepath, 'r') as f:
            tree = ast.parse(f.read())
        return [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
        return []


def get_function_calls_from_file(filepath: Path) -> Set[str]:
    """Extract all function calls from a Python file."""
    try:
        with open(filepath, 'r') as f:
            tree = ast.parse(f.read())
        
        calls = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Direct function call: func()
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                # Method or attribute call: obj.method()
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)
        return calls
    except Exception as e:
        print(f"Error getting calls from {filepath}: {e}")
        return set()


def get_docstring(filepath: Path) -> str:
    """Extract module docstring from a Python file."""
    try:
        with open(filepath, 'r') as f:
            tree = ast.parse(f.read())
        docstring = ast.get_docstring(tree)
        if docstring:
            return docstring.split('\n')[0].strip()
        return ""
    except:
        return ""


def get_imports_from_file(filepath: Path, module_filter: str = None) -> Set[str]:
    """Extract imported function names from a Python file."""
    try:
        with open(filepath, 'r') as f:
            tree = ast.parse(f.read())
        
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if module_filter is None or (node.module and module_filter in node.module):
                    for alias in node.names:
                        imported.add(alias.name)
        return imported
    except Exception as e:
        print(f"Error parsing imports from {filepath}: {e}")
        return set()


def get_all_names_used(filepath: Path) -> Set[str]:
    """Extract all Name references (function calls, variables, identifiers) from a Python file."""
    try:
        with open(filepath, 'r') as f:
            tree = ast.parse(f.read())
        
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                names.add(node.id)
        return names
    except Exception as e:
        print(f"Error getting names from {filepath}: {e}")
        return set()


def get_decorated_functions(filepath: Path) -> Set[str]:
    """Get functions that have decorators (likely framework-managed)."""
    try:
        with open(filepath, 'r') as f:
            tree = ast.parse(f.read())
        
        decorated = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.decorator_list:
                decorated.add(node.name)
        return decorated
    except:
        return set()


def analyze_codebase(project_root: Path) -> Tuple[Dict, Dict, Set, Set]:
    """
    Analyze the entire codebase for function definitions and calls.
    
    Returns:
        (all_definitions, all_calls_by_file, all_calls, decorated_funcs)
    """
    utils_dir = project_root / "src" / "utils"
    server_path = project_root / "server.py"
    
    # Collect all function definitions by module
    all_definitions = {}
    
    # Scan utils modules
    for py_file in sorted(utils_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        functions = get_functions_from_file(py_file)
        if functions:
            all_definitions[py_file.name] = {
                "path": str(py_file.relative_to(project_root)),
                "functions": functions,
                "description": get_docstring(py_file)
            }
    
    # Add server.py
    server_functions = get_functions_from_file(server_path)
    if server_functions:
        all_definitions["server.py"] = {
            "path": "server.py",
            "functions": server_functions,
            "description": get_docstring(server_path)
        }
    
    # Add ui.py
    ui_path = project_root / "ui.py"
    ui_functions = get_functions_from_file(ui_path)
    if ui_functions:
        all_definitions["ui.py"] = {
            "path": "ui.py",
            "functions": ui_functions,
            "description": get_docstring(ui_path)
        }
    
    # Add app.py
    app_path = project_root / "app.py"
    app_functions = get_functions_from_file(app_path)
    if app_functions:
        all_definitions["app.py"] = {
            "path": "app.py",
            "functions": app_functions,
            "description": get_docstring(app_path)
        }
    
    # Collect all function calls AND all name references across all Python files
    all_calls = set()
    all_calls_by_file = {}
    
    # Scan all Python files
    for py_file in project_root.rglob("*.py"):
        if "__pycache__" in str(py_file) or "tooling" in str(py_file):
            continue
        calls = get_function_calls_from_file(py_file)
        names = get_all_names_used(py_file)  # Also get name references (for imports used as values)
        combined = calls | names
        all_calls.update(combined)
        all_calls_by_file[str(py_file.relative_to(project_root))] = combined
    
    # Get decorated functions from server.py (these are framework-managed)
    decorated_funcs = get_decorated_functions(server_path)
    
    return all_definitions, all_calls_by_file, all_calls, decorated_funcs


def generate_qc_report(project_root: Path) -> dict:
    """Generate the complete QC report."""
    server_path = project_root / "server.py"
    
    # Analyze codebase
    all_definitions, all_calls_by_file, all_calls, decorated_funcs = analyze_codebase(project_root)
    
    # Get server imports from utils
    server_imports = get_imports_from_file(server_path, "src.utils")
    
    report = {
        "_description": "QC report: function definitions, usage, and unused function detection",
        "_generated": True,
        "_summary": {},
        "modules": {},
        "server": {},
        "unused_functions": {}
    }
    
    total_functions = 0
    total_unused = 0
    unused_by_module = {}
    
    # Analyze each utils module
    for module_name, module_data in all_definitions.items():
        if module_name == "server.py":
            continue
            
        functions = module_data["functions"]
        total_functions += len(functions)
        
        # Determine usage status for each function
        used_in_server = [f for f in functions if f in server_imports]
        used_internally = [f for f in functions if f in all_calls and f not in server_imports]
        
        # Truly unused: not in server imports AND not called anywhere
        truly_unused = [f for f in functions if f not in all_calls]
        
        module_report = {
            "description": module_data["description"],
            "path": module_data["path"],
            "total_functions": len(functions),
            "functions": sorted(functions),
        }
        
        if used_in_server:
            module_report["used_in_server"] = sorted(used_in_server)
        
        if used_internally:
            module_report["used_internally"] = sorted(used_internally)
        
        if truly_unused:
            module_report["unused"] = sorted(truly_unused)
            total_unused += len(truly_unused)
            unused_by_module[module_name] = sorted(truly_unused)
        
        report["modules"][module_name] = module_report
    
    # Analyze server.py
    if "server.py" in all_definitions:
        server_functions = all_definitions["server.py"]["functions"]
        
        # Decorated functions are framework-managed (Shiny uses them)
        framework_managed = [f for f in server_functions if f in decorated_funcs]
        
        # Helper functions (called within server.py)
        server_calls = all_calls_by_file.get("server.py", set())
        helper_functions = [f for f in server_functions if f not in decorated_funcs and f in server_calls]
        
        # Unused in server
        server_unused = [f for f in server_functions if f not in decorated_funcs and f not in all_calls]
        
        report["server"] = {
            "path": "server.py",
            "total_functions": len(server_functions),
            "functions": sorted(server_functions),
            "framework_managed": sorted(framework_managed),
            "helper_functions": sorted(helper_functions),
        }
        
        if server_unused:
            report["server"]["unused"] = sorted(server_unused)
            total_unused += len(server_unused)
            unused_by_module["server.py"] = sorted(server_unused)
        
        total_functions += len(server_functions)
    
    # Summary
    report["_summary"] = {
        "total_functions": total_functions,
        "total_unused": total_unused,
        "unused_percentage": round(total_unused / total_functions * 100, 1) if total_functions > 0 else 0
    }
    
    if unused_by_module:
        report["unused_functions"] = unused_by_module
    
    return report


def main():
    # Determine paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    output_path = project_root / "qcmetric" / "server_function_qc.json"
    
    # Ensure output directory exists
    output_path.parent.mkdir(exist_ok=True)
    
    # Generate QC report
    report = generate_qc_report(project_root)
    
    # Write to JSON
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    # Print summary
    print(f"Generated {output_path}")
    print(f"\n=== QC Summary ===")
    print(f"Total functions: {report['_summary']['total_functions']}")
    print(f"Unused functions: {report['_summary']['total_unused']}")
    print(f"Unused percentage: {report['_summary']['unused_percentage']}%")
    
    if report.get("unused_functions"):
        print(f"\n=== Unused Functions by Module ===")
        for module, funcs in report["unused_functions"].items():
            print(f"  {module}: {', '.join(funcs)}")


if __name__ == "__main__":
    main()
