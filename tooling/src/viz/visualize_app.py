#!/usr/bin/env python3
"""
Visualize app function relations as an interactive graph.
Generates an HTML file with a force-directed graph visualization.
"""

import ast
import json
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple, Any

# Try to import visualization libraries
try:
    from pyvis.network import Network
    HAS_PYVIS = True
except ImportError:
    HAS_PYVIS = False

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False


def get_function_details(filepath: Path) -> Dict[str, Any]:
    """Extract functions and their calls from a Python file."""
    with open(filepath, 'r') as f:
        content = f.read()
    tree = ast.parse(content)
    
    functions = {}
    
    # First pass: collect all function definitions
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            decorators = []
            for d in node.decorator_list:
                if hasattr(d, 'attr'):
                    decorators.append(d.attr)
                elif hasattr(d, 'id'):
                    decorators.append(d.id)
            
            # Get calls within this function
            calls = set()
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Name):
                        calls.add(child.func.id)
                    elif isinstance(child.func, ast.Attribute):
                        calls.add(child.func.attr)
            
            functions[node.name] = {
                'line': node.lineno,
                'decorators': decorators,
                'calls': list(calls)
            }
    
    return functions


def build_graph_data() -> Tuple[Dict, List, List]:
    """Build nodes and edges for the graph."""
    
    files_to_analyze = [
        ('src/server.py', 'server'),
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
    
    all_functions = {}  # func_name -> {module, decorators, calls, line}
    modules = {}  # module_name -> [func_names]
    
    for filepath, module_name in files_to_analyze:
        path = Path(filepath)
        if path.exists():
            try:
                funcs = get_function_details(path)
                modules[module_name] = list(funcs.keys())
                for fname, fdata in funcs.items():
                    full_name = f"{module_name}.{fname}"
                    all_functions[full_name] = {
                        'module': module_name,
                        'short_name': fname,
                        **fdata
                    }
            except Exception as e:
                print(f"Error analyzing {filepath}: {e}")
    
    # Build nodes
    nodes = []
    for full_name, data in all_functions.items():
        node_type = 'default'
        if data['decorators']:
            if 'Effect' in data['decorators']:
                node_type = 'effect'
            elif 'ui' in data['decorators'] or 'render' in data['decorators']:
                node_type = 'render'
            elif 'download' in data['decorators']:
                node_type = 'download'
        elif data['short_name'].startswith('_'):
            node_type = 'private'
        
        nodes.append({
            'id': full_name,
            'label': data['short_name'],
            'module': data['module'],
            'type': node_type,
            'decorators': data['decorators'],
            'line': data['line']
        })
    
    # Build edges (function calls)
    edges = []
    func_short_names = {}  # short_name -> full_name
    for n in nodes:
        func_short_names[n['label']] = n['id']
    
    for full_name, data in all_functions.items():
        for call in data['calls']:
            # Try to find the called function
            if call in func_short_names:
                edges.append({
                    'from': full_name,
                    'to': func_short_names[call],
                    'type': 'call'
                })
    
    return modules, nodes, edges


def generate_pyvis_graph(modules: Dict, nodes: List, edges: List, output_path: str):
    """Generate an interactive graph using pyvis."""
    
    # Create network
    net = Network(
        height="900px",
        width="100%",
        bgcolor="#1a1a2e",
        font_color="white",
        directed=True,
        select_menu=True,
        filter_menu=True
    )
    
    # Color scheme by module
    module_colors = {
        'server': '#e74c3c',      # Red
        'ui': '#3498db',          # Blue
        'config': '#9b59b6',      # Purple
        'config_instance': '#8e44ad',
        'datum': '#1abc9c',       # Teal
        'table_utils': '#2ecc71', # Green
        'pagination_utils': '#27ae60',
        'data_operations': '#f39c12',  # Orange
        'filter_utils': '#e67e22',
        'preset_utils': '#d35400',
        'modal_utils': '#c0392b',
        'column_utils': '#16a085',
        'event_handlers': '#2980b9',
        'process_mods': '#8e44ad',
    }
    
    # Node shapes by type
    type_shapes = {
        'effect': 'diamond',
        'render': 'star',
        'download': 'triangle',
        'private': 'dot',
        'default': 'dot'
    }
    
    # Add nodes
    for node in nodes:
        color = module_colors.get(node['module'], '#95a5a6')
        shape = type_shapes.get(node['type'], 'dot')
        size = 20 if node['type'] in ['effect', 'render'] else 15
        
        title = f"<b>{node['id']}</b><br>"
        title += f"Module: {node['module']}<br>"
        title += f"Line: {node['line']}<br>"
        if node['decorators']:
            title += f"Decorators: @{', @'.join(node['decorators'])}"
        
        net.add_node(
            node['id'],
            label=node['label'],
            color=color,
            shape=shape,
            size=size,
            title=title,
            group=node['module']
        )
    
    # Add edges
    for edge in edges:
        net.add_edge(
            edge['from'],
            edge['to'],
            color='#555555',
            arrows='to',
            smooth={'type': 'curvedCW', 'roundness': 0.2}
        )
    
    # Physics settings for better layout
    net.set_options("""
    {
        "physics": {
            "enabled": true,
            "forceAtlas2Based": {
                "gravitationalConstant": -100,
                "centralGravity": 0.01,
                "springLength": 200,
                "springConstant": 0.08,
                "damping": 0.4
            },
            "solver": "forceAtlas2Based",
            "stabilization": {
                "enabled": true,
                "iterations": 1000
            }
        },
        "nodes": {
            "font": {
                "size": 12,
                "face": "monospace"
            },
            "borderWidth": 2
        },
        "edges": {
            "smooth": {
                "type": "curvedCW",
                "roundness": 0.2
            },
            "arrows": {
                "to": {
                    "enabled": true,
                    "scaleFactor": 0.5
                }
            }
        },
        "interaction": {
            "hover": true,
            "navigationButtons": true,
            "keyboard": true
        }
    }
    """)
    
    # Save
    net.save_graph(output_path)
    print(f"✅ Interactive graph saved to {output_path}")


def generate_html_d3_graph(modules: Dict, nodes: List, edges: List, output_path: str):
    """Generate a custom D3.js force-directed graph (no dependencies needed)."""
    
    # Color scheme
    module_colors = {
        'server': '#e74c3c',
        'ui': '#3498db',
        'config': '#9b59b6',
        'config_instance': '#8e44ad',
        'datum': '#1abc9c',
        'table_utils': '#2ecc71',
        'pagination_utils': '#27ae60',
        'data_operations': '#f39c12',
        'filter_utils': '#e67e22',
        'preset_utils': '#d35400',
        'modal_utils': '#c0392b',
        'column_utils': '#16a085',
        'event_handlers': '#2980b9',
        'process_mods': '#8e44ad',
    }
    
    # Prepare data for D3
    graph_data = {
        'nodes': [{
            'id': n['id'],
            'label': n['label'],
            'module': n['module'],
            'type': n['type'],
            'color': module_colors.get(n['module'], '#95a5a6'),
            'decorators': n['decorators'],
            'line': n['line']
        } for n in nodes],
        'links': [{
            'source': e['from'],
            'target': e['to']
        } for e in edges]
    }
    
    html_content = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>App Function Graph - datumTableEditor</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        body {{
            margin: 0;
            background: #1a1a2e;
            font-family: 'Segoe UI', monospace;
            overflow: hidden;
        }}
        #graph {{
            width: 100vw;
            height: 100vh;
        }}
        .node {{
            cursor: pointer;
        }}
        .node text {{
            font-size: 10px;
            fill: white;
            pointer-events: none;
        }}
        .link {{
            stroke: #555;
            stroke-opacity: 0.6;
            fill: none;
        }}
        .tooltip {{
            position: absolute;
            background: rgba(0,0,0,0.9);
            color: white;
            padding: 10px;
            border-radius: 5px;
            font-size: 12px;
            pointer-events: none;
            max-width: 300px;
        }}
        #legend {{
            position: fixed;
            top: 10px;
            left: 10px;
            background: rgba(0,0,0,0.8);
            padding: 15px;
            border-radius: 8px;
            color: white;
            font-size: 12px;
            z-index: 100;
        }}
        #legend h3 {{
            margin: 0 0 10px 0;
            font-size: 14px;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            margin: 5px 0;
        }}
        .legend-color {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
        }}
        #controls {{
            position: fixed;
            top: 10px;
            right: 10px;
            background: rgba(0,0,0,0.8);
            padding: 15px;
            border-radius: 8px;
            color: white;
            z-index: 100;
        }}
        #controls button {{
            background: #3498db;
            border: none;
            color: white;
            padding: 8px 15px;
            margin: 5px;
            border-radius: 5px;
            cursor: pointer;
        }}
        #controls button:hover {{
            background: #2980b9;
        }}
        #stats {{
            position: fixed;
            bottom: 10px;
            left: 10px;
            background: rgba(0,0,0,0.8);
            padding: 10px 15px;
            border-radius: 8px;
            color: #aaa;
            font-size: 11px;
        }}
    </style>
