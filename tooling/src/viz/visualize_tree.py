#!/usr/bin/env python3
"""
Tree visualization with function clustering by logic type.
"""

import ast
import json
from pathlib import Path
from collections import defaultdict

def classify_function(name: str, decorators: list, calls: list, module: str) -> str:
    """Classify a function by its logic type."""
    name_lower = name.lower()
    
    # By decorators first
    if 'Effect' in decorators or 'event' in decorators:
        if any(x in name_lower for x in ['page', 'pagination', 'first', 'prev', 'next', 'last', 'jump']):
            return 'pagination_handlers'
        if any(x in name_lower for x in ['filter', 'search']):
            return 'filter_handlers'
        if any(x in name_lower for x in ['sort', 'column', 'order', 'width', 'reset']):
            return 'column_handlers'
        if any(x in name_lower for x in ['preset', 'layout', 'save_current']):
            return 'preset_handlers'
        if any(x in name_lower for x in ['edit', 'cell', 'undo', 'modification']):
            return 'edit_handlers'
        if any(x in name_lower for x in ['approve', 'reject', 'clear_approval', 'status']):
            return 'approval_handlers'
        if any(x in name_lower for x in ['export', 'reload', 'copy']):
            return 'data_handlers'
        return 'other_handlers'
    
    if 'ui' in decorators or 'render' in decorators or 'text' in decorators:
        return 'ui_renderers'
    
    if 'download' in decorators:
        return 'download_handlers'
    
    # By function name patterns
    if name.startswith('_') and not name.startswith('__'):
        if 'load' in name_lower or 'get' in name_lower or 'fetch' in name_lower:
            return 'data_loaders'
        if 'save' in name_lower or 'update' in name_lower or 'insert' in name_lower:
            return 'data_savers'
        return 'internal_helpers'
    
    if 'build' in name_lower or 'create' in name_lower or 'render' in name_lower:
        return 'ui_builders'
    
    if 'load' in name_lower or 'get' in name_lower or 'fetch' in name_lower or 'read' in name_lower:
        return 'data_loaders'
    
    if 'save' in name_lower or 'update' in name_lower or 'write' in name_lower or 'insert' in name_lower:
        return 'data_savers'
    
    if 'filter' in name_lower or 'search' in name_lower or 'find' in name_lower:
        return 'filters'
    
    if 'sort' in name_lower or 'order' in name_lower:
        return 'sorters'
    
    if 'validate' in name_lower or 'check' in name_lower or 'is_' in name_lower:
        return 'validators'
    
    if 'format' in name_lower or 'convert' in name_lower or 'parse' in name_lower or 'transform' in name_lower:
        return 'transformers'
    
    if 'process' in name_lower or 'perform' in name_lower or 'execute' in name_lower or 'apply' in name_lower:
        return 'processors'
    
    if 'datum' in module or 'db' in module:
        return 'database_ops'
    
    if 'util' in module:
        return 'utilities'
    
    return 'other'


def analyze_functions(filepath: Path, module: str) -> list:
    """Extract and classify functions from a file."""
    with open(filepath, 'r') as f:
        content = f.read()
    tree = ast.parse(content)
    
    functions = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            decorators = []
            for d in node.decorator_list:
                if hasattr(d, 'attr'):
                    decorators.append(d.attr)
                elif hasattr(d, 'id'):
                    decorators.append(d.id)
            
            calls = []
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Name):
                        calls.append(child.func.id)
                    elif isinstance(child.func, ast.Attribute):
                        calls.append(child.func.attr)
            
            func_type = classify_function(node.name, decorators, calls, module)
            
            functions.append({
                'name': node.name,
                'module': module,
                'line': node.lineno,
                'decorators': decorators,
                'calls': calls,  # Keep calls for connection visualization
                'type': func_type
            })
    
    return functions


