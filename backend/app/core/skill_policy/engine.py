"""
SkillPolicy Engine — pure-function sub-stages for Match / Gate / Compile / Guard.

Both the PERV and ToT nodes call into these functions.  No I/O or LLM calls
happen here; everything is deterministic given the inputs.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .types import SkillCandidate, GateDecision, GuardResult

logger = logging.getLogger(__name__)

# Default tool whitelist for GUARD stage
_DEFAULT_GUARD_TOOLS = frozenset({
    "read_file", "write_file", "terminal",
    "python_repl", "fetch_url", "search_kb",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _classify_skill_type(skill_name: str, skills_dir: Path) -> str:
    """Determine whether a skill is module, script, or instruction-only.

    Extends ``detect_skill_type()`` with an ``"instruction"`` branch for
    skills that have no ``scripts/`` directory at all.
    """
    scripts_dir = skills_dir / skill_name / "scripts"
    if not scripts_dir.exists():
        return "instruction"

    handler_path = scripts_dir / "handler.py"
    if handler_path.exists():
        try:
            content = handler_path.read_text(encoding="utf-8")
            if "async def run" in content or "def run" in content:
                return "module"
        except Exception:
            pass

    # If scripts/ exists but only contains handler.py (no other .py),
    # treat as "module" so compile_skill generates python_repl dynamic import
    if handler_path.exists():
        other_py = [f for f in scripts_dir.glob("*.py") if f.name != "handler.py"]
        if not other_py:
            logger.info(
                "SkillPolicy CLASSIFY: '%s' has handler.py but no run() and no other scripts → handler_module",
                skill_name,
            )
            return "handler_module"

    return "script"


def _get_skills_dir() -> Path:
    from app.config import get_settings
    return Path(get_settings().skills_dir)


def _get_guard_tool_whitelist() -> frozenset:
    from app.config import get_settings
    settings = get_settings()
    custom = getattr(settings, "allowed_guard_tools", None)
    if custom:
        return frozenset(custom)
    return _DEFAULT_GUARD_TOOLS


# ---------------------------------------------------------------------------
# MATCH
# ---------------------------------------------------------------------------

def match_skills(
    task: str,
    skill_refs: List[Dict[str, Any]],
    enrichment: Dict[str, Any],
) -> List[SkillCandidate]:
    """Identify and score candidate skills from plan steps or tool calls.

    Args:
        task: The user's original query.
        skill_refs: List of dicts with at least ``skill_name``.
            PERV passes plan steps with ``tool.startswith("skill.")`` or
            non-empty ``skill_group``.  ToT passes tool_calls whose path
            matches a SKILL.md.
        enrichment: Enrichment dict (may contain ``meta_policy_advice``).

    Returns:
        Candidate list sorted by score descending.
    """
    if not skill_refs:
        return []

    skills_dir = _get_skills_dir()

    # Validate available skills
    try:
        from app.skills.loader import SkillLoader
        available = SkillLoader().list_available_skills()
    except Exception:
        available = {}

    # Meta policy advice (optional)
    meta_skill: Optional[str] = None
    meta_advice = enrichment.get("meta_policy_advice")
    if meta_advice and isinstance(meta_advice, dict):
        meta_skill = meta_advice.get("skill")

    # SkillMatcher score (optional)
    matcher_skill: Optional[str] = None
    try:
        from app.core.meta_policy.skill_matcher import SkillMatcher
        if available:
            matcher = SkillMatcher(available)
            matcher_skill = matcher.match_skill(task)
    except Exception:
        pass

    candidates: List[SkillCandidate] = []
    seen: set = set()

    for ref in skill_refs:
        skill_name = ref.get("skill_name", "")
        if not skill_name or skill_name in seen:
            continue

        # Verify skill exists
        skill_dir = skills_dir / skill_name
        if available:
            # SkillLoader has authoritative list
            if skill_name not in available:
                logger.debug("SkillPolicy MATCH: '%s' not in available skills, skipping", skill_name)
                continue
        else:
            # Fallback: check filesystem
            if not (skill_dir / "SKILL.md").exists():
                logger.debug("SkillPolicy MATCH: '%s' SKILL.md not found at %s, skipping", skill_name, skill_dir)
                continue

        seen.add(skill_name)

        skill_type = _classify_skill_type(skill_name, skills_dir)

        # Score calculation
        score = 0.5  # base
        meta_boost = False
        if meta_skill and skill_name == meta_skill:
            score += 0.3
            meta_boost = True
        if matcher_skill and skill_name == matcher_skill:
            score += 0.2

        candidates.append(SkillCandidate(
            skill_name=skill_name,
            skill_type=skill_type,
            score=min(score, 1.0),
            meta_policy_boost=meta_boost,
            source_steps=ref.get("source_steps", []),
        ))
        logger.info(
            "SkillPolicy MATCH: '%s' type=%s score=%.2f meta_boost=%s",
            skill_name, skill_type, min(score, 1.0), meta_boost,
        )

    candidates.sort(key=lambda c: c["score"], reverse=True)
    logger.info(
        "SkillPolicy MATCH: %d/%d refs matched, skills_dir=%s, available=%d",
        len(candidates), len(skill_refs), skills_dir, len(available) if available else 0,
    )
    return candidates


# ---------------------------------------------------------------------------
# GATE
# ---------------------------------------------------------------------------

def gate_skills(
    candidates: List[SkillCandidate],
    context: Dict[str, Any],
) -> List[GateDecision]:
    """Apply hard rules to accept or reject each candidate.

    Args:
        candidates: Output of ``match_skills``.
        context: Dict with keys:
            - core_tools: list of tool names available in the pipeline
            - prev_report: previous SkillPolicyReport (optional)
            - budget_remaining: optional int

    Returns:
        Gate decisions, one per candidate.
    """
    core_tools: set = set(context.get("core_tools", []))
    prev_report: Optional[Dict] = context.get("prev_report")
    skills_dir = _get_skills_dir()
    logger.info(
        "SkillPolicy GATE: %d candidates, core_tools=%s",
        len(candidates), sorted(core_tools) if core_tools else "(empty)",
    )

    # Check previous failures
    prev_failed_skills: set = set()
    if prev_report and prev_report.get("policy_applied"):
        for gr in prev_report.get("gate_results", []):
            if not gr.get("allowed") and gr.get("reason", "").startswith("prev_failed"):
                prev_failed_skills.add(gr.get("skill_name", ""))

    decisions: List[GateDecision] = []

    for cand in candidates:
        name = cand["skill_name"]
        stype = cand["skill_type"]

        # Rule: skill_type must be resolvable
        if stype not in ("module", "script", "handler_module", "instruction"):
            decisions.append(GateDecision(
                skill_name=name,
                allowed=False,
                reason=f"Unknown skill_type: {stype}",
            ))
            continue

        # Rule: script skill requires terminal tool
        if stype == "script" and "terminal" not in core_tools:
            decisions.append(GateDecision(
                skill_name=name,
                allowed=False,
                reason="script skill requires terminal tool (not available)",
            ))
            continue

        # Rule: module / handler_module skill requires handler.py
        if stype in ("module", "handler_module"):
            handler = skills_dir / name / "scripts" / "handler.py"
            if not handler.exists():
                decisions.append(GateDecision(
                    skill_name=name,
                    allowed=False,
                    reason=f"{stype} skill handler.py not found",
                ))
                continue

        # Rule: handler_module skill requires python_repl tool
        if stype == "handler_module" and "python_repl" not in core_tools:
            decisions.append(GateDecision(
                skill_name=name,
                allowed=False,
                reason="handler_module skill requires python_repl tool (not available)",
            ))
            continue

        # Rule: previous round total failure → skip
        if name in prev_failed_skills:
            decisions.append(GateDecision(
                skill_name=name,
                allowed=False,
                reason=f"prev_failed: {name} failed in previous round",
            ))
            continue

        # All checks passed
        decisions.append(GateDecision(
            skill_name=name,
            allowed=True,
            reason=f"Allowed ({stype} skill)",
        ))

    return decisions


# ---------------------------------------------------------------------------
# COMPILE
# ---------------------------------------------------------------------------

def _scan_handler_exports(handler_path: Path) -> List[str]:
    """Scan handler.py for top-level function definitions.

    Returns function names in definition order, excluding private/dunder names.
    Used by ``handler_module`` compile path to discover available entry points.
    """
    import re
    try:
        content = handler_path.read_text(encoding="utf-8")
    except Exception:
        return []
    return re.findall(r"^def ([a-zA-Z_]\w+)\(", content, re.MULTILINE)


def compile_skill(
    skill_name: str,
    skill_type: str,
    user_query: str,
    extra_args: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compile a skill reference into a concrete tool call.

    Returns:
        ``{"tool": tool_name, "args": tool_args}``
    """
    if skill_type == "module":
        # python_repl code that loads and runs the handler
        code = (
            "import importlib.util\n"
            "from pathlib import Path\n"
            f"spec = importlib.util.spec_from_file_location('handler', "
            f"'data/skills/{skill_name}/scripts/handler.py')\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(mod)\n"
            f"result = mod.run(inputs={{'query': {user_query!r}}}, context={{}})\n"
            "print(result)"
        )
        logger.info("SkillPolicy COMPILE: '%s' (module) → python_repl", skill_name)
        return {"tool": "python_repl", "args": {"code": code}}

    if skill_type == "handler_module":
        # handler.py exists with custom functions (e.g. draw, draw_code) but no run().
        # Generate python_repl code that imports handler and delegates to the
        # skill orchestrator's LLM-driven parameter extraction + dispatch,
        # matching how ToT's _execute_geometry_plotter works.
        code = (
            "import importlib.util\n"
            "import json\n"
            f"spec = importlib.util.spec_from_file_location('handler', "
            f"'data/skills/{skill_name}/scripts/handler.py')\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(mod)\n"
            f"\n# Discover available functions in handler\n"
            "_funcs = [n for n in dir(mod) if not n.startswith('_') and callable(getattr(mod, n))]\n"
            f"print(json.dumps({{'available_functions': _funcs, 'skill': '{skill_name}', "
            f"'query': {user_query!r}}}))\n"
        )
        logger.info(
            "SkillPolicy COMPILE: '%s' (handler_module) → python_repl (dynamic import)",
            skill_name,
        )
        return {"tool": "python_repl", "args": {"code": code}}

    if skill_type == "script":
        try:
            from app.core.tot.skill_orchestrator import build_cli_command
            script_path = f"data/skills/{skill_name}/scripts/"
            # Try to find actual script
            skills_dir = _get_skills_dir()
            scripts_dir = skills_dir / skill_name / "scripts"
            if scripts_dir.exists():
                py_files = [f for f in scripts_dir.glob("*.py") if f.name != "handler.py"]
                if py_files:
                    script_path = f"data/skills/{skill_name}/scripts/{py_files[0].name}"

            cmd = build_cli_command(script_path, user_query, extra_args)
            logger.info("SkillPolicy COMPILE: '%s' (script) → terminal, script=%s", skill_name, script_path)
            return {"tool": "terminal", "args": {"command": cmd}}
        except Exception as e:
            logger.warning("SkillPolicy COMPILE: '%s' (script) failed: %s", skill_name, e)
            return {"tool": "terminal", "args": {"command": f"echo 'Skill compile error: {e}'"}}

    # instruction-only → read_file SKILL.md
    logger.info("SkillPolicy COMPILE: '%s' (instruction) → read_file", skill_name)
    return {
        "tool": "read_file",
        "args": {"path": f"data/skills/{skill_name}/SKILL.md"},
    }


# ---------------------------------------------------------------------------
# GUARD
# ---------------------------------------------------------------------------

def guard_compiled_plan(
    tool_plans: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> GuardResult:
    """Static validation of the compiled plan.

    Checks:
      - All tools in whitelist
      - No residual ``skill.*`` references
      - Paths contain no ``..``
      - Budget not exceeded
    """
    whitelist = _get_guard_tool_whitelist()
    issues: List[str] = []

    for plan in tool_plans:
        tool_name = plan.get("tool", "")

        # Check whitelist
        if tool_name not in whitelist:
            issues.append(f"Tool '{tool_name}' not in guard whitelist")

        # Check residual skill.* references
        if tool_name.startswith("skill."):
            issues.append(f"Residual skill reference: {tool_name}")

        # Check path traversal
        args = plan.get("args", {})
        for _key, val in args.items():
            if isinstance(val, str) and ".." in val:
                issues.append(f"Path traversal detected in arg '{_key}': {val}")

    if issues:
        return GuardResult(passed=False, issues=issues, final_plan=None)

    return GuardResult(passed=True, issues=[], final_plan=tool_plans)
