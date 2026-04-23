"""
ToT Prompt Composer

Combines the original Agent system prompt (from SystemPromptBuilder, containing
SOUL / IDENTITY / USER / AGENTS / SKILLS_SNAPSHOT / MEMORY) with ToT role-specific
instructions.  The base prompt is never truncated -- it is always included in full,
followed by a separator and the role appendix.

Supports a ``prompt_level`` parameter for research-mode token optimisation:
  - ``"full"`` (default): Keep existing behaviour -- full base prompt + role appendix.
  - ``"writing"``: SOUL + stripped IDENTITY + BASE_RESEARCH_SYSTEM_PROMPT.
  - ``"analysis"``: IDENTITY (role declaration only) + BASE_RESEARCH_SYSTEM_PROMPT.
  - ``"skill_internal"``: Empty string (no system prompt needed).
"""

import logging
import re
from typing import Dict, List, Optional, Sequence

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Variant hints (used only by the *generator* role)
# ---------------------------------------------------------------------------
_VARIANT_HINTS: Dict[int, str] = {
    0: "Strategy: Be thorough and conservative. Prioritize correctness.",
    1: "Strategy: Be creative and explore unconventional approaches.",
    2: "Strategy: Balance between proven methods and novel ideas.",
}

# ---------------------------------------------------------------------------
# 三重分化提示词体系 (Phase 0: 分支多样性基础保障)
# ---------------------------------------------------------------------------

# 思维框架池 — 每个分支使用不同的推理方式
_REASONING_FRAMEWORKS: Dict[int, str] = {
    0: "自顶向下分解: 将问题从最高层逐步拆解为子问题，逐一解决。",
    1: "类比迁移: 从已知的相似问题/领域借鉴思路，映射到当前问题。",
    2: "对抗性思考: 主动寻找当前方案的反例、弱点和边界条件，再针对性改进。",
    3: "逆向推理: 从目标状态倒推必要条件，构建逆向路径。",
    4: "归纳综合: 从具体实例中提炼规律，用归纳法构建解决方案。",
}

# 角色扮演池 — 每个分支扮演不同的专家角色
_EXPERT_ROLES: Dict[int, str] = {
    0: "审稿人: 以批判性眼光审查方案的完整性和严谨性，关注逻辑漏洞。",
    1: "创新者: 追求非传统视角，大胆假设，探索边界可能性。",
    2: "工程师: 关注可执行性和效率，优先考虑实际落地方案。",
    3: "研究者: 系统性地收集证据，遵循学术方法论。",
    4: "架构师: 从全局视角设计，关注模块化和可扩展性。",
}


def _build_opposition_hint(existing_branches_summary: str) -> str:
    """构建反对机制提示词，要求新分支必须与已有思路不同。"""
    if not existing_branches_summary:
        return ""
    return f"""
=== 已有分支摘要（你 MUST NOT 重复这些思路）===
{existing_branches_summary}
=== 要求 ===
你生成的分支必须与上述已有思路在策略、工具选择或推理角度上显著不同。
如果某个方向已被探索，你必须选择完全不同的方向。"""


def _build_diversity_injection(
    branch_index: int,
    existing_branches_summary: str = "",
) -> str:
    """为每个分支构建组合的分化提示词。"""
    framework = _REASONING_FRAMEWORKS[branch_index % len(_REASONING_FRAMEWORKS)]
    role = _EXPERT_ROLES[(branch_index + 1) % len(_EXPERT_ROLES)]  # 错开选
    opposition = _build_opposition_hint(existing_branches_summary)

    parts = [
        f"\n=== 思维框架 ===\n{framework}",
        f"\n=== 你的角色 ===\n{role}",
    ]
    if opposition:
        parts.append(opposition)
    return "\n".join(parts)

# ---------------------------------------------------------------------------
# Prompt-level helpers (writing / analysis / skill_internal)
# ---------------------------------------------------------------------------

# Regex to detect section headers like "# SECTION_NAME" or "# **SECTION_NAME**"
_SECTION_HEADER_RE = re.compile(r"^#\s+\*{0,2}(\w+)\*{0,2}", re.MULTILINE)

# Sections from AGENTS.md that are conversational / non-essential for research
_AGENTS_CONVERSATIONAL_SECTIONS = frozenset({
    "GREETING",
    "CONVERSATION",
    "GREETING_AND_CONVERSATION",
    "CHITCHAT",
    "PERSONALITY_EXPRESSION",
    "EMOTIONAL_RESPONSE",
    "CASUAL_CHAT",
    "WELCOME",
})


