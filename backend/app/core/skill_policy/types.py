"""Shared type definitions for the SkillPolicy pipeline."""

from typing import Any, Dict, List, Optional, TypedDict


class SkillCandidate(TypedDict):
    """Match stage output: a candidate skill with scoring."""
    skill_name: str
    skill_type: str          # "module" | "script" | "instruction"
    score: float             # 0.0-1.0 combined match score
    meta_policy_boost: bool  # whether meta_policy recommended this skill
    source_steps: List[Any]  # PERV: step_ids / ToT: tool_call refs


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
