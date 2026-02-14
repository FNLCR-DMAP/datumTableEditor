#!/usr/bin/env python3
"""
Full QC Check - Analyze function relations and generate app mapping
"""

import ast
import json
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Any

def analyze_file(filepath: Path) -> Dict[str, Any]:
    """Analyze a Python file for functions, classes, imports, and calls."""
    with open(filepath, 'r') as f:
        content = f.read()
    tree = ast.parse(content)
    
    result = {
        'functions': [],
        'classes': [],
        'imports': [],
        'calls': set(),
        'decorators': defaultdict(list)
    }
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            decorators = []
            for d in node.decorator_list:
                if hasattr(d, 'attr'):
                    decorators.append(d.attr)
                elif hasattr(d, 'id'):
                    decorators.append(d.id)
            result['functions'].append({
                'name': node.name,
                'line': node.lineno,
                'decorators': decorators
            })
            for dec in decorators:
                result['decorators'][dec].append(node.name)
        elif isinstance(node, ast.ClassDef):
            result['classes'].append({'name': node.name, 'line': node.lineno})
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                for alias in node.names:
                    result['imports'].append({'from': node.module, 'name': alias.name})
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                result['calls'].add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                result['calls'].add(node.func.attr)
    
    result['calls'] = list(result['calls'])
    result['decorators'] = dict(result['decorators'])
    return result


def main():
    # Source files to analyze
    files_to_analyze = [
        'src/server.py',
        'src/ui.py', 
        'src/config/config.py',
        'src/config/config_instance.py',
        'src/config/app_config_schema.py',
        'src/adapter/datum.py',
        'src/utils/table_utils.py',
        'src/utils/pagination_utils.py',
        'src/utils/data_operations.py',
        'src/utils/filter_utils.py',
        'src/utils/preset_utils.py',
        'src/utils/modal_utils.py',
        'src/utils/column_utils.py',
        'src/utils/event_handlers.py',
        'src/utils/filter_handlers.py',
        'src/widgets/__init__.py',
        'src/db/db_operations.py',
        'src/processing/process_modifications.py',
    ]

    app_map = {}
    all_functions = {}
    all_calls = set()
    
    print("=" * 60)
    print("FULL QC CHECK - APP STRUCTURE MAPPING")
    print("=" * 60)
    print()

    for fp in files_to_analyze:
        path = Path(fp)
        if path.exists():
            try:
                result = analyze_file(path)
                module = fp.replace('src/', '').replace('.py', '').replace('/', '.')
                app_map[module] = result
                for func in result['functions']:
                    all_functions[func['name']] = {
                        'module': module, 
                        'line': func['line'], 
                        'decorators': func['decorators']
                    }
                all_calls.update(result['calls'])
            except Exception as e:
                print(f"Error analyzing {fp}: {e}")
        else:
            print(f"File not found: {fp}")

    # Print module summary
    print("📁 MODULE STRUCTURE")
    print("-" * 40)
    for module, data in sorted(app_map.items()):
        func_count = len(data['functions'])
        class_count = len(data['classes'])
        print(f"  {module}")
        print(f"    Functions: {func_count}, Classes: {class_count}")
        if data['decorators']:
            for dec, funcs in sorted(data['decorators'].items()):
                print(f"      @{dec}: {len(funcs)} handlers")
    print()

    # Find unused functions
    framework_decorators = {'render', 'reactive', 'Effect', 'event', 'ui', 'output', 'download', 'dataclass', 'staticmethod', 'classmethod'}
    unused = []
    for fname, finfo in all_functions.items():
        if fname.startswith('_'):
            continue  # Skip private functions
        if fname in all_calls:
            continue
        if any(d in framework_decorators for d in finfo.get('decorators', [])):
            continue
        unused.append({
            'name': fname, 
            'module': finfo['module'], 
            'line': finfo['line']
        })

    print("⚠️  POTENTIALLY UNUSED FUNCTIONS")
    print("-" * 40)
    if unused:
        for u in sorted(unused, key=lambda x: (x['module'], x['line'])):
            print(f"  {u['module']}:{u['line']} - {u['name']}")
    else:
        print("  None found!")
    print()

    # Print reactive handlers in server.py
    if 'server' in app_map:
        server_data = app_map['server']
        print("🔄 REACTIVE HANDLERS (server.py)")
        print("-" * 40)
        reactive_funcs = [f for f in server_data['functions'] if any(d in ['Effect', 'event', 'ui', 'render', 'download'] for d in f['decorators'])]
        for f in reactive_funcs:
            decs = ', '.join(f['decorators'])
            print(f"  Line {f['line']}: {f['name']} (@{decs})")
    print()

    # Print config instance methods
    if 'config.config_instance' in app_map:
        ci_data = app_map['config.config_instance']
        print("⚙️  CONFIG INSTANCE METHODS")
        print("-" * 40)
        public_methods = [f for f in ci_data['functions'] if not f['name'].startswith('_')]
        for f in sorted(public_methods, key=lambda x: x['line']):
            print(f"  Line {f['line']}: {f['name']}")
    print()

    # Summary stats
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Total modules analyzed: {len(app_map)}")
    print(f"  Total functions: {len(all_functions)}")
    print(f"  Total unique calls: {len(all_calls)}")
    print(f"  Potentially unused: {len(unused)}")
    print()

    # Save to JSON
    output = {
        'modules': {k: {'functions': v['functions'], 'classes': v['classes']} for k, v in app_map.items()},
        'stats': {
            'total_modules': len(app_map),
            'total_functions': len(all_functions),
            'potentially_unused': len(unused)
        },
        'unused_functions': unused
    }
    
    output_path = Path('qcmetric/app_mapping.json')
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"✅ Full mapping saved to {output_path}")


if __name__ == '__main__':
    main()
