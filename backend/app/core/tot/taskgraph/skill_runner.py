"""
SkillRunner — Skill-first 执行。

检测 tool_plan 中的 skill 调用，通过 SkillPolicy gate 执行。
失败时降级到 TaskGraph。
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from app.core.tot.taskgraph.models import SkillRunResult

logger = logging.getLogger(__name__)


class SkillRunner:
    """Skill-first 执行器"""

    def __init__(self, tools: Dict[str, Any] = None):
        self.tools = tools or {}

    def detect_skill_invocation(self, tool_plan: List[Dict[str, Any]]) -> Optional[str]:
        """检测 tool_plan 中是否包含 skill 调用 (read_file(*SKILL.md))"""
        for item in tool_plan:
            tool_name = item.get("tool_name", "")
            args = item.get("args_template", {})
            if tool_name == "read_file":
                path = args.get("path", "")
                if "SKILL.md" in path:
                    match = re.search(r"skills/([^/]+)/SKILL\.md", path)
                    if match:
                        return match.group(1)
        return None

    async def run(
        self,
        skill_id: str,
        args: Dict[str, Any],
        context: Dict[str, Any],
        max_attempts: int = 3,
    ) -> SkillRunResult:
        """执行 skill"""
        logger.info("SkillRunner: skill %s detected, delegating to TaskGraph for now", skill_id)
        return SkillRunResult(
            success=False,
            should_fallback=True,
            error=f"Skill {skill_id} 需要通过 TaskGraph 执行",
        )
