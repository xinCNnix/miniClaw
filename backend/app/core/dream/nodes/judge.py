"""
StrongJudge — 6-dimension evaluation for Dream trajectories.

Supports three modes:
- rule: Pure rule-based scoring (fast, no LLM cost)
- llm: LLM-based scoring (thorough, requires LLM call)
- hybrid: Rule pre-filter + LLM for borderline cases (default)
"""

import json
import logging
from typing import Dict, Optional

from app.core.dream.config import DreamConfig
from app.core.dream.models import DreamState, DreamTrajectory, JudgeScore
from app.core.dream.prompts.judge import (
    STRONG_JUDGE_SYSTEM,
    format_judge_prompt,
)

logger = logging.getLogger(__name__)

# Weight constants matching spec
W_CORRECTNESS = 0.45
W_EVIDENCE = 0.20
W_REASONING = 0.10
W_TOOL_USAGE = 0.10
W_ROBUSTNESS = 0.10
W_SAFETY = 0.05


def _compute_score_total(j: JudgeScore) -> float:
    """Compute weighted total from 6 dimension scores."""
    return (
        W_CORRECTNESS * j.correctness
        + W_EVIDENCE * j.evidence_quality
        + W_REASONING * j.reasoning_coherence
        + W_TOOL_USAGE * j.tool_usage
        + W_ROBUSTNESS * j.robustness
        + W_SAFETY * j.safety
    ) * 100  # Scale to 0-100


# ======================================================================
# Rule-based Judge
# ======================================================================

def rule_based_judge(traj: DreamTrajectory) -> JudgeScore:
    """Fast rule-based scoring without LLM."""
    steps = traj.steps
    n_steps = len(steps)

    # Correctness: based on success and answer quality
    correctness = 0.5
    if traj.success and traj.final_answer:
        correctness = 0.8
    if not traj.success:
        correctness = 0.2

    # Evidence quality: steps with non-empty results
    if steps:
        with_result = sum(1 for s in steps if s.result and len(str(s.result)) > 10)
        evidence_quality = with_result / max(n_steps, 1)
    else:
        evidence_quality = 0.1

    # Reasoning coherence: step count and sequential reasoning
    reasoning = min(n_steps / 5.0, 1.0) * 0.7 + 0.3 * (1.0 if traj.success else 0.3)

    # Tool usage: diversity of tools used
    tools_used = set()
    for s in steps:
        if s.action:
            tools_used.add(s.action)
    tool_usage = min(len(tools_used) / 3.0, 1.0)

    # Robustness: handles errors well
    error_steps = sum(1 for s in steps if not s.success)
    robustness = 0.5 if error_steps > 0 else 0.8
    if error_steps > 0 and traj.success:
        robustness = 0.9  # Recovered from errors

    # Safety: check for dangerous patterns
    safety = 1.0
    dangerous_patterns = ["rm -rf", "format ", "del /", "shutdown", "mkfs"]
    for s in steps:
        action_lower = (s.action or "").lower()
        input_lower = str(s.input_data).lower()
        for pattern in dangerous_patterns:
            if pattern in action_lower or pattern in input_lower:
                safety = 0.0
                break

    # Hard failure checks
    error_tags: list[str] = []
    if not traj.success:
        error_tags.append("execution_failed")
    if safety == 0.0:
        error_tags.append("unsafe_action")

    score = JudgeScore(
        success=traj.success and safety > 0,
        correctness=correctness,
        evidence_quality=evidence_quality,
        reasoning_coherence=min(reasoning, 1.0),
        tool_usage=tool_usage,
        robustness=robustness,
        safety=safety,
        error_tags=error_tags,
        explanation=f"Rule-based evaluation: {n_steps} steps, {len(tools_used)} tools",
    )
    score.score_total = _compute_score_total(score)
    return score


# ======================================================================
# LLM-based Judge
# ======================================================================

