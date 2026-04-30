"""
Chart Render Node

Post-processes the writer's draft by parsing chart/diagram placeholders,
invoking the appropriate skill (chart-plotter, geometry-plotter, diagram-plotter)
to generate images, registering them with MediaRegistry, and replacing
placeholders with markdown image references.
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.core.tot.state import ToTState

logger = logging.getLogger(__name__)

_CHART_RE = re.compile(r'<!--\s*CHART:\s*(\{.*?\})\s*-->', re.DOTALL)
_GEO_RE = re.compile(r'<!--\s*GEO_PLOT:\s*(\{.*?\})\s*-->', re.DOTALL)
_DIAGRAM_RE = re.compile(r'<!--\s*DIAGRAM:\s*(\{.*?\})\s*-->', re.DOTALL)


async def chart_render_node(state: ToTState) -> Dict:
    """Parse chart placeholders in the draft and generate images.

    Scans the draft for <!-- CHART: {...} -->, <!-- GEO_PLOT: {...} -->,
    and <!-- DIAGRAM: {...} --> placeholders. For each, generates the
    corresponding image, registers it with MediaRegistry, and replaces
    the placeholder with a markdown image reference.
    """
    task_mode = state.get("task_mode", "standard")
    draft = state.get("draft", "")

    if task_mode != "research" or not draft:
        return {}

    chart_placeholders = list(_CHART_RE.finditer(draft))
    geo_placeholders = list(_GEO_RE.finditer(draft))
    diagram_placeholders = list(_DIAGRAM_RE.finditer(draft))

    total = len(chart_placeholders) + len(geo_placeholders) + len(diagram_placeholders)
    if total == 0:
        logger.debug("chart_render_node: no placeholders found, passing through")
        return {}

    logger.info(f"chart_render_node: found {total} chart placeholders")

    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)

    replacements: List[Tuple[re.Match, str]] = []

    for match in chart_placeholders:
        try:
            spec = json.loads(match.group(1))
            img_ref = await _render_chart(spec, output_dir, state)
            if img_ref:
                replacements.append((match, img_ref))
        except Exception as exc:
            logger.warning(f"chart_render_node: CHART render failed: {exc}")
            replacements.append((match, _fallback_text(match.group(0))))

    for match in geo_placeholders:
        try:
            spec = json.loads(match.group(1))
            img_ref = await _render_geo(spec, output_dir, state)
            if img_ref:
                replacements.append((match, img_ref))
        except Exception as exc:
            logger.warning(f"chart_render_node: GEO_PLOT render failed: {exc}")
            replacements.append((match, _fallback_text(match.group(0))))

    for match in diagram_placeholders:
        try:
            spec = json.loads(match.group(1))
            img_ref = await _render_diagram(spec, output_dir, state)
            if img_ref:
                replacements.append((match, img_ref))
        except Exception as exc:
            logger.warning(f"chart_render_node: DIAGRAM render failed: {exc}")
            replacements.append((match, _fallback_text(match.group(0))))

    if not replacements:
        return {}

    new_draft = draft
    for match, replacement in sorted(replacements, key=lambda x: x[0].start(), reverse=True):
        new_draft = new_draft[:match.start()] + replacement + new_draft[match.end():]

    logger.info(
        f"chart_render_node: replaced {len(replacements)}/{total} placeholders, "
        f"draft length {len(draft)} -> {len(new_draft)}"
    )

    return {"draft": new_draft}


async def _render_chart(spec: Dict, output_dir: Path, state: ToTState) -> Optional[str]:
    """Render a data chart using chart-plotter skill."""
    chart_type = spec.get("type", "bar")
    title = spec.get("title", "Chart")
    data_csv = spec.get("data", "")
    xlabel = spec.get("xlabel", "")
    ylabel = spec.get("ylabel", "")
    name = _safe_filename(title)

    csv_path = output_dir / f"_chart_{name}.csv"
    csv_path.write_text(data_csv.replace("\\n", "\n"), encoding="utf-8")

    cmd_parts = [
        "python", "data/skills/chart-plotter/scripts/plot.py",
        "--input", str(csv_path),
        "--type", chart_type,
        "--title", f'"{title}"',
        "--output-svg", f"{name}.svg",
    ]
    if xlabel:
        cmd_parts.extend(["--xlabel", f'"{xlabel}"'])
    if ylabel:
        cmd_parts.extend(["--ylabel", f'"{ylabel}"'])

    command = " ".join(cmd_parts)
    result = await _run_terminal(command, state)
    if not result:
        return None

    svg_path = output_dir / f"{name}.svg"
    if not svg_path.exists():
        logger.warning(f"chart_render_node: SVG not found at {svg_path}")
        return None

    return await _register_image(svg_path, state, title)


async def _render_geo(spec: Dict, output_dir: Path, state: ToTState) -> Optional[str]:
    """Render a math/geometry plot using geometry-plotter skill via python_repl."""
    expr = spec.get("expr", "x")
    x_range = spec.get("x_range", [-5, 5])
    title = spec.get("title", "Plot")
    latex_label = spec.get("latex_label", "")
    name = _safe_filename(title)

    code = (
        "import sys; sys.path.insert(0, 'data/skills/geometry-plotter/scripts')\n"
        "from handler import draw\n"
        f"result = draw(\n"
        f"    expr={repr(expr)},\n"
        f"    x_range={repr(tuple(x_range))},\n"
        f"    title={repr(title)},\n"
        f"    latex_label={repr(latex_label)},\n"
        f"    save_name={repr(name)},\n"
        ")\n"
        "print(result)\n"
    )

    result = await _run_python_repl(code, state)
    if not result:
        return None

    for ext in (".svg", ".png"):
        candidate = Path("outputs") / f"{name}{ext}"
        if candidate.exists():
            return await _register_image(candidate, state, title)

    logger.warning(f"chart_render_node: geo plot output not found for {name}")
    return None


async def _render_diagram(spec: Dict, output_dir: Path, state: ToTState) -> Optional[str]:
    """Render an architecture/flow diagram using diagram-plotter skill."""
    diag_type = spec.get("type", "flow")
    title = spec.get("title", "Diagram")
    content = spec.get("content", "")
    direction = spec.get("direction", "TB")
    shape = spec.get("shape", "box")
    name = _safe_filename(title)

    cmd_parts = [
        "python", "data/skills/diagram-plotter/scripts/diagram_plotter.py",
        "--type", diag_type,
        "--content", f'"{content}"',
        "--title", f'"{title}"',
        "--direction", direction,
        "--shape", shape,
        "--format", "svg",
        "--output", f"{name}.svg",
    ]

    command = " ".join(cmd_parts)
    result = await _run_terminal(command, state)
    if not result:
        return None

    svg_path = output_dir / f"{name}.svg"
    if not svg_path.exists():
        logger.warning(f"chart_render_node: diagram SVG not found at {svg_path}")
        return None

    return await _register_image(svg_path, state, title)


async def _run_terminal(command: str, state: ToTState) -> Optional[str]:
    """Execute a command via the terminal tool from state."""
    tools = state.get("tools", [])
    terminal_tool = None
    for tool in tools:
        if hasattr(tool, "name") and tool.name == "terminal":
            terminal_tool = tool
            break

    if not terminal_tool:
        logger.warning("chart_render_node: terminal tool not found in state")
        return None

    try:
        result = await terminal_tool.ainvoke({"command": command})
        return str(result) if result else None
    except Exception as exc:
        logger.warning(f"chart_render_node: terminal command failed: {exc}")
        return None


async def _run_python_repl(code: str, state: ToTState) -> Optional[str]:
    """Execute Python code via the python_repl tool from state."""
    tools = state.get("tools", [])
    repl_tool = None
    for tool in tools:
        if hasattr(tool, "name") and tool.name == "python_repl":
            repl_tool = tool
            break

    if not repl_tool:
        logger.warning("chart_render_node: python_repl tool not found in state")
        return None

    try:
        result = await repl_tool.ainvoke({"code": code})
        return str(result) if result else None
    except Exception as exc:
        logger.warning(f"chart_render_node: python_repl failed: {exc}")
        return None


async def _register_image(file_path: Path, state: ToTState, description: str) -> Optional[str]:
    """Register an image file with MediaRegistry and return markdown reference."""
    try:
        from app.core.media import get_registry

        registry = get_registry()
        session_id = state.get("session_id")

        entry = registry.register(
            file_path=file_path,
            source="chart_render_node",
            session_id=session_id,
            description=description,
        )

        media_url = f"/api/media/{entry.media_id}"
        logger.info(f"chart_render_node: registered image {entry.media_id} -> {media_url}")
        return f"![{description}]({media_url})"

    except Exception as exc:
        logger.error(f"chart_render_node: MediaRegistry failed: {exc}")
        return None


def _fallback_text(original: str) -> str:
    """Generate fallback text when image rendering fails."""
    return "\n> [图表生成失败]\n"


def _safe_filename(title: str) -> str:
    """Convert a title to a safe filename."""
    safe = re.sub(r'[^\w]', '_', title)
    safe = re.sub(r'_+', '_', safe).strip('_')
    return safe[:40] if safe else "chart"
