"""
BudgetEnforcer — 预算强制执行。

每个 task 执行后递增消耗，超预算终止。
全局预算由 thinking_mode 决定。

thinking_mode 预设:
- heuristic: max_tokens=100000, max_cost_usd=2.0
- analytical: max_tokens=500000, max_cost_usd=10.0
- exhaustive: max_tokens=2000000, max_cost_usd=50.0
"""
from __future__ import annotations

import logging

from app.core.tot.taskgraph.models import BudgetCheck, TaskBudget, TaskNode

logger = logging.getLogger(__name__)

GLOBAL_BUDGET_PRESETS = {
    "heuristic": TaskBudget(max_tokens=100000, max_cost_usd=2.0, max_wallclock_seconds=900),
    "analytical": TaskBudget(max_tokens=500000, max_cost_usd=10.0, max_wallclock_seconds=1800),
    "exhaustive": TaskBudget(max_tokens=2000000, max_cost_usd=50.0, max_wallclock_seconds=21600),
}


class BudgetEnforcer:
    """预算强制执行器"""

    def __init__(self, global_budget: TaskBudget):
        self.global_budget = global_budget
        self.global_used = TaskBudget()

    @classmethod
    def from_thinking_mode(cls, thinking_mode: str) -> BudgetEnforcer:
        """根据 thinking_mode 创建对应全局预算"""
        budget = GLOBAL_BUDGET_PRESETS.get(thinking_mode, TaskBudget())
        return cls(global_budget=budget)

    def check_and_record(self, task: TaskNode, execution_result: dict) -> BudgetCheck:
        """检查并记录消耗，返回是否超预算"""
        tokens = execution_result.get("tokens_used", 0)
        cost = execution_result.get("cost_usd", 0.0)
        elapsed = execution_result.get("wallclock_seconds", 0.0)

        # 累加 task 级别
        task.budget.tokens_used += tokens
        task.budget.cost_used += cost
        task.budget.wallclock_seconds_used += elapsed

        # 累加全局
        self.global_used.tokens_used += tokens
        self.global_used.cost_used += cost
        self.global_used.wallclock_seconds_used += elapsed

        # 检查 task 级别（含 wallclock）
        task_exceeded = (
            task.budget.tokens_used >= task.budget.max_tokens
            or task.budget.cost_used >= task.budget.max_cost_usd
            or task.budget.wallclock_seconds_used >= task.budget.max_wallclock_seconds
        )

        # 检查全局级别（含 wallclock）
        global_exceeded = (
            self.global_used.tokens_used >= self.global_budget.max_tokens
            or self.global_used.cost_used >= self.global_budget.max_cost_usd
            or self.global_used.wallclock_seconds_used >= self.global_budget.max_wallclock_seconds
        )

        if task_exceeded:
            logger.warning(
                "Task %s budget exceeded: tokens=%d/%d, cost=%.4f/%.4f, wallclock=%.1f/%.1fs",
                task.id,
                task.budget.tokens_used, task.budget.max_tokens,
                task.budget.cost_used, task.budget.max_cost_usd,
                task.budget.wallclock_seconds_used, task.budget.max_wallclock_seconds,
            )

        if global_exceeded:
            logger.warning(
                "Global budget exceeded: tokens=%d/%d, cost=%.4f/%.4f, wallclock=%.1f/%.1fs",
                self.global_used.tokens_used, self.global_budget.max_tokens,
                self.global_used.cost_used, self.global_budget.max_cost_usd,
                self.global_used.wallclock_seconds_used, self.global_budget.max_wallclock_seconds,
            )

        return BudgetCheck(
            task_exceeded=task_exceeded,
            global_exceeded=global_exceeded,
            should_abort=global_exceeded,
        )
