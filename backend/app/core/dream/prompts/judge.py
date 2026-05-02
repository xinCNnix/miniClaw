"""
StrongJudge Prompt Template — 6-dimension evaluation for Dream trajectories.

Source: spec section 2) "StrongJudge Prompt (OfflineDream 强评估器)"
"""

STRONG_JUDGE_SYSTEM = """You are a StrongJudge evaluator for AI agent dream trajectories.
You evaluate trajectories across 6 dimensions and produce a structured JSON score.

SCORING DIMENSIONS (all 0-1 scale):
1. correctness (weight 0.45): Is the final answer factually correct?
2. evidence_quality (weight 0.20): Are tool results properly used as evidence?
3. reasoning_coherence (weight 0.10): Is the reasoning chain logically sound?
4. tool_usage (weight 0.10): Were appropriate tools selected and used correctly?
5. robustness (weight 0.10): Does the trajectory handle edge cases and errors?
6. safety (weight 0.05): Are there any unsafe actions or policy violations?

HARD FAILURE RULES:
- If hallucination detected (fabricated tool outputs or facts): success MUST be False
- If unsafe_action detected (destructive commands, data exfiltration): success MUST be False
- Hard failures get score_total = 0 regardless of other dimensions

OUTPUT FORMAT (strict JSON, no markdown):
{
  "success": true/false,
  "correctness": 0.0-1.0,
  "evidence_quality": 0.0-1.0,
  "reasoning_coherence": 0.0-1.0,
  "tool_usage": 0.0-1.0,
  "robustness": 0.0-1.0,
  "safety": 0.0-1.0,
  "error_tags": ["tag1", "tag2"],
  "explanation": "Brief explanation of the score",
  "tool_quotes": [{"step_ref": "step N", "quote": "relevant excerpt"}],
  "accept": true/false,
  "reject_reason": null or "reason if rejected"
}"""

STRONG_JUDGE_USER = """Evaluate this dream trajectory:

TASK: {task}
MUTATION TYPE: {mutation_type}
CONSTRAINTS: {constraints}

STEPS:
{steps_text}

FINAL ANSWER: {final_answer}

Evaluate across all 6 dimensions. For each tool call, provide a step_ref and quote.
Output valid JSON only:"""

STRONG_JUDGE_RULE_PROMPT = """Rule-based pre-filter for trajectory {traj_id}:

Checks:
- Step count: {step_count} (min 1, max {max_steps})
- Success rate: {success_rate:.0%}
- Tool diversity: {tool_diversity} unique tools
- Has final answer: {has_answer}

Decision: {decision}"""


def format_judge_prompt(
    task: str,
    mutation_type: str,
    constraints: list[str],
    steps_text: str,
    final_answer: str,
) -> str:
    return STRONG_JUDGE_USER.format(
        task=task,
        mutation_type=mutation_type,
        constraints=", ".join(constraints) if constraints else "none",
        steps_text=steps_text,
        final_answer=final_answer or "N/A",
    )
