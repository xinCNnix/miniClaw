"""Shared type definitions for the SkillPolicy pipeline.

Includes both the new PolicyInput/PolicyOutput interfaces (v2) and
legacy types for backward compatibility.
"""

from typing import Any, Dict, List, Optional, TypedDict


# ---------------------------------------------------------------------------
# v2: Unified interface (referenced by docs/skill节点.md)
# ---------------------------------------------------------------------------


class PolicyInput(TypedDict):
    """Unified input for SkillPolicy pipeline.

    Constructed by each mode's adapter layer before calling run_skill_policy().
    """

    user_query: str
    current_step: Dict[str, Any]      # step context: id, intent, tool_hint, etc.
    available_tools: List[str]        # tool names available in this pipeline
    candidate_skills: List[Dict]      # pre-matched skill candidates (optional)
    skill_content: str                # raw SKILL.md content
    skill_name: str
    skill_type: str                   # instruction | module | script | handler_module
    history: Dict[str, Any]          # prior tool output summaries


class PolicyOutput(TypedDict):
    """Unified output from SkillPolicy pipeline.

    The adapter layer branches on ``action`` to decide what to do next.
    """

    action: str                       # EXECUTE_TOOL_PLAN | PASS_THROUGH | BLOCK
    tool_plan: List[Dict[str, Any]]   # [{"tool": str, "args": dict}]
    selected_skill: Optional[Dict]    # matched skill metadata
    guardrails: Dict[str, Any]       # budget constraints, allowed/forbidden tools
    notes: str                        # logging / debug info


# ---------------------------------------------------------------------------
# Legacy types (kept for backward compatibility)
# ---------------------------------------------------------------------------


class SkillCandidate(TypedDict):
    """Match stage output: a candidate skill with scoring."""

    skill_name: str
    skill_type: str          # "module" | "script" | "handler_module" | "instruction"
    score: float             # 0.0-1.0 combined match score
    meta_policy_boost: bool  # whether meta_policy recommended this skill
    source_steps: List[Any]  # PERV: step_ids / ToT: tool_call refs
    skill_status: str        # "stable" | "candidate" | "provisional" (default stable)


class GateDecision(TypedDict):
    """Gate stage output: allow/reject decision for a skill."""

    skill_name: str
    allowed: bool
    reason: str              # allow/reject reason


class GuardResult(TypedDict):
    """Guard stage output: static validation of compiled plan."""

    passed: bool
    issues: List[str]
    final_plan: Optional[List[Dict[str, Any]]]


class SkillPolicyReport(TypedDict):
    """Full SkillPolicyNode processing report (stored in state)."""

    policy_applied: bool             # False = PASS_THROUGH
    matched_skills: List[Dict]
    gate_results: List[Dict]
    guard_passed: bool
    guard_issues: List[str]
    compiled_plan: Optional[List]    # PERV: PlanStep[] / ToT: None (in-place)
    error: Optional[str]
