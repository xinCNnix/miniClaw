"""
Patch 策略 — 三次递进修补。

attempt 0: 修改参数（注入 patch_hints）
attempt 1: 换备选工具（swap tool_name ↔ fallback）
attempt 2: 标记 REPLAN（交给 MicroToT）
"""
from __future__ import annotations

import time

from app.core.tot.taskgraph.models import (
    PatchRecord,
    TaskNode,
    VerifierVerdict,
)
from app.core.tot.taskgraph.executor import map_tool_args


def apply_patch(
    task: TaskNode,
    verdict: VerifierVerdict,
    attempt: int,
) -> TaskNode:
    """根据失败次数应用不同修补策略"""
    if attempt == 0:
        return _patch_retry_args(task, verdict)
    elif attempt == 1:
        return _patch_fallback_tool(task, verdict)
    else:
        return _patch_replan(task, verdict)


def _patch_retry_args(task: TaskNode, verdict: VerifierVerdict) -> TaskNode:
    """attempt 0: 修改工具参数，注入修补建议"""
    for call in task.tool_plan:
        call.args_template["__patch_hints"] = verdict.patch_suggestions

    task.patch_history.append(PatchRecord(
        attempt=0,
        patch_type="RETRY_ARGS",
        suggestions_applied=verdict.patch_suggestions,
        previous_error="; ".join(verdict.failed_reasons),
        timestamp=time.time(),
    ))
    return task


def _patch_fallback_tool(task: TaskNode, verdict: VerifierVerdict) -> TaskNode:
    """Attempt 1: 换到 fallback 工具，映射参数名"""
    swapped = False
    for call in task.tool_plan:
        if call.fallback:
            old_name = call.tool_name
            new_name = call.fallback
            # 映射参数到新工具的 schema
            clean_args = {k: v for k, v in call.args_template.items() if k != "__patch_hints"}
            call.args_template = map_tool_args(new_name, clean_args)
            call.tool_name = new_name
            call.fallback = old_name
            swapped = True
            break

    task.patch_history.append(PatchRecord(
        attempt=1,
        patch_type="FALLBACK_TOOL" if swapped else "REPLAN",
        suggestions_applied=verdict.patch_suggestions[:3],
        previous_error="; ".join(verdict.failed_reasons[:3]),
        timestamp=time.time(),
    ))
    return task


def _patch_replan(task: TaskNode, verdict: VerifierVerdict) -> TaskNode:
    """attempt 2+: 标记需要重规划，交给 MicroToT"""
    task.patch_history.append(PatchRecord(
        attempt=2,
        patch_type="REPLAN",
        suggestions_applied=verdict.patch_suggestions,
        previous_error="; ".join(verdict.failed_reasons),
        timestamp=time.time(),
    ))
    return task