def _extract_components(base_system_prompt: str) -> Dict[str, str]:
    """Split the base_system_prompt by ``---`` and identify components by header.

    The system prompt is composed of multiple Markdown sections separated by
    ``---`` dividers.  Each section typically starts with a ``# SECTION_NAME``
    header (e.g., ``# SOUL``, ``# IDENTITY``, ``# AGENTS``).  This function
    splits on ``---`` and indexes each chunk by its first ``# WORD`` header.

    Args:
        base_system_prompt: The full system prompt string from
            SystemPromptBuilder.

    Returns:
        A dict mapping uppercase section names to their raw content strings.
        Sections without a recognisable header are stored under the key
        ``"_UNKNOWN_<index>"``.
    """
    if not base_system_prompt or not base_system_prompt.strip():
        return {}

    raw_parts = re.split(r"\n---\n", base_system_prompt)
    components: Dict[str, str] = {}

    for idx, part in enumerate(raw_parts):
        stripped = part.strip()
        if not stripped:
            continue

        match = _SECTION_HEADER_RE.match(stripped)
        if match:
            section_name = match.group(1).upper()
            # Handle potential duplicate section names by appending index
            if section_name in components:
                section_name = f"{section_name}_{idx}"
            components[section_name] = stripped
        else:
            components[f"_UNKNOWN_{idx}"] = stripped

    return components


def _filter_agents_for_level(
    agents_content: str,
    prompt_level: str,
) -> str:
    """Remove conversational / non-essential sections from AGENTS.md content.

    For ``"full"`` level, removes sections whose headers match known
    conversational patterns.  For other levels (``"writing"``, ``"analysis"``),
    the AGENTS section is not used at all.

    Args:
        agents_content: The raw AGENTS.md section text.
        prompt_level: The current prompt level.

    Returns:
        Filtered AGENTS content with conversational sub-sections removed.
    """
    if not agents_content or not agents_content.strip():
        return ""

    if prompt_level != "full":
        # Non-full levels do not use AGENTS at all
        return ""

    # Split AGENTS content by ## headers (sub-sections within AGENTS)
    sub_sections = re.split(r"\n(?=##\s)", agents_content)
    filtered: List[str] = []

    for sub in sub_sections:
        stripped = sub.strip()
        if not stripped:
            continue

        # Check if this sub-section header matches a conversational pattern
        header_match = re.match(r"^##\s+\*{0,2}(\w+)", stripped)
        if header_match:
            header_name = header_match.group(1).upper()
            if header_name in _AGENTS_CONVERSATIONAL_SECTIONS:
                logger.debug(
                    "Filtering out AGENTS sub-section '%s' for prompt_level='full'",
                    header_name,
                )
                continue

        filtered.append(stripped)

    return "\n\n".join(filtered)


def _build_writing_prompt(base_system_prompt: str) -> str:
    """Build a prompt for the *writing* research level.

    Includes SOUL + a stripped IDENTITY (role declaration only) +
    the shared BASE_RESEARCH_SYSTEM_PROMPT.

    Args:
        base_system_prompt: The full system prompt to extract components from.

    Returns:
        The composed writing-level system prompt.
    """
    from app.core.tot.research.prompts import get_base_research_system_prompt

    components = _extract_components(base_system_prompt)

    parts: List[str] = []

    # SOUL section
    soul = components.get("SOUL", "")
    if soul:
        parts.append(soul)

    # IDENTITY section -- stripped to role declaration only (first paragraph)
    identity = components.get("IDENTITY", "")
    if identity:
        # Keep only up to the first blank line (the core role declaration)
        first_para = identity.split("\n\n", 1)[0]
        parts.append(first_para)

    # Append the shared research system prompt
    base_research = get_base_research_system_prompt()
    if base_research:
        parts.append(base_research)

    return "\n\n---\n\n".join(parts) if parts else ""


def _build_analysis_prompt(base_system_prompt: str) -> str:
    """Build a prompt for the *analysis* research level.

    Includes only the IDENTITY role declaration + the shared
    BASE_RESEARCH_SYSTEM_PROMPT.  Minimal context for focused analytical work.

    Args:
        base_system_prompt: The full system prompt to extract components from.

    Returns:
        The composed analysis-level system prompt.
    """
    from app.core.tot.research.prompts import get_base_research_system_prompt

    components = _extract_components(base_system_prompt)

    parts: List[str] = []

    # IDENTITY section -- role declaration only (first paragraph)
    identity = components.get("IDENTITY", "")
    if identity:
        first_para = identity.split("\n\n", 1)[0]
        parts.append(first_para)

    # Append the shared research system prompt
    base_research = get_base_research_system_prompt()
    if base_research:
        parts.append(base_research)

    return "\n\n---\n\n".join(parts) if parts else ""


