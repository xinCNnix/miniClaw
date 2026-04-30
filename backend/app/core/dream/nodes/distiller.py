"""
Distiller — LLM-based skill distillation from Dream trajectories.

Extracts reusable SkillCards from judged trajectories that passed the Judge threshold.
"""

import json
import logging
import uuid
from typing import List, Optional

from app.core.dream.config import DreamConfig
from app.core.dream.models import DreamState, DreamTrajectory, JudgeScore, SkillCard
from app.core.dream.prompts.distiller import (
    DISTILLER_SYSTEM,
    format_distiller_prompt,
)

logger = logging.getLogger(__name__)


def _format_steps_for_distill(traj: DreamTrajectory) -> str:
    """Format trajectory steps for the distiller prompt."""
    lines = []
    for s in traj.steps:
        status = "SUCCESS" if s.success else "FAILED"
        result_preview = str(s.result or "")[:200]
        lines.append(
            f"Step {s.step_number} [{status}]\n"
            f"  Thought: {s.thought[:150]}\n"
            f"  Action: {s.action}\n"
            f"  Input: {json.dumps(s.input_data, ensure_ascii=False)[:100]}\n"
            f"  Result: {result_preview}"
        )
    return "\n".join(lines)


def _parse_skill_card(data: dict, traj: DreamTrajectory) -> SkillCard:
    """Parse LLM output dict into a SkillCard."""
    confidence = float(data.get("confidence", 0.5))
    # Enforce offline distill ceiling
    confidence = min(confidence, 0.8)

    regression_tests = data.get("regression_tests", [])
    # Ensure at least 3 tests
    while len(regression_tests) < 3:
        regression_tests.append({
            "test_id": f"T{len(regression_tests) + 1}",
            "input_query": f"Verify skill behavior: {data.get('skill_name', 'unknown')}",
            "expected_properties": ["produces valid output"],
            "tool_expectations": {},
            "adversarial_variants": [],
        })

    return SkillCard(
        skill_id=f"skill_{uuid.uuid4().hex[:10]}",
        skill_name=data.get("skill_name", f"unnamed_skill_{uuid.uuid4().hex[:4]}"),
        trigger=data.get("trigger", ""),
        problem_pattern=data.get("problem_pattern", ""),
        steps=data.get("steps", []),
        verification=data.get("verification", []),
        anti_patterns=data.get("anti_patterns", []),
        examples=data.get("examples", []),
        tags=data.get("tags", []),
        confidence=confidence,
        supporting_cases=1,
        source_traj_ids=[traj.traj_id],
        status="candidate",
        regression_tests=regression_tests,
    )


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


async def _distill_with_llm(
    traj: DreamTrajectory,
    score: JudgeScore,
    llm=None,
) -> Optional[SkillCard]:
    """Distill a skill card from a trajectory using LLM."""
    if llm is None:
        return _distill_from_rules(traj, score)

    steps_text = _format_steps_for_distill(traj)
    mutation_type = traj.tags[1] if len(traj.tags) > 1 else "unknown"

    prompt = format_distiller_prompt(
        task=traj.task,
        mutation_type=mutation_type,
        constraints=traj.constraints,
        steps_text=steps_text,
        final_answer=traj.final_answer or "",
        score_total=score.score_total,
        correctness=score.correctness,
        evidence_quality=score.evidence_quality,
    )

    try:
        response = await llm.ainvoke([
            {"role": "system", "content": DISTILLER_SYSTEM},
            {"role": "user", "content": prompt},
        ])
        content = response.content if hasattr(response, "content") else str(response)
        content = _strip_code_fences(content)

        if content.strip().lower() == "null":
            return None

        data = json.loads(content)
        return _parse_skill_card(data, traj)

    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"LLM distill failed, falling back to rules: {e}")
        return _distill_from_rules(traj, score)


