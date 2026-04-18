"""
ToT Skill Orchestrator

当 thought_executor 检测到 read_file 读取 SKILL.md 时，
自动解析 SKILL.md 内容并执行对应的 skill 脚本或模块。
"""

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.tools import BaseTool

from app.core.streaming.image_embedder import embed_output_images, embed_output_images_v2

# MediaRegistry integration (optional — graceful fallback if unavailable)
try:
    from app.core.media import register_file
except ImportError:
    register_file = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def _register_embedded_images(result_str: str) -> None:
    """Scan result text for image file paths and register them with MediaRegistry.

    Looks for paths matching common output patterns and registers any that
    exist on disk.

    Args:
        result_str: Tool/skill output text that may contain image path references.
    """
    if not register_file:
        return
    try:
        import re as _re
        from pathlib import Path as _Path
        for match in _re.finditer(
            r'(?:outputs?[/\\]|data[/\\]outputs?[/\\])[\w\-]+\.(?:png|jpg|jpeg|gif|webp|svg)',
            result_str, _re.IGNORECASE,
        ):
            img_path = _Path(match.group(0))
            if img_path.exists():
                try:
                    register_file(str(img_path), source="skill_orchestrator")
                except Exception:
                    pass
    except Exception:
        pass


def is_skill_file(path: str) -> bool:
    """检查路径是否指向 SKILL.md 文件。

    Args:
        path: 文件路径字符串。

    Returns:
        True 如果路径包含 skills/ 和 SKILL.md。
    """
    if not path:
        return False
    normalized = path.replace("\\", "/").lower()
    return "skill.md" in normalized and "skills/" in normalized


def extract_skill_name(path: str) -> Optional[str]:
    """从 SKILL.md 路径提取 skill 名称。

    Args:
        path: SKILL.md 文件路径。

    Returns:
        skill 名称，例如 'arxiv-search'，失败返回 None。

    Examples:
        >>> extract_skill_name("data/skills/arxiv-search/SKILL.md")
        'arxiv-search'
    """
    normalized = path.replace("\\", "/")
    parts = normalized.split("/")
    for i, part in enumerate(parts):
        if part.lower() == "skills" and i + 1 < len(parts):
            return parts[i + 1]
    return None


def detect_skill_type(skill_name: str, skills_dir: Path) -> str:
    """检测 skill 是 module 还是 script 类型。

    Args:
        skill_name: skill 名称。
        skills_dir: skills 根目录路径。

    Returns:
        "module" 或 "script"。
    """
    handler_path = skills_dir / skill_name / "scripts" / "handler.py"
    if handler_path.exists():
        try:
            content = handler_path.read_text(encoding="utf-8")
            if "async def run" in content or "def run" in content:
                return "module"
        except Exception:
            pass
    return "script"


def extract_script_path(
    skill_name: str,
    skill_content: str,
    skills_dir: Path,
) -> Optional[str]:
    """提取 skill 脚本的完整路径。

    优先搜索 scripts/ 目录获取可验证的完整路径，
    回退到从 SKILL.md bash 代码块中提取。

    Args:
        skill_name: skill 名称。
        skill_content: SKILL.md 文件内容。
        skills_dir: skills 根目录路径。

    Returns:
        脚本路径字符串，未找到返回 None。
    """
    # 方法1（优先）: 搜索 scripts/ 目录下的 .py 文件
    # 这确保返回实际存在的完整路径
    scripts_dir = skills_dir / skill_name / "scripts"
    if scripts_dir.exists():
        py_files = [f for f in scripts_dir.glob("*.py") if f.name != "handler.py"]
        if py_files:
            # 优先选择名字中包含 skill_name 关键词的文件
            for f in py_files:
                if skill_name.replace("-", "_") in f.name or skill_name in f.name:
                    return f"data/skills/{skill_name}/scripts/{f.name}"
            return f"data/skills/{skill_name}/scripts/{py_files[0].name}"

    # 方法2（回退）: 从 bash 代码块中提取
    bash_blocks = re.findall(r'```bash\s*\n(.*?)```', skill_content, re.DOTALL)
    for block in bash_blocks:
        match = re.search(r'python\s+([\w/.\-]+\.py)', block)
        if match:
            return match.group(1)

    return None


def extract_cli_template(skill_content: str) -> Optional[str]:
    """从 SKILL.md 的第一个 bash 代码块提取完整的 CLI 命令模板。

    Args:
        skill_content: SKILL.md 文件内容。

    Returns:
        CLI 命令模板字符串，未找到返回 None。
    """
    bash_blocks = re.findall(r'```bash\s*\n(.*?)```', skill_content, re.DOTALL)
    for block in bash_blocks:
        lines = block.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("python ") and ".py" in line:
                return line
    return None


