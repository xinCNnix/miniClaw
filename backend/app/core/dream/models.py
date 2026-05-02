"""
Dream pipeline data models.

Reuses StepRecord, ToolCallRecord, TrajectorySummary from execution_trace.
Dream-specific models use the Dream* prefix to avoid name collisions.
DreamState is a TypedDict(total=False) matching the project's LangGraph state convention.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, TypedDict

# Reuse existing execution trace models
from app.core.execution_trace.models import StepRecord, ToolCallRecord, TrajectorySummary

# ---------------------------------------------------------------------------
# Failure type enumeration (fixed set for stable knowledge graph edges)
# ---------------------------------------------------------------------------

FailureType = Literal[
    "ImportError",
    "DependencyMissing",
    "TestFailure",
    "SyntaxError",
    "RuntimeError",
    "Timeout",
    "ToolError",
    "PermissionDenied",
    "NetworkBlocked",
    "LogicBug",
    "SpecAmbiguity",
    "IncompleteDoD",
    "Unknown",
]

# ---------------------------------------------------------------------------
# Dream trajectory (extends TrajectorySummary for Dream pipeline input)
# ---------------------------------------------------------------------------


@dataclass
class DreamTrajectory:
    """Dream pipeline trajectory, converted from TrajectorySummary by TrajectoryStore."""

    traj_id: str
    source: Literal["online", "dream"] = "online"
    task: str = ""
    constraints: List[str] = field(default_factory=list)
    context_digest: Optional[str] = None
    steps: List[StepRecord] = field(default_factory=list)
    final_answer: Optional[str] = None
    success: bool = False
    failure_type: Optional[str] = None
    failure_summary: Optional[str] = None
    cost_tokens: Optional[int] = None
    cost_time_ms: Optional[int] = None
    tags: List[str] = field(default_factory=list)
    created_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Mutation specification
# ---------------------------------------------------------------------------


@dataclass
class MutationSpec:
    mutation_id: str
    mutation_type: Literal[
        "constraint_flip",
        "scale_up",
        "scale_down",
        "error_injection",
        "goal_variant",
        "tool_restriction",
        "edge_case",
        "adversarial",
    ]
    new_task: str
    new_constraints: List[str] = field(default_factory=list)
    expected_difficulty: Literal["easy", "medium", "hard"] = "medium"
    rationale: Optional[str] = None


# ---------------------------------------------------------------------------
# Dream batch
# ---------------------------------------------------------------------------


@dataclass
class DreamBatch:
    base_traj_id: str
    sampled_reason: str
    mutation_specs: List[MutationSpec] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Judge score (6-dimension)
# ---------------------------------------------------------------------------


@dataclass
class JudgeScore:
    success: bool
    score_total: float = 0.0  # weighted total 0-100
    correctness: float = 0.0  # 0-1
    evidence_quality: float = 0.0  # 0-1
    reasoning_coherence: float = 0.0  # 0-1
    tool_usage: float = 0.0  # 0-1
    robustness: float = 0.0  # 0-1
    safety: float = 0.0  # 0-1
    error_tags: List[str] = field(default_factory=list)
    explanation: str = ""
    accept: bool = False
    reject_reason: Optional[str] = None

    # Weighted formula:
    # 0.45*correctness + 0.20*evidence_quality + 0.10*reasoning_coherence
    # + 0.10*tool_usage + 0.10*robustness + 0.05*safety
    # Hard failure: hallucination or unsafe_action → success must be False


# ---------------------------------------------------------------------------
# Skill card (core Dream product)
# ---------------------------------------------------------------------------


@dataclass
class SkillCard:
    """Dream-distilled skill card.

    Lifecycle: provisional → candidate → stable → deprecated
    Aligned with skill_policy/types.py SkillCandidate.skill_status.
    """

    skill_id: str
    skill_name: str
    trigger: str  # trigger condition
    problem_pattern: str  # task pattern description
    steps: List[str]  # executable steps
    verification: List[str]  # verification commands
    anti_patterns: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    confidence: float = 0.5
    supporting_cases: int = 0
    source_traj_ids: List[str] = field(default_factory=list)
    status: Literal["provisional", "candidate", "stable", "deprecated"] = "provisional"

    # Regression tests (required for stable promotion)
    regression_tests: List[Dict[str, Any]] = field(default_factory=list)
    # regression_tests item format:
    # {
    #   "test_id": "T1",
    #   "input_query": "synthetic but realistic user query",
    #   "expected_properties": ["property-based expectation"],
    #   "tool_expectations": {
    #     "must_call": ["tool_name"],
    #     "must_not_call": ["tool_name"],
    #     "max_calls": 5,
    #   },
    #   "adversarial_variants": ["prompt injection attempt"],
    # }


# ---------------------------------------------------------------------------
# Dream subgraph state (TypedDict for LangGraph, matches project convention)
# ---------------------------------------------------------------------------


class DreamState(TypedDict, total=False):
    """Dream subgraph shared state.

    Uses total=False (like MemoryState) since different nodes populate different subsets.
    """

    # Input
    dream_request_id: str
    dream_mode: Literal["nightly", "manual", "triggered"]

    # Trajectory store sampling result
    sampled_trajectories: List[DreamTrajectory]

    # Generated mutation batches
    dream_batches: List[DreamBatch]

    # Executor-produced dream trajectories
    dream_trajectories: List[DreamTrajectory]

    # Judge scores
    judge_scores: Dict[str, JudgeScore]

    # Distilled skills
    distilled_skills: List[SkillCard]

    # Deduplicated skills
    deduplicated_skills: List[SkillCard]

    # Regression test results
    regression_report: Dict[str, Dict[str, Any]]  # skill_id -> {"passed": bool, ...}

    # Memory writer output
    written_skill_ids: List[str]
    write_errors: List[str]

    # Control parameters
    max_samples: int  # default 3
    mutations_per_traj: int  # default 5
    max_exec_steps: int  # default 8
    min_accept_score: float  # default 75.0
    executor_mode: Literal["simulated", "replay"]  # default "simulated"
