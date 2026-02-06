#!/usr/bin/env python3
"""
Frontend QC: JavaScript and CSS validation for the Epitopes Data Editor.
Performs syntax checks and common pattern detection without external dependencies.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any


def check_js_syntax(content: str, filepath: str) -> list[dict[str, Any]]:
    """Check JavaScript for common syntax issues."""
    issues: list[dict[str, Any]] = []
    lines = content.split('\n')
    
    # Track braces, brackets, parens
    brace_count = 0
    bracket_count = 0
    paren_count = 0
    
    in_string = False
    in_template = False
    in_comment = False
    in_multiline_comment = False
    
    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()
        
        # Skip empty lines
        if not stripped:
            continue
        
        # Track multiline comments
        if '/*' in line and '*/' not in line:
            in_multiline_comment = True
            continue
        if '*/' in line:
            in_multiline_comment = False
            continue
        if in_multiline_comment:
            continue
        
        # Skip single-line comments
        if stripped.startswith('//'):
            continue
        
        # Check for common issues
        # 1. Console.log statements (warning)
        if 'console.log' in line:
            issues.append({
                "file": filepath,
                "line": line_num,
                "type": "warning",
                "message": "console.log statement found (consider removing for production)"
            })
        
        # 2. Debugger statements
        if re.search(r'\bdebugger\b', line):
            issues.append({
                "file": filepath,
                "line": line_num,
                "type": "error",
                "message": "debugger statement found"
            })
        
        # 3. == instead of === (potential issue)
        if re.search(r'[^=!]==[^=]', line) and 'null ==' not in line:
            issues.append({
                "file": filepath,
                "line": line_num,
                "type": "warning",
                "message": "Using == instead of === (consider strict equality)"
            })
        
        # 4. var usage (prefer let/const)
        if re.search(r'\bvar\s+\w', line):
            issues.append({
                "file": filepath,
                "line": line_num,
                "type": "info",
                "message": "Using 'var' (consider using 'let' or 'const')"
            })
        
        # 5. Missing semicolons (basic check - not in control structures)
        if stripped and not stripped.endswith((';', '{', '}', ',', ':', '(', ')', '[', ']', '`', '/')) \
           and not stripped.startswith(('if', 'else', 'for', 'while', 'function', 'switch', 'case', 'default', 'try', 'catch', 'finally', '//', '/*', '*')) \
           and 'function' not in stripped and '=>' not in stripped:
            # More specific check - assignment or call without semicolon
            if re.search(r'(=\s*[^{].*[^;{}\s]$|^\s*\w+\([^)]*\)[^;{]*$)', stripped):
                if not stripped.endswith(('&&', '||', '?', '+')):
                    issues.append({
                        "file": filepath,
                        "line": line_num,
                        "type": "info",
                        "message": f"Possible missing semicolon"
                    })
        
        # Count brackets for balance check (simplified)
        for char in line:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
            elif char == '[':
                bracket_count += 1
            elif char == ']':
                bracket_count -= 1
            elif char == '(':
                paren_count += 1
            elif char == ')':
                paren_count -= 1
    
    # Check final balance
    if brace_count != 0:
        issues.append({
            "file": filepath,
            "line": 0,
            "type": "error",
            "message": f"Unbalanced braces: {brace_count:+d}"
        })
    if bracket_count != 0:
        issues.append({
            "file": filepath,
            "line": 0,
            "type": "error",
            "message": f"Unbalanced brackets: {bracket_count:+d}"
        })
    if paren_count != 0:
        issues.append({
            "file": filepath,
            "line": 0,
            "type": "error",
            "message": f"Unbalanced parentheses: {paren_count:+d}"
        })
    
    return issues


def check_css_syntax(content: str, filepath: str) -> list[dict[str, Any]]:
    """Check CSS for common syntax issues."""
    issues: list[dict[str, Any]] = []
    lines = content.split('\n')
    
    brace_count = 0
    in_comment = False
    
    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()
        
        if not stripped:
            continue
        
        # Track multiline comments
        if '/*' in line:
            in_comment = True
        if '*/' in line:
            in_comment = False
            continue
        if in_comment:
            continue
        
        # Check for common issues
        # 1. !important usage (warning)
        if '!important' in line:
            issues.append({
                "file": filepath,
                "line": line_num,
                "type": "warning",
                "message": "!important usage (consider specificity instead)"
            })
        
        # 2. Missing semicolons in property values
        if ':' in stripped and not stripped.endswith((';', '{', '}', ',')) and '{' not in stripped:
            issues.append({
                "file": filepath,
                "line": line_num,
                "type": "error",
                "message": "Missing semicolon after property value"
            })
        
        # 3. Vendor prefixes without standard (info)
        if re.search(r'-webkit-|-moz-|-ms-|-o-', line):
            issues.append({
                "file": filepath,
                "line": line_num,
                "type": "info",
                "message": "Vendor prefix found (ensure standard property is also present)"
            })
        
        # 4. Color without # for hex (skip rgba, rgb, hsl, numbers, etc.)
        # Only flag if it looks like a standalone hex value (not inside a function or as a plain number)
        if re.search(r':\s*[a-fA-F][0-9a-fA-F]{2,5}[;\s]', line) and '#' not in line \
           and not re.search(r'rgba?\s*\(|hsla?\s*\(', line):
            issues.append({
                "file": filepath,
                "line": line_num,
                "type": "warning",
                "message": "Possible hex color missing # prefix"
            })
        
        # Count braces
        brace_count += line.count('{') - line.count('}')
    
    if brace_count != 0:
        issues.append({
            "file": filepath,
            "line": 0,
            "type": "error",
            "message": f"Unbalanced braces: {brace_count:+d}"
        })
    
    return issues


def analyze_js_functions(content: str) -> list[str]:
    """Extract function names from JavaScript."""
    functions: list[str] = []
    
    # Standard function declarations
    for match in re.finditer(r'function\s+(\w+)\s*\(', content):
        functions.append(match.group(1))
    
    # Arrow functions assigned to variables
    for match in re.finditer(r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>', content):
        functions.append(match.group(1))
    
    # Window assignments
    for match in re.finditer(r'window\.(\w+)\s*=\s*function', content):
        functions.append(match.group(1))
    
    return functions


def run_frontend_qc(src_dir: Path) -> dict[str, Any]:
    """Run QC on all JS and CSS files."""
    results: dict[str, Any] = {
        "js_files": [],
        "css_files": [],
        "js_issues": [],
        "css_issues": [],
        "js_functions": [],
        "_summary": {
            "js_file_count": 0,
            "css_file_count": 0,
            "js_errors": 0,
            "js_warnings": 0,
            "css_errors": 0,
            "css_warnings": 0,
            "total_js_functions": 0
        }
    }
    
    js_dir = src_dir / "js"
    css_dir = src_dir / "css"
    
    # Process JS files
    if js_dir.exists():
        for js_file in sorted(js_dir.glob("*.js")):
            results["js_files"].append(str(js_file.name))
            content = js_file.read_text()
            
            issues = check_js_syntax(content, js_file.name)
            results["js_issues"].extend(issues)
            
            functions = analyze_js_functions(content)
            results["js_functions"].extend([{"file": js_file.name, "function": f} for f in functions])
    
    # Process CSS files
    if css_dir.exists():
        for css_file in sorted(css_dir.glob("*.css")):
            results["css_files"].append(str(css_file.name))
            content = css_file.read_text()
            
            issues = check_css_syntax(content, css_file.name)
            results["css_issues"].extend(issues)
    
    # Calculate summary
    results["_summary"]["js_file_count"] = len(results["js_files"])
    results["_summary"]["css_file_count"] = len(results["css_files"])
    results["_summary"]["js_errors"] = len([i for i in results["js_issues"] if i["type"] == "error"])
    results["_summary"]["js_warnings"] = len([i for i in results["js_issues"] if i["type"] == "warning"])
    results["_summary"]["css_errors"] = len([i for i in results["css_issues"] if i["type"] == "error"])
    results["_summary"]["css_warnings"] = len([i for i in results["css_issues"] if i["type"] == "warning"])
    results["_summary"]["total_js_functions"] = len(results["js_functions"])
    
    return results


def main() -> int:
    """Main entry point."""
    project_root = Path(__file__).parent.parent
    src_dir = project_root / "src"
    output_dir = project_root / "qcmetric"
    output_dir.mkdir(exist_ok=True)
    
    results = run_frontend_qc(src_dir)
    
    # Write results
    output_file = output_dir / "frontend_qc.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    # Print summary
    summary = results["_summary"]
    print(f"Frontend QC Results:")
    print(f"  JS files: {summary['js_file_count']}, CSS files: {summary['css_file_count']}")
    print(f"  JS: {summary['js_errors']} errors, {summary['js_warnings']} warnings")
    print(f"  CSS: {summary['css_errors']} errors, {summary['css_warnings']} warnings")
    print(f"  JS functions found: {summary['total_js_functions']}")
    
    # Return error code if errors found
    total_errors = summary['js_errors'] + summary['css_errors']
    return 1 if total_errors > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