def _apply_agents_filter(base_system_prompt: str) -> str:
    """Apply AGENTS conversational section filtering to the full system prompt.

    Extracts the AGENTS component from the base prompt, filters out
    conversational sub-sections, and reconstructs the prompt with the
    filtered AGENTS content.

    Args:
        base_system_prompt: The full system prompt string.

    Returns:
        The system prompt with AGENTS conversational sections removed.
        If no AGENTS section is found, returns the prompt unchanged.
    """
    components = _extract_components(base_system_prompt)

    agents_content = components.get("AGENTS", "")
    if not agents_content:
        # No AGENTS section found -- return unchanged
        return base_system_prompt

    # Filter conversational sub-sections
    filtered_agents = _filter_agents_for_level(agents_content, "full")
    if filtered_agents == agents_content:
        # Nothing was filtered -- return unchanged
        return base_system_prompt

    if not filtered_agents:
        # Entire AGENTS section was conversational -- remove it
        # Rebuild without AGENTS
        parts: List[str] = []
        raw_parts = re.split(r"\n---\n", base_system_prompt)
        for part in raw_parts:
            stripped = part.strip()
            if not stripped:
                continue
            match = _SECTION_HEADER_RE.match(stripped)
            if match and match.group(1).upper() == "AGENTS":
                continue  # skip AGENTS entirely
            parts.append(part)
        return "\n---\n".join(parts) if parts else base_system_prompt

    # Replace AGENTS section with filtered version
    # Split the prompt and replace the AGENTS chunk
    raw_parts = re.split(r"\n---\n", base_system_prompt)
    rebuilt: List[str] = []
    for part in raw_parts:
        stripped = part.strip()
        if not stripped:
            rebuilt.append(part)
            continue
        match = _SECTION_HEADER_RE.match(stripped)
        if match and match.group(1).upper() == "AGENTS":
            rebuilt.append(filtered_agents)
        else:
            rebuilt.append(part)

    return "\n---\n".join(rebuilt)


# ---------------------------------------------------------------------------
# Role-specific instruction templates
# ---------------------------------------------------------------------------

_GENERATOR_TEMPLATE = """\
[ToT Reasoning Mode - Generator Role]

You are now in Tree-of-Thought reasoning mode. You MUST follow this search procedure:
1. Generate multiple distinct candidate approaches (branches).
2. Each branch must explicitly state its strategy, key tools, and risk points.
3. Evaluate each branch and select the optimal path for expansion.
4. If a branch is unviable, backtrack immediately and record the failure reason.
{domain_methods_section}
Tool Usage:
- Core tools (use LangChain native function calling): {tool_list}
- Skills (高级能力，读取 SKILL.md 即可自动执行):
  系统会在你 read_file 一个 SKILL.md 时自动通过 SkillPolicy 门控执行。
  使用方法: read_file(path="data/skills/<skill-name>/SKILL.md")
  示例: read_file(path="data/skills/arxiv-search/SKILL.md") 将自动搜索 arXiv 论文。

IMPORTANT:
- Use native function calling (NOT XML format) to invoke tools
- Each approach must use a DIFFERENT strategy or tool combination
- Do NOT reference tools that are not in the available list
- Skills expand your capabilities beyond raw tool calls — use them when relevant

=== SKILL PRIORITY RULES ===
- 有对应 Skill → 优先使用 read_file(SKILL.md)
- 没有对应 Skill → 使用 python_repl 或 terminal
- 禁止用 python_repl/terminal 重新实现 skill 已有的能力
{variant_hint}
{diversity_injection}"""

_EVALUATOR_TEMPLATE = """\
[ToT Reasoning Mode - Evaluator Role]

You are a strict reasoning evaluator, responsible for scoring candidate reasoning branches
and selecting the optimal path for expansion.

You MUST focus on checking: logical validity, condition matching, goal progress,
hidden assumptions, and executability.

You will receive a rubric_profile that defines the scoring dimensions, weights,
fatal flaw types, and style constraints for this task.
You MUST strictly follow the rubric_profile for scoring.
Output must be JSON."""

