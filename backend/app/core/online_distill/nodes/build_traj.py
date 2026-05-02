"""BuildTrajectory node — packages execution data into DistillTrajectory."""

from __future__ import annotations

import time
import uuid
from typing import Dict, List

from app.core.execution_trace.models import ToolCallRecord
from app.core.online_distill.models import DistillState, DistillTrajectory


def _to_tool_call_records(raw_calls: List[Dict]) -> List[ToolCallRecord]:
    """Convert raw tool_call dicts to ToolCallRecord instances."""
    records: List[ToolCallRecord] = []
    for i, tc in enumerate(raw_calls):
        records.append(
            ToolCallRecord(
                tool_name=tc.get("tool", tc.get("name", f"unknown_{i}")),
                step_id=tc.get("step_id", str(i)),
                success=tc.get("success", True),
                output_preview=tc.get("output_preview", "")[:200],
                args_summary=tc.get("args_summary", ""),
                duration_ms=tc.get("duration", 0.0),
                error=tc.get("error"),
            )
        )
    return records


def build_traj_node(state: DistillState) -> DistillState:
    """Package execution data into a DistillTrajectory."""
    verify = state.get("verify_result")

    traj = DistillTrajectory(
        traj_id=str(uuid.uuid4()),
        execution_mode=state.get("execution_mode", "normal"),
        user_query=state.get("user_query", ""),
        final_answer=state.get("agent_output", ""),
        tool_calls=_to_tool_call_records(state.get("tool_calls", [])),
        success=verify.success if verify else False,
        score=verify.score if verify else 0.0,
        error_tags=verify.error_tags if verify else [],
        evidence=verify.evidence if verify else {},
        duration_ms=state.get("execution_time", 0.0) * 1000,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        # PEVR extensions
        plan=state.get("plan"),
        observations=state.get("observations"),
        verifier_report=state.get("verifier_report"),
        # ToT extensions
        thought_count=state.get("thought_count", 0),
        best_score=state.get("best_score", 0.0),
        max_depth=state.get("max_depth", 0),
    )

    state["trajectory"] = traj
    return state