def main():
    files = [
        ('src/server/core.py', 'server_core'),
        ('src/server/filters.py', 'server_filters'),
        ('src/server/pagination.py', 'server_pagination'),
        ('src/server/presets.py', 'server_presets'),
        ('src/server/edits.py', 'server_edits'),
        ('src/server/export.py', 'server_export'),
        ('src/server/synthesis.py', 'server_synthesis'),
        ('src/ui.py', 'ui'),
        ('src/config/config.py', 'config'),
        ('src/config/config_instance.py', 'config_instance'),
        ('src/adapter/datum.py', 'datum'),
        ('src/utils/table_utils.py', 'table_utils'),
        ('src/utils/pagination_utils.py', 'pagination_utils'),
        ('src/utils/data_operations.py', 'data_operations'),
        ('src/utils/filter_utils.py', 'filter_utils'),
        ('src/utils/preset_utils.py', 'preset_utils'),
        ('src/utils/modal_utils.py', 'modal_utils'),
        ('src/utils/column_utils.py', 'column_utils'),
        ('src/utils/event_handlers.py', 'event_handlers'),
        ('src/processing/process_modifications.py', 'process_mods'),
    ]
    
    # Collect all functions
    all_funcs = []
    for filepath, module in files:
        p = Path(filepath)
        if p.exists():
            all_funcs.extend(analyze_functions(p, module))
    
    # Group by type
    by_type = defaultdict(list)
    for f in all_funcs:
        by_type[f['type']].append(f)
    
    # Define category groupings and colors
    categories = {
        'Event Handlers': {
            'color': '#e74c3c',
            'icon': '⚡',
            'types': ['pagination_handlers', 'filter_handlers', 'column_handlers', 
                     'preset_handlers', 'edit_handlers', 'approval_handlers', 
                     'data_handlers', 'other_handlers', 'download_handlers']
        },
        'UI Components': {
            'color': '#3498db',
            'icon': '🎨',
            'types': ['ui_renderers', 'ui_builders']
        },
        'Data Operations': {
            'color': '#2ecc71',
            'icon': '📊',
            'types': ['data_loaders', 'data_savers', 'database_ops']
        },
        'Processing': {
            'color': '#9b59b6',
            'icon': '⚙️',
            'types': ['processors', 'transformers', 'filters', 'sorters', 'validators']
        },
        'Utilities': {
            'color': '#f39c12',
            'icon': '🔧',
            'types': ['utilities', 'internal_helpers', 'other']
        }
    }
    
    # Type display names
    type_names = {
        'pagination_handlers': 'Pagination',
        'filter_handlers': 'Filters',
        'column_handlers': 'Columns',
        'preset_handlers': 'Presets',
        'edit_handlers': 'Cell Editing',
        'approval_handlers': 'Approval Flow',
        'data_handlers': 'Data Actions',
        'other_handlers': 'Other Effects',
        'download_handlers': 'Downloads',
        'ui_renderers': 'Renderers',
        'ui_builders': 'Builders',
        'data_loaders': 'Loaders',
        'data_savers': 'Savers',
        'database_ops': 'Database',
        'processors': 'Processors',
        'transformers': 'Transformers',
        'filters': 'Filter Logic',
        'sorters': 'Sort Logic',
        'validators': 'Validators',
        'utilities': 'General Utils',
        'internal_helpers': 'Internal',
        'other': 'Misc'
    }
    
    # Build tree data
    tree_data = {'name': 'datumTableEditor', 'children': []}
    
    # Build function lookup for connections
    func_lookup = {f['name']: f for f in all_funcs}
    all_func_names = set(func_lookup.keys())
    
    # Build connections (edges between functions)
    connections = []
    for f in all_funcs:
        for call in f.get('calls', []):
            if call in all_func_names and call != f['name']:
                connections.append({
                    'source': f['name'],
                    'target': call,
                    'sourceModule': f['module'],
                    'targetModule': func_lookup[call]['module']
                })
    
    for cat_name, cat_info in categories.items():
        cat_node = {
            'name': f"{cat_info['icon']} {cat_name}",
            'color': cat_info['color'],
            'children': []
        }
        
        for func_type in cat_info['types']:
            if func_type in by_type and by_type[func_type]:
                type_node = {
                    'name': type_names.get(func_type, func_type),
                    'color': cat_info['color'],
                    'children': []
                }
                
                # Group functions by module within type
                by_module = defaultdict(list)
                for f in by_type[func_type]:
                    by_module[f['module']].append(f)
                
                for module, funcs in sorted(by_module.items()):
                    for func in sorted(funcs, key=lambda x: x['name']):
                        dec_str = f" @{','.join(func['decorators'])}" if func['decorators'] else ""
                        type_node['children'].append({
                            'name': func['name'],
                            'module': module,
                            'line': func['line'],
                            'decorators': dec_str,
                            'color': cat_info['color'],
                            'calls': [c for c in func.get('calls', []) if c in all_func_names]
                        })
                
                if type_node['children']:
                    cat_node['children'].append(type_node)
        
        if cat_node['children']:
            tree_data['children'].append(cat_node)
    
    # Generate HTML
    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Function Tree - datumTableEditor</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'SF Mono', Consolas, monospace;
            background: #0d1117;
            color: #c9d1d9;
            margin: 0;
            padding: 20px;
        }}
        h1 {{
            text-align: center;
            color: #58a6ff;
            font-weight: 400;
            margin-bottom: 10px;
        }}
        .subtitle {{
            text-align: center;
            color: #8b949e;
            font-size: 14px;
            margin-bottom: 30px;
        }}
        #tree-container {{
            width: 100%;
            overflow-x: auto;
        }}
        .node {{
            cursor: pointer;
        }}
        .node circle {{
            stroke-width: 2px;
        }}
        .node text {{
            font-size: 12px;
            fill: #c9d1d9;
        }}
        .node--leaf text {{
            font-size: 11px;
            fill: #8b949e;
        }}
        .link {{
            fill: none;
            stroke: #30363d;
            stroke-width: 1.5px;
        }}
        .connection {{
            fill: none;
            stroke: #ff69b4;
            stroke-width: 1px;
            stroke-opacity: 0.4;
            pointer-events: none;
        }}
        .connection.highlight {{
            stroke-opacity: 0.9;
            stroke-width: 2px;
        }}
        .tooltip {{
            position: absolute;
            background: #161b22;
            border: 1px solid #30363d;
            padding: 10px 14px;
            border-radius: 6px;
            font-size: 12px;
            pointer-events: none;
            box-shadow: 0 8px 24px rgba(0,0,0,0.4);
        }}
        .tooltip strong {{
            color: #58a6ff;
        }}
        .stats {{
            display: flex;
            justify-content: center;
            gap: 30px;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }}
        .stat-box {{
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 15px 25px;
            text-align: center;
        }}
        .stat-value {{
            font-size: 28px;
            font-weight: bold;
            color: #58a6ff;
        }}
        .stat-label {{
            font-size: 12px;
            color: #8b949e;
            margin-top: 5px;
        }}
        .legend {{
            display: flex;
            justify-content: center;
            gap: 20px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 13px;
        }}
        .legend-dot {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }}
        #controls {{
            text-align: center;
            margin-bottom: 20px;
        }}
        #controls button {{
            background: #21262d;
            border: 1px solid #30363d;
            color: #c9d1d9;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            margin: 0 5px;
            font-size: 13px;
        }}
        #controls button:hover {{
            background: #30363d;
        }}
    </style>
