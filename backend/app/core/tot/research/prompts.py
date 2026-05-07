"""
Research Prompt Template Loader and Filler.

Loads .md prompt template files from the prompts/ directory and fills
{variable} placeholders with runtime values. Also provides a JSON
parsing utility with json_repair fallback for LLM output handling.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# Cache for loaded templates to avoid repeated file I/O
_template_cache: Dict[str, str] = {}


def _load_template(name: str) -> str:
    """Load a prompt template .md file by name (without extension).

    Templates are cached in memory after the first load to avoid
    repeated file I/O across multiple calls in the same process.

    Args:
        name: Template filename without the .md extension
            (e.g., "planner", "base_research").

    Returns:
        The template content as a string.

    Raises:
        FileNotFoundError: If the template .md file does not exist.
    """
    if name in _template_cache:
        return _template_cache[name]

    template_path = _PROMPTS_DIR / f"{name}.md"
    if not template_path.exists():
        raise FileNotFoundError(
            f"Prompt template not found: {template_path}. "
            f"Available templates: {[p.stem for p in _PROMPTS_DIR.glob('*.md')]}"
        )

    content = template_path.read_text(encoding="utf-8")
    _template_cache[name] = content
    return content


def _fill_template(template: str, **kwargs: Any) -> str:
    """Fill {variable} placeholders in a template string.

    Uses regex substitution so that non-placeholder braces (e.g. JSON
    objects like {"type":"bar"}) are left untouched. Only standalone
    {word} patterns (alphanumeric + underscore) are treated as variables.

    Args:
        template: Template string with {variable} placeholders.
        **kwargs: Key-value pairs to fill into the template.

    Returns:
        The template with placeholders filled. Placeholders not
        present in kwargs are left unchanged.
    """
    def _replace(match: re.Match) -> str:
        key = match.group(1)
        if key in kwargs:
            return str(kwargs[key])
        return match.group(0)  # Leave as-is

    return re.sub(r"\{(\w+)\}", _replace, template)


# ---------------------------------------------------------------------------
# Public prompt accessor functions
# ---------------------------------------------------------------------------


def get_base_research_system_prompt() -> str:
    """Load the shared BASE_RESEARCH_SYSTEM_PROMPT.

    This prompt is appended to the system prompt of all research nodes
    (writing and analysis levels) as a shared behavioral contract.

    Returns:
        The base research system prompt string.
    """
    return _load_template("base_research")


def get_planner_prompt(
    user_query: str,
    evidence_summary: str,
    coverage_map: str,
    contradictions: str,
    remaining_rounds: str,
) -> str:
    """Build the research planner prompt for subsequent rounds.

    Args:
        user_query: The original user research query.
        evidence_summary: Formatted text of current evidence store.
        coverage_map: JSON string of the current coverage map.
        contradictions: JSON string of known contradictions.
        remaining_rounds: Number of research rounds remaining.

    Returns:
        The filled prompt template ready to send as a user message.
    """
    template = _load_template("planner")
    return _fill_template(
        template,
        user_query=user_query,
        evidence_summary=evidence_summary,
        coverage_map=coverage_map,
        contradictions=contradictions,
        remaining_rounds=remaining_rounds,
    )


def get_first_round_planner_prompt(user_query: str) -> str:
    """Build the simplified first-round planner prompt.

    Used when no prior evidence, coverage, or contradictions exist.
    The planner must infer research sub-topics from the query alone.

    Args:
        user_query: The original user research query.

    Returns:
        The filled prompt template ready to send as a user message.
    """
    template = _load_template("first_round_planner")
    return _fill_template(template, user_query=user_query)


def get_evaluator_prompt(
    user_query: str,
    candidate_plans: str,
    evidence_summary: str,
) -> str:
    """Build the research plan evaluator prompt.

    Args:
        user_query: The original user research query.
        candidate_plans: JSON string of the 5 candidate plans.
        evidence_summary: Formatted text of current evidence store.

    Returns:
        The filled prompt template ready to send as a user message.
    """
    template = _load_template("evaluator")
    return _fill_template(
        template,
        user_query=user_query,
        candidate_plans=candidate_plans,
        evidence_summary=evidence_summary,
    )


def get_coverage_prompt(
    user_query: str,
    evidence_summary: str,
) -> str:
    """Build the coverage analysis prompt.

    Args:
        user_query: The original user research query.
        evidence_summary: Formatted text of current evidence store.

    Returns:
        The filled prompt template ready to send as a user message.
    """
    template = _load_template("coverage")
    return _fill_template(
        template,
        user_query=user_query,
        evidence_summary=evidence_summary,
    )


def get_contradiction_prompt(
    user_query: str,
    evidence_summary: str,
) -> str:
    """Build the contradiction detection prompt.

    Args:
        user_query: The original user research query.
        evidence_summary: Formatted text of current evidence store.

    Returns:
        The filled prompt template ready to send as a user message.
    """
    template = _load_template("contradiction")
    return _fill_template(
        template,
        user_query=user_query,
        evidence_summary=evidence_summary,
    )


def get_writer_prompt(
    user_query: str,
    coverage_map: str,
    contradictions: str,
    draft: str,
    evidence_summary: str,
) -> str:
    """Build the incremental draft writer prompt.

    Args:
        user_query: The original user research query.
        coverage_map: JSON string of the current coverage map.
        contradictions: JSON string of known contradictions.
        draft: The previous draft Markdown (empty string for first round).
        evidence_summary: Formatted text of current evidence store.

    Returns:
        The filled prompt template ready to send as a user message.
    """
    template = _load_template("writer")
    return _fill_template(
        template,
        user_query=user_query,
        coverage_map=coverage_map,
        contradictions=contradictions,
        draft=draft if draft else "（无前序草稿，这是首轮写作）",
        evidence_summary=evidence_summary,
    )


def get_termination_prompt(
    user_query: str,
    research_round: int,
    token_used: int,
    token_budget: int,
    coverage_map: str,
    contradictions: str,
    evidence_count: int,
) -> str:
    """Build the termination check prompt.

    Args:
        user_query: The original user research query.
        research_round: Current research round number.
        token_used: Tokens consumed so far.
        token_budget: Total token budget.
        coverage_map: JSON string of the current coverage map.
        contradictions: JSON string of known contradictions.
        evidence_count: Number of evidence items collected.

    Returns:
        The filled prompt template ready to send as a user message.
    """
    template = _load_template("termination")
    return _fill_template(
        template,
        user_query=user_query,
        research_round=str(research_round),
        token_used=str(token_used),
        token_budget=str(token_budget),
        coverage_map=coverage_map,
        contradictions=contradictions,
        evidence_count=str(evidence_count),
    )


def get_synthesis_prompt(
    user_query: str,
    evidence_summary: str,
    coverage_map: str,
    contradictions: str,
    draft: str,
) -> str:
    """Build the final report synthesis prompt.

    Args:
        user_query: The original user research query.
        evidence_summary: Formatted text of current evidence store.
        coverage_map: JSON string of the final coverage map.
        contradictions: JSON string of all known contradictions.
        draft: The current working draft Markdown.

    Returns:
        The filled prompt template ready to send as a user message.
    """
    template = _load_template("synthesis")
    return _fill_template(
        template,
        user_query=user_query,
        evidence_summary=evidence_summary,
        coverage_map=coverage_map,
        contradictions=contradictions,
        draft=draft if draft else "（无前序草稿）",
    )


def get_verifier_prompt(
    user_query: str,
    evidence_summary: str,
    final_report: str,
) -> str:
    """Build the report verification / audit prompt.

    Args:
        user_query: The original user research query.
        evidence_summary: Formatted text of current evidence store.
        final_report: The synthesized final report Markdown.

    Returns:
        The filled prompt template ready to send as a user message.
    """
    template = _load_template("verifier")
    return _fill_template(
        template,
        user_query=user_query,
        evidence_summary=evidence_summary,
        final_report=final_report,
    )


def get_repair_prompt(
    user_query: str,
    evidence_summary: str,
    audit_result: str,
    final_report: str,
) -> str:
    """Build the report repair prompt.

    Args:
        user_query: The original user research query.
        evidence_summary: Formatted text of current evidence store.
        audit_result: JSON string of the verifier's audit output.
        final_report: The original final report to be repaired.

    Returns:
        The filled prompt template ready to send as a user message.
    """
    template = _load_template("repair")
    return _fill_template(
        template,
        user_query=user_query,
        evidence_summary=evidence_summary,
        audit_result=audit_result,
        final_report=final_report,
    )


def get_citation_chasing_prompt(
    user_query: str,
    coverage_map: str,
    contradictions: str,
    evidence_summary: str,
) -> str:
    """Build the citation chasing planner prompt.

    Args:
        user_query: The original user research query.
        coverage_map: JSON string of the current coverage map.
        contradictions: JSON string of known contradictions.
        evidence_summary: Formatted text of current evidence store.

    Returns:
        The filled prompt template ready to send as a user message.
    """
    template = _load_template("citation_chasing")
    return _fill_template(
        template,
        user_query=user_query,
        coverage_map=coverage_map,
        contradictions=contradictions,
        evidence_summary=evidence_summary,
    )


# ---------------------------------------------------------------------------
# JSON parsing utility
# ---------------------------------------------------------------------------


def parse_json_output(llm_output: str) -> Dict:
    """Parse JSON from LLM output with robust fallback strategies.

    Strategy order:
      1. Try direct json.loads on the full output.
      2. Try extracting JSON from markdown code blocks (```json ... ```).
      3. Try json_repair library (if installed).
      4. Try finding the first valid JSON object or array via brace matching.
      5. Return empty dict on complete failure.

    Args:
        llm_output: Raw text output from the LLM.

    Returns:
        Parsed JSON as a dictionary. Returns an empty dict if all
        parsing strategies fail.
    """
    if not llm_output or not llm_output.strip():
        return {}

    text = llm_output.strip()

    # Strategy 1: Direct parse
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
        if isinstance(result, list):
            return {"_array": result}
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: Extract from markdown code blocks
    code_block_patterns = [
        r"```json\s*\n?(.*?)\n?\s*```",
        r"```\s*\n?(.*?)\n?\s*```",
    ]
    for pattern in code_block_patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            json_str = match.group(1).strip()
            try:
                result = json.loads(json_str)
                if isinstance(result, dict):
                    return result
                if isinstance(result, list):
                    return {"_array": result}
            except (json.JSONDecodeError, ValueError):
                pass

    # Strategy 3: Try built-in JSON repair module
    try:
        from app.core.perv.json_repair import repair_json_or_none

        result = repair_json_or_none(text)
        if isinstance(result, dict):
            return result
        if isinstance(result, list):
            return {"_array": result}
    except Exception as exc:
        logger.debug(f"json_repair failed: {exc}")

    # Strategy 4: Find first valid JSON via brace/bracket matching
    json_str = _extract_json_by_braces(text)
    if json_str:
        try:
            result = json.loads(json_str)
            if isinstance(result, dict):
                return result
            if isinstance(result, list):
                return {"_array": result}
        except (json.JSONDecodeError, ValueError):
            pass

    logger.warning(
        f"Failed to parse JSON from LLM output "
        f"(first 200 chars): {text[:200]}"
    )
    return {}


def _extract_json_by_braces(text: str) -> Optional[str]:
    """Extract the first balanced JSON object or array from text.

    Finds the first '{' or '[' and attempts to find its matching
    closing brace/bracket by counting nesting depth.

    Args:
        text: Text that may contain a JSON object or array.

    Returns:
        Extracted JSON string if found, None otherwise.
    """
    # Find first { or [
    start = -1
    open_char = ""
    close_char = ""
    for i, ch in enumerate(text):
        if ch == "{":
            start = i
            open_char = "{"
            close_char = "}"
            break
        if ch == "[":
            start = i
            open_char = "["
            close_char = "]"
            break

    if start < 0:
        return None

    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        ch = text[i]

        if escape_next:
            escape_next = False
            continue

        if ch == "\\":
            escape_next = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    return None