_TERMINATION_TEMPLATE = """\
[ToT Reasoning Mode - Termination Checker]

You are a research quality assessor. Evaluate whether the current Tree of Thoughts
reasoning has gathered sufficient information.

Focus on:
- Information completeness relative to the user query
- Whether continued exploration would yield diminishing returns
- Quality and diversity of collected evidence

Provide a clear YES/NO recommendation."""

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_tool_list_string(tools: Sequence[BaseTool]) -> str:
    """Format tool names from a sequence of LangChain ``BaseTool`` instances.

    Args:
        tools: Sequence of tools (typically ``state["tools"]``).

    Returns:
        A comma-separated string of tool names, e.g. ``"search_kb, fetch_url, read_file"``.
    """
    if not tools:
        return "(none)"
    return ", ".join(tool.name for tool in tools)


# ---------------------------------------------------------------------------
# Main composition function
# ---------------------------------------------------------------------------

def compose_system_prompt(
    base_system_prompt: str,
    node_role: str,
    domain_profile: Optional[Dict] = None,
    variant: int = 0,
    tools: Optional[Sequence[BaseTool]] = None,
    prompt_level: str = "full",
    enrichment: Optional[Dict] = None,
) -> str:
    """Compose the full system prompt for a ToT node.

    Structure::

        [base_system_prompt]           <- from SystemPromptBuilder (never truncated)
        ---
        [ToT role instructions]
        [domain_profile injection (if provided)]
        [tool & skill usage guidance]

    The ``prompt_level`` parameter controls how much of the base system prompt
    is included:

    - ``"full"`` (default): Keep existing behaviour -- full base prompt with
      AGENTS conversational sections filtered out, followed by role appendix.
    - ``"writing"``: SOUL + stripped IDENTITY + BASE_RESEARCH_SYSTEM_PROMPT.
      Used for research draft-writing nodes where full agent context is not
      needed.
    - ``"analysis"``: IDENTITY (role declaration only) + BASE_RESEARCH_SYSTEM_PROMPT.
      Minimal context for focused analytical work (coverage, contradiction
      detection, evaluation).
    - ``"skill_internal"``: Returns an empty string.  Used when a skill handles
      its own system prompt construction.

    Args:
        base_system_prompt: The original Agent system prompt stored in
            ``state["system_prompt"]``.  It contains SOUL, IDENTITY, USER,
            AGENTS, SKILLS_SNAPSHOT, and MEMORY components.
        node_role: One of ``"generator"``, ``"evaluator"``, ``"termination"``.
        domain_profile: Optional dict with task-specific metadata.  If it
            contains a ``"preferred_methods"`` key (list of strings), those
            methods are injected into the generator prompt.
        variant: Strategy variant hint for the **generator** role only.
            0 = conservative, 1 = creative, 2 = balanced.
        tools: Optional sequence of BaseTool instances.  Used to build a
            dynamic tool list injected into all role prompts so nodes know
            which tools they can call.
        prompt_level: Controls system prompt verbosity.  One of ``"full"``,
            ``"writing"``, ``"analysis"``, ``"skill_internal"``.  Defaults to
            ``"full"`` for full backward compatibility.
        enrichment: Optional dict with enrichment data.  If it contains a
            ``meta_policy_advice`` key with an ``injection_text`` value, that
            text is appended as a guidance section to the system prompt.

    Returns:
        The fully composed system prompt string.

    Raises:
        ValueError: If *node_role* is not one of the accepted values, or
            *prompt_level* is not recognised.
    """
    role = node_role.lower()
    if role not in ("generator", "evaluator", "termination"):
        raise ValueError(
            f"Invalid node_role '{node_role}'. "
            "Must be one of: generator, evaluator, termination."
        )

    # -- Handle prompt_level dispatch ----------------------------------------
    level = prompt_level.lower()
    valid_levels = {"full", "writing", "analysis", "skill_internal"}
    if level not in valid_levels:
        raise ValueError(
            f"Invalid prompt_level '{prompt_level}'. "
            f"Must be one of: {', '.join(sorted(valid_levels))}."
        )

    # skill_internal: no system prompt needed
    if level == "skill_internal":
        logger.info(
            f"[ToT PromptComposer] role={role}, prompt_level={level}, "
            f"result=empty (skill_internal)"
        )
        return ""

    # writing: SOUL + stripped IDENTITY + BASE_RESEARCH_SYSTEM_PROMPT
    if level == "writing":
        composed = _build_writing_prompt(base_system_prompt)
        logger.info(
            f"[ToT PromptComposer] role={role}, prompt_level={level}, "
            f"total_len={len(composed)}"
        )
        return composed

    # analysis: IDENTITY (role declaration) + BASE_RESEARCH_SYSTEM_PROMPT
    if level == "analysis":
        composed = _build_analysis_prompt(base_system_prompt)
        logger.info(
            f"[ToT PromptComposer] role={role}, prompt_level={level}, "
            f"total_len={len(composed)}"
        )
        return composed

    # -- prompt_level == "full" (default, backward-compatible path) ----------

    # -- Build the role-specific appendix ---------------------------------
    if role == "generator":
        # Tool list from tools parameter (not from domain_profile dict)
        tool_list = get_tool_list_string(tools) if tools else "(none)"

        # Domain-specific preferred methods
        domain_methods_section = ""
        if domain_profile and domain_profile.get("preferred_methods"):
            methods = domain_profile["preferred_methods"]
            if isinstance(methods, (list, tuple)) and methods:
                formatted = "\n".join(f"- {m}" for m in methods)
                domain_methods_section = (
                    "\nPreferred methods for this domain:\n" + formatted + "\n"
                )

        # Variant hint (one-liner strategy nudge)
        variant_hint = _VARIANT_HINTS.get(variant % len(_VARIANT_HINTS), "")

        # Diversity injection (三重分化 — Phase 0)
        diversity_injection = _build_diversity_injection(
            branch_index=variant,
            existing_branches_summary=(enrichment or {}).get("existing_branches_summary", ""),
        )

        appendix = _GENERATOR_TEMPLATE.format(
            domain_methods_section=domain_methods_section,
            tool_list=tool_list,
            variant_hint=variant_hint,
            diversity_injection=diversity_injection,
        )

        # 域特有生成器指令
        domain_instruction = ""
        if domain_profile and domain_profile.get("generator_instruction"):
            domain_instruction = f"\n--- Domain-Specific Generator Instructions ---\n{domain_profile['generator_instruction']}"
        appendix += domain_instruction

    elif role == "evaluator":
        appendix = _EVALUATOR_TEMPLATE

        # 域特有评估器指令
        domain_eval_instruction = ""
        if domain_profile and domain_profile.get("evaluator_instruction"):
            domain_eval_instruction = f"\n--- Domain-Specific Evaluator Instructions ---\n{domain_profile['evaluator_instruction']}"
        appendix += domain_eval_instruction

        # Brief tool hint for evaluator
        tool_list = get_tool_list_string(tools) if tools else "(none)"
        appendix += f"\nTools: {tool_list}. Use tools to verify claims when needed."

    else:  # termination
        appendix = _TERMINATION_TEMPLATE

        # 域特有终止指令
        domain_term_instruction = ""
        if domain_profile and domain_profile.get("termination_instruction"):
            domain_term_instruction = f"\n--- Domain-Specific Termination Instructions ---\n{domain_profile['termination_instruction']}"
        appendix += domain_term_instruction

        # Brief tool hint for termination checker
        tool_list = get_tool_list_string(tools) if tools else "(none)"
        appendix += f"\nTools: {tool_list}. Use tools to verify claims when needed."

    # -- Assemble final prompt --------------------------------------------
    # Apply AGENTS conversational filtering for full level
    filtered_base = _apply_agents_filter(base_system_prompt)
    composed = filtered_base + "\n---\n" + appendix

    # -- Meta policy advice injection ----------------------------------------
    meta_advice = (enrichment or {}).get("meta_policy_advice")
    if meta_advice and meta_advice.get("injection_text"):
        composed += f"\n\n[Meta Policy Guidance]\n{meta_advice['injection_text']}"

    # -- TCA decomposition guidance ------------------------------------------
    tca_decision = (enrichment or {}).get("tca_decision")
    if tca_decision and tca_decision.get("injection_text"):
        composed += f"\n\n[Task Decomposition Guidance]\n{tca_decision['injection_text']}"

    # -- Chat history injection -----------------------------------------------
    chat_history = (enrichment or {}).get("chat_history")
    if chat_history:
        composed += f"\n\n[Conversation History]\n{chat_history}"

    logger.info(
        f"[ToT PromptComposer] role={role}, prompt_level={level}, "
        f"total_len={len(composed)}, base_len={len(filtered_base)}, "
        f"appendix_len={len(appendix)}, "
        f"domain_profile={'yes' if domain_profile else 'none'}, "
        f"tools={len(tools) if tools else 0}, "
        f"variant={variant}"
    )

    return composed
