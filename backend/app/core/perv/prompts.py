"""
PERV Prompt Templates (Plan-Execute-Verify-Replan)

Prompt construction functions for the PERV pipeline.
Each builder targets a specific node: Planner, Executor, Verifier, Replanner
(Repair), and Finalizer.  All prompts are in English because LLMs follow
structured English instructions more reliably.

Design principles:
  - Planner produces a JSON DSL plan with explicit tool calls and dependencies.
  - Executor interprets the plan deterministically (Interpreter Mode) — it
    never re-plans, adds steps, or modifies existing ones.
  - Verifier acts as an Auditor: checklist validation only, no re-doing work.
  - Replanner (Repair Agent) prefers patching failed steps over full replans.
  - Finalizer converts verified structured results into a user-facing answer.

Helper utilities:
  - get_style_context()         loads SOUL / USER / IDENTITY from workspace
  - extract_system_style()      extracts style from the assembled system_prompt
  - extract_system_core()       extracts everything except MEMORY from system_prompt
  - extract_agents_for_planning() strips generic chat rules from AGENTS
  - build_tool_list_text()      serialises LangChain BaseTool instances
  - build_tool_whitelist_text() minimal tool-name-only whitelist for Executor
  - build_skills_list_text()    reads SKILLS_SNAPSHOT.md from workspace
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional, Sequence

from langchain_core.tools import BaseTool

from app.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_STYLE_CHARS = 2000  # truncation budget per workspace file
_MAX_SYSTEM_CORE_CHARS = 4000  # truncation budget for system core extraction

GLOBAL_OUTPUT_RULES = """\
## Output Rules (ALL NODES)
- You MUST follow the output format required by the current node.
- Do NOT output any extra commentary unless explicitly allowed.
- If you cannot comply, output: {"status":"error","reason":"..."}
"""

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _truncate(text: str, limit: int = _MAX_STYLE_CHARS) -> str:
    """Truncate *text* to *limit* characters with an ellipsis marker."""
    if len(text) <= limit:
        return text
    return text[: limit - 15] + "\n...[truncated]"


def get_style_context() -> str:
    """Read SOUL.md, USER.md, IDENTITY.md from the workspace directory.

    Each file is truncated to 2000 characters to stay within prompt budgets.

    Returns:
        A formatted multi-section string ready for injection into prompts.
        If a file is missing it is silently skipped.
    """
    settings = get_settings()
    workspace_dir = Path(settings.workspace_dir)

    sections: list[str] = []

    for filename in ("SOUL.md", "USER.md", "IDENTITY.md"):
        filepath = workspace_dir / filename
        try:
            content = filepath.read_text(encoding="utf-8")
            truncated = _truncate(content)
            sections.append(f"## {filename}\n{truncated}")
        except FileNotFoundError:
            logger.debug("Workspace file %s not found, skipping", filepath)
        except OSError as exc:
            logger.warning("Could not read %s: %s", filepath, exc)

    if not sections:
        return ""

    return "# Agent Style Context\n\n" + "\n\n".join(sections)


def build_tool_list_text(tools: Sequence[BaseTool]) -> str:
    """Format a list of LangChain ``BaseTool`` instances for prompt inclusion.

    Each tool is rendered with its name, description and argument schema so
    the LLM can reason about which tools to use and how.

    Args:
        tools: Sequence of BaseTool instances.

    Returns:
        A human-readable bullet list describing every tool.
    """
    if not tools:
        return "(no tools available)"

    lines: list[str] = []
    for tool in tools:
        lines.append(f"- **{tool.name}**: {tool.description.strip()}")

        # Extract arg schema if available
        args_schema = getattr(tool, "args_schema", None)
        if args_schema is not None:
            try:
                schema = args_schema.schema()
                properties = schema.get("properties", {})
                if properties:
                    arg_parts: list[str] = []
                    for arg_name, arg_meta in properties.items():
                        arg_type = arg_meta.get("type", "any")
                        arg_desc = arg_meta.get("description", "")
                        arg_parts.append(f"    - {arg_name} ({arg_type}): {arg_desc}")
                    lines.extend(arg_parts)
            except Exception:
                pass  # Non-critical: best-effort schema extraction

    return "\n".join(lines)


def build_skills_list_text(workspace_dir: str | Path | None = None) -> str:
    """Read SKILLS_SNAPSHOT.md from the workspace directory.

    Args:
        workspace_dir: Override for the workspace directory path.
            Falls back to ``get_settings().workspace_dir`` when not provided.

    Returns:
        The raw text content of SKILLS_SNAPSHOT.md, or a placeholder string
        if the file cannot be found.
    """
    if workspace_dir is None:
        workspace_dir = Path(get_settings().workspace_dir)
    else:
        workspace_dir = Path(workspace_dir)

    filepath = workspace_dir / "SKILLS_SNAPSHOT.md"
    try:
        return filepath.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.debug("SKILLS_SNAPSHOT.md not found at %s", filepath)
        return "(no skills snapshot available)"
    except OSError as exc:
        logger.warning("Could not read %s: %s", filepath, exc)
        return "(could not read skills snapshot)"


# ---------------------------------------------------------------------------
# New extraction helpers
# ---------------------------------------------------------------------------


def extract_system_style(system_prompt: str) -> str:
    """Extract SOUL + IDENTITY + USER sections from the assembled system_prompt.

    The system_prompt is composed of several sections separated by '---'.
    Section layout: SKILLS_SNAPSHOT, SOUL, IDENTITY, USER, AGENTS, MEMORY.
    This function extracts SOUL, IDENTITY and USER (indices 1-3) for the
    Finalizer so it can match the agent's voice and style.

    Args:
        system_prompt: The fully assembled system prompt string.

    Returns:
        A concatenated string of SOUL + IDENTITY + USER sections, truncated
        to stay within prompt budget.  Returns empty string on failure.
    """
    if not system_prompt:
        return ""
    parts = system_prompt.split("---")
    # parts[0] = SKILLS_SNAPSHOT, parts[1] = SOUL, parts[2] = IDENTITY,
    # parts[3] = USER, parts[4] = AGENTS, parts[5] = MEMORY
    style_parts: list[str] = []
    for part in parts[1:4]:  # SOUL, IDENTITY, USER
        trimmed = part.strip()
        if trimmed:
            style_parts.append(trimmed)
    combined = "\n\n".join(style_parts) if style_parts else ""
    return _truncate(combined, _MAX_STYLE_CHARS)


def extract_system_core(system_prompt: str) -> str:
    """Extract core sections from the assembled system_prompt.

    Strips Memory Context / SEMANTIC_HISTORY section (the last `---`
    separated block) to avoid duplication — memory is injected separately
    via the enrichment block or semantic_history parameter.

    Args:
        system_prompt: The fully assembled system prompt string.

    Returns:
        All sections except the last memory-related block, truncated to
        _MAX_SYSTEM_CORE_CHARS.
    """
    if not system_prompt:
        return ""
    parts = system_prompt.split("---")
    core_parts: list[str] = []
    for part in parts:
        trimmed = part.strip()
        if not trimmed:
            continue
        # Skip memory-related sections (injected via enrichment instead)
        lower = trimmed.lower()
        if lower.startswith("#") and (
            "memory context" in lower
            or "semantic search" in lower
            or "knowledge graph facts" in lower
            or "relevant historical" in lower
        ):
            continue
        core_parts.append(trimmed)
    combined = "\n\n".join(core_parts) if core_parts else ""
    return _truncate(combined, _MAX_SYSTEM_CORE_CHARS)


def extract_agents_for_planning(agents_content: str) -> str:
    """Strip generic conversation rules from AGENTS content for planning.

    Removes lines that mention casual-chat patterns (greetings, small talk,
    "no tool needed" rules) so the Planner stays focused on tool-oriented
    planning logic.

    Args:
        agents_content: Raw AGENTS.md section text.

    Returns:
        Filtered AGENTS content with generic chat rules removed.
    """
    if not agents_content:
        return ""
    skip_patterns = [
        "简单对话不需要工具",
        "问候不需要工具",
        "简单问候",
        "闲聊",
        "不需要使用工具",
    ]
    lines = agents_content.split("\n")
    filtered: list[str] = []
    skip = False
    for line in lines:
        # Check if this line starts a section to skip
        if any(p in line for p in skip_patterns):
            skip = True
            continue
        # New section header resets skip
        if line.startswith("#") or line.startswith("##"):
            skip = False
        if not skip:
            filtered.append(line)
    return "\n".join(filtered)


def build_tool_whitelist_text(tools: Sequence[BaseTool]) -> str:
    """Generate a minimal tool-name-only whitelist for the Executor node.

    The Executor does not need full tool descriptions — only the list of
    allowed tool names to validate against.

    Args:
        tools: Sequence of BaseTool instances.

    Returns:
        A single line listing all allowed tool names.
    """
    if not tools:
        return "Allowed tools: (none)"
    return "Allowed tools: " + ", ".join(t.name for t in tools)


# ---------------------------------------------------------------------------
# PERV prompt builders
# ---------------------------------------------------------------------------


def build_planner_prompt(
    system_prompt: str,
    task: str,
    tool_list_text: str,
    skills_list_text: str,
    max_steps: int,
    observations: Optional[list] = None,
    conversation_context: str = "",
    semantic_history: str = "",
    enrichment: Optional[dict] = None,
) -> str:
    """Build the prompt for the **Planner** node.

    The Planner receives the user task and produces a structured JSON plan
    (a DSL) with discrete, tool-callable steps, dependencies, and failure
    handling.  When *observations* is provided the Planner treats them as
    context for replanning.

    Args:
        system_prompt: The fully assembled system prompt (all sections).
        task: The user's original task / question.
        tool_list_text: Formatted tool catalogue (from ``build_tool_list_text``).
        skills_list_text: Formatted skills snapshot (from ``build_skills_list_text``).
        max_steps: Upper bound on the number of plan steps.
        observations: Optional prior execution observations for replanning.
        conversation_context: Optional recent conversation turns for continuity.
        semantic_history: Optional semantic summary of longer conversation history.
        enrichment: Optional dict with pre-hook enrichment data (retrieved
            patterns, strategy prompt, semantic history).

    Returns:
        A single prompt string ready to be sent to the LLM.
    """
    system_core = extract_system_core(system_prompt)

    conversation_context_block = ""
    if conversation_context:
        conversation_context_block = (
            "\n## Conversation Context\n"
            "Recent conversation turns for continuity:\n\n"
            f"{conversation_context}\n"
        )

    semantic_history_block = ""
    if semantic_history:
        semantic_history_block = (
            "\n## Semantic History\n"
            "Summary of earlier conversation context:\n\n"
            f"{semantic_history}\n"
        )

    replan_block = ""
    if observations:
        obs_text = "\n".join(f"  - {obs}" for obs in observations)
        replan_block = (
            "\n## Prior Observations (replanning)\n"
            "The previous plan did not fully succeed.  Use the observations "
            "below to create an improved plan.\n\n"
            f"{obs_text}\n"
        )

    enrichment_block = ""
    if enrichment:
        parts = []
        if enrichment.get("retrieved_patterns"):
            pattern_lines = []
            for p in enrichment["retrieved_patterns"]:
                line = f"- **Situation**: {p.get('situation', '')}\n  **Outcome**: {p.get('outcome', '')}"
                if p.get("fix_action"):
                    line += f"\n  **Fix**: {p['fix_action']}"
                pattern_lines.append(line)
            parts.append("## Relevant Past Patterns\n" + "\n".join(pattern_lines))

        if enrichment.get("strategy_prompt"):
            parts.append(f"## Strategy Guidance\n{enrichment['strategy_prompt']}")

        if enrichment.get("semantic_history"):
            sh = enrichment["semantic_history"]
            if isinstance(sh, str):
                parts.append(f"## Relevant Memory Context\n{sh}")
            else:
                hist_lines = [f"- {h}" for h in sh]
                parts.append("## Relevant Conversation History\n" + "\n".join(hist_lines))

        if enrichment.get("meta_policy_advice"):
            mp = enrichment["meta_policy_advice"]
            injection_text = mp.get("injection_text", "")
            if injection_text:
                meta_lines = [injection_text]
                if mp.get("tool"):
                    meta_lines.append(f"Recommended tool: {mp['tool']}")
                if mp.get("skill"):
                    meta_lines.append(f"Recommended skill: {mp['skill']}")
                parts.append("## Meta Policy Recommendation\n" + "\n".join(meta_lines))

        enrichment_block = "\n\n".join(parts)

    plan_schema = json.dumps(
        {
            "objective": "string",
            "assumptions": ["list"],
            "constraints": {"max_steps": max_steps, "allow_repair_patch": True},
            "artifacts": {"final_output_type": "report | code | json | answer"},
            "steps": [
                {
                    "id": "s1",
                    "name": "short step name",
                    "tool": "tool_name",
                    "skill_group": "skill_name or null",
                    "purpose": "what this step achieves",
                    "inputs": {},
                    "depends_on": [],
                    "output_key": "unique_key",
                    "on_fail": {
                        "retry": 1,
                        "fallback_tool": None,
                        "fallback_inputs": None,
                    },
                }
            ],
        },
        indent=2,
        ensure_ascii=False,
    )

    return f"""You are an autonomous planning agent.

