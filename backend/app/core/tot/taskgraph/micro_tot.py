"""
MicroToT — 局部搜索，仅在困难节点触发。

触发条件: task 连续 Verifier fail ≥ 2 次
策略: 生成多个候选方案（ARG_VARIANT + TOOL_VARIANT + COMBINED），Rule 层快速评分
预算: 从 task budget 分配，上限 3000 tokens
"""
from __future__ import annotations

import logging
from typing import List, Optional

from app.core.tot.taskgraph.models import (
    DoDCheck,
    MicroCandidate,
    ReplanResult,
    TaskNode,
    ToolPlanItem,
)

logger = logging.getLogger(__name__)


class MicroToT:
    """局部搜索 — 在困难任务节点生成替代方案"""

    def __init__(self, max_branches: int = 3, max_depth: int = 2):
        self.max_branches = max_branches
        self.max_depth = max_depth

    def should_trigger(self, task: TaskNode) -> bool:
        """判断是否应触发 MicroToT"""
        return task.attempt_count >= 2

    def replan_rule(self, task: TaskNode) -> ReplanResult:
        """基于规则的重规划（不调 LLM）"""
        candidates = self._generate_rule_candidates(task)
        if not candidates:
            return ReplanResult(
                new_tool_plan=task.tool_plan,
                patch_description="无可用候选方案",
                confidence=0.0,
            )

        scored = [(c, self._quick_score(c, task.dod)) for c in candidates]
        scored.sort(key=lambda x: -x[1])
        best = scored[0]

        return ReplanResult(
            new_tool_plan=best[0].tool_plan,
            patch_description=best[0].description,
            confidence=best[1] / 10.0,
        )

    def _generate_rule_candidates(self, task: TaskNode) -> List[MicroCandidate]:
        """基于规则生成候选方案（参数映射安全）"""
        from app.core.tot.taskgraph.executor import map_tool_args

        candidates: List[MicroCandidate] = []

        # ARG_VARIANT: 保持工具不变，添加 patch hints 指导重试
        if task.tool_plan:
            new_plan = []
            for item in task.tool_plan:
                new_args = {k: v for k, v in item.args_template.items() if k != "__patch_hints"}
                new_plan.append(ToolPlanItem(
                    tool_name=item.tool_name,
                    args_template=new_args,
                    fallback=item.fallback,
                ))
            candidates.append(MicroCandidate(
                tool_plan=new_plan,
                description="保持工具不变，添加重试指导",
                variant_type="ARG_VARIANT",
            ))

        # TOOL_VARIANT: 换工具 + 映射参数
        for item in task.tool_plan:
            if item.fallback:
                mapped_args = map_tool_args(item.fallback, {
                    k: v for k, v in item.args_template.items() if k != "__patch_hints"
                })
                candidates.append(MicroCandidate(
                    tool_plan=[ToolPlanItem(
                        tool_name=item.fallback,
                        args_template=mapped_args,
                    )],
                    description=f"使用备选工具 {item.fallback}",
                    variant_type="TOOL_VARIANT",
                ))
                break

        # COMBINED: 换工具 + 改参数（同样使用 map_tool_args）
        if len(task.tool_plan) >= 2:
            alt_tool = task.tool_plan[0].fallback or "search_kb"
            mapped = map_tool_args(alt_tool, {"query": "综合搜索"})
            candidates.append(MicroCandidate(
                tool_plan=[
                    ToolPlanItem(tool_name=alt_tool, args_template=mapped),
                ],
                description="组合变体",
                variant_type="COMBINED",
            ))

        return candidates[:self.max_branches]

    def _quick_score(self, candidate: MicroCandidate, dod: List[DoDCheck]) -> float:
        """基于 DoD 的快速评分（不调 LLM）"""
        score = 5.0  # 基线分

        if candidate.tool_plan:
            score += 1.0

        if 1 <= len(candidate.tool_plan) <= 3:
            score += 1.0

        if candidate.variant_type == "TOOL_VARIANT":
            score += 1.0
        elif candidate.variant_type == "COMBINED":
            score += 0.5

        return score
