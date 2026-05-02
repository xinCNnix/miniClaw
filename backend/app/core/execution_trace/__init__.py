"""
Unified Execution Trace Module

Provides execution trace logging for all three agent modes:
- NormalTrace: Standard agent execution (dual-mode: manual + LangChain callback)
- PEVRTrace: Planner-Executor-Verifier-Replanner loop
- ToTTrace: Tree of Thoughts reasoning

Public API:
    from app.core.execution_trace import (
        NormalTrace, PEVRTrace, ToTTrace,
        extract_token_usage,
    )
"""

__all__ = [
    # Trace classes
    "NormalTrace",
    "PEVRTrace",
    "ToTTrace",
    # Utilities
    "extract_token_usage",
    # Models
    "TokenUsage",
    "TokenBreakdown",
    "ToolCallRecord",
    "RoundMetrics",
    "StepRecord",
    "SkillExecutionRecord",
    "TrajectorySummary",
    "PlanStepRecord",
    "SkillPolicyRecord",
    "LoopRecord",
    "ThoughtScore",
    "PromptCompositionRecord",
    "EvidenceExtractionRecord",
    "CoverageUpdateRecord",
    "ContradictionRecord",
    "CitationChaseRecord",
    "IterationRecord",
]


def __getattr__(name: str):
    """Lazy imports to avoid circular dependencies."""
    # Trace classes
    if name == "NormalTrace":
        from app.core.execution_trace.normal_trace import NormalTrace
        return NormalTrace
    if name == "PEVRTrace":
        from app.core.execution_trace.perv_trace import PEVRTrace
        return PEVRTrace
    if name == "ToTTrace":
        from app.core.execution_trace.tot_trace import ToTTrace
        return ToTTrace

    # Utilities
    if name == "extract_token_usage":
        from app.core.execution_trace.token_utils import extract_token_usage
        return extract_token_usage

    # Models
    _MODEL_NAMES = {
        "TokenUsage", "TokenBreakdown", "ToolCallRecord",
        "RoundMetrics", "StepRecord", "SkillExecutionRecord", "TrajectorySummary",
        "PlanStepRecord", "SkillPolicyRecord", "LoopRecord",
        "ThoughtScore", "PromptCompositionRecord",
        "EvidenceExtractionRecord", "CoverageUpdateRecord",
        "ContradictionRecord", "CitationChaseRecord", "IterationRecord",
    }
    if name in _MODEL_NAMES:
        from app.core.execution_trace import models
        return getattr(models, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
