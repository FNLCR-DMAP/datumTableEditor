#!/usr/bin/env python3
"""
Generate QC reports based on tooling/config.json configuration.
Creates separate JSON files for each target (server, ui, app).
"""

import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Set, Any, Tuple, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))


def load_config(config_path: Path) -> dict:
    """Load configuration from config.json."""
    with open(config_path, 'r') as f:
        return json.load(f)


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
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)
        return calls
    except Exception as e:
        return set()


def get_all_names_used(filepath: Path) -> Set[str]:
    """Extract all Name references from a Python file."""
    try:
        with open(filepath, 'r') as f:
            tree = ast.parse(f.read())
        
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                names.add(node.id)
        return names
    except:
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
    except:
        return set()


def get_decorated_functions(filepath: Path) -> Set[str]:
    """Get functions that have decorators."""
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


def get_type_annotations(filepath: Path) -> Dict[str, Any]:
    """Extract type annotation coverage from a Python file."""
    try:
        with open(filepath, 'r') as f:
            tree = ast.parse(f.read())
    except Exception as e:
        return {"error": str(e)}
    
    stats = {
        "functions": {"total": 0, "with_return_type": 0, "fully_annotated": 0},
        "parameters": {"total": 0, "annotated": 0},
        "missing_annotations": []
    }
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            stats["functions"]["total"] += 1
            has_return = node.returns is not None
            if has_return:
                stats["functions"]["with_return_type"] += 1
            
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
            
            if has_return and all_params_annotated:
                stats["functions"]["fully_annotated"] += 1
            elif not has_return:
                stats["missing_annotations"].append({
                    "type": "return",
                    "function": node.name,
                    "line": node.lineno
                })
    
    return stats


def run_mypy_on_files(project_root: Path, files: List[Path]) -> Dict[str, List[Dict]]:
    """Run mypy on specific files."""
    # Framework type issues to ignore (Shiny/htmltools return types)
    IGNORED_PATTERNS = [
        "is not valid as a type",
        "htmltools.tags",
        "Function \"shiny",
        "Callable[...]",
        "callback protocol",
    ]
    
    try:
        cmd = [sys.executable, "-m", "mypy",
               "--ignore-missing-imports",
               "--no-error-summary",
               "--show-column-numbers",
               "--no-color-output"]
        cmd.extend([str(f) for f in files])
        
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=project_root)
        
        errors_by_file: Dict[str, List[Dict]] = {}
        for line in result.stdout.strip().split('\n'):
            if not line or line.startswith('Found') or line.startswith('Success'):
                continue
            
            # Skip framework type issues and notes
            if any(pattern in line for pattern in IGNORED_PATTERNS):
                continue
            
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


def generate_target_report(
    project_root: Path,
    target: dict,
    utils_dir: Path,
    all_calls: Set[str]
) -> dict:
    """Generate QC report for a single target."""
    report = {
        "_description": f"QC report for {target['name']}",
        "_generated": True,
        "_summary": {},
        "files": {},
        "function_mapping": {},
        "type_coverage": {},
        "mypy_errors": {}
    }
    
    total_functions = 0
    total_unused = 0
    total_annotated_functions = 0
    total_params = 0
    total_annotated_params = 0
    
    files_to_analyze = [project_root / f for f in target["files"]]
    
    # Include utils if specified
    if target.get("include_utils"):
        for py_file in sorted(utils_dir.glob("*.py")):
            if not py_file.name.startswith("_"):
                files_to_analyze.append(py_file)
    
    for py_file in files_to_analyze:
        if not py_file.exists():
            continue
        
        rel_path = str(py_file.relative_to(project_root))
        
        # Function mapping
        functions = get_functions_from_file(py_file)
        decorated = get_decorated_functions(py_file)
        
        # Dunder methods are implicitly called by Python, not "unused"
        dunder_methods = {f for f in functions if f.startswith('__') and f.endswith('__')}
        
        used = [f for f in functions if f in all_calls or f in dunder_methods]
        unused = [f for f in functions if f not in all_calls and f not in decorated and f not in dunder_methods]
        
        report["function_mapping"][rel_path] = {
            "total": len(functions),
            "functions": sorted(functions),
            "used": sorted(used),
            "unused": sorted(unused) if unused else None,
            "framework_managed": sorted([f for f in functions if f in decorated])
        }
        
        # Clean up None values
        if report["function_mapping"][rel_path]["unused"] is None:
            del report["function_mapping"][rel_path]["unused"]
        if not report["function_mapping"][rel_path]["framework_managed"]:
            del report["function_mapping"][rel_path]["framework_managed"]
        
        total_functions += len(functions)
        total_unused += len(unused)
        
        # Type coverage
        type_stats = get_type_annotations(py_file)
        if "error" not in type_stats:
            report["type_coverage"][rel_path] = {
                "functions": type_stats["functions"],
                "parameters": type_stats["parameters"]
            }
            
            if type_stats["missing_annotations"]:
                report["type_coverage"][rel_path]["missing"] = type_stats["missing_annotations"][:10]
            
            total_annotated_functions += type_stats["functions"]["fully_annotated"]
            total_params += type_stats["parameters"]["total"]
            total_annotated_params += type_stats["parameters"]["annotated"]
    
    # Run mypy
    mypy_results = run_mypy_on_files(project_root, files_to_analyze)
    if mypy_results and "_error" not in mypy_results:
        report["mypy_errors"] = mypy_results
    
    mypy_error_count = sum(len(e) for f, e in mypy_results.items() if f != "_error" and isinstance(e, list))
    
    # Summary
    func_coverage = round(total_annotated_functions / total_functions * 100, 1) if total_functions > 0 else 0
    param_coverage = round(total_annotated_params / total_params * 100, 1) if total_params > 0 else 0
    
    report["_summary"] = {
        "total_functions": total_functions,
        "unused_functions": total_unused,
        "fully_annotated_functions": total_annotated_functions,
        "function_coverage_percent": func_coverage,
        "parameter_coverage_percent": param_coverage,
        "mypy_errors": mypy_error_count
    }
    
    return report


def main():
    from config_loader import load_qc_config, get_project_root, get_output_dir, resolve_all_python_files

    root = get_project_root()
    config = load_qc_config()
    output_dir = get_output_dir(root, config)
    
    # Collect all function calls across entire codebase
    all_calls: Set[str] = set()
    for py_file in resolve_all_python_files(root, config):
        all_calls.update(get_function_calls_from_file(py_file))
        all_calls.update(get_all_names_used(py_file))
    
    # Generate report for each target
    for target in config["qc_targets"]:
        # Resolve files from glob or explicit list
        target_files = []
        if "files_glob" in target:
            target_files = [str(f.relative_to(root)) for f in sorted(root.glob(target["files_glob"])) if f.name != "__init__.py"]
        elif "files" in target:
            target_files = target["files"]

        legacy_target = {
            "name": target["name"],
            "files": target_files,
            "output": str(output_dir / target["output"]),
            "include_utils": False
        }
        utils_dir = root / config["python"]["source_dirs"][0] if config["python"]["source_dirs"] else root / "src" / "utils"
        report = generate_target_report(root, legacy_target, utils_dir, all_calls)
        
        output_path = output_dir / target["output"]
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        summary = report["_summary"]
        print(f"Generated {output_path.name}:")
        print(f"  Functions: {summary['total_functions']} (unused: {summary['unused_functions']})")
        print(f"  Type coverage: {summary['function_coverage_percent']}%")
        print(f"  Mypy errors: {summary['mypy_errors']}")
        print()


if __name__ == "__main__":
    main()