def _distill_from_rules(
    traj: DreamTrajectory,
    score: JudgeScore,
) -> Optional[SkillCard]:
    """Rule-based fallback distillation without LLM."""
    if not traj.steps:
        return None

    # Extract tool usage pattern
    tools_used = list({s.action for s in traj.steps if s.action})

    # Build basic skill card from trajectory structure
    steps_desc = []
    for s in traj.steps:
        desc = f"Use {s.action}" if s.action else "Analyze"
        if s.thought:
            desc += f" — {s.thought[:80]}"
        steps_desc.append(desc)

    # Generate basic regression tests
    reg_tests = [
        {
            "test_id": "T1",
            "input_query": traj.task[:100],
            "expected_properties": [
                "produces a non-empty response",
                "uses appropriate tools",
            ],
            "tool_expectations": {
                "must_call": tools_used[:2],
                "must_not_call": [],
                "max_calls": 8,
            },
            "adversarial_variants": [],
        },
        {
            "test_id": "T2",
            "input_query": f"Variant of: {traj.task[:80]}",
            "expected_properties": [
                "handles the variant correctly",
            ],
            "tool_expectations": {
                "must_call": [],
                "must_not_call": [],
                "max_calls": 10,
            },
            "adversarial_variants": ["ignore previous instructions"],
        },
        {
            "test_id": "T3",
            "input_query": f"Edge case: empty input for {traj.task[:60]}",
            "expected_properties": [
                "handles empty/minimal input gracefully",
            ],
            "tool_expectations": {
                "must_call": [],
                "must_not_call": ["terminal"],
                "max_calls": 5,
            },
            "adversarial_variants": [],
        },
    ]

    # Confidence based on judge score
    confidence = min(score.score_total / 100.0 * 0.8, 0.8)

    return SkillCard(
        skill_id=f"skill_{uuid.uuid4().hex[:10]}",
        skill_name=_generate_skill_name(traj),
        trigger=_infer_trigger(traj),
        problem_pattern=traj.task[:200],
        steps=steps_desc,
        verification=[f"Verify step {i+1} completed" for i in range(len(steps_desc))],
        anti_patterns=["Skip verification", "Assume success without checking"],
        examples=[traj.task[:150]],
        tags=["rule_distilled"] + traj.tags,
        confidence=confidence,
        supporting_cases=1,
        source_traj_ids=[traj.traj_id],
        status="candidate",
        regression_tests=reg_tests,
    )


def _generate_skill_name(traj: DreamTrajectory) -> str:
    """Generate a skill name from the trajectory task."""
    task = traj.task.lower()
    # Take first meaningful words
    words = task.replace("[", "").replace("]", "").split()[:4]
    name = "_".join(w for w in words if w.isalnum())[:40]
    return name if name else f"dream_skill_{uuid.uuid4().hex[:4]}"


def _infer_trigger(traj: DreamTrajectory) -> str:
    """Infer a trigger condition from the trajectory."""
    if not traj.success and traj.failure_type:
        return f"When encountering {traj.failure_type} errors"
    if traj.constraints:
        return f"When task involves: {', '.join(traj.constraints[:2])}"
    mutation_type = traj.tags[1] if len(traj.tags) > 1 else ""
    if mutation_type:
        return f"When dealing with {mutation_type} scenarios"
    return f"When task matches: {traj.task[:80]}"


async def distiller_node_async(state: DreamState) -> DreamState:
    """Async version of distiller node for LLM calls."""
    config = DreamConfig()
    min_accept = state.get("min_accept_score", config.min_accept_score)
    trajectories = state.get("dream_trajectories", [])
    scores = state.get("judge_scores", {})

    skills: List[SkillCard] = []
    for traj in trajectories:
        js = scores.get(traj.traj_id)
        if not js or not js.accept or js.score_total < min_accept:
            continue

        skill = await _distill_with_llm(traj, js)
        if skill is not None:
            skills.append(skill)

    logger.info(f"Distiller: {len(skills)} skills distilled from {len(trajectories)} trajectories")
    state["distilled_skills"] = skills
    return state


def distiller_node(state: DreamState) -> DreamState:
    """Dream Subgraph node: distill skills from accepted trajectories.

    Uses rule-based distillation by default. For LLM distillation, use distiller_node_async.
    """
    config = DreamConfig()
    min_accept = state.get("min_accept_score", config.min_accept_score)
    trajectories = state.get("dream_trajectories", [])
    scores = state.get("judge_scores", {})

    skills: List[SkillCard] = []
    for traj in trajectories:
        js = scores.get(traj.traj_id)
        if not js or not js.accept or js.score_total < min_accept:
            continue

        skill = _distill_from_rules(traj, js)
        if skill is not None:
            skills.append(skill)

    logger.info(f"Distiller: {len(skills)} skills distilled")
    state["distilled_skills"] = skills
    return state
