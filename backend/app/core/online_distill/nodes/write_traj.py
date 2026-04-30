"""WriteTrajectory node — persists trajectory to SQLite + JSON trace file."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict

from app.core.online_distill.models import DistillState

logger = logging.getLogger(__name__)

# Traces are stored under backend/logs/traces/ (project convention)
_TRACES_BASE = Path("logs/traces/online_distill")


def _step_to_dict(s: Any) -> Dict[str, Any]:
    """Convert a StepRecord to a JSON-serializable dict."""
    if hasattr(s, "__dataclass_fields__"):
        return asdict(s)
    if isinstance(s, dict):
        return s
    return {"repr": str(s)}


async def write_traj_node(state: DistillState) -> DistillState:
    """Persist trajectory to SQLite index + full JSON trace file.

    1. Write complete JSON trace to logs/traces/online_distill/{mode}/ (for Dream replay)
    2. Write SQLite index row via TrajectoryStore.add()
    """
    from app.core.dream.nodes.trajectory_store import TrajectoryStore

    traj = state.get("trajectory")
    if not traj:
        state["traj_id"] = ""
        return state

    # 1. Write complete JSON trace (for Dream _row_to_trajectory replay)
    traces_dir = _TRACES_BASE / traj.execution_mode
    traces_dir.mkdir(parents=True, exist_ok=True)
    trace_path = traces_dir / f"{traj.traj_id}.json"
    trace_data: Dict[str, Any] = {
        "user_question": traj.user_query,
        "final_answer": traj.final_answer,
        "success": traj.success,
        "created_at": traj.created_at,
        "total_duration": traj.duration_ms / 1000.0,
        "constraints": [],
        "steps": [_step_to_dict(s) for s in traj.steps] if traj.steps else [],
        "skills": [],
        "tool_calls": [_step_to_dict(tc) for tc in traj.tool_calls] if traj.tool_calls else [],
    }
    try:
        trace_path.write_text(
            json.dumps(trace_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as e:
        logger.warning("[OnlineDistill] Failed to write trace file: %s", e)

    # 2. Write SQLite index row
    try:
        # Ensure all values are SQLite-compatible types (no raw list/dict)
        _reasoning = traj.evidence.get("reasoning", "")
        if isinstance(_reasoning, (list, dict)):
            _reasoning = json.dumps(_reasoning, ensure_ascii=False)
        _failure_summary = str(_reasoning)[:500]

        _error_tags = traj.error_tags or []
        _failure_type = ",".join(str(t) for t in _error_tags) if _error_tags else None

        store = TrajectoryStore()
        store.add(
            traj_id=traj.traj_id,
            source="online",
            mode=traj.execution_mode,
            task=traj.user_query[:500],
            success=traj.success,
            failure_type=_failure_type,
            failure_summary=_failure_summary,
            tags_json="[]",
            cost_time_ms=traj.duration_ms,
            created_at=traj.created_at,
            file_path=str(trace_path),
        )
    except Exception as e:
        logger.warning("[OnlineDistill] Failed to write trajectory index: %s", e)

    state["traj_id"] = traj.traj_id
    return state
