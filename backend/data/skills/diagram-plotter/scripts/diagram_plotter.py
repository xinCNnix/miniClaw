#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagram Plotter - Generate diagrams from text descriptions

Supports:
- Architecture diagrams (hierarchy)
- Flowcharts (flow)
- Network topology (network)
- Mind maps (mindmap)
- UML diagrams (uml)
"""

import argparse
import os
import sys
import re
from pathlib import Path

# Ensure UTF-8 encoding for file operations
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

try:
    from graphviz import Digraph
except ImportError:
    print("Error: graphviz Python library not installed.")
    print("Run: pip install graphviz>=0.20.0")
    sys.exit(1)


# Auto-detect available Chinese font on the system
def detect_chinese_font() -> str:
    """Detect the best available Chinese font for Graphviz rendering."""
    import os

    known_fonts = [
        ("msyh.ttc", "Microsoft YaHei"),
        ("msyhbd.ttc", "Microsoft YaHei"),
        ("simhei.ttf", "SimHei"),
        ("simsun.ttc", "SimSun"),
        ("simkai.ttf", "KaiTi"),
        ("STZHONGS.TTF", "STZhongsong"),
        ("STKAITI.TTF", "STKaiti"),
        ("NotoSansCJK-Regular.ttc", "Noto Sans CJK SC"),
        ("WenQuanYi Micro Hei", "WenQuanYi Micro Hei"),
        ("Droid Sans Fallback", "Droid Sans Fallback"),
    ]

    font_dirs = []
    if sys.platform == "win32":
        windir = os.environ.get("WINDIR", r"C:\Windows")
        font_dirs.append(os.path.join(windir, "Fonts"))
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        if local_appdata:
            font_dirs.append(os.path.join(local_appdata, "Microsoft", "Windows", "Fonts"))
    else:
        font_dirs.extend([
            "/usr/share/fonts",
            "/usr/local/share/fonts",
            "/System/Library/Fonts",
            os.path.expanduser("~/.fonts"),
            os.path.expanduser("~/.local/share/fonts"),
        ])

    for directory in font_dirs:
        if not os.path.isdir(directory):
            continue
        for fname, fontname in known_fonts:
            if os.path.exists(os.path.join(directory, fname)):
                return fontname

    return "Sans"


# Check for system Graphviz binaries
def check_graphviz_installed():
    """Check if Graphviz binaries are available"""
    import shutil
    for cmd in ['dot', 'circo', 'fdp', 'neato']:
        if shutil.which(cmd):
            return True
    return False


def parse_simple_format(content: str) -> list:
    """
    Parse simple arrow format into list of edges.

    Supports:
    - A -> B -> C
    - A -> B; B -> C
    - A <-> B
    - A -[label]-> B
    """
    edges = []

    # Split by semicolons or newlines
    statements = re.split(r'[;\n]', content)

    for stmt in statements:
        stmt = stmt.strip()
        if not stmt:
            continue

        # Parse bidirectional edges (A <-> B)
        if '<->' in stmt:
            parts = stmt.split('<->')
            if len(parts) == 2:
                edges.append((parts[0].strip(), parts[1].strip(), None, True))
                edges.append((parts[1].strip(), parts[0].strip(), None, True))
            continue

        # Parse labeled edges (A -[label]-> B)
        labeled_match = re.match(r'(.+?)\s*-\[(.+?)\]->\s*(.+)', stmt)
        if labeled_match:
            src, label, dst = labeled_match.groups()
            edges.append((src.strip(), dst.strip(), label.strip(), False))
            continue

        # Parse chain (A -> B -> C) and multiple targets (A -> B, C, D)
        if '->' in stmt:
            parts = [p.strip() for p in stmt.split('->')]
            for i in range(len(parts) - 1):
                src = parts[i]
                # Check if destination contains comma (multiple targets)
                if ',' in parts[i + 1]:
                    # Split by comma and create edges to each target
                    targets = [t.strip() for t in parts[i + 1].split(',')]
                    for target in targets:
                        if target:
                            edges.append((src, target, None, False))
                else:
                    edges.append((src, parts[i + 1], None, False))

    return edges


def generate_dot_code(
    edges: list,
    diagram_type: str = "hierarchy",
    title: str = "",
    shape: str = "box",
    color: str = "lightblue",
    direction: str = "TB",
) -> str:
    """
    Generate Graphviz DOT code from edges.

    Args:
        edges: List of (src, dst, label, bidirectional) tuples
        diagram_type: Type of diagram
        title: Diagram title
        shape: Node shape
        color: Node color
        direction: Graph direction (TB, LR, BT, RL)

    Returns:
        DOT code as string
    """
    # Map diagram types to layout engines
    layout_engines = {
        "hierarchy": "dot",
        "flow": "dot",
        "network": "fdp",
        "mindmap": "circo",
        "uml": "dot",
    }

    # Map diagram types to shapes
    shape_map = {
        "hierarchy": "box",
        "flow": "box",
        "network": "ellipse",
        "mindmap": "ellipse",
        "uml": "record",
    }

    engine = layout_engines.get(diagram_type, "dot")
    node_shape = shape if shape != "default" else shape_map.get(diagram_type, "box")
    cn_font = detect_chinese_font()

    # Build DOT code — graph-level fontname ensures title/label renders correctly
    lines = [
        f"digraph G {{",
        f"    rankdir={direction};",
        f'    fontname="{cn_font}";',
        f"    node [shape={node_shape}, style=filled, fillcolor={color}, fontname=\"{cn_font}\"];",
        f'    edge [fontname="{cn_font}"];',
    ]

    if title:
        lines.append(f'    label="{title}";')
        lines.append(f'    fontsize=20;')
        lines.append(f'    labelloc=top;')

    # Add edges
    for src, dst, label, bidirectional in edges:
        if label:
            line = f'    "{src}" -> "{dst}" [label="{label}"];'
        else:
            line = f'    "{src}" -> "{dst}";'

        if bidirectional:
            line = line.replace('->', '->', 1).replace('->', '->', 1)
            line = line.replace('->', '->', 1)  # Keep as directed but add both directions

        lines.append(line)

    lines.append("}")

    return "\n".join(lines)


# Script: backend/data/skills/diagram-plotter/scripts/diagram_plotter.py
# backend/ root is 5 levels up: scripts/ → diagram-plotter/ → skills/ → data/ → backend/
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_PROJECT_ROOT = _BACKEND_ROOT.parent  # project root (miniclaw/)


def _resolve_output_path(output_path: str) -> str:
    """Resolve output path: absolute as-is, relative against project_root/outputs/."""
    p = Path(output_path)
    if p.is_absolute():
        return str(p)
    # Always place output in outputs/ unless path already includes it
    if not output_path.startswith("outputs" + os.sep) and not output_path.startswith("outputs/"):
        output_path = f"outputs{os.sep}{output_path}"
    return str(_PROJECT_ROOT / output_path)


def create_diagram(
    content: str,
    diagram_type: str = "hierarchy",
    title: str = "",
    shape: str = "box",
    color: str = "lightblue",
    direction: str = "TB",
    layout: str = None,
    output_path: str = "output.svg",
    save_dot: bool = True,
    output_format: str = "svg",
) -> str:
    """
    Create a diagram from text description.

    Args:
        content: Text description of the diagram
        diagram_type: Type of diagram
        title: Diagram title
        shape: Node shape
        color: Node color
        direction: Graph direction
        layout: Override layout engine
        output_path: Output file path
        save_dot: Whether to save DOT source file

    Returns:
        Path to created diagram
    """
    # Check Graphviz installation
    if not check_graphviz_installed():
        print("Warning: Graphviz binaries not found.")
        print("Please install Graphviz:")
        print("  - Windows: winget install Graphviz.Graphviz")
        print("  - macOS: brew install graphviz")
        print("  - Linux: sudo apt install graphviz")
        print("Falling back to DOT file generation only...")

    # Parse content into edges
    edges = parse_simple_format(content)

    if not edges:
        print("Error: No edges found in content. Please check your format.")
        print("Example: 'A -> B -> C' or 'A -> B; B -> C'")
        return None

    # Generate DOT code
    dot_code = generate_dot_code(
        edges,
        diagram_type=diagram_type,
        title=title,
        shape=shape,
        color=color,
        direction=direction,
    )

    # Determine layout engine
    layout_engines = {
        "hierarchy": "dot",
        "flow": "dot",
        "network": "fdp",
        "mindmap": "circo",
        "uml": "dot",
    }
    engine = layout or layout_engines.get(diagram_type, "dot")

    # Create diagram using graphviz
    try:
        # Parse DOT code
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dot', delete=False, encoding='utf-8') as f:
            f.write(dot_code)
            temp_dot = f.name

        # Render diagram
        dot = Digraph()
        dot.body = [line.strip() for line in dot_code.split('\n') if line.strip() and not line.strip().startswith('digraph') and not line.strip() == '}']

        # Use source file approach
        from graphviz import Source
        src = Source(dot_code)
        src.format = 'png'

        # Render
        src.format = output_format

        # Resolve output path against project backend root
        abs_output = _resolve_output_path(output_path)
        base_name = str(Path(abs_output).with_suffix(''))
        output_file = src.render(
            filename=base_name,
            cleanup=True,
            engine=engine if check_graphviz_installed() else 'dot'
        )

        print(f"[OK] Created diagram: {output_file}")
        print(f"  - Type: {diagram_type}")
        print(f"  - Engine: {engine}")
        print(f"  - Format: {output_format.upper()}")
        print(f"  - Nodes: {len(set([e[0] for e in edges] + [e[1] for e in edges]))}")
        print(f"  - Edges: {len(edges)}")

        # Save DOT file if requested
        if save_dot:
            dot_rel_path = output_path.replace('.png', '.dot').replace('.svg', '.dot').replace('.pdf', '.dot')
            dot_path = _resolve_output_path(dot_rel_path)
            Path(dot_path).parent.mkdir(parents=True, exist_ok=True)
            with open(dot_path, 'w', encoding='utf-8') as f:
                f.write(dot_code)
            print(f"  - DOT source: {dot_path}")

        return output_file

    except Exception as e:
        print(f"Error rendering diagram: {e}")
        print("Saving DOT file for manual rendering...")

        # Save DOT file anyway
        dot_rel_path = output_path.replace('.png', '.dot').replace('.svg', '.dot').replace('.pdf', '.dot')
        dot_path = _resolve_output_path(dot_rel_path)
        Path(dot_path).parent.mkdir(parents=True, exist_ok=True)
        with open(dot_path, 'w', encoding='utf-8') as f:
            f.write(dot_code)

        print(f"[OK] DOT file saved: {dot_path}")
        print("You can render it manually using:")
        print(f"  dot -Tpng {dot_path} -o output.png")

        return dot_path


def create_diagram_from_file(
    input_path: str,
    layout: str = "dot",
    output_path: str = "output.png",
) -> str:
    """
    Create diagram from existing DOT file.

    Args:
        input_path: Path to DOT file
        layout: Layout engine
        output_path: Output file path

    Returns:
        Path to created diagram
    """
    input_file = Path(input_path)
    if not input_file.exists():
        print(f"Error: Input file not found: {input_path}")
        return None

    # Read DOT code
    with open(input_file, 'r', encoding='utf-8') as f:
        dot_code = f.read()

    try:
        from graphviz import Source
        src = Source(dot_code)
        src.format = 'png'

        abs_output = _resolve_output_path(output_path)
        output_file = src.render(
            filename=str(Path(abs_output).with_suffix('')),
            cleanup=True,
            engine=layout if check_graphviz_installed() else 'dot'
        )

        print(f"[OK] Created diagram: {output_file}")
        print(f"  - Input: {input_path}")
        print(f"  - Engine: {layout}")

        return output_file

    except Exception as e:
        print(f"Error rendering diagram: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Create diagrams from text descriptions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Architecture diagram
  python diagram_plotter.py --type hierarchy --content "用户 -> API网关 -> 服务A, 服务B"

  # Flowchart
  python diagram_plotter.py --type flow --content "开始 -> 登录 -> 验证 -> 成功"

  # Mind map
  python diagram_plotter.py --type mindmap --content "主题 -> 子主题1, 子主题2, 子主题3"

  # From DOT file
  python diagram_plotter.py --input diagram.dot --output custom.png
        """
    )

    parser.add_argument(
        "--type",
        default="hierarchy",
        choices=["hierarchy", "flow", "network", "mindmap", "uml"],
        help="Diagram type (default: hierarchy)"
    )

    parser.add_argument(
        "--content",
        help="Text description of the diagram"
    )

    parser.add_argument(
        "--input",
        help="Input DOT file (overrides --content)"
    )

    parser.add_argument(
        "--title",
        help="Diagram title"
    )

    parser.add_argument(
        "--shape",
        default="box",
        choices=["box", "ellipse", "diamond", "circle", "record", "none"],
        help="Node shape (default: box)"
    )

    parser.add_argument(
        "--color",
        default="lightblue",
        help="Node color (default: lightblue)"
    )

    parser.add_argument(
        "--direction",
        default="TB",
        choices=["TB", "LR", "BT", "RL"],
        help="Graph direction (default: TB - top to bottom)"
    )

    parser.add_argument(
        "--layout",
        choices=["dot", "neato", "fdp", "circo", "twopi", "osage"],
        help="Override layout engine"
    )

    parser.add_argument(
        "--output",
        default="output.svg",
        help="Output file path (default: output.svg). Supports: .png, .svg, .pdf"
    )

    parser.add_argument(
        "--format",
        choices=["png", "svg", "pdf"],
        default="svg",
        help="Output format (default: svg - vector graphics, higher quality)"
    )

    args = parser.parse_args()

    # Check if content or input is provided
    if not args.input and not args.content:
        print("Error: Please provide --content or --input")
        parser.print_help()
        sys.exit(1)

    try:
        if args.input:
            # Render from DOT file
            result = create_diagram_from_file(
                input_path=args.input,
                layout=args.layout or "dot",
                output_path=args.output,
            )
        else:
            # Create from text description
            result = create_diagram(
                content=args.content,
                diagram_type=args.type,
                title=args.title or "",
                shape=args.shape,
                color=args.color,
                direction=args.direction,
                layout=args.layout,
                output_path=args.output,
                save_dot=True,
                output_format=args.format,
            )

        if result:
            print(f"\n[SUCCESS] Diagram created: {result}")
        else:
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
