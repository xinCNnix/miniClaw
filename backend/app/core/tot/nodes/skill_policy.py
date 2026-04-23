"""ToT SkillPolicy adapter — hooks into thought_executor's tool execution.

Uses the unified run_skill_policy pipeline instead of separate gate + compile
calls. No longer hard-codes skip for script/handler_module types.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def check_skill_policy_gate(
    skill_name: str,
    user_query: str,
    tools: List,
    llm: Any,
    skills_dir: Path,
    enrichment: Dict[str, Any] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Run unified SkillPolicy pipeline for a single skill.

    Returns tool_plan list on success, None on failure/pass-through.
    Used by thought_executor before executing a read_file(SKILL.md).
    """
    try:
        from app.core.skill_policy.engine import run_skill_policy, _classify_skill_type
        from app.core.skill_policy.types import PolicyInput
    except ImportError:
        logger.debug("[ToT SkillPolicy] SkillPolicy not available")
        return None

    skill_md_path = skills_dir / skill_name / "SKILL.md"
    if not skill_md_path.exists():
        return None

    skill_type = _classify_skill_type(skill_name, skills_dir)
    logger.info("ToT SkillPolicy: checking gate for '%s' type=%s", skill_name, skill_type)

    try:
        skill_content = skill_md_path.read_text(encoding="utf-8")
    except Exception:
        return None

    core_tools = [t.name for t in tools] if tools else []

    policy_input = PolicyInput(
        user_query=user_query,
        current_step={"tool": "read_file"},
        available_tools=core_tools,
        candidate_skills=[],
        skill_content=skill_content,
        skill_name=skill_name,
        skill_type=skill_type,
        history=enrichment or {},
    )

    output = await run_skill_policy(policy_input, llm)

    if output.get("action") == "EXECUTE_TOOL_PLAN" and output.get("tool_plan"):
        logger.info(
            "ToT SkillPolicy: '%s' gate passed, tool_plan=%d step(s)",
            skill_name, len(output["tool_plan"]),
        )
        return output["tool_plan"]

    logger.info(
        "ToT SkillPolicy: '%s' action=%s",
        skill_name, output.get("action", "?"),
    )
    return None
