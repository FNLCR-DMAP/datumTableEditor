#!/usr/bin/env python3
"""
Generate server_variable_type_qc.json by analyzing type annotations in Python files.
Uses mypy for static type checking if available, falls back to AST analysis.
"""

import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Set, Any


def get_type_annotations(filepath: Path) -> Dict[str, Any]:
    """Extract type annotation coverage from a Python file."""
    try:
        with open(filepath, 'r') as f:
            source = f.read()
            tree = ast.parse(source)
    except Exception as e:
        return {"error": str(e)}
    
    stats = {
        "functions": {"total": 0, "with_return_type": 0, "fully_annotated": 0},
        "parameters": {"total": 0, "annotated": 0},
        "variables": {"total": 0, "annotated": 0},
        "missing_annotations": []
    }
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            stats["functions"]["total"] += 1
            
            # Check return type
            has_return = node.returns is not None
            if has_return:
                stats["functions"]["with_return_type"] += 1
            
            # Check parameters
            all_params_annotated = True
            for arg in node.args.args:
                if arg.arg == "self":
                    continue
                stats["parameters"]["total"] += 1
                if arg.annotation is not None:
                    stats["parameters"]["annotated"] += 1
                else:
                    all_params_annotated = False
                    stats["missing_annotations"].append({
                        "type": "parameter",
                        "function": node.name,
                        "name": arg.arg,
                        "line": node.lineno
                    })
            
            # Check if fully annotated
            if has_return and all_params_annotated:
                stats["functions"]["fully_annotated"] += 1
            elif not has_return:
                stats["missing_annotations"].append({
                    "type": "return",
                    "function": node.name,
                    "line": node.lineno
                })
        
        # Check annotated assignments (variable type hints)
        elif isinstance(node, ast.AnnAssign):
            stats["variables"]["total"] += 1
            stats["variables"]["annotated"] += 1
        
        # Check regular assignments (no type hint)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    # Only count module-level or class-level assignments
                    stats["variables"]["total"] += 1
    
    return stats


def run_mypy(project_root: Path) -> Dict[str, List[Dict]]:
    """Run mypy type checker and parse results."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "mypy", 
             "--ignore-missing-imports",
             "--no-error-summary",
             "--show-column-numbers",
             "--no-color-output",
             str(project_root / "server.py"),
             str(project_root / "ui.py"),
             str(project_root / "app.py"),
             str(project_root / "src" / "utils")],
            capture_output=True,
            text=True,
            cwd=project_root
        )
        
        errors_by_file: Dict[str, List[Dict]] = {}
        
        for line in result.stdout.strip().split('\n'):
            if not line or line.startswith('Found') or line.startswith('Success'):
                continue
            
            # Parse mypy output: file:line:col: error: message
            parts = line.split(':', 3)
            if len(parts) >= 4:
                filepath = parts[0]
                try:
                    lineno = int(parts[1])
                    col = int(parts[2]) if parts[2].strip().isdigit() else 0
                except ValueError:
                    continue
                
                msg_parts = parts[3].split(':', 1)
                level = msg_parts[0].strip() if msg_parts else "error"
                message = msg_parts[1].strip() if len(msg_parts) > 1 else parts[3].strip()
                
                if filepath not in errors_by_file:
                    errors_by_file[filepath] = []
                
                errors_by_file[filepath].append({
                    "line": lineno,
                    "column": col,
                    "level": level,
                    "message": message
                })
        
        return errors_by_file
    
    except FileNotFoundError:
        return {"_error": [{"message": "mypy not installed"}]}
    except Exception as e:
        return {"_error": [{"message": str(e)}]}


def generate_type_qc(project_root: Path) -> dict:
    """Generate the complete type QC report."""
    utils_dir = project_root / "src" / "utils"
    server_path = project_root / "server.py"
    ui_path = project_root / "ui.py"
    app_path = project_root / "app.py"
    
    report = {
        "_description": "Type annotation coverage and mypy type checking results",
        "_generated": True,
        "_summary": {},
        "annotation_coverage": {},
        "mypy_errors": {}
    }
    
    total_functions = 0
    total_annotated_functions = 0
    total_params = 0
    total_annotated_params = 0
    total_missing = 0
    
    # Analyze each Python file
    files_to_check = [server_path, ui_path, app_path] + list(utils_dir.glob("*.py"))
    
    for py_file in files_to_check:
        if py_file.name.startswith("_"):
            continue
        
        rel_path = str(py_file.relative_to(project_root))
        stats = get_type_annotations(py_file)
        
        if "error" in stats:
            report["annotation_coverage"][rel_path] = stats
            continue
        
        total_functions += stats["functions"]["total"]
        total_annotated_functions += stats["functions"]["fully_annotated"]
        total_params += stats["parameters"]["total"]
        total_annotated_params += stats["parameters"]["annotated"]
        total_missing += len(stats["missing_annotations"])
        
        coverage = {
            "functions": stats["functions"],
            "parameters": stats["parameters"],
        }
        
        if stats["missing_annotations"]:
            # Only include first 10 missing annotations per file
            coverage["missing_annotations"] = stats["missing_annotations"][:10]
            if len(stats["missing_annotations"]) > 10:
                coverage["missing_annotations_truncated"] = len(stats["missing_annotations"]) - 10
        
        report["annotation_coverage"][rel_path] = coverage
    
    # Run mypy
    mypy_results = run_mypy(project_root)
    if mypy_results:
        report["mypy_errors"] = mypy_results
    
    # Calculate summary
    func_coverage = round(total_annotated_functions / total_functions * 100, 1) if total_functions > 0 else 0
    param_coverage = round(total_annotated_params / total_params * 100, 1) if total_params > 0 else 0
    
    mypy_error_count = sum(
        len(errors) for f, errors in mypy_results.items() 
        if f != "_error" and isinstance(errors, list)
    )
    
    report["_summary"] = {
        "total_functions": total_functions,
        "fully_annotated_functions": total_annotated_functions,
        "function_coverage_percent": func_coverage,
        "total_parameters": total_params,
        "annotated_parameters": total_annotated_params,
        "parameter_coverage_percent": param_coverage,
        "mypy_errors": mypy_error_count,
        "mypy_available": "_error" not in mypy_results
    }
    
    return report


def main():
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    output_path = project_root / "qcmetric" / "server_variable_type_qc.json"
    
    # Ensure output directory exists
    output_path.parent.mkdir(exist_ok=True)
    
    # Generate type QC report
    report = generate_type_qc(project_root)
    
    # Write to JSON
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    # Print summary
    summary = report["_summary"]
    print(f"Generated {output_path}")
    print(f"\n=== Type QC Summary ===")
    print(f"Function coverage: {summary['fully_annotated_functions']}/{summary['total_functions']} ({summary['function_coverage_percent']}%)")
    print(f"Parameter coverage: {summary['annotated_parameters']}/{summary['total_parameters']} ({summary['parameter_coverage_percent']}%)")
    
    if summary.get("mypy_available"):
        print(f"Mypy errors: {summary['mypy_errors']}")
    else:
        print("Mypy: not available (install with: pip install mypy)")


if __name__ == "__main__":
    main()
