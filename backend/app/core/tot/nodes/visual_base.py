"""
Visual Base — 通用图片生成底座

分析 reduced_json，生成视觉需求清单，路由到对应 skill，
返回统一的 image_paths 列表。
"""

import asyncio
import csv
import json
import logging
from pathlib import Path
from typing import List, Dict, Any

from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

# 路由表：type -> skill_name
VISUAL_ROUTES = {
    "chart": "chart-plotter",
    "diagram": "diagram-plotter",
}


async def generate_visuals(
    reduced_json: dict,
    user_query: str,
    llm,
) -> List[str]:
    """
    分析 reduced_json，生成视觉需求，路由到对应 skill，返回图片路径列表。

    Returns:
        image_paths: 生成的图片文件路径列表
    """
    # Step 1: LLM 分析，生成 visual_requests
    visual_requests = await _analyze_visual_needs(reduced_json, user_query, llm)

    if not visual_requests:
        logger.info("No visual needs identified, skipping visual generation")
        return []

    logger.info(f"Generated {len(visual_requests)} visual requests")

    # Step 2: 并发生成所有视觉内容
    tasks = [_route_and_generate(req) for req in visual_requests]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Step 3: 收集成功的图片路径
    image_paths = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning(f"Visual generation failed for request {i}: {result}")
        elif result:
            image_paths.append(result)

    logger.info(f"Generated {len(image_paths)} visual assets")
    return image_paths


async def _analyze_visual_needs(
    reduced_json: dict,
    user_query: str,
    llm,
) -> List[Dict[str, Any]]:
    """
    LLM 分析 reduced_json，决定需要生成哪些图表。
    返回 visual_requests 列表。
    """
    payload = json.dumps(reduced_json, ensure_ascii=False)[:8000]

    prompt = f"""分析以下研究数据，判断需要生成哪些图表来增强报告的可读性。

研究课题: {user_query}

研究数据:
{payload}

请返回 JSON 数组，每个元素是一个图表需求：
- type: "chart" (数据图表) 或 "diagram" (架构/流程图)
- 对于 chart: 还需要 chart_type (bar/line/scatter/pie), title, data (基于研究数据提取的数值)
- 对于 diagram: 还需要 diagram_type (hierarchy/flow/network/mindmap), content (节点关系描述)

最多生成 3 个图表。只在数据确实适合可视化时才生成。
返回纯 JSON 数组，不要其他文字。如果没有适合可视化的数据，返回空数组 []。"""

    bound_llm = llm.bind(max_tokens=2000)

    response = await bound_llm.ainvoke([HumanMessage(content=prompt)])

    try:
        # 提取 JSON
        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except (json.JSONDecodeError, IndexError) as e:
        logger.warning(f"Failed to parse visual requests: {e}")
        return []


async def _route_and_generate(request: Dict[str, Any]) -> str | None:
    """
    根据请求类型路由到对应 skill，生成图片，返回文件路径。
    """
    req_type = request.get("type", "")

    if req_type not in VISUAL_ROUTES:
        logger.warning(f"Unknown visual type: {req_type}, skipping")
        return None

    try:
        if req_type == "chart":
            return await _generate_chart(request)
        elif req_type == "diagram":
            return await _generate_diagram(request)
    except Exception as e:
        logger.error(f"Visual generation error ({req_type}): {e}", exc_info=True)
        return None

    return None


async def _generate_chart(request: Dict[str, Any]) -> str:
    """
    调用 chart-plotter skill 生成数据图表。
    """
    scripts_dir = Path("backend/data/skills/chart-plotter/scripts")
    output_dir = Path("backend/data/outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    chart_type = request.get("chart_type", "bar")
    title = request.get("title", "chart")
    data = request.get("data", {})

    # 生成 CSV 数据文件
    csv_path = output_dir / "_chart_temp.csv"
    _write_chart_csv(data, csv_path)

    output_name = f"chart_{hash(title) % 10000:04d}"

    cmd = [
        "python", str(scripts_dir / "plot.py"),
        "--input", str(csv_path),
        "--type", chart_type,
        "--title", title,
        "--output-svg", str(output_dir / f"{output_name}.svg"),
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await process.communicate()

    svg_path = output_dir / f"{output_name}.svg"
    if svg_path.exists():
        return str(svg_path)

    # fallback: 尝试 output.png
    png_path = output_dir / f"{output_name}.png"
    if png_path.exists():
        return str(png_path)

    raise FileNotFoundError(f"Chart output not found: {output_name}")


async def _generate_diagram(request: Dict[str, Any]) -> str:
    """
    调用 diagram-plotter skill 生成架构/流程图。
    """
    scripts_dir = Path("backend/data/skills/diagram-plotter/scripts")
    output_dir = Path("backend/data/outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    diagram_type = request.get("diagram_type", "flow")
    content = request.get("content", "")
    title = request.get("title", "diagram")

    output_name = f"diagram_{hash(title) % 10000:04d}"

    cmd = [
        "python", str(scripts_dir / "diagram_plotter.py"),
        "--type", diagram_type,
        "--content", content,
        "--title", title,
        "--format", "svg",
        "--output", str(output_dir / output_name),
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await process.communicate()

    svg_path = output_dir / f"{output_name}.svg"
    if svg_path.exists():
        return str(svg_path)

    png_path = output_dir / f"{output_name}.png"
    if png_path.exists():
        return str(png_path)

    raise FileNotFoundError(f"Diagram output not found: {output_name}")


def _write_chart_csv(data: Any, csv_path: Path) -> None:
    """将图表数据写入临时 CSV 文件。"""
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if isinstance(data, dict):
            if "labels" in data and "values" in data:
                writer.writerow(["label", "value"])
                for label, value in zip(data["labels"], data["values"]):
                    writer.writerow([label, value])
            else:
                writer.writerow(["key", "value"])
                for k, v in data.items():
                    writer.writerow([k, v])
        elif isinstance(data, list):
            if data and isinstance(data[0], dict):
                keys = list(data[0].keys())
                writer.writerow(keys)
                for row in data:
                    writer.writerow([row.get(k, "") for k in keys])
            else:
                for row in data:
                    writer.writerow(row if isinstance(row, list) else [row])
