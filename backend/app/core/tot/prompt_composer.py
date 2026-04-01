"""
ToT Prompt Composer

Combines the original Agent system prompt (from SystemPromptBuilder, containing
SOUL / IDENTITY / USER / AGENTS / SKILLS_SNAPSHOT / MEMORY) with ToT role-specific
instructions.  The base prompt is never truncated -- it is always included in full,
followed by a separator and the role appendix.
"""

import logging
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
- Skills: The SKILLS_SNAPSHOT in your system prompt lists available skills.
  To use a skill: first read_file its SKILL.md, then follow the instructions using core tools.
  Example: for arxiv-search, read_file("data/skills/arxiv-search/SKILL.md") first.

IMPORTANT:
- Use native function calling (NOT XML format) to invoke tools
- Each approach must use a DIFFERENT strategy or tool combination
- Do NOT reference tools that are not in the available list
- Skills expand your capabilities beyond raw tool calls — use them when relevant
{variant_hint}"""

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
) -> str:
    """Compose the full system prompt for a ToT node.

    Structure::

        [base_system_prompt]           <- from SystemPromptBuilder (never truncated)
        ---
        [ToT role instructions]
        [domain_profile injection (if provided)]

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

    Returns:
        The fully composed system prompt string.

    Raises:
        ValueError: If *node_role* is not one of the accepted values.
    """
    role = node_role.lower()
    if role not in ("generator", "evaluator", "termination"):
        raise ValueError(
            f"Invalid node_role '{node_role}'. "
            "Must be one of: generator, evaluator, termination."
        )

    # -- Build the role-specific appendix ---------------------------------
    if role == "generator":
        # Tool list -- derived dynamically so it always matches state["tools"]
        tool_list = "(none)"
        if domain_profile and "tools" in domain_profile:
            tool_list = get_tool_list_string(domain_profile["tools"])

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

        appendix = _GENERATOR_TEMPLATE.format(
            domain_methods_section=domain_methods_section,
            tool_list=tool_list,
            variant_hint=variant_hint,
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

    else:  # termination
        appendix = _TERMINATION_TEMPLATE

        # 域特有终止指令
        domain_term_instruction = ""
        if domain_profile and domain_profile.get("termination_instruction"):
            domain_term_instruction = f"\n--- Domain-Specific Termination Instructions ---\n{domain_profile['termination_instruction']}"
        appendix += domain_term_instruction

    # -- Assemble final prompt --------------------------------------------
    composed = base_system_prompt + "\n---\n" + appendix

    logger.info(
        f"[ToT PromptComposer] role={role}, "
        f"total_len={len(composed)}, base_len={len(base_system_prompt)}, "
        f"appendix_len={len(appendix)}, "
        f"domain_profile={'yes' if domain_profile else 'none'}, "
        f"variant={variant}"
    )

    return composed