</head>
<body>
    <h1>🌳 Function Tree</h1>
    <p class="subtitle">Functions clustered by logic type</p>
    
    <div class="stats">
        <div class="stat-box">
            <div class="stat-value">{len(all_funcs)}</div>
            <div class="stat-label">Total Functions</div>
        </div>
        <div class="stat-box">
            <div class="stat-value">{len(connections)}</div>
            <div class="stat-label">Call Connections</div>
        </div>
        <div class="stat-box">
            <div class="stat-value">{len([f for f in all_funcs if 'Effect' in f['decorators']])}</div>
            <div class="stat-label">Event Handlers</div>
        </div>
        <div class="stat-box">
            <div class="stat-value">{len([f for f in all_funcs if 'ui' in f['decorators'] or 'render' in f['decorators']])}</div>
            <div class="stat-label">UI Renderers</div>
        </div>
        <div class="stat-box">
            <div class="stat-value">{len(by_type)}</div>
            <div class="stat-label">Logic Types</div>
        </div>
    </div>
    
    <div class="legend">
        <div class="legend-item"><div class="legend-dot" style="background:#e74c3c"></div>Event Handlers</div>
        <div class="legend-item"><div class="legend-dot" style="background:#3498db"></div>UI Components</div>
        <div class="legend-item"><div class="legend-dot" style="background:#2ecc71"></div>Data Operations</div>
        <div class="legend-item"><div class="legend-dot" style="background:#9b59b6"></div>Processing</div>
        <div class="legend-item"><div class="legend-dot" style="background:#f39c12"></div>Utilities</div>
        <div class="legend-item"><div class="legend-dot" style="background:#ff69b4;opacity:0.6"></div>Function Calls</div>
    </div>
    
    <div id="controls">
        <button onclick="expandAll()">Expand All</button>
        <button onclick="collapseAll()">Collapse All</button>
        <button onclick="toggleConnections()">Toggle Connections</button>
        <button onclick="resetView()">Reset View</button>
    </div>
    
    <div id="tree-container"></div>
    <div class="tooltip" style="display:none"></div>
    
    <script>
        const treeData = {json.dumps(tree_data)};
        const connections = {json.dumps(connections)};
        let showConnections = true;
        
        const margin = {{top: 20, right: 120, bottom: 20, left: 180}};
        const width = Math.max(1400, window.innerWidth - 40);
        const baseHeight = 800;
        
        const svg = d3.select("#tree-container")
            .append("svg")
            .attr("width", width)
            .attr("height", baseHeight);
        
        const g = svg.append("g")
            .attr("transform", `translate(${{margin.left}},${{margin.top}})`);
        
        // Zoom
        const zoom = d3.zoom()
            .scaleExtent([0.3, 3])
            .on("zoom", (event) => g.attr("transform", event.transform));
        svg.call(zoom);
        
        const root = d3.hierarchy(treeData);
        root.x0 = baseHeight / 2;
        root.y0 = 0;
        
        // Collapse all except first level
        root.children.forEach(collapse);
        
        function collapse(d) {{
            if (d.children) {{
                d._children = d.children;
                d._children.forEach(collapse);
                d.children = null;
            }}
        }}
        
        function expand(d) {{
            if (d._children) {{
                d.children = d._children;
                d._children = null;
            }}
            if (d.children) {{
                d.children.forEach(expand);
            }}
        }}
        
        const tooltip = d3.select(".tooltip");
        
        function update(source) {{
            const treeLayout = d3.tree().nodeSize([22, 200]);
            treeLayout(root);
            
            // Compute new height
            let minY = Infinity, maxY = -Infinity;
            root.each(d => {{
                if (d.x < minY) minY = d.x;
                if (d.x > maxY) maxY = d.x;
            }});
            const newHeight = maxY - minY + margin.top + margin.bottom + 100;
            svg.attr("height", Math.max(baseHeight, newHeight));
            
            const nodes = root.descendants();
            const links = root.links();
            
            // Normalize y position
            nodes.forEach(d => {{ d.y = d.depth * 200; }});
            
            // Nodes
            const node = g.selectAll(".node")
                .data(nodes, d => d.data.name);
            
            const nodeEnter = node.enter()
                .append("g")
                .attr("class", d => "node" + (d.children || d._children ? "" : " node--leaf"))
                .attr("transform", d => `translate(${{source.y0 || 0}},${{source.x0 || 0}})`)
                .on("click", (event, d) => {{
                    if (d.children) {{
                        d._children = d.children;
                        d.children = null;
                    }} else if (d._children) {{
                        d.children = d._children;
                        d._children = null;
                    }}
                    update(d);
                }})
                .on("mouseover", (event, d) => {{
                    if (d.data.module) {{
                        const callsTo = (d.data.calls || []).slice(0, 10);
                        const calledBy = connections.filter(c => c.target === d.data.name).map(c => c.source).slice(0, 10);
                        let callInfo = '';
                        if (callsTo.length > 0) callInfo += `<br>Calls: ${{callsTo.join(', ')}}`;
                        if (calledBy.length > 0) callInfo += `<br>Called by: ${{calledBy.join(', ')}}`;
                        
                        tooltip.style("display", "block")
                            .html(`<strong>${{d.data.name}}</strong><br>
                                   Module: ${{d.data.module}}<br>
                                   Line: ${{d.data.line}}${{d.data.decorators || ''}}${{callInfo}}`)
                            .style("left", (event.pageX + 15) + "px")
                            .style("top", (event.pageY - 10) + "px");
                        
                        // Highlight connections
                        g.selectAll(".connection")
                            .classed("highlight", c => c.source === d.data.name || c.target === d.data.name);
                    }}
                }})
                .on("mouseout", () => {{
                    tooltip.style("display", "none");
                    g.selectAll(".connection").classed("highlight", false);
                }});
            
            nodeEnter.append("circle")
                .attr("r", d => d.children || d._children ? 6 : 4)
                .attr("fill", d => d.data.color || "#8b949e")
                .attr("stroke", d => d.children || d._children ? d.data.color || "#8b949e" : "none");
            
            nodeEnter.append("text")
                .attr("dy", "0.35em")
                .attr("x", d => d.children || d._children ? -12 : 10)
                .attr("text-anchor", d => d.children || d._children ? "end" : "start")
                .text(d => d.data.name)
                .style("fill", d => d.data.module ? "#8b949e" : "#c9d1d9");
            
            // Add count badge for parent nodes
            nodeEnter.filter(d => d._children || d.children)
                .append("text")
                .attr("class", "count")
                .attr("dy", "0.35em")
                .attr("x", 12)
                .style("fill", "#8b949e")
                .style("font-size", "10px")
                .text(d => {{
                    const count = (d._children || d.children || []).length;
                    return count > 0 ? `(${{count}})` : '';
                }});
            
            const nodeUpdate = nodeEnter.merge(node);
            
            nodeUpdate.transition()
                .duration(300)
                .attr("transform", d => `translate(${{d.y}},${{d.x}})`);
            
            node.exit()
                .transition()
                .duration(300)
                .attr("transform", d => `translate(${{source.y}},${{source.x}})`)
                .remove();
            
            // Links
            const link = g.selectAll(".link")
                .data(links, d => d.target.data.name);
            
            const linkEnter = link.enter()
                .insert("path", "g")
                .attr("class", "link")
                .attr("d", d => {{
                    const o = {{x: source.x0 || 0, y: source.y0 || 0}};
                    return diagonal(o, o);
                }});
            
            linkEnter.merge(link)
                .transition()
                .duration(300)
                .attr("d", d => diagonal(d.source, d.target));
            
            link.exit()
                .transition()
                .duration(300)
                .attr("d", d => {{
                    const o = {{x: source.x, y: source.y}};
                    return diagonal(o, o);
                }})
                .remove();
            
            nodes.forEach(d => {{
                d.x0 = d.x;
                d.y0 = d.y;
            }});
            
            // Draw connections between functions
            updateConnections();
        }}
        
        function updateConnections() {{
            // Build node position map
            const nodePositions = {{}};
            root.each(d => {{
                if (d.data.module) {{
                    nodePositions[d.data.name] = {{ x: d.x, y: d.y, visible: true }};
                }}
            }});
            
            // Filter to only visible connections
            const visibleConnections = showConnections ? connections.filter(c => 
                nodePositions[c.source] && nodePositions[c.target]
            ) : [];
            
            const conn = g.selectAll(".connection")
                .data(visibleConnections, d => d.source + '-' + d.target);
            
            conn.enter()
                .insert("path", ".node")
                .attr("class", "connection")
                .attr("d", d => {{
                    const s = nodePositions[d.source];
                    const t = nodePositions[d.target];
                    if (!s || !t) return "";
                    // Draw curved arc
                    const dx = t.y - s.y;
                    const dy = t.x - s.x;
                    const dr = Math.sqrt(dx * dx + dy * dy) * 0.8;
                    return `M${{s.y}},${{s.x}} A${{dr}},${{dr}} 0 0,1 ${{t.y}},${{t.x}}`;
                }});
            
            conn.transition()
                .duration(300)
                .attr("d", d => {{
                    const s = nodePositions[d.source];
                    const t = nodePositions[d.target];
                    if (!s || !t) return "";
                    const dx = t.y - s.y;
                    const dy = t.x - s.x;
                    const dr = Math.sqrt(dx * dx + dy * dy) * 0.8;
                    return `M${{s.y}},${{s.x}} A${{dr}},${{dr}} 0 0,1 ${{t.y}},${{t.x}}`;
                }});
            
            conn.exit().remove();
        }}
        
        function toggleConnections() {{
            showConnections = !showConnections;
            updateConnections();
        }}
        
        function diagonal(s, d) {{
            return `M ${{s.y}} ${{s.x}}
                    C ${{(s.y + d.y) / 2}} ${{s.x}},
                      ${{(s.y + d.y) / 2}} ${{d.x}},
                      ${{d.y}} ${{d.x}}`;
        }}
        
        function expandAll() {{
            root.each(d => {{
                if (d._children) {{
                    d.children = d._children;
                    d._children = null;
                }}
            }});
            update(root);
        }}
        
        function collapseAll() {{
            root.children.forEach(collapse);
            update(root);
        }}
        
        function resetView() {{
            svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity);
        }}
        
        update(root);
        
        // Initial slight zoom out for overview
        svg.call(zoom.transform, d3.zoomIdentity.translate(50, 100).scale(0.9));
    </script>
</body>
</html>
'''
    
    output = Path('qcmetric/function_tree.html')
    output.parent.mkdir(exist_ok=True)
    output.write_text(html)
    print(f"✅ Function tree saved to {output}")
    print(f"   {len(all_funcs)} functions in {len(by_type)} logic types")
    print(f"   {len(connections)} call connections between functions")


if __name__ == '__main__':
    main()