def build_cli_command(
    script_path: str,
    query: str,
    extra_args: Optional[Dict[str, Any]] = None,
) -> str:
    """根据脚本路径和查询构造 CLI 命令。

    只使用 extra_args 中显式提供的参数，不再自动追加 --query 或 --max-results，
    因为不同 skill 脚本接受的参数不同（如 diagram-plotter 需要 --type/--content，
    chart-plotter 需要 --input/--type）。

    Args:
        script_path: 脚本文件路径。
        query: 用户查询字符串（仅在 extra_args 中包含 query 时使用）。
        extra_args: 额外的 CLI 参数。

    Returns:
        构造好的 CLI 命令字符串。
    """
    cmd = f'python {script_path}'

    if extra_args:
        for k, v in extra_args.items():
            # 将下划线转为连字符以匹配 CLI 参数惯例
            cli_key = k.replace("_", "-")
            if isinstance(v, bool) and v:
                cmd += f' --{cli_key}'
            elif isinstance(v, (int, float)):
                cmd += f' --{cli_key} {v}'
            elif isinstance(v, str):
                escaped = v.replace('"', '\\"')
                cmd += f' --{cli_key} "{escaped}"'

    return cmd


def build_skill_hints() -> str:
    """动态构建工具和 skill 提示文本。

    从 SkillLoader 加载可用 skill，生成包含 skill 路径的提示列表，
    引导 LLM 通过 read_file(SKILL.md) 触发 skill 自动执行。

    Returns:
        格式化的工具 + skill 提示文本。
    """
    lines = [
        "Available tools:",
        "- search_kb: Search the knowledge base",
        "- fetch_url: Fetch content from a URL",
        "- read_file: Read a local file",
        "- python_repl: Execute Python code",
        "- terminal: Execute shell commands",
        "",
        "Skills (高级能力，读取 SKILL.md 即可自动执行):",
    ]

    try:
        from app.skills.loader import SkillLoader
        loader = SkillLoader()
        skills = loader.list_available_skills()

        if skills:
            for skill_name, description in skills.items():
                short_desc = description[:60] + "..." if len(description) > 60 else description
                lines.append(
                    f"- {skill_name}: {short_desc} "
                    f'→ read_file("data/skills/{skill_name}/SKILL.md")'
                )
        else:
            lines.append("(暂无可用 skill)")
    except Exception:
        lines.append("(skill 列表加载失败)")

    lines.extend([
        "",
        "使用 skill: 只需 read_file 对应的 SKILL.md，系统会自动识别并执行 skill。",
        "示例: read_file(path=\"data/skills/arxiv-search/SKILL.md\") 将自动搜索论文。",
        "",
        "=== SKILL 优先规则（必须遵守）===",
        "收到任务时，先看上面 Available Skills 列表有没有对应 skill。",
        "有 → 必须用 read_file(SKILL.md) 调用，禁止用 python_repl/terminal 自己实现。",
        "没有 → 才可以用 python_repl 或 terminal。",
        "绝对禁止：用 python_repl/terminal 重新实现 skill 已有的能力。",
    ])

    return "\n".join(lines)


