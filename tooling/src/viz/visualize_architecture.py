#!/usr/bin/env python3
"""
Generate a clean, hierarchical app architecture diagram.
"""

import ast
import json
from pathlib import Path
from collections import defaultdict

def analyze_module(filepath: Path) -> dict:
    """Get module summary."""
    with open(filepath, 'r') as f:
        content = f.read()
    tree = ast.parse(content)
    
    functions = []
    imports_from = set()
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            decorators = []
            for d in node.decorator_list:
                if hasattr(d, 'attr'):
                    decorators.append(d.attr)
                elif hasattr(d, 'id'):
                    decorators.append(d.id)
            functions.append({
                'name': node.name,
                'decorators': decorators,
                'is_handler': any(d in ['Effect', 'event', 'ui', 'render', 'download'] for d in decorators)
            })
        elif isinstance(node, ast.ImportFrom):
            if node.module and 'src' in str(filepath):
                # Track internal imports
                if node.module.startswith('.') or 'utils' in node.module or 'config' in node.module:
                    imports_from.add(node.module)
    
    handlers = [f for f in functions if f['is_handler']]
    return {
        'total_functions': len(functions),
        'handlers': len(handlers),
        'imports': list(imports_from)
    }


def main():
    modules = {
        'server': 'src/server.py',
        'ui': 'src/ui.py',
        'config': 'src/config/config.py',
        'config_instance': 'src/config/config_instance.py',
        'datum': 'src/adapter/datum.py',
        'table_utils': 'src/utils/table_utils.py',
        'pagination_utils': 'src/utils/pagination_utils.py',
        'data_operations': 'src/utils/data_operations.py',
        'filter_utils': 'src/utils/filter_utils.py',
        'preset_utils': 'src/utils/preset_utils.py',
        'modal_utils': 'src/utils/modal_utils.py',
        'column_utils': 'src/utils/column_utils.py',
        'process_mods': 'src/processing/process_modifications.py',
    }
    
    data = {}
    for name, path in modules.items():
        p = Path(path)
        if p.exists():
            data[name] = analyze_module(p)
    
    # Module dependencies (simplified)
    deps = {
        'server': ['ui', 'config_instance', 'table_utils', 'pagination_utils', 'data_operations', 'filter_utils', 'preset_utils', 'modal_utils', 'column_utils', 'process_mods'],
        'ui': [],
        'config_instance': ['config', 'datum'],
        'config': [],
        'datum': [],
        'table_utils': ['pagination_utils'],
        'pagination_utils': [],
        'data_operations': [],
        'filter_utils': [],
        'preset_utils': ['config_instance'],
        'modal_utils': [],
        'column_utils': [],
        'process_mods': ['config_instance'],
    }
    
    html = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>App Architecture - datumTableEditor</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            padding: 30px;
            color: white;
        }
        h1 {
            text-align: center;
            margin-bottom: 30px;
            font-size: 24px;
            color: #e0e0e0;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        .layer {
            margin-bottom: 20px;
            padding: 20px;
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
        }
        .layer-title {
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 2px;
            color: #888;
            margin-bottom: 15px;
            padding-left: 10px;
            border-left: 3px solid #3498db;
        }
        .modules {
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
            justify-content: center;
        }
        .module {
            background: rgba(0,0,0,0.4);
            border-radius: 10px;
            padding: 15px 20px;
            min-width: 150px;
            border: 2px solid transparent;
            transition: all 0.3s ease;
            cursor: pointer;
        }
        .module:hover {
            transform: translateY(-3px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }
        .module.server { border-color: #e74c3c; }
        .module.ui { border-color: #3498db; }
        .module.config { border-color: #9b59b6; }
        .module.data { border-color: #1abc9c; }
        .module.utils { border-color: #2ecc71; }
        .module.processing { border-color: #f39c12; }
        
        .module-name {
            font-weight: bold;
            font-size: 14px;
            margin-bottom: 8px;
        }
        .module-stats {
            font-size: 11px;
            color: #aaa;
        }
        .module-stats span {
            display: inline-block;
            background: rgba(255,255,255,0.1);
            padding: 2px 8px;
            border-radius: 10px;
            margin-right: 5px;
        }
        
        .arrows {
            text-align: center;
            padding: 10px;
            color: #555;
            font-size: 24px;
        }
        
        .flow-diagram {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 20px;
            margin: 40px 0;
            flex-wrap: wrap;
        }
        .flow-box {
            background: rgba(0,0,0,0.5);
            border-radius: 10px;
            padding: 20px 30px;
            text-align: center;
            border: 2px solid #444;
        }
        .flow-box.highlight {
            border-color: #3498db;
            background: rgba(52, 152, 219, 0.1);
        }
        .flow-arrow {
            font-size: 30px;
            color: #555;
        }
        
        .legend {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: rgba(0,0,0,0.8);
            padding: 15px;
            border-radius: 10px;
            font-size: 11px;
        }
        .legend-item {
            display: flex;
            align-items: center;
            margin: 5px 0;
        }
        .legend-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🏗️ datumTableEditor Architecture</h1>
        
        <!-- Data Flow -->
        <div class="flow-diagram">
            <div class="flow-box">
                <div style="font-size:24px">👤</div>
                <div>User Action</div>
            </div>
            <div class="flow-arrow">→</div>
            <div class="flow-box highlight">
                <div style="font-size:24px">⚡</div>
                <div>@Effect Handler</div>
                <div style="font-size:10px;color:#888">server.py</div>
            </div>
            <div class="flow-arrow">→</div>
            <div class="flow-box">
                <div style="font-size:24px">📊</div>
                <div>reactive.Value</div>
            </div>
            <div class="flow-arrow">→</div>
            <div class="flow-box highlight">
                <div style="font-size:24px">🎨</div>
                <div>@ui Renderer</div>
                <div style="font-size:10px;color:#888">server.py</div>
            </div>
            <div class="flow-arrow">→</div>
            <div class="flow-box">
                <div style="font-size:24px">🖥️</div>
                <div>UI Update</div>
            </div>
        </div>
        
        <!-- Application Layer -->
        <div class="layer">
            <div class="layer-title">Application Layer</div>
            <div class="modules">
                <div class="module server">
                    <div class="module-name">📡 server.py</div>
                    <div class="module-stats">
                        <span>58 funcs</span>
                        <span>31 @Effect</span>
                        <span>11 @ui</span>
                    </div>
                </div>
                <div class="module ui">
                    <div class="module-name">🎨 ui.py</div>
                    <div class="module-stats">
                        <span>3 funcs</span>
                        <span>Layout</span>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="arrows">▼</div>
        
        <!-- Business Logic Layer -->
        <div class="layer">
            <div class="layer-title">Business Logic Layer</div>
            <div class="modules">
                <div class="module config">
                    <div class="module-name">⚙️ config_instance</div>
                    <div class="module-stats">
                        <span>46 funcs</span>
                        <span>State Mgmt</span>
                    </div>
                </div>
                <div class="module processing">
                    <div class="module-name">🔄 process_mods</div>
                    <div class="module-stats">
                        <span>11 funcs</span>
                        <span>Undo/Redo</span>
                    </div>
                </div>
                <div class="module config">
                    <div class="module-name">📋 config.py</div>
                    <div class="module-stats">
                        <span>24 funcs</span>
                        <span>Fallback</span>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="arrows">▼</div>
        
        <!-- Utilities Layer -->
        <div class="layer">
            <div class="layer-title">Utilities Layer</div>
            <div class="modules">
                <div class="module utils">
                    <div class="module-name">📊 table_utils</div>
                    <div class="module-stats"><span>7 funcs</span></div>
                </div>
                <div class="module utils">
                    <div class="module-name">📄 pagination</div>
                    <div class="module-stats"><span>3 funcs</span></div>
                </div>
                <div class="module utils">
                    <div class="module-name">🔧 data_ops</div>
                    <div class="module-stats"><span>14 funcs</span></div>
                </div>
                <div class="module utils">
                    <div class="module-name">🔍 filter_utils</div>
                    <div class="module-stats"><span>1 func</span></div>
                </div>
                <div class="module utils">
                    <div class="module-name">💾 preset_utils</div>
                    <div class="module-stats"><span>11 funcs</span></div>
                </div>
                <div class="module utils">
                    <div class="module-name">🪟 modal_utils</div>
                    <div class="module-stats"><span>8 funcs</span></div>
                </div>
                <div class="module utils">
                    <div class="module-name">📐 column_utils</div>
                    <div class="module-stats"><span>8 funcs</span></div>
                </div>
            </div>
        </div>
        
        <div class="arrows">▼</div>
        
        <!-- Data Layer -->
        <div class="layer">
            <div class="layer-title">Data Layer</div>
            <div class="modules">
                <div class="module data">
                    <div class="module-name">🔌 datum.py</div>
                    <div class="module-stats">
                        <span>3 funcs</span>
                        <span>Proxy Client</span>
                    </div>
                </div>
                <div class="module data" style="border-style: dashed;">
                    <div class="module-name">🐘 PostgreSQL</div>
                    <div class="module-stats">
                        <span>External</span>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Key Flows -->
        <div style="margin-top: 40px; padding: 20px; background: rgba(0,0,0,0.3); border-radius: 10px;">
            <h3 style="margin-bottom: 15px; font-size: 14px; color: #888;">📌 Key Data Flows</h3>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px;">
                <div style="background: rgba(231,76,60,0.1); padding: 15px; border-radius: 8px; border-left: 3px solid #e74c3c;">
                    <strong>Cell Edit</strong><br>
                    <span style="font-size: 12px; color: #aaa;">
                        input.cell_edit → _handle_cell_edit → perform_cell_edit → save_modification_to_db → datum.execute_sql
                    </span>
                </div>
                <div style="background: rgba(52,152,219,0.1); padding: 15px; border-radius: 8px; border-left: 3px solid #3498db;">
                    <strong>Sort Column</strong><br>
                    <span style="font-size: 12px; color: #aaa;">
                        input.sort_column → _sort_column → sort_dataframe → current_page.set(1) → table_container re-renders
                    </span>
                </div>
                <div style="background: rgba(46,204,113,0.1); padding: 15px; border-radius: 8px; border-left: 3px solid #2ecc71;">
                    <strong>Load Data</strong><br>
                    <span style="font-size: 12px; color: #aaa;">
                        config_instance._load_data → _load_from_datum → datum.execute_sql → apply_modifications → DataFrame
                    </span>
                </div>
                <div style="background: rgba(155,89,182,0.1); padding: 15px; border-radius: 8px; border-left: 3px solid #9b59b6;">
                    <strong>Pagination</strong><br>
                    <span style="font-size: 12px; color: #aaa;">
                        input.next_page_btn → _next_page → current_page.set(n+1) → save_ui_state → table_container re-renders
                    </span>
                </div>
            </div>
        </div>
    </div>
    
    <div class="legend">
        <div class="legend-item"><div class="legend-dot" style="background:#e74c3c"></div>Server (main app)</div>
        <div class="legend-item"><div class="legend-dot" style="background:#3498db"></div>UI Layout</div>
        <div class="legend-item"><div class="legend-dot" style="background:#9b59b6"></div>Config/State</div>
        <div class="legend-item"><div class="legend-dot" style="background:#2ecc71"></div>Utilities</div>
        <div class="legend-item"><div class="legend-dot" style="background:#1abc9c"></div>Data Layer</div>
    </div>
</body>
</html>
'''
    
    output = Path('qcmetric/app_architecture.html')
    output.write_text(html)
    print(f"✅ Architecture diagram saved to {output}")


if __name__ == '__main__':
    main()
