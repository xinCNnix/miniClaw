"""
Unified Execution Trace Data Models

Consolidates data models from trajectory/models.py, perv/pevr_logger.py,
and tot/tot_logger.py into a single source of truth.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Token tracking
# ---------------------------------------------------------------------------

@dataclass
class TokenUsage:
    """Single LLM call token usage record."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }

    @classmethod
    def from_response(cls, response: Any) -> "TokenUsage":
        """Build TokenUsage from an LLM response."""
        from app.core.execution_trace.token_utils import extract_token_usage
        usage = extract_token_usage(response)
        return cls(
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            total_tokens=usage["total_tokens"],
        )


@dataclass
class TokenBreakdown:
    """Per-component token usage breakdown across rounds."""

    system_prompt: int = 0
    conversation_history: int = 0
    user_input: int = 0
    tool_results: int = 0
    tca_injection: int = 0
    meta_policy_injection: int = 0
    total_prompt: int = 0
    total_completion: int = 0
    total: int = 0

    def to_dict(self) -> dict:
        return {
            "system_prompt": self.system_prompt,
            "conversation_history": self.conversation_history,
            "user_input": self.user_input,
            "tool_results": self.tool_results,
            "tca_injection": self.tca_injection,
            "meta_policy_injection": self.meta_policy_injection,
            "total_prompt": self.total_prompt,
            "total_completion": self.total_completion,
            "total": self.total,
        }

    def __add__(self, other: "TokenBreakdown") -> "TokenBreakdown":
        return TokenBreakdown(
            system_prompt=self.system_prompt + other.system_prompt,
            conversation_history=self.conversation_history + other.conversation_history,
            user_input=self.user_input + other.user_input,
            tool_results=self.tool_results + other.tool_results,
            tca_injection=self.tca_injection + other.tca_injection,
            meta_policy_injection=self.meta_policy_injection + other.meta_policy_injection,
            total_prompt=self.total_prompt + other.total_prompt,
            total_completion=self.total_completion + other.total_completion,
            total=self.total + other.total,
        )


# ---------------------------------------------------------------------------
# Tool call records (unified superset)
# ---------------------------------------------------------------------------

@dataclass
class ToolCallRecord:
    """Unified tool call record (compatible with PEVR and ToT fields)."""
    tool_name: str
    # PEVR-specific
    step_id: str = ""
    status: str = "success"
    output_preview: str = ""
    # ToT-specific
    args_summary: str = ""
    cached: bool = False
    # Common
    success: bool = True
    duration_ms: float = 0.0
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Normal mode models (from trajectory/models.py)
# ---------------------------------------------------------------------------

@dataclass
class RoundMetrics:
    """Metrics for a single LLM round."""
    round_number: int = 0
    llm_duration: float = 0.0
    tool_count: int = 0
    tool_duration: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class StepRecord:
    """Single step execution record in agent trajectory."""
    step_number: int
    thought: str
    action: str
    input_data: dict
    result: Optional[str] = None
    success: bool = True
    duration: float = 0.0
    timestamp: str = ""
    error: Optional[str] = None
    round_number: int = 0


@dataclass
class SkillExecutionRecord:
    """Record of a skill interception during execution."""
    skill_name: str
    matched: bool = False
    executed: bool = False
    success: bool = False
    duration: float = 0.0
    error: Optional[str] = None


@dataclass
class TrajectorySummary:
    """Trajectory execution summary."""
    user_question: str = ""
    total_duration: float = 0.0
    llm_duration: float = 0.0
    tool_duration: float = 0.0
    total_rounds: int = 0
    successful_steps: int = 0
    failed_steps: int = 0
    actions_used: list[str] = field(default_factory=list)
    token_breakdown: Optional[TokenBreakdown] = None
    rounds: list[RoundMetrics] = field(default_factory=list)
    skills: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# PEVR mode models (from perv/pevr_logger.py)
# ---------------------------------------------------------------------------

@dataclass
class PlanStepRecord:
    """Record of a plan step generated by the planner."""
    step_id: str
    tool: str
    description: str = ""
    expected: str = ""


@dataclass
class SkillPolicyRecord:
    """Record of SkillPolicyNode execution within a PEVR loop."""
    policy_applied: bool = False
    plan_steps_in: int = 0
    skill_refs_found: int = 0
    skill_refs: List[Dict[str, Any]] = field(default_factory=list)
    matched_count: int = 0
    matched_skills: List[Dict[str, Any]] = field(default_factory=list)
    gate_results: List[Dict[str, Any]] = field(default_factory=list)
    guard_passed: bool = False
    guard_issues: List[str] = field(default_factory=list)
    compiled_count: int = 0
    compiled_skills: List[Dict[str, Any]] = field(default_factory=list)
    plan_steps_out: int = 0
    duration_ms: float = 0.0
    error: Optional[str] = None
    feature_enabled: bool = True