async def _execute_module_skill(
    skill_name: str,
    user_query: str,
    extra_args: Optional[Dict[str, Any]],
    llm: Optional[Any],
) -> Dict[str, Any]:
    """执行模块型 skill。

    Args:
        skill_name: skill 名称。
        user_query: 用户查询。
        extra_args: 额外参数。
        llm: LLM 实例。

    Returns:
        执行结果 dict。
    """
    # 旧代码（注释掉）：from app.skills.loader import execute_skill — loader.py 中无此函数
    # from app.skills.loader import execute_skill
    # result = await execute_skill(skill_name, inputs=inputs, context={"llm": llm})

    # 新代码：直接用 importlib 加载 scripts/handler.py 并调用 run()
    import importlib.util
    from app.config import settings

    skills_dir = Path(getattr(settings, "skills_dir", "data/skills"))
    handler_path = skills_dir / skill_name / "scripts" / "handler.py"

    if not handler_path.exists():
        raise FileNotFoundError(f"Module handler not found: {handler_path}")

    spec = importlib.util.spec_from_file_location(f"skill_{skill_name}_handler", handler_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to create module spec for {handler_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    run_func = getattr(module, "run", None)
    if run_func is None:
        raise RuntimeError(f"No 'run' function in {handler_path}")

    inputs = {"query": user_query}
    if extra_args:
        inputs.update(extra_args)

    try:
        if asyncio.iscoroutinefunction(run_func):
            result = await run_func(inputs=inputs, context={"llm": llm})
        else:
            result = run_func(inputs=inputs, context={"llm": llm})
        # 统一图片嵌入：module skill 也可能生成图片
        result_str, gen_images = embed_output_images_v2(str(result))
        # Register generated images with MediaRegistry (keep for document insertion)
        _register_embedded_images(result_str)
        if gen_images:
            logger.info("[SkillOrchestrator] module %s generated %d image(s)", skill_name, len(gen_images))
        return {
            "status": "success",
            "result": result_str,
            "skill_type": "module",
            "skill_name": skill_name,
            "generated_images": gen_images if gen_images else None,
        }
    except Exception as e:
        logger.error(f"Module skill execution failed for {skill_name}: {e}")
        return {
            "status": "error",
            "result": str(e),
            "skill_type": "module",
            "skill_name": skill_name,
        }


async def _execute_script_skill(
    skill_name: str,
    skill_content: str,
    user_query: str,
    tools: List[BaseTool],
    extra_args: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """执行脚本型 skill。

    Args:
        skill_name: skill 名称。
        skill_content: SKILL.md 内容。
        user_query: 用户查询。
        tools: 可用工具列表。
        extra_args: 额外参数。

    Returns:
        执行结果 dict。
    """
    from app.config import get_settings
    settings = get_settings()
    skills_dir = Path(settings.skills_dir)

    # 提取脚本路径
    script_path = extract_script_path(skill_name, skill_content, skills_dir)

    if not script_path:
        return {
            "status": "error",
            "result": f"No script found for skill '{skill_name}'",
            "skill_type": "script",
            "skill_name": skill_name,
        }

    # 确保用户查询作为参数传递给脚本
    if extra_args is None:
        extra_args = {}
    if "content" not in extra_args and user_query:
        extra_args["content"] = user_query

    # 构造 CLI 命令
    cmd = build_cli_command(script_path, user_query, extra_args)
    logger.info(f"Executing script skill {skill_name}: {cmd[:200]}")

    # 找到 terminal 工具
    terminal_tool = next((t for t in tools if t.name == "terminal"), None)
    if not terminal_tool:
        return {
            "status": "error",
            "result": "terminal tool not available",
            "skill_type": "script",
            "skill_name": skill_name,
        }

    # 执行，设置超时 120 秒（图形生成可能较慢）
    try:
        result = await asyncio.wait_for(
            terminal_tool.ainvoke({"command": cmd}),
            timeout=120.0,
        )
        # 后处理：扫描 outputs/ 目录，将生成的图片嵌入为 base64
        result_str = str(result)
        result_str, gen_images = embed_output_images_v2(result_str)
        # Register generated images with MediaRegistry (keep for document insertion)
        _register_embedded_images(result_str)
        if gen_images:
            logger.info("[SkillOrchestrator] script %s generated %d image(s)", skill_name, len(gen_images))
        return {
            "status": "success",
            "result": result_str,
            "skill_type": "script",
            "skill_name": skill_name,
            "generated_images": gen_images if gen_images else None,
        }
    except asyncio.TimeoutError:
        logger.warning(f"Script skill {skill_name} timed out (120s)")
        return {
            "status": "error",
            "result": f"Skill execution timed out (120s): {skill_name}",
            "skill_type": "script",
            "skill_name": skill_name,
        }
    except Exception as e:
        logger.error(f"Script skill execution failed for {skill_name}: {e}")
        return {
            "status": "error",
            "result": str(e),
            "skill_type": "script",
            "skill_name": skill_name,
        }


async def execute_skill_from_skillmd(
    skill_name: str,
    skill_content: str,
    user_query: str,
    tools: List[BaseTool],
    llm: Optional[Any] = None,
    extra_args: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """从 SKILL.md 内容自动检测并执行 skill。

    根据技能类型（模块或脚本）选择合适的执行方式：
    - 模块型: 调用 execute_skill() 委托给 handler.py
    - 脚本型: 提取脚本路径，通过 terminal 工具执行 CLI 命令

    Args:
        skill_name: skill 目录名称。
        skill_content: SKILL.md 文件内容。
        user_query: 用户查询字符串。
        tools: 可用的 BaseTool 实例列表。
        llm: 可选的 LLM 实例（模块型 skill 需要）。
        extra_args: 额外的 skill 参数。

    Returns:
        包含 status/result/skill_type/skill_name 的结果 dict。
    """
    from app.config import get_settings
    settings = get_settings()
    skills_dir = Path(settings.skills_dir)

    skill_type = detect_skill_type(skill_name, skills_dir)
    logger.info(
        f"Skill orchestrator: executing '{skill_name}' as {skill_type} "
        f"for query: {user_query[:80]}"
    )

    # geometry-plotter 特例：handler 有 draw()/draw_code()，无 run()
    if skill_name == "geometry-plotter":
        return await _execute_geometry_plotter(skill_content, user_query, tools, llm)

    if skill_type == "module":
        return await _execute_module_skill(skill_name, user_query, extra_args, llm)
    else:
        return await _execute_script_skill(
            skill_name, skill_content, user_query, tools, extra_args
        )


# ---------------------------------------------------------------------------
# geometry-plotter 特例：LLM 提取参数 → 直接调用 draw()/draw_code()
# ---------------------------------------------------------------------------

async def _extract_draw_params(skill_content: str, user_query: str, llm: Any) -> dict:
    """LLM 根据 SKILL.md 提取 draw()/draw_code() 参数，输出 JSON。

    Args:
        skill_content: SKILL.md 文件内容。
        user_query: 用户查询字符串。
        llm: LLM 实例。

    Returns:
        参数 dict，包含 mode (draw/draw_code) 及对应参数。
    """
    import json as _json
    from langchain_core.messages import SystemMessage, HumanMessage

    system_msg = (
        "你是一个参数提取器。根据 SKILL.md 说明和用户请求，提取绘图参数，输出 JSON。\n"
        "只输出 JSON，不要其他内容。\n\n"
        "draw 模式参数: mode, expr, x_range, y_range, title, latex_label, xlabel, ylabel, save_name\n"
        "draw_code 模式参数: mode, code (matplotlib 代码，以 plt.savefig(SAVE_PATH) 结尾), save_name\n\n"
        "示例 — 用户说'画正弦曲线':\n"
        '{"mode": "draw", "expr": "np.sin(x)", "title": "正弦函数", '
        '"latex_label": "$\\\\sin(x)$", "x_range": [-6.28, 6.28]}'
    )
    user_msg = f"用户请求: {user_query}\n\nSKILL.md:\n{skill_content}"

    response = await llm.ainvoke([SystemMessage(content=system_msg), HumanMessage(content=user_msg)])
    text = response.content.strip()
    # 清理 markdown 代码块包裹
    text = re.sub(r'^```\w*\n?', '', text).rstrip('`').strip()

    try:
        return _json.loads(text)
    except _json.JSONDecodeError:
        m = re.search(r'\{[^{}]+\}', text, re.DOTALL)
        if m:
            try:
                return _json.loads(m.group(0))
            except _json.JSONDecodeError:
                pass
        logger.warning("[geometry-plotter] Failed to parse LLM params, using fallback")
        return {"mode": "draw", "expr": "np.sin(x)"}


async def _execute_geometry_plotter(
    skill_content: str,
    user_query: str,
    tools: List[BaseTool],
    llm: Optional[Any],
) -> Dict[str, Any]:
    """geometry-plotter 特例处理。

    handler.py 有 draw()/draw_code() 但无 run()，
    通过 LLM 提取参数后直接调用对应函数。

    所有 matplotlib 配置（字体、backend、输出格式）均在 handler 内部，
    此函数只负责参数提取和函数调度。
    """
    import importlib.util

    # 1. LLM 提取参数
    params = await _extract_draw_params(skill_content, user_query, llm)
    logger.info(f"[geometry-plotter] LLM extracted params: {params}")

    # 2. 动态加载 handler.py
    from app.config import get_settings
    skills_dir = Path(get_settings().skills_dir)
    handler_path = skills_dir / "geometry-plotter" / "scripts" / "handler.py"

    if not handler_path.exists():
        return {
            "status": "error",
            "result": f"geometry-plotter handler not found: {handler_path}",
            "skill_name": "geometry-plotter",
        }

    spec = importlib.util.spec_from_file_location("geometry_plotter_handler", handler_path)
    if spec is None or spec.loader is None:
        return {
            "status": "error",
            "result": f"Failed to load geometry-plotter handler",
            "skill_name": "geometry-plotter",
        }

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # 3. 根据参数选择 draw() 或 draw_code()
    try:
        if params.get("mode") == "draw_code":
            result = module.draw_code(params.get("code", ""), save_name=params.get("save_name"))
        else:
            result = module.draw(
                expr=params.get("expr", "np.sin(x)"),
                x_range=tuple(params["x_range"]) if "x_range" in params else (-5, 5),
                y_range=tuple(params["y_range"]) if "y_range" in params else None,
                title=params.get("title"),
                latex_label=params.get("latex_label"),
                xlabel=params.get("xlabel"),
                ylabel=params.get("ylabel"),
                save_name=params.get("save_name"),
            )
    except Exception as e:
        logger.error(f"[geometry-plotter] draw() execution failed: {e}")
        return {
            "status": "error",
            "result": f"geometry-plotter draw failed: {str(e)}",
            "skill_name": "geometry-plotter",
        }

    result_str, gen_images = embed_output_images_v2(str(result))
    _register_embedded_images(result_str)
    if gen_images:
        logger.info("[geometry-plotter] generated %d image(s)", len(gen_images))

    return {
        "status": "success",
        "result": result_str,
        "skill_type": "geometry_plotter_special",
        "skill_name": "geometry-plotter",
        "generated_images": gen_images or None,
    }
