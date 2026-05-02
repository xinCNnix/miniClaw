"""Online Distill data models — VerifyResult, DistillTrajectory, DistillState."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, TypedDict

from app.core.dream.models import SkillCard
from app.core.execution_trace.models import StepRecord, ToolCallRecord


# ---------------------------------------------------------------------------
# Verify result
# ---------------------------------------------------------------------------


@dataclass
class VerifyResult:
    """Online execution evaluation result."""

    success: bool
    score: float  # 0-10 (from ReflectionResult.quality_score)
    error_tags: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    # evidence: { "tool_quotes": [...], "step_refs": [...], "reasoning": "..." }
    reusable_pattern: Optional[str] = None
    failure_type: Optional[str] = None
    should_distill: bool = False


# ---------------------------------------------------------------------------
# Online Distill trajectory
# ---------------------------------------------------------------------------


@dataclass
class DistillTrajectory:
    """Online execution trajectory, shared between Online Distill and Dream."""

    traj_id: str
    execution_mode: Literal["normal", "tot", "perv"]
    user_query: str
    final_answer: str
    steps: List[StepRecord] = field(default_factory=list)
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    tool_logs: List[Dict[str, Any]] = field(default_factory=list)
    success: bool = False
    score: float = 0.0
    error_tags: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    created_at: str = ""

    # PEVR-specific fields
    plan: Optional[List[Dict[str, Any]]] = None
    observations: Optional[List[Dict[str, Any]]] = None
    verifier_report: Optional[Dict[str, Any]] = None

    # ToT-specific fields
    thought_count: int = 0
    best_score: float = 0.0
    max_depth: int = 0


# ---------------------------------------------------------------------------
# Online Distill subgraph state (TypedDict for LangGraph)
# ---------------------------------------------------------------------------


class DistillState(TypedDict, total=False):
    """OnlineDistillGraph shared state."""

    # Input
    user_query: str
    agent_output: str
    tool_calls: List[Dict[str, Any]]
    execution_time: float
    execution_mode: Literal["normal", "tot", "perv"]

    # PEVR extended input
    plan: List[Dict[str, Any]]
    observations: List[Dict[str, Any]]
    verifier_report: Dict[str, Any]

    # ToT extended input
    thought_count: int
    best_score: float
    max_depth: int

    # verify output
    verify_result: VerifyResult

    # build_traj output
    trajectory: DistillTrajectory

    # write_traj output
    traj_id: str

    # distill output
    distilled_skill: Optional[SkillCard]

    # write_provisional output
    written_skill_id: Optional[str]
    write_error: Optional[str]
