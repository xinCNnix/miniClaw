"""
ToT Skill Orchestrator

当 thought_executor 检测到 read_file 读取 SKILL.md 时，
自动解析 SKILL.md 内容并执行对应的 skill 脚本或模块。
"""

import asyncio
import logging
import os
import re
import sys
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
    """检测 skill 类型: module / script / instruction。

    - module: scripts/handler.py 存在且包含 def 定义
    - script: scripts/ 目录下有 .py 文件但无 handler.py
    - instruction: 仅 SKILL.md，无可执行脚本

    Args:
        skill_name: skill 名称。
        skills_dir: skills 根目录路径。

    Returns:
        "module", "script" 或 "instruction"。
    """
    skill_dir = skills_dir / skill_name
    handler_path = skill_dir / "scripts" / "handler.py"
    if handler_path.exists():
        try:
            content = handler_path.read_text(encoding="utf-8")
            if re.search(r'\bdef\s+\w+', content):
                return "module"
        except Exception:
            pass

    scripts_dir = skill_dir / "scripts"
    if scripts_dir.exists():
        py_files = list(scripts_dir.glob("*.py"))
        if py_files:
            return "script"

    return "instruction"


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


def _extract_usage_params(skill_content: str) -> Dict[str, str]:
    """从 SKILL.md 的 Usage/示例部分提取脚本参数。

    解析 ```bash 代码块中的 --key value 对，作为 extra_args 传入。
    只提取静态参数（如 --type bar），不提取动态参数（如 --input data.csv）。
    """
    params: Dict[str, str] = {}
    bash_blocks = re.findall(r'```bash\s*\n(.*?)```', skill_content, re.DOTALL)
    for block in bash_blocks:
        # 提取所有 --key value 对
        for match in re.finditer(r'--([\w-]+)\s+([\w-]+)', block):
            key, value = match.group(1), match.group(2)
            # 只保留非动态的参数（排除 input, output, query 等）
            if key not in ("input", "output", "output-svg", "output-png", "query", "content"):
                params[key] = value
    return params


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
    python_cmd = sys.executable or "python"
    cmd = f'"{python_cmd}" {script_path}'

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

    优先查找 run() 函数，不存在时查找 handler 中的第一个 async def / def 公开函数。
    对 geometry-plotter 这类无 run() 的 skill，使用 LLM 提取参数后调用对应函数。

    Args:
        skill_name: skill 名称。
        user_query: 用户查询。
        extra_args: 额外参数。
        llm: LLM 实例。

    Returns:
        执行结果 dict。
    """
    import importlib.util
    from app.config import get_settings

    settings = get_settings()
    skills_dir = Path(getattr(settings, "skills_dir", "data/skills"))
    handler_path = skills_dir / skill_name / "scripts" / "handler.py"

    if not handler_path.exists():
        raise FileNotFoundError(f"Module handler not found: {handler_path}")

    spec = importlib.util.spec_from_file_location(f"skill_{skill_name}_handler", handler_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to create module spec for {handler_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # 1. 优先找 run() 函数
    run_func = getattr(module, "run", None)
    if run_func is not None:
        inputs = {"query": user_query}
        if extra_args:
            inputs.update(extra_args)
        try:
            if asyncio.iscoroutinefunction(run_func):
                result = await run_func(inputs=inputs, context={"llm": llm})
            else:
                result = run_func(inputs=inputs, context={"llm": llm})
        except Exception as e:
            logger.error(f"Module skill execution failed for {skill_name}: {e}")
            return {
                "status": "error",
                "result": str(e),
                "skill_type": "module",
                "skill_name": skill_name,
            }
    else:
        # 2. 无 run()：使用 LLM 提取参数，调用匹配的函数
        result = await _execute_custom_module(skill_name, module, user_query, llm, handler_path)

    result_str, gen_images = embed_output_images_v2(str(result))
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


async def _execute_custom_module(
    skill_name: str,
    module: Any,
    user_query: str,
    llm: Optional[Any],
    handler_path: Path,
) -> Any:
    """对无 run() 函数的 module skill，使用 LLM 提取参数并调用对应函数。

    扫描 handler 中的公开函数（不以 _ 开头），用 LLM 决定调用哪个函数及参数。

    Args:
        skill_name: skill 名称。
        module: 已加载的 handler 模块。
        user_query: 用户查询。
        llm: LLM 实例。
        handler_path: handler.py 路径。

    Returns:
        函数执行结果。
    """
    import inspect

    # 收集公开函数及其签名
    public_funcs = {}
    for name, obj in inspect.getmembers(module, inspect.isfunction):
        if not name.startswith("_"):
            sig = inspect.signature(obj)
            public_funcs[name] = {
                "func": obj,
                "params": list(sig.parameters.keys()),
            }

    if not public_funcs:
        raise RuntimeError(f"No public functions found in {handler_path}")

    if llm is None:
        # 无 LLM：尝试带 user_query 调用第一个公开函数，失败则无参调用
        first_name = next(iter(public_funcs))
        func = public_funcs[first_name]["func"]
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(query=user_query)
            return func(query=user_query)
        except TypeError:
            if asyncio.iscoroutinefunction(func):
                return await func()
            return func()

    # 用 LLM 提取参数
    import json as _json
    from langchain_core.messages import SystemMessage, HumanMessage

    func_descriptions = []
    for fname, info in public_funcs.items():
        params_str = ", ".join(info["params"])
        func_descriptions.append(f"- {fname}({params_str})")

    # 读取 SKILL.md 获取技能描述
    skill_md_path = handler_path.parent.parent / "SKILL.md"
    skill_desc = ""
    if skill_md_path.exists():
        try:
            skill_desc = skill_md_path.read_text(encoding="utf-8")[:2000]
        except Exception:
            pass

    system_msg = (
        f"你是参数提取器。根据 SKILL.md 说明和用户请求，选择正确的函数并提取参数，输出 JSON。\n"
        f"只输出 JSON，不要其他内容。\n\n"
        f"可用函数:\n" + "\n".join(func_descriptions) + "\n\n"
        f"输出格式: {{\"function\": \"函数名\", \"args\": {{参数名: 值}}}}"
    )
    user_msg = f"用户请求: {user_query}\n\nSKILL.md:\n{skill_desc}"

    try:
        response = await llm.ainvoke([SystemMessage(content=system_msg), HumanMessage(content=user_msg)])
        text = response.content.strip()
        text = re.sub(r'^```\w*\n?', '', text).rstrip('`').strip()
        params = _json.loads(text)
    except Exception as e:
        logger.warning("[SkillOrchestrator] LLM param extraction failed for %s: %s", skill_name, e)
        # 回退：调用第一个公开函数
        first_name = next(iter(public_funcs))
        func = public_funcs[first_name]["func"]
        if asyncio.iscoroutinefunction(func):
            return await func()
        return func()

    func_name = params.get("function", next(iter(public_funcs)))
    func_args = params.get("args", {})

    if func_name not in public_funcs:
        logger.warning("[SkillOrchestrator] LLM chose unknown function '%s', using first available", func_name)
        func_name = next(iter(public_funcs))

    func = public_funcs[func_name]["func"]
    logger.info("[SkillOrchestrator] custom module %s: calling %s(%s)", skill_name, func_name, list(func_args.keys()))

    try:
        if asyncio.iscoroutinefunction(func):
            return await func(**func_args)
        return func(**func_args)
    except TypeError as te:
        logger.warning("[SkillOrchestrator] function %s args mismatch: %s, falling back to no-args call", func_name, te)
        if asyncio.iscoroutinefunction(func):
            return await func()
        return func()


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

    # 从 Settings 中读取 skill 需要的环境变量并临时设置到系统环境变量
    _env_backup = {}
    _skill_env_keys = ["BAIDU_API_KEY", "ARXIV_API_KEY", "GITHUB_TOKEN"]
    for key in _skill_env_keys:
        val = getattr(settings, key.lower(), None) or getattr(settings, key, None)
        if val:
            _env_backup[key] = os.environ.get(key)
            os.environ[key] = str(val)

    # 提取脚本路径
    script_path = extract_script_path(skill_name, skill_content, skills_dir)

    if not script_path:
        return {
            "status": "error",
            "result": f"No script found for skill '{skill_name}'",
            "skill_type": "script",
            "skill_name": skill_name,
        }

    # 构造 CLI 命令：不再盲目添加 --content，交给 LLM 或用户 extra_args 决定参数
    if extra_args is None:
        extra_args = {}
    # 仅在 SKILL.md 明确声明接受 content 参数时才自动传入
    if "content" not in extra_args and user_query:
        # 检查 SKILL.md 中是否有 usage 部分提示需要的参数
        _usage_hint = _extract_usage_params(skill_content)
        if _usage_hint:
            # SKILL.md 有明确的参数说明，让 LLM 提取参数
            extra_args.update(_usage_hint)
        else:
            # 无明确参数说明，作为 positional arg 或 query 传递
            extra_args["query"] = user_query

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

    # 执行，设置超时 120 秒（图形生成可能较慢），失败重试 1 次
    max_attempts = 2
    last_error = None
    for attempt in range(max_attempts):
        try:
            result = await asyncio.wait_for(
                terminal_tool.ainvoke({"command": cmd}),
                timeout=120.0,
            )
            # 成功 → 后处理
            result_str = str(result)
            result_str, gen_images = embed_output_images_v2(result_str)
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
            last_error = f"Skill execution timed out (120s): {skill_name}"
            logger.warning(f"Script skill {skill_name} timed out (120s), attempt {attempt + 1}/{max_attempts}")
        except Exception as e:
            last_error = str(e)
            logger.warning(
                "Script skill %s failed (attempt %d/%d): %s",
                skill_name, attempt + 1, max_attempts, e,
            )

    logger.error(f"Script skill {skill_name} failed after {max_attempts} attempts")
    return {
        "status": "error",
        "result": f"Skill execution failed after {max_attempts} attempts: {last_error}",
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

    根据技能类型选择合适的执行方式：
    - module: 调用 handler.py 中的函数
    - script: 提取脚本路径，通过 terminal 工具执行 CLI 命令
    - instruction: 返回 SKILL.md 内容供 LLM 解读

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
        "Skill orchestrator: executing '%s' as %s "
        "for query: %s",
        skill_name, skill_type, user_query[:80],
    )

    if skill_type == "module":
        return await _execute_module_skill(skill_name, user_query, extra_args, llm)
    elif skill_type == "script":
        return await _execute_script_skill(
            skill_name, skill_content, user_query, tools, extra_args
        )
    else:
        # instruction 类型：返回 SKILL.md 内容，让 LLM 自行解读指令
        return {
            "status": "success",
            "result": skill_content,
            "skill_type": "instruction",
            "skill_name": skill_name,
        }