</head>
<body>
    <div id="legend">
        <h3>📊 Modules</h3>
        <div class="legend-item"><div class="legend-color" style="background:#e74c3c"></div>server</div>
        <div class="legend-item"><div class="legend-color" style="background:#3498db"></div>ui</div>
        <div class="legend-item"><div class="legend-color" style="background:#9b59b6"></div>config</div>
        <div class="legend-item"><div class="legend-color" style="background:#1abc9c"></div>datum</div>
        <div class="legend-item"><div class="legend-color" style="background:#2ecc71"></div>utils</div>
        <div class="legend-item"><div class="legend-color" style="background:#f39c12"></div>data_ops</div>
        <h3 style="margin-top:15px">🔷 Node Types</h3>
        <div class="legend-item">◆ @Effect handler</div>
        <div class="legend-item">★ @ui renderer</div>
        <div class="legend-item">● function</div>
    </div>
    
    <div id="controls">
        <button onclick="resetZoom()">Reset View</button>
        <button onclick="toggleLabels()">Toggle Labels</button>
        <button onclick="togglePhysics()">Freeze/Unfreeze</button>
    </div>
    
    <div id="stats">
        Nodes: {len(nodes)} | Edges: {len(edges)} | Drag to move, scroll to zoom
    </div>
    
    <svg id="graph"></svg>
    <div class="tooltip" style="display:none"></div>
    
    <script>
        const data = {json.dumps(graph_data)};
        
        const width = window.innerWidth;
        const height = window.innerHeight;
        
        const svg = d3.select("#graph")
            .attr("width", width)
            .attr("height", height);
        
        const g = svg.append("g");
        
        // Zoom behavior
        const zoom = d3.zoom()
            .scaleExtent([0.1, 4])
            .on("zoom", (event) => g.attr("transform", event.transform));
        svg.call(zoom);
        
        // Arrow marker
        svg.append("defs").append("marker")
            .attr("id", "arrowhead")
            .attr("viewBox", "-0 -5 10 10")
            .attr("refX", 20)
            .attr("refY", 0)
            .attr("orient", "auto")
            .attr("markerWidth", 6)
            .attr("markerHeight", 6)
            .append("path")
            .attr("d", "M 0,-5 L 10,0 L 0,5")
            .attr("fill", "#555");
        
        // Force simulation
        const simulation = d3.forceSimulation(data.nodes)
            .force("link", d3.forceLink(data.links).id(d => d.id).distance(100))
            .force("charge", d3.forceManyBody().strength(-200))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .force("collision", d3.forceCollide().radius(30));
        
        // Links
        const link = g.append("g")
            .selectAll("path")
            .data(data.links)
            .join("path")
            .attr("class", "link")
            .attr("marker-end", "url(#arrowhead)");
        
        // Nodes
        const node = g.append("g")
            .selectAll("g")
            .data(data.nodes)
            .join("g")
            .attr("class", "node")
            .call(d3.drag()
                .on("start", dragstarted)
                .on("drag", dragged)
                .on("end", dragended));
        
        // Node shapes
        node.each(function(d) {{
            const el = d3.select(this);
            const size = d.type === 'effect' || d.type === 'render' ? 10 : 7;
            
            if (d.type === 'effect') {{
                // Diamond
                el.append("path")
                    .attr("d", d3.symbol().type(d3.symbolDiamond).size(size * 20))
                    .attr("fill", d.color)
                    .attr("stroke", "white")
                    .attr("stroke-width", 1);
            }} else if (d.type === 'render') {{
                // Star
                el.append("path")
                    .attr("d", d3.symbol().type(d3.symbolStar).size(size * 20))
                    .attr("fill", d.color)
                    .attr("stroke", "white")
                    .attr("stroke-width", 1);
            }} else {{
                // Circle
                el.append("circle")
                    .attr("r", size)
                    .attr("fill", d.color)
                    .attr("stroke", "white")
                    .attr("stroke-width", 1);
            }}
        }});
        
        // Labels
        let showLabels = true;
        const labels = node.append("text")
            .text(d => d.label)
            .attr("x", 12)
            .attr("y", 4);
        
        // Tooltip
        const tooltip = d3.select(".tooltip");
        
        node.on("mouseover", function(event, d) {{
            tooltip.style("display", "block")
                .html(`<b>${{d.id}}</b><br>
                       Module: ${{d.module}}<br>
                       Line: ${{d.line}}<br>
                       Type: ${{d.type}}<br>
                       ${{d.decorators.length ? 'Decorators: @' + d.decorators.join(', @') : ''}}`)
                .style("left", (event.pageX + 10) + "px")
                .style("top", (event.pageY - 10) + "px");
            
            // Highlight connected
            link.style("stroke", l => (l.source.id === d.id || l.target.id === d.id) ? "#fff" : "#555")
                .style("stroke-width", l => (l.source.id === d.id || l.target.id === d.id) ? 2 : 1);
        }})
        .on("mouseout", function() {{
            tooltip.style("display", "none");
            link.style("stroke", "#555").style("stroke-width", 1);
        }});
        
        // Tick
        simulation.on("tick", () => {{
            link.attr("d", d => {{
                const dx = d.target.x - d.source.x;
                const dy = d.target.y - d.source.y;
                return `M${{d.source.x}},${{d.source.y}} L${{d.target.x}},${{d.target.y}}`;
            }});
            node.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
        }});
        
        // Drag functions
        function dragstarted(event) {{
            if (!event.active) simulation.alphaTarget(0.3).restart();
            event.subject.fx = event.subject.x;
            event.subject.fy = event.subject.y;
        }}
        
        function dragged(event) {{
            event.subject.fx = event.x;
            event.subject.fy = event.y;
        }}
        
        function dragended(event) {{
            if (!event.active) simulation.alphaTarget(0);
            event.subject.fx = null;
            event.subject.fy = null;
        }}
        
        // Controls
        function resetZoom() {{
            svg.transition().duration(750).call(zoom.transform, d3.zoomIdentity);
        }}
        
        function toggleLabels() {{
            showLabels = !showLabels;
            labels.style("display", showLabels ? "block" : "none");
        }}
        
        let physicsEnabled = true;
        function togglePhysics() {{
            physicsEnabled = !physicsEnabled;
            if (physicsEnabled) {{
                simulation.alpha(0.3).restart();
            }} else {{
                simulation.stop();
            }}
        }}
    </script>