@dataclass
class LoopRecord:
    """Record of a single PEVR loop iteration (plan -> execute -> verify)."""
    loop_index: int
    start_time: float = 0.0
    start_ts: str = ""
    end_time: float = 0.0
    end_ts: str = ""

    # Planning phase
    plan_steps: List[PlanStepRecord] = field(default_factory=list)
    planning_duration_ms: float = 0.0
    planning_error: Optional[str] = None
    planning_tokens: TokenUsage = field(default_factory=TokenUsage)

    # SkillPolicy phase (between planning and execution)
    skill_policy: Optional[SkillPolicyRecord] = None

    # Execution phase
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    execution_duration_ms: float = 0.0
    execution_error: Optional[str] = None
    execution_tokens: TokenUsage = field(default_factory=TokenUsage)

    # Verification phase
    verification_passed: bool = False
    verification_coverage: float = 0.0
    verification_grounded: bool = False
    verification_reason: str = ""
    verification_missing: List[str] = field(default_factory=list)
    verification_duration_ms: float = 0.0
    verification_error: Optional[str] = None
    verification_tokens: TokenUsage = field(default_factory=TokenUsage)

    # Replanning phase (only when verification fails)
    replan_action: Optional[str] = None
    replan_target_step: Optional[str] = None
    replan_new_steps_count: int = 0
    replan_duration_ms: float = 0.0
    replan_error: Optional[str] = None
    replan_tokens: TokenUsage = field(default_factory=TokenUsage)


# ---------------------------------------------------------------------------
# ToT mode models (from tot/tot_logger.py)
# ---------------------------------------------------------------------------

@dataclass
class ThoughtScore:
    """Score for a single thought in evaluation."""
    thought_id: str
    score: float
    criteria: dict = field(default_factory=dict)
    fatal_flaw: Optional[str] = None


@dataclass
class PromptCompositionRecord:
    """Record of how a prompt was composed for a ToT node."""
    node_role: str = ""
    template_name: str = ""
    system_prompt_length: int = 0
    base_prompt_length: int = 0
    appendix_length: int = 0
    appendix_preview: str = ""
    user_prompt_preview: str = ""
    domain_methods_injected: list = field(default_factory=list)
    domain_instruction_preview: str = ""
    tool_list: str = ""
    variant: int = 0


@dataclass
class EvidenceExtractionRecord:
    """Record of evidence extracted from a single source."""
    source_id: str
    source_type: str
    claim_count: int
    number_count: int
    reliability: float
    duration_ms: float


@dataclass
class CoverageUpdateRecord:
    """Record of a coverage map update during research."""
    coverage_score: float
    topics_covered: int
    topics_total: int
    critical_missing: List[str]


@dataclass
class ContradictionRecord:
    """Record of contradiction detection results."""
    conflict_count: int
    max_severity: float
    types_found: List[str]


@dataclass
class CitationChaseRecord:
    """Record of citation chasing activity."""
    targets_count: int
    fetched_count: int
    budget_remaining: int


@dataclass
class IterationRecord:
    """Record of a single ToT iteration (generate -> evaluate -> execute -> terminate)."""
    depth: int
    start_time: float = 0.0
    end_time: float = 0.0

    # Generation phase
    generation_count: int = 0
    generation_variant: str = ""
    generation_prompt_length: int = 0
    generation_duration_ms: float = 0.0

    # Prompt composition tracking
    generation_prompt_composition: Optional[PromptCompositionRecord] = None
    evaluation_prompt_composition: Optional[PromptCompositionRecord] = None
    termination_prompt_preview: str = ""

    # Evaluation phase
    scores: list = field(default_factory=list)
    best_path_changed: bool = False
    beam_pruned: int = 0
    evaluation_duration_ms: float = 0.0

    # Phase 9: Beam search tracking
    active_beam_count: int = 0
    beam_width_used: int = 0
    backtrack_events: list = field(default_factory=list)
    local_loop_steps: int = 0

    # Execution phase
    tool_calls: list = field(default_factory=list)
    cache_hits: int = 0
    cache_misses: int = 0
    execution_duration_ms: float = 0.0

    # Termination decision
    should_stop: bool = False
    stop_trigger: Optional[str] = None
    termination_details: dict = field(default_factory=dict)

    # Research phase tracking
    evidence_extraction: Optional[List[EvidenceExtractionRecord]] = None
    coverage_update: Optional[CoverageUpdateRecord] = None
    contradiction_detection: Optional[ContradictionRecord] = None
    citation_chase: Optional[CitationChaseRecord] = None
    token_used_this_iteration: Optional[int] = None
    research_round: Optional[int] = None

    # ISO UTC timestamps (millisecond precision)
    start_ts: str = ""
    end_ts: str = ""

    # Per-phase token tracking
    generation_tokens: Dict[str, int] = field(default_factory=dict)
    evaluation_tokens: Dict[str, int] = field(default_factory=dict)
    execution_tokens: Dict[str, int] = field(default_factory=dict)
    termination_tokens: Dict[str, int] = field(default_factory=dict)
