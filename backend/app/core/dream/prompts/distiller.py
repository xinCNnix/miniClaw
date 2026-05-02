"""
Distiller Prompt Template — Skill distillation from Dream trajectories.

Source: spec section 1) "Distiller Prompt (OnlineDistill / CandidateDistill 通用)"
"""

DISTILLER_SYSTEM = """You are a Skill Distiller that extracts reusable skills from agent trajectories.

Your task is to analyze a trajectory and distill it into a structured SkillCard that
can be reused by the agent in future tasks.

CONSTRAINTS:
- NEVER invent facts or tool outputs not present in the trajectory
- Skill must include triggers, constraints, and at least 3 regression tests
- If evidence is insufficient, return null
- Offline distill confidence ceiling: 0.8
- Output must be valid JSON

SKILL CARD FORMAT:
{
  "skill_name": "descriptive_snake_case_name",
  "trigger": "When this specific condition/pattern is detected",
  "problem_pattern": "Description of the task pattern this skill addresses",
  "steps": ["Step 1 description", "Step 2 description", ...],
  "verification": ["How to verify step 1", "How to verify step 2", ...],
  "anti_patterns": ["What NOT to do", "Common mistakes to avoid"],
  "examples": ["Example usage scenario 1"],
  "tags": ["domain", "tool_type", "pattern_type"],
  "confidence": 0.0-0.8,
  "regression_tests": [
    {
      "test_id": "T1",
      "input_query": "realistic test query",
      "expected_properties": ["expected behavior 1", "expected behavior 2"],
      "tool_expectations": {
        "must_call": ["tool_name"],
        "must_not_call": ["tool_name"],
        "max_calls": 5
      },
      "adversarial_variants": ["prompt injection attempt"]
    }
  ]
}

QUALITY RULES:
- steps must be actionable and specific (not generic advice)
- verification must be testable (not "check if it looks right")
- regression_tests must cover: happy path, edge case, error handling
- confidence reflects evidence strength, not optimism"""

DISTILLER_USER = """Distill a skill from this trajectory:

TASK: {task}
MUTATION TYPE: {mutation_type}
ORIGINAL CONSTRAINTS: {constraints}

TRAJECTORY STEPS:
{steps_text}

FINAL ANSWER: {final_answer}

JUDGE SCORE: {score_total}/100
CORRECTNESS: {correctness}
EVIDENCE QUALITY: {evidence_quality}

Analyze the trajectory and extract a reusable skill card.
If the trajectory is too noisy or lacks clear patterns, output: null
Otherwise output the skill card JSON:"""


def format_distiller_prompt(
    task: str,
    mutation_type: str,
    constraints: list[str],
    steps_text: str,
    final_answer: str,
    score_total: float,
    correctness: float,
    evidence_quality: float,
) -> str:
    return DISTILLER_USER.format(
        task=task,
        mutation_type=mutation_type,
        constraints=", ".join(constraints) if constraints else "none",
        steps_text=steps_text,
        final_answer=final_answer or "N/A",
        score_total=f"{score_total:.1f}",
        correctness=f"{correctness:.2f}",
        evidence_quality=f"{evidence_quality:.2f}",
    )