{system_core}
{conversation_context_block}
{semantic_history_block}
{enrichment_block}

{GLOBAL_OUTPUT_RULES}

## Your Job
- Understand the user goal.
- Consult memory/context if provided.
- Produce an executable structured plan (JSON DSL).
- The plan must be deterministic and tool-oriented.

## Rules
- Do NOT execute tools.
- Do NOT write final answer to user.
- Prefer minimal number of steps.
- Every step must be directly executable.
- Steps must include explicit tool name and input args.
- If critical information is missing and cannot be inferred, output {{"status":"need_info","reason":"describe what is missing"}} instead of fabricating data.
- Consider cost/time constraints, failure modes and fallbacks.
- Avoid unnecessary browsing or long reasoning.
- When a skill is needed, use tool: "skill.<skill-name>" as a single step. Do NOT expand into read_file + follow-up steps. The skill policy node will handle compilation automatically.
- Each skill is a single step with tool: "skill.<skill-name>", depends_on: [], skill_group: "<skill-name>"
- When multiple skills are needed:
  - Independent skills → all have depends_on: [] (parallel)
  - Sequential skills → second skill depends_on the first skill's step ID
  - The skill policy node compiles skill.* references into concrete tool calls before execution

## Task
{task}

## Available Tools
{tool_list_text}

