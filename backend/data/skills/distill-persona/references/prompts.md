# Distill Persona — Prompt Templates Reference

This file contains all prompt templates used in the distill-persona skill pipeline.

## Template Index

| Template | Purpose |
|----------|---------|
| `DISTILL_PROFILE_PROMPT` | Extract skill profile from samples |
| `PROFILE_JUDGE_PROMPT` | Audit profile quality |
| `IMITATION_TEST_PROMPT` | Generate test outputs using profile |
| `IMITATION_JUDGE_PROMPT` | Evaluate imitation quality |
| `PROFILE_REPAIR_PROMPT` | Fix profile issues |
| `EXTRACT_FEWSHOT_PROMPT` | Select representative examples |
| `GENERATE_SKILL_MD_PROMPT` | Generate skill.md |
| `GENERATE_SKILL_PY_PROMPT` | Generate skill.py runtime |

## Profile Extraction (`DISTILL_PROFILE_PROMPT`)

Input variables: `persona_name`, `output_language`, `strictness`, `desired_skill_type`, `target_domain`, `samples_json`

Output JSON fields:
- `persona_name` — persona identifier
- `domain` — target domain
- `style_rules` — writing/speaking style rules
- `structure_preferences` — output structure habits
- `intake_questions` — questions the persona always asks
- `decision_heuristics` — decision-making logic
- `redlines` — hard boundaries/refusals
- `common_phrases` — characteristic expressions
- `output_templates` — templates for default/analysis/recommendation
- `judge_rubric` — scoring weights (alignment, usefulness, correctness, clarity)
- `scoring_rules` — detailed scoring criteria

## Profile Audit (`PROFILE_JUDGE_PROMPT`)

Input variables: `profile_json`, `samples_json`

Output JSON fields:
- `pass` — whether profile meets quality bar
- `score` — overall score 0.0-1.0
- `missing_fields` — absent required fields
- `inconsistencies` — internal contradictions
- `weak_rules` — vague or unactionable rules
- `repair_suggestions` — specific fix suggestions
- `summary` — brief assessment

## Imitation Testing (`IMITATION_TEST_PROMPT`)

Input variables: `profile_json`, `test_cases_json`

Output: JSON array of `{task, generated, key_rules_used}`

## Imitation Evaluation (`IMITATION_JUDGE_PROMPT`)

Input variables: `profile_json`, `samples_json`, `generated_json`

Output JSON fields:
- `score` — similarity score 0.0-1.0
- `pass` — meets threshold
- `failure_modes` — specific mismatch types
- `suggested_profile_fixes` — profile improvements

## Profile Repair (`PROFILE_REPAIR_PROMPT`)

Input variables: `profile_json`, `samples_json`, `issues_json`

Output: Repaired profile JSON (same schema as input profile)

## Fewshot Extraction (`EXTRACT_FEWSHOT_PROMPT`)

Input variables: `profile_json`, `samples_json`, `k`

Output: JSON array of `{input, output}` pairs

## Skill Generation (`GENERATE_SKILL_MD_PROMPT` / `GENERATE_SKILL_PY_PROMPT`)

Input variables: `profile_json`

Output: Markdown/Python source code string