async def llm_judge(
    traj: DreamTrajectory,
    llm=None,
    mutation_type: str = "",
) -> JudgeScore:
    """LLM-based scoring using StrongJudge prompt."""
    if llm is None:
        return rule_based_judge(traj)

    steps_text = _format_steps(traj)
    prompt = format_judge_prompt(
        task=traj.task,
        mutation_type=mutation_type,
        constraints=traj.constraints,
        steps_text=steps_text,
        final_answer=traj.final_answer or "",
    )

    try:
        response = await llm.ainvoke([
            {"role": "system", "content": STRONG_JUDGE_SYSTEM},
            {"role": "user", "content": prompt},
        ])
        content = response.content if hasattr(response, "content") else str(response)
        content = _strip_code_fences(content)

        data = json.loads(content)
        score = JudgeScore(
            success=data.get("success", False),
            correctness=_clamp(data.get("correctness", 0)),
            evidence_quality=_clamp(data.get("evidence_quality", 0)),
            reasoning_coherence=_clamp(data.get("reasoning_coherence", 0)),
            tool_usage=_clamp(data.get("tool_usage", 0)),
            robustness=_clamp(data.get("robustness", 0)),
            safety=_clamp(data.get("safety", 0)),
            error_tags=data.get("error_tags", []),
            explanation=data.get("explanation", ""),
        )
        score.score_total = _compute_score_total(score)

        # Apply hard failure rules
        if "hallucination" in score.error_tags or "unsafe_action" in score.error_tags:
            score.success = False
            score.score_total = 0

        return score

    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"LLM judge failed, falling back to rules: {e}")
        return rule_based_judge(traj)


# ======================================================================
# Hybrid Judge
# ======================================================================

def rule_pre_filter(traj: DreamTrajectory) -> bool:
    """Quick rule-based filter. Returns True if LLM evaluation is warranted."""
    # Skip LLM for obviously bad trajectories
    if not traj.steps:
        return False
    if len(traj.steps) < 2:
        return False
    # Skip if no final answer at all
    if not traj.final_answer and traj.success:
        return False
    return True


async def hybrid_judge(
    traj: DreamTrajectory,
    llm=None,
    mutation_type: str = "",
) -> JudgeScore:
    """Hybrid: rule pre-filter, LLM for promising trajectories."""
    if not rule_pre_filter(traj):
        score = rule_based_judge(traj)
        score.accept = False
        score.reject_reason = "Filtered by rule pre-check"
        return score

    if llm is not None:
        return await llm_judge(traj, llm, mutation_type)
    return rule_based_judge(traj)


# ======================================================================
# Node function
# ======================================================================

def _format_steps(traj: DreamTrajectory) -> str:
    lines = []
    for s in traj.steps:
        status = "OK" if s.success else "FAIL"
        lines.append(
            f"Step {s.step_number} [{status}]: "
            f"Thought: {s.thought[:100]} | "
            f"Action: {s.action} | "
            f"Result: {str(s.result or '')[:150]}"
        )
    return "\n".join(lines)


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


async def judge_node_async(state: DreamState) -> DreamState:
    """Async version of judge node for LLM calls."""
    config = DreamConfig()
    judge_mode = config.judge_mode
    min_accept = state.get("min_accept_score", config.min_accept_score)

    scores: Dict[str, JudgeScore] = {}
    trajectories = state.get("dream_trajectories", [])

    for traj in trajectories:
        mutation_type = traj.tags[1] if len(traj.tags) > 1 else ""

        if judge_mode == "rule":
            score = rule_based_judge(traj)
        elif judge_mode == "llm":
            score = await llm_judge(traj, mutation_type=mutation_type)
        else:  # hybrid
            score = await hybrid_judge(traj, mutation_type=mutation_type)

        score.accept = score.score_total >= min_accept and score.success
        if not score.accept and not score.reject_reason:
            score.reject_reason = f"Score {score.score_total:.1f} < {min_accept}"

        scores[traj.traj_id] = score

    accepted = sum(1 for s in scores.values() if s.accept)
    logger.info(
        f"Judge: {accepted}/{len(scores)} trajectories accepted "
        f"(mode={judge_mode}, threshold={min_accept})"
    )

    state["judge_scores"] = scores
    return state


def judge_node(state: DreamState) -> DreamState:
    """Dream Subgraph node: evaluate trajectories with 6-dim scoring.

    Uses rule-based judge by default. For hybrid/llm modes, use judge_node_async.
    """
    config = DreamConfig()
    judge_mode = config.judge_mode
    min_accept = state.get("min_accept_score", config.min_accept_score)

    scores: Dict[str, JudgeScore] = {}
    trajectories = state.get("dream_trajectories", [])

    for traj in trajectories:
        mutation_type = traj.tags[1] if len(traj.tags) > 1 else ""

        if judge_mode == "rule":
            score = rule_based_judge(traj)
        else:
            # For hybrid/llm without async, use rules as fallback
            score = rule_based_judge(traj)

        score.accept = score.score_total >= min_accept and score.success
        if not score.accept and not score.reject_reason:
            score.reject_reason = f"Score {score.score_total:.1f} < {min_accept}"

        scores[traj.traj_id] = score

    accepted = sum(1 for s in scores.values() if s.accept)
    logger.info(
        f"Judge: {accepted}/{len(scores)} accepted (mode={judge_mode})"
    )

    state["judge_scores"] = scores
    return state
