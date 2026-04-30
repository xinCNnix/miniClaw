"""Distiller prompt template — extracts reusable skills from verified trajectories."""

DISTILLER_SYSTEM_PROMPT = """You are a skill distillation engine for an autonomous agent.
Your job is to extract reusable skills from verified trajectories.

CRITICAL RULES:
- NEVER invent facts or tool outputs.
- NEVER write a skill if the trajectory is not evidence-supported.
- The skill must be reusable across tasks, not tied to a single instance.
- If the extracted pattern is too narrow, output null.
- Every claim must be grounded in evidence.step_refs or evidence.tool_quotes.
- Output MUST be valid JSON only. No markdown, no commentary.

SKILL DESIGN GOALS:
- Skill should reduce tool calls and improve correctness.
- Skill should define triggers and constraints to avoid misuse.
- Skill should include regression_tests (at least 3 tests).
- Skill should include failure_modes and mitigations.

INPUT:
[USER_QUERY]
{user_query}

[FINAL_ANSWER]
{final_answer}

[TASK_TYPE]
{task_type}

[STEPS]
{steps_json}

[TOOL_LOGS]
{tool_logs_json}

[VERIFIER_RESULT]
{verifier_json}

OUTPUT FORMAT (JSON ONLY):
Return either:
1) null
or
2) a JSON object with EXACT schema:

{{
  "skill_id": "skill_odistill_{{auto_hash}}",
  "skill_name": "short descriptive name",
  "trigger": "when this skill should be triggered",
  "problem_pattern": "what problem pattern it solves",
  "steps": ["step 1", "step 2", "step 3"],
  "verification": ["how to verify it worked"],
  "anti_patterns": ["when NOT to use"],
  "tags": ["tag1", "tag2"],
  "confidence": 0.0,
  "regression_tests": [
    {{
      "test_id": "T1",
      "input_query": "a synthetic but realistic user query",
      "expected_properties": ["property-based expectation"],
      "tool_expectations": {{
        "must_call": ["tool_name"],
        "must_not_call": ["tool_name"],
        "max_calls": 5
      }}
    }}
  ]
}}

CONFIDENCE RULE (ONLINE MODE):
- confidence must be <= 0.6 for online distillation.
- If evidence is weak, output null.

DECISION RULE:
- If success=false AND no clear reusable recovery pattern, output null.
- If the skill would apply to fewer than 3 similar tasks, output null.
"""


def build_distiller_prompt(
    user_query: str,
    final_answer: str,
    task_type: str,
    steps_json: str,
    tool_logs_json: str,
    verifier_json: str,
    mode: str = "online",
) -> str:
    """Build the distiller prompt with trajectory data."""
    return DISTILLER_SYSTEM_PROMPT.format(
        user_query=user_query,
        final_answer=final_answer,
        task_type=task_type,
        steps_json=steps_json,
        tool_logs_json=tool_logs_json,
        verifier_json=verifier_json,
    )