## Available Skills
{skills_list_text}
{replan_block}

## Output Format (STRICT JSON)
{plan_schema}

Strict requirements:
- depends_on lists the IDs of steps whose outputs this step needs
- Steps with empty depends_on can run in parallel
- Steps that only need the task context (not another step's output) should have depends_on: []
- output_key must be unique across all steps
- skill_group identifies which skill a step belongs to (match the skill name, null if no skill)
- Respond ONLY with valid JSON — no markdown fences, no commentary

## Parallel Execution Examples

Example 1 — Multiple independent skills:
  s1: skill.get_weather      depends_on: [], skill_group: "get_weather"
  s2: skill.arxiv-search     depends_on: [], skill_group: "arxiv-search"
  → Layer 0: [s1, s2] parallel

Example 2 — Skills with data dependency:
  s1: skill.arxiv-search     depends_on: [], skill_group: "arxiv-search"
  s2: skill.chart-plotter    depends_on: ["s1"], skill_group: "chart-plotter"
  → Layer 0: [s1]
  → Layer 1: [s2]
"""


def build_executor_messages(
    task: str,
    plan: list,
    observations: Optional[list] = None,
    system_prompt: str = "",
    mode: str = "batch",
    tools: Optional[Sequence[BaseTool]] = None,
) -> list[dict[str, str]]:
    """Construct the message list for the **Executor** node (Interpreter Mode).

    The Executor interprets and executes the plan deterministically.  It never
    re-plans, adds new steps, or modifies existing ones.

    Two modes are supported:
      - **batch** (default): execute all steps at once, return a JSON list of
        observations.  Used when the plan has <= 3 steps.
      - **step**: execute one step at a time, return a single observation.
        Used when the plan has > 3 steps.

    Args:
        task: The original user task.
        plan: The plan (list of step dicts, or a dict with a "steps" key).
        observations: Optional prior observations to carry forward as context.
        system_prompt: The fully assembled system prompt (used for tool whitelist).
        mode: "batch" or "step".
        tools: Sequence of BaseTool instances for building the tool whitelist.
            When provided, the prompt includes concrete allowed tool names.

    Returns:
        A list of message dicts (``{"role": ..., "content": ...}``) suitable
        for the ``AgentManager``.
    """
    # Normalise plan to a list of steps
    steps = plan.get("steps", plan) if isinstance(plan, dict) else plan
    steps_text = json.dumps(steps, indent=2, ensure_ascii=False)

    # Build tool whitelist from available tools registered in the system
    tool_whitelist = build_tool_whitelist_text(tools) if tools else "Allowed tools: (none)"

    obs_block = ""
    if observations:
        obs_text = "\n".join(f"  - {obs}" for obs in observations)
        obs_block = (
            "\n## Prior Observations\n"
            "The following observations were collected from earlier execution:\n\n"
            f"{obs_text}\n"
        )

    system_msg = (
        "You are a deterministic Plan Executor (Interpreter Mode).\n\n"
        f"{GLOBAL_OUTPUT_RULES}\n\n"
        "Hard rules:\n"
        "- DO NOT re-plan.\n"
        "- DO NOT add new steps.\n"
        "- DO NOT modify existing steps.\n"
        "- DO NOT change tools unless the step explicitly allows fallback_tool.\n"
        "- DO NOT produce a final user-facing answer.\n"
        "- Use memory ONLY to fill missing parameters, never to alter intent.\n"
        "- Do NOT use any skill. Planner has already expanded all skills into "
        "explicit tool-call steps, or the skill policy node has pre-compiled "
        "them. Execute steps as specified.\n\n"
        f"{tool_whitelist}"
    )

    if mode == "step":
        # Step-by-step mode: execute a single step
        current_step = steps[0] if isinstance(steps, list) and steps else steps
        current_step_text = json.dumps(
            current_step, indent=2, ensure_ascii=False
        )

        prior_outputs = ""
        if observations:
            prior_text = "\n".join(
                f"  [{i + 1}] {obs}" for i, obs in enumerate(observations)
            )
            prior_outputs = (
                "\n## Prior Step Outputs\n"
                "Results from already-executed steps:\n\n"
                f"{prior_text}\n"
            )

        user_msg = f"""## Task
{task}

## Current Step to Execute
{current_step_text}
{prior_outputs}

## Instructions
Execute the single step above.  Use the exact tool and inputs specified.
If a prior output is referenced, substitute it.

## Output Format (STRICT JSON)
Output exactly ONE of the following JSON objects:

1. Tool call result:
{{
  "type": "tool_call",
  "step_id": "...",
  "tool": "...",
  "inputs": {{}},
  "result": "full output"
}}

2. Step completed:
{{
  "type": "step_result",
  "step_id": "...",
  "output_key": "...",
  "summary": "one-line summary",
  "result": "full output"
}}

3. Step failed:
{{
  "type": "step_failed",
  "step_id": "...",
  "error": "error description",
  "retry_possible": true | false
}}

Respond ONLY with valid JSON — no markdown fences, no commentary."""
    else:
        # Batch mode: execute all steps at once
        user_msg = f"""## Task
{task}

## Plan (execute all steps in order)
{steps_text}
{obs_block}

## Instructions
Execute each step of the plan in order, respecting dependencies.  For
each step:
1. Call the specified tool with the given arguments.
2. Record the full tool output.
3. If a step fails, note the error and continue with the next independent step.

## Output Format (STRICT JSON)
Return a JSON list of observations:
[
  {{
    "step_id": "s1",
    "status": "success" | "failed",
    "tool_result": "... (full output or error message)",
    "output_key": "...",
    "summary": "one-line summary of what was found"
  }}
]

Respond ONLY with valid JSON — no markdown fences, no commentary."""

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def build_verifier_prompt(
    task: str,
    plan,  # can be list or dict
    observations: list,
) -> str:
    """Build the prompt for the **Verifier** node (Auditor Mode).

    The Verifier examines whether the execution results (observations) fully
    answer the original task.  It performs checklist validation only — it does
    not redo the task, rewrite reports, or call tools.

    Args:
        task: The original user task.
        plan: The plan that was executed (list of steps or dict with "steps").
        observations: Execution observations collected by the Executor.

    Returns:
        A prompt string asking the LLM to verify the results.
    """
    steps = plan.get("steps", plan) if isinstance(plan, dict) else plan
    steps_text = json.dumps(steps, indent=2, ensure_ascii=False)
    obs_text = "\n".join(f"  - {obs}" for obs in observations)

    verifier_schema = json.dumps(
        {
            "verdict": "pass | fail | needs_repair",
            "confidence": "0.0-1.0",
            "checks": [
                {
                    "name": "step_completion",
                    "status": "pass|fail",
                    "evidence": "...",
                    "fix_suggestion": "...",
                },
                {
                    "name": "result_validity",
                    "status": "pass|fail",
                    "evidence": "...",
                    "fix_suggestion": "...",
                },
                {
                    "name": "evidence_grounded",
                    "status": "pass|fail",
                    "evidence": "...",
                    "fix_suggestion": "...",
                },
                {
                    "name": "task_coverage",
                    "status": "pass|fail",
                    "evidence": "...",
                    "fix_suggestion": "...",
                },
            ],
            "missing": ["list"],
            "risk_notes": ["list"],
        },
        indent=2,
        ensure_ascii=False,
    )

    return f"""You are a Verification Agent (Auditor Mode).
{GLOBAL_OUTPUT_RULES}

## Your Job
- Verify whether the execution outputs satisfy the objective.
- Perform checklist validation only.
- Do NOT redo the task.
- Do NOT rewrite the report.
- Do NOT browse or call tools.

## Task
{task}

## Plan That Was Executed
{steps_text}

## Execution Observations
{obs_text}

## Output Format (STRICT JSON)
{verifier_schema}

Set verdict to "pass" only when confidence >= 0.7 and no critical checks fail.
Respond ONLY with valid JSON — no markdown fences, no commentary.
"""


def build_replanner_prompt(
    system_prompt: str,
    task: str,
    plan,  # list or dict
    observations: list,
    verifier_report: dict,
    tool_list_text: str,
    skills_list_text: str,
    conversation_context: str = "",
    semantic_history: str = "",
    consecutive_failures: int = 0,
) -> str:
    """Build the prompt for the **Replanner** (Repair Agent) node.

    The Replanner receives the original plan, execution observations and the
    Verifier's report.  It prefers patching failed steps over producing a
    full replan.  Full replans are allowed only after repeated failures
    (controlled by *consecutive_failures*).

    Args:
        system_prompt: The fully assembled system prompt (all sections).
        task: The original user task.
        plan: The plan that was executed (list of steps or dict with "steps").
        observations: Execution observations from the last run.
        verifier_report: The Verifier's JSON report.
        tool_list_text: Formatted tool catalogue.
        skills_list_text: Formatted skills snapshot.
        conversation_context: Optional recent conversation turns.
        semantic_history: Optional semantic summary of longer history.
        consecutive_failures: Number of consecutive repair failures so far.

    Returns:
        A prompt string asking the LLM to produce a corrective patch or replan.
    """
    system_core = extract_system_core(system_prompt)

    steps = plan.get("steps", plan) if isinstance(plan, dict) else plan
    steps_text = json.dumps(steps, indent=2, ensure_ascii=False)
    obs_text = "\n".join(f"  - {obs}" for obs in observations)
    report_text = json.dumps(verifier_report, indent=2, ensure_ascii=False)

    conversation_context_block = ""
    if conversation_context:
        conversation_context_block = (
            "\n## Conversation Context\n\n"
            f"{conversation_context}\n"
        )

    semantic_history_block = ""
    if semantic_history:
        semantic_history_block = (
            "\n## Semantic History\n\n"
            f"{semantic_history}\n"
        )

    full_replan_allowed_block = ""
    if consecutive_failures >= 3:
        full_replan_allowed_block = (
            "\n- **Full replan is ALLOWED** because the task has failed "
            f"{consecutive_failures} consecutive times.  You may output a "
            "complete new plan using mode \"full_replan\".\n"
        )

    repair_patch_schema = json.dumps(
        {
            "mode": "repair_patch",
            "reason": "...",
            "patch": [
                {
                    "op": "edit_step_inputs",
                    "step_id": "s3",
                    "new_inputs": {},
                },
                {
                    "op": "replace_step_tool",
                    "step_id": "s3",
                    "new_tool": "...",
                    "new_inputs": {},
                },
                {
                    "op": "insert_step_after",
                    "after_step_id": "s3",
                    "step": {
                        "id": "s3b",
                        "name": "...",
                        "tool": "...",
                        "purpose": "...",
                        "inputs": {},
                        "depends_on": ["s3"],
                        "output_key": "...",
                        "on_fail": {
                            "retry": 1,
                            "fallback_tool": None,
                            "fallback_inputs": None,
                        },
                    },
                },
            ],
        },
        indent=2,
        ensure_ascii=False,
    )

    return f"""You are the Repair Agent.
{system_core}
{conversation_context_block}
{semantic_history_block}

{GLOBAL_OUTPUT_RULES}

## Goal
- Fix plan execution failures with minimal modifications.
- Prefer PATCHING the current step over full replan.

## Repair Rules
- Keep the original objective unchanged.
- Never modify already-successful steps.
- Only patch steps at or after the failed step.
- Default mode is "repair_patch".
- Full replan is allowed ONLY if repair is impossible after multiple failures.
{full_replan_allowed_block}

## Task
{task}

## Previous Plan
{steps_text}

## Execution Observations
{obs_text}

## Verifier Report
{report_text}

## Available Tools
{tool_list_text}

## Available Skills
{skills_list_text}

## Output Format (STRICT JSON)
Default mode (repair_patch):
{repair_patch_schema}

Supported patch operations:
- edit_step_inputs: change the inputs of an existing step
- replace_step_tool: change the tool and inputs of an existing step
- insert_step_after: add a new step after a given step
- remove_step: remove a step entirely

If full replan is allowed (see rules above), you may instead output:
{{
  "mode": "full_replan",
  "reason": "...",
  "steps": [ ... same schema as Planner output ... ]
}}

Respond ONLY with valid JSON — no markdown fences, no commentary.
"""


def build_finalizer_prompt(
    system_prompt: str,
    task: str,
    observations: list,
) -> str:
    """Build the prompt for the **Finalizer** node.

    The Finalizer converts verified structured results into a clean,
    user-facing response.  It uses the agent's style context (SOUL, IDENTITY,
    USER) to match the expected voice.

    Args:
        system_prompt: The fully assembled system prompt (all sections).
        task: The original user task.
        observations: Execution observations collected across all plan steps.

    Returns:
        A prompt string asking the LLM to produce the final answer.
    """
    style_context = extract_system_style(system_prompt)
    obs_text = "\n".join(f"  [{i + 1}] {obs}" for i, obs in enumerate(observations))

    style_block = ""
    if style_context:
        style_block = f"\n## Agent Style\n{style_context}\n"

    return f"""You are a Final Answer Writer.
{style_block}

{GLOBAL_OUTPUT_RULES}

## Task
- Convert verified structured results into a clean final user-facing response.

## Rules
- Do not mention internal plan, nodes, tool traces.
- Be concise, correct, and complete.
- If verifier verdict is fail, do not fabricate.
- Use user's language (Chinese).

## Original Task
{task}

## Collected Observations
{obs_text}

## Output Format
Respond with a well-formatted answer (markdown, fine).
For factual claims, cite observation number: [1], [2], etc.
Do NOT wrap in JSON. Begin directly.
"""
