"""
DoDGenerator — 自动生成完成标准 (Definition of Done) 检查项。

三路策略:
1. 通用基线 — 所有任务都有
2. Domain profile 增强 — 按任务类型和领域
3. 工具推断 — 根据工具计划推断额外检查
"""
from __future__ import annotations

import logging
from typing import List

from app.core.tot.taskgraph.models import DoDCheck, ToolPlanItem
from app.core.tot.profiles.base import DomainProfile

logger = logging.getLogger(__name__)


class DoDGenerator:
    """为 TaskGraph 节点自动生成 DoD 检查项"""

    def generate(
        self,
        task_type: str,
        domain: DomainProfile,
        tool_plan: List[ToolPlanItem],
    ) -> List[DoDCheck]:
        """为任务生成完成标准检查项列表"""
        checks: List[DoDCheck] = []

        # 1. 通用基线
        checks.extend(self._baseline_checks())

        # 2. Domain profile 增强
        checks.extend(self._domain_checks(task_type, domain))

        # 3. 工具推断
        checks.extend(self._tool_inferred_checks(tool_plan))

        return checks

    def generate_for_skill(self, skill_md: str) -> List[DoDCheck]:
        """从 skill.md 提取 DoD（给 SkillRunner 用）"""
        checks = self._baseline_checks()
        if "write_file" in skill_md or "保存" in skill_md:
            checks.append(DoDCheck(
                check_type="FILE_EXISTS",
                severity="HARD",
                description="Skill 应产生输出文件",
            ))
        return checks

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _baseline_checks(self) -> List[DoDCheck]:
        """通用基线检查 — 所有任务都必须通过"""
        return [
            DoDCheck(
                check_type="NON_EMPTY",
                severity="HARD",
                description="工具结果不能为空",
            ),
            DoDCheck(
                check_type="TOOL_SUCCESS",
                severity="HARD",
                description="所有工具调用必须成功（无 error）",
            ),
        ]

    def _domain_checks(self, task_type: str, domain: DomainProfile) -> List[DoDCheck]:
        """按任务类型生成领域特定检查"""
        checks: List[DoDCheck] = []

        if task_type in ("research_writing", "research"):
            checks.append(DoDCheck(
                check_type="SOURCE_COUNT",
                severity="SOFT",
                description="研究类任务建议引用多个来源",
                params={"min_sources": 2},
            ))
            checks.append(DoDCheck(
                check_type="NO_CONTRADICTION",
                severity="SOFT",
                description="不应存在未解决的矛盾",
            ))

        elif task_type in ("coding_debug", "coding"):
            checks.append(DoDCheck(
                check_type="CODE_EXECUTABLE",
                severity="HARD",
                description="代码必须可执行，无 traceback",
            ))

        elif task_type == "writing":
            checks.append(DoDCheck(
                check_type="MIN_LENGTH",
                severity="SOFT",
                description="输出至少 200 字",
                params={"min_length": 200},
            ))

        return checks

    def _tool_inferred_checks(self, tool_plan: List[ToolPlanItem]) -> List[DoDCheck]:
        """根据工具计划推断额外检查"""
        checks: List[DoDCheck] = []

        for item in tool_plan:
            if item.tool_name == "write_file":
                path = item.args_template.get("path", "")
                if path:
                    checks.append(DoDCheck(
                        check_type="FILE_EXISTS",
                        severity="HARD",
                        description=f"文件 {path} 应该已创建",
                        params={"path": path},
                    ))

        return checks