</body>
</html>
'''
    
    with open(output_path, 'w') as f:
        f.write(html_content)
    
    print(f"✅ D3.js interactive graph saved to {output_path}")


def main():
    print("=" * 60)
    print("GENERATING APP FUNCTION GRAPH VISUALIZATION")
    print("=" * 60)
    print()
    
    # Build graph data
    modules, nodes, edges = build_graph_data()
    
    print(f"📊 Graph Statistics:")
    print(f"   Modules: {len(modules)}")
    print(f"   Nodes (functions): {len(nodes)}")
    print(f"   Edges (calls): {len(edges)}")
    print()
    
    # Generate D3.js graph (no dependencies required)
    output_d3 = "qcmetric/app_graph.html"
    Path(output_d3).parent.mkdir(exist_ok=True)
    generate_html_d3_graph(modules, nodes, edges, output_d3)
    
    # Generate pyvis graph if available
    if HAS_PYVIS:
        output_pyvis = "qcmetric/app_graph_pyvis.html"
        generate_pyvis_graph(modules, nodes, edges, output_pyvis)
    else:
        print("💡 Install pyvis for an alternative visualization: pip install pyvis")
    
    print()
    print(f"🌐 Open {output_d3} in a browser to explore the graph!")


if __name__ == '__main__':
    main()
