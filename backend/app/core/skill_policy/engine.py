"""
SkillPolicy Engine — Match / Gate / Compile / Guard pipeline.

Core design (ref: docs/skill节点.md):
  - Match: identify and score candidate skills (pure function)
  - Gate: hard-rule accept/reject (pure function)
  - Compile: generate tool_plan — all types via LLM, fallback to read_file
  - Guard: static validation of compiled plan (pure function)

The ``run_skill_policy`` function is the unified entry point.  Each mode
(Normal Agent / PERV / ToT) constructs a PolicyInput and consumes the
PolicyOutput.
"""

import asyncio
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .types import (
    PolicyInput,
    PolicyOutput,
    SkillCandidate,
    GateDecision,
    GuardResult,
)

logger = logging.getLogger(__name__)


def get_python_command() -> str:
    return sys.executable or "python"


# Default tool whitelist for GUARD stage
_DEFAULT_GUARD_TOOLS = frozenset({
    "read_file", "write_file", "terminal",
    "python_repl", "fetch_url", "search_kb",
})

# Default guard config for budget control and duplicate detection
_DEFAULT_GUARD_CONFIG = {
    "max_tool_calls": 10,
    "detect_duplicate_url": True,
    "detect_dead_loop": True,
}

# Gate thresholds — conservative before strategy learning network.
# Design doc targets (0.65/0.75/0.85) will be restored once the learning
# network can produce calibrated scores.  Current values give generous
# headroom so multi-skill plans and skills without keyword catalogs are
# not accidentally blocked.
_STATUS_THRESHOLDS = {
    "stable":      {"min_sim": 0.35},
    "candidate":   {"min_sim": 0.50, "min_confidence": 0.7},
    "provisional": {"min_sim": 0.65, "min_confidence": 0.6, "require_success": True},
}

# Phase 2: policy_score formula weights (docs/skill节点.md Section 3)
_SCORE_WEIGHTS = {
    "sim":              0.35,
    "task_match":       0.20,
    "confidence":       0.20,
    "status_weight":    0.15,
    "cost_penalty":     0.10,
    "conflict_penalty": 0.10,
}

# Default values when skill metadata is missing
# Conservative defaults: unknown skills pass the 0.55 stable gate comfortably.
# Default total = 0.35*0.80 + 0.20*0.50 + 0.20*0.70 + 0.15*1.00 = 0.67
_DEFAULT_SCORE_COMPONENTS = {
    "sim":              0.80,
    "task_match":       0.50,
    "confidence":       0.70,
    "status_weight":    1.00,
    "cost_penalty":     0.00,
    "conflict_penalty": 0.00,
}

# SkillMatcher keyword fallback — used when skill frontmatter lacks "triggers".
# Mirrors SkillMatcher._build_keyword_index hard-coded mapping.
_SKILL_KEYWORD_FALLBACK: Dict[str, List[str]] = {
    "arxiv-search": [
        "arxiv", "paper", "论文", "学术", "academic", "research paper",
        "论文搜索", "学术论文", "文献", "literature",
    ],
    "find-skill": [
        "find skill", "install skill", "搜索技能", "安装技能",
        "skill search", "技能搜索", "download skill",
    ],
    "github": [
        "github", "pr", "pull request", "issue", "code review",
        "ci", "commit", "branch", "merge", "repo",
    ],
    "research_report_writer": [
        "report", "报告", "write report", "写报告", "research report",
        "研究报告", "调研报告",
    ],
    "cluster_reduce_synthesis": [
        "cluster", "synthesis", "聚类", "合并", "consensus",
        "摘要综合", "多源", "聚类合并",
    ],
    "diagram-plotter": [
        "diagram", "architecture", "flowchart", "mind map",
        "架构图", "流程图", "思维导图", "时序图", "uml",
    ],
    "arxiv-download-paper": [
        "download paper", "pdf", "下载论文", "full text",
        "论文下载", "全文",
    ],
    "baidu-search": [
        "百度", "baidu", "搜索", "search", "查找", "资讯",
        "新闻", "实时搜索", "中文搜索",
    ],
    "deep_source_extractor": [
        "extract", "提取", "结构化", "structured", "深层次",
        "信息提取", "extraction",
    ],
    "doc-creator": [
        "document", "docx", "word", "office", "文档",
        "创建文档", "word文档", "报告文档",
    ],
    "chart-plotter": [
        "chart", "plot", "graph", "可视化", "数据图",
        "折线图", "柱状图", "饼图", "散点图", "统计图",
        "matplotlib", "visualization", "画图", "绘图", "作图",
        "函数图", "曲线图", "sin", "cos",
    ],
    "skill_validator": [
        "validate skill", "验证技能", "检查技能",
    ],
    "skill-creator": [
        "create skill", "创建技能", "新建技能", "make skill",
    ],
    "get_weather": [
        "weather", "天气", "气温", "温度", "forecast",
        "天气预报",
    ],
}

# Cache for parsed skill frontmatter: {skill_name: dict | None}
_frontmatter_cache: Dict[str, Optional[Dict[str, Any]]] = {}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _classify_skill_type(skill_name: str, skills_dir: Path) -> str:
    """Determine whether a skill is module, script, handler_module, or instruction."""
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

    if handler_path.exists():
        other_py = [f for f in scripts_dir.glob("*.py") if f.name != "handler.py"]
        if not other_py:
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


def _parse_skill_frontmatter(skill_name: str) -> Optional[Dict[str, Any]]:
    """Parse SKILL.md frontmatter and return the YAML dict. Cached."""
    if skill_name in _frontmatter_cache:
        return _frontmatter_cache[skill_name]

    skills_dir = _get_skills_dir()
    skill_md = skills_dir / skill_name / "SKILL.md"
    if not skill_md.exists():
        _frontmatter_cache[skill_name] = None
        return None

    try:
        content = skill_md.read_text(encoding="utf-8")
    except Exception:
        _frontmatter_cache[skill_name] = None
        return None

    frontmatter: Dict[str, Any] = {}
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                import yaml
                frontmatter = yaml.safe_load(parts[1]) or {}
            except Exception:
                pass

    _frontmatter_cache[skill_name] = frontmatter
    return frontmatter


def _compute_sim_score(
    user_query: str,
    triggers: List[str],
    skill_name: str = "",
) -> float:
    """Compute semantic similarity between query and skill triggers.

    Uses frontmatter triggers when available, falls back to the
    SkillMatcher keyword catalog when triggers are absent.
    Returns 0.4-1.0.
    """
    keywords = triggers

    # Fallback: use SkillMatcher keyword catalog when frontmatter has no triggers
    if not keywords and skill_name:
        keywords = _SKILL_KEYWORD_FALLBACK.get(skill_name, [])

    if not keywords:
        return _DEFAULT_SCORE_COMPONENTS["sim"]

    query_lower = user_query.lower()
    matched = sum(1 for t in keywords if t.lower() in query_lower)
    ratio = matched / len(keywords)

    # For keyword catalogs (many keywords), amplify so a single match is meaningful.
    # For frontmatter triggers (few items), scale linearly.
    if not triggers and skill_name:
        # Keyword catalog mode: min 0.75 for any match, cap at 1.0
        if ratio > 0:
            return min(0.75 + 0.25 * min(ratio * 3, 1.0), 1.0)
        return 0.4

    # Frontmatter triggers mode: direct ratio scaling
    if ratio >= 1.0:
        return 1.0
    elif ratio > 0:
        return 0.7 + 0.3 * ratio
    return 0.4


def _compute_task_match(user_query: str, skill_meta: Dict[str, Any]) -> float:
    """Compute task type/tag match score.

    Checks if query keywords overlap with skill tags/task_type.
    """
    tags = skill_meta.get("tags", [])
    task_type = skill_meta.get("task_type", "")

    if not tags and not task_type:
        return _DEFAULT_SCORE_COMPONENTS["task_match"]

    query_lower = user_query.lower()

    tag_hits = sum(1 for t in tags if t.lower() in query_lower)
    tag_score = min(tag_hits / max(len(tags), 1), 1.0) if tags else 0.0

    type_score = 0.0
    if task_type:
        type_words = task_type.replace("_", " ").lower().split()
        type_hits = sum(1 for w in type_words if w in query_lower)
        type_score = min(type_hits / max(len(type_words), 1), 1.0) if type_words else 0.0

    # Combine: tag match is primary, task_type is secondary
    if tags and task_type:
        return 0.6 * tag_score + 0.4 * type_score
    elif tags:
        return tag_score
    else:
        return type_score


def _compute_conflict_penalty(step_intent: str, skill_meta: Dict[str, Any]) -> float:
    """Compute penalty for intent-skill conflict.

    Returns 0.0 (no conflict) to 1.0 (strong conflict).
    """
    if not step_intent:
        return 0.0

    constraints = skill_meta.get("constraints", [])
    if not constraints:
        return 0.0

    intent_lower = step_intent.lower()
    conflicts = sum(1 for c in constraints if c.lower() in intent_lower)
    return min(conflicts / max(len(constraints), 1), 1.0)


def _compute_policy_score(
    user_query: str,
    skill_meta: Dict[str, Any],
    step_intent: str = "",
    skill_name: str = "",
) -> float:
    """Compute policy_score using 6-dimension formula.

    Formula (docs/skill节点.md Section 3):
      policy_score = 0.35*sim + 0.20*task_match + 0.20*confidence
                   + 0.15*status_weight - 0.10*cost_penalty - 0.10*conflict
    """
    c = {**_DEFAULT_SCORE_COMPONENTS}

    # 1. sim_score — uses frontmatter triggers, falls back to keyword catalog
    triggers = skill_meta.get("triggers", [])
    c["sim"] = _compute_sim_score(user_query, triggers, skill_name)

    # 2. task_match
    if skill_meta.get("task_type") or skill_meta.get("tags"):
        c["task_match"] = _compute_task_match(user_query, skill_meta)

    # 3. confidence
    if "confidence" in skill_meta:
        c["confidence"] = skill_meta["confidence"]

    # 4. status_weight
    status = skill_meta.get("status", "stable")
    c["status_weight"] = {"stable": 1.0, "candidate": 0.7, "provisional": 0.4}.get(status, 1.0)

    # 5. cost_penalty
    max_calls = skill_meta.get("max_tool_calls", 0)
    if max_calls > 0:
        c["cost_penalty"] = min(max_calls / 10.0, 1.0)

    # 6. conflict_penalty
    if step_intent:
        c["conflict_penalty"] = _compute_conflict_penalty(step_intent, skill_meta)

    w = _SCORE_WEIGHTS
    return (
        w["sim"] * c["sim"]
        + w["task_match"] * c["task_match"]
        + w["confidence"] * c["confidence"]
        + w["status_weight"] * c["status_weight"]
        - w["cost_penalty"] * c["cost_penalty"]
        - w["conflict_penalty"] * c["conflict_penalty"]
    )


# ---------------------------------------------------------------------------
# MATCH (pure function — unchanged)
# ---------------------------------------------------------------------------


def match_skills(
    task: str,
    skill_refs: List[Dict[str, Any]],
    enrichment: Dict[str, Any],
) -> List[SkillCandidate]:
    """Identify and score candidate skills using 6-dimension policy_score."""
    if not skill_refs:
        return []

    skills_dir = _get_skills_dir()

    try:
        from app.skills.loader import SkillLoader
        available = SkillLoader().list_available_skills()
    except Exception:
        available = {}

    step_intent = enrichment.get("step_intent", "")

    candidates: List[SkillCandidate] = []
    seen: set = set()

    for ref in skill_refs:
        skill_name = ref.get("skill_name", "")
        if not skill_name or skill_name in seen:
            continue

        skill_dir = skills_dir / skill_name
        if available:
            if skill_name not in available:
                continue
        else:
            if not (skill_dir / "SKILL.md").exists():
                continue

        seen.add(skill_name)
        skill_type = _classify_skill_type(skill_name, skills_dir)

        # Parse skill frontmatter for scoring metadata
        frontmatter = _parse_skill_frontmatter(skill_name) or {}

        # Compute policy_score using 6-dimension formula
        score = _compute_policy_score(task, frontmatter, step_intent, skill_name)

        # Boost from meta_policy (preserves existing integration)
        meta_boost = False
        meta_skill = enrichment.get("meta_policy_advice")
        if meta_skill and isinstance(meta_skill, dict):
            if meta_skill.get("skill") == skill_name:
                score += 0.05  # Small boost, not dominant
                meta_boost = True

        # Read status from frontmatter if available
        skill_status = frontmatter.get("status", "stable")

        candidates.append(SkillCandidate(
            skill_name=skill_name,
            skill_type=skill_type,
            score=min(score, 1.0),
            meta_policy_boost=meta_boost,
            source_steps=ref.get("source_steps", []),
            skill_status=skill_status,
        ))

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates


# ---------------------------------------------------------------------------
# GATE (pure function — unchanged)
# ---------------------------------------------------------------------------


def gate_skills(
    candidates: List[SkillCandidate],
    context: Dict[str, Any],
) -> List[GateDecision]:
    """Apply hard rules to accept or reject each candidate."""
    core_tools: set = set(context.get("core_tools", []))
    _core_tools_known = len(core_tools) > 0
    prev_report: Optional[Dict] = context.get("prev_report")
    skills_dir = _get_skills_dir()

    prev_failed_skills: set = set()
    if prev_report and prev_report.get("policy_applied"):
        for gr in prev_report.get("gate_results", []):
            if not gr.get("allowed") and gr.get("reason", "").startswith("prev_failed"):
                prev_failed_skills.add(gr.get("skill_name", ""))

    decisions: List[GateDecision] = []

    for cand in candidates:
        name = cand["skill_name"]
        stype = cand["skill_type"]

        if stype not in ("module", "script", "handler_module", "instruction"):
            decisions.append(GateDecision(skill_name=name, allowed=False,
                                          reason=f"Unknown skill_type: {stype}"))
            continue

        if _core_tools_known and stype == "script" and "terminal" not in core_tools:
            decisions.append(GateDecision(skill_name=name, allowed=False,
                                          reason="script skill requires terminal tool"))
            continue

        if stype in ("module", "handler_module"):
            handler = skills_dir / name / "scripts" / "handler.py"
            if not handler.exists():
                decisions.append(GateDecision(skill_name=name, allowed=False,
                                              reason=f"{stype} skill handler.py not found"))
                continue

        if _core_tools_known and stype == "handler_module" and "python_repl" not in core_tools:
            decisions.append(GateDecision(skill_name=name, allowed=False,
                                          reason="handler_module requires python_repl"))
            continue

        if name in prev_failed_skills:
            decisions.append(GateDecision(skill_name=name, allowed=False,
                                          reason=f"prev_failed: {name}"))
            continue

        # Score threshold check (6-dimension policy_score)
        skill_status = cand.get("skill_status", "stable")
        threshold = _STATUS_THRESHOLDS.get(skill_status, _STATUS_THRESHOLDS["stable"])
        if cand["score"] < threshold["min_sim"]:
            decisions.append(GateDecision(
                skill_name=name, allowed=False,
                reason=f"score {cand['score']:.3f} below {skill_status} threshold {threshold['min_sim']}",
            ))
            continue

        # Confidence check for candidate/provisional
        if "min_confidence" in threshold:
            fm = _parse_skill_frontmatter(name) or {}
            skill_confidence = fm.get("confidence", _DEFAULT_SCORE_COMPONENTS["confidence"])
            if skill_confidence < threshold["min_confidence"]:
                decisions.append(GateDecision(
                    skill_name=name, allowed=False,
                    reason=f"confidence {skill_confidence:.2f} below {skill_status} threshold {threshold['min_confidence']}",
                ))
                continue

        logger.info("SkillPolicy GATE: '%s' allowed (%s skill)", name, stype)
        decisions.append(GateDecision(skill_name=name, allowed=True,
                                      reason=f"Allowed ({stype} skill)"))

    return decisions


# ---------------------------------------------------------------------------
# COMPILE — instruction (pure function)
# ---------------------------------------------------------------------------


def _compile_instruction(skill_name: str) -> List[Dict[str, Any]]:
    """Fallback: when LLM is unavailable or skill_content is missing, return read_file."""
    logger.info("SkillPolicy COMPILE FALLBACK: '%s' → read_file", skill_name)
    return [{"tool": "read_file",
             "args": {"path": f"data/skills/{skill_name}/SKILL.md"}}]


def _load_skill_content(skill_name: str) -> Optional[str]:
    """Load SKILL.md content from file system."""
    skills_dir = _get_skills_dir()
    skill_md = skills_dir / skill_name / "SKILL.md"
    if not skill_md.exists():
        logger.warning("SkillPolicy: SKILL.md not found for '%s' at %s", skill_name, skill_md)
        return None
    try:
        content = skill_md.read_text(encoding="utf-8")
        logger.debug("SkillPolicy: loaded SKILL.md for '%s' (%d chars)", skill_name, len(content))
        return content
    except Exception as e:
        logger.error("SkillPolicy: failed to read SKILL.md for '%s': %s", skill_name, e)
        return None


# ---------------------------------------------------------------------------
# COMPILE — LLM-backed (module / script / handler_module)
# ---------------------------------------------------------------------------


_COMPILE_SYSTEM_PROMPT = """\
You are a Tool Policy Compiler. You MUST output a JSON tool_plan only — no markdown, no commentary, no Chinese text.

RULES:
- Only use tools from the [AVAILABLE_TOOLS] list.
- Each entry: {{"tool": "<name>", "args": {{...}}}}
- Output a JSON array. Nothing else.
- Never exceed [MAX_TOOL_CALLS] total tool calls.
- Each tool call should serve the [STEP_INTENT] purpose.
- 禁止输出任何中文解释，只输出纯 JSON 数组。

OUTPUT FORMAT (MANDATORY):
Output ONLY a raw JSON array. No markdown fences. No explanation.
Example: [{{"tool": "python_repl", "args": {{"code": "import importlib.util\\n..."}}}}]

TYPE-SPECIFIC RULES:
- For **instruction** type: Read the skill instructions carefully. Generate the ACTUAL tool calls described in the instructions, with parameters extracted from the user query. For example, if the skill says to run a curl command, generate a terminal tool call with that curl command. NEVER output read_file — that step is already done.
- For **script** type: generate a `terminal` command running the correct Python script with correct arguments extracted from the user query. Use `python` (not `python3`) for the command.
- For **module** type: generate `python_repl` code that uses importlib to load handler.py and calls run() with properly extracted parameters.
- For **handler_module** type: generate `python_repl` code that uses importlib to load handler.py and calls the correct function with parameters extracted from the user query.

[SKILL_NAME] {skill_name}
[SKILL_TYPE] {skill_type}
[AVAILABLE_TOOLS] {available_tools}
[STEP_INTENT] {step_intent}
[MAX_TOOL_CALLS] {max_tool_calls}
"""

_COMPILE_USER_PROMPT = """\
[USER_QUERY]
{user_query}

[SKILL_INSTRUCTIONS]
{skill_content}

Generate the tool_plan JSON now:"""


def _parse_tool_plan_json(raw: str) -> Optional[List[Dict[str, Any]]]:
    """Parse LLM output into a tool_plan list."""
    text = raw.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    text = text.strip()
    # Strip JavaScript-style comments (LLM sometimes adds these)
    text = re.sub(r"(?<!:)//.*?$", "", text, flags=re.MULTILINE)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = text.strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Try repair
        try:
            from app.core.perv.json_repair import repair_json_or_none
            parsed = repair_json_or_none(text)
        except ImportError:
            parsed = None

    if parsed is None:
        return None

    if isinstance(parsed, dict):
        # Single tool call wrapped in dict — normalize to list
        if "tool" in parsed:
            return [parsed]
        return None

    if isinstance(parsed, list):
        return [p for p in parsed if isinstance(p, dict) and "tool" in p]

    return None


async def _llm_compile(
    skill_name: str,
    skill_type: str,
    user_query: str,
    skill_content: str,
    available_tools: List[str],
    llm: Any,
    *,
    step_intent: str = "",
    max_tool_calls: int = 10,
) -> List[Dict[str, Any]]:
    """Use LLM to compile skill into a tool_plan JSON.

    Returns list of {"tool": str, "args": dict} entries.
    """
    from langchain_core.messages import SystemMessage, HumanMessage

    system_msg = _COMPILE_SYSTEM_PROMPT.format(
        skill_name=skill_name,
        skill_type=skill_type,
        available_tools=json.dumps(available_tools),
        step_intent=step_intent,
        max_tool_calls=max_tool_calls,
    )
    user_msg = _COMPILE_USER_PROMPT.format(
        user_query=user_query,
        skill_content=skill_content[:6000],  # truncate to stay within context
    )

    logger.info("SkillPolicy COMPILE: '%s' (%s) → calling LLM", skill_name, skill_type)

    # Bind response_format to force JSON output (provider-dependent)
    compile_llm = llm
    try:
        compile_llm = llm.bind(response_format={"type": "json_object"})
    except Exception:
        pass  # Provider may not support response_format

    max_retries = 2
    for attempt in range(1, max_retries + 1):
        response = await compile_llm.ainvoke([
            SystemMessage(content=system_msg),
            HumanMessage(content=user_msg),
        ])

        raw = response.content.strip()
        parsed = _parse_tool_plan_json(raw)

        if parsed:
            break

        logger.warning(
            "SkillPolicy COMPILE: '%s' attempt %d/%d invalid JSON: %s",
            skill_name, attempt, max_retries, raw[:200],
        )
        if attempt < max_retries:
            await asyncio.sleep(0.5)

    if not parsed:
        logger.warning(
            "SkillPolicy COMPILE: LLM returned invalid JSON for '%s' after %d attempts: %s",
            skill_name, max_retries, raw[:200],
        )
        raise RuntimeError(f"LLM compile failed for {skill_name}: invalid JSON output after {max_retries} attempts")

    # Tag each step with source metadata for guard validation
    for step in parsed:
        step["_source_skill_type"] = skill_type
        step["_source_skill_name"] = skill_name

    logger.info(
        "SkillPolicy COMPILE: '%s' (%s) → %d step(s): %s",
        skill_name, skill_type, len(parsed),
        [s.get("tool", "?") for s in parsed],
    )
    return parsed


# ---------------------------------------------------------------------------
# COMPILE — unified entry
# ---------------------------------------------------------------------------


async def compile_skill(
    skill_name: str,
    skill_type: str,
    user_query: str,
    *,
    extra_args: Optional[Dict[str, Any]] = None,
    llm: Optional[Any] = None,
    skill_content: Optional[str] = None,
    available_tools: Optional[List[str]] = None,
    step_intent: str = "",
    max_tool_calls: int = 10,
) -> List[Dict[str, Any]]:
    """Compile a skill reference into a tool_plan.

    All four types now go through LLM compile. _compile_instruction()
    is used as fallback when LLM is unavailable or skill_content is missing.

    Returns list of {"tool": str, "args": dict} entries.
    """
    # Fallback: LLM not available
    if llm is None:
        logger.warning(
            "SkillPolicy COMPILE: '%s' type=%s requires LLM but none provided, "
            "falling back to read_file (instruction fallback)",
            skill_name, skill_type,
        )
        return _compile_instruction(skill_name)

    # Auto-load skill_content if not provided
    if skill_content is None:
        skill_content = _load_skill_content(skill_name)
        if skill_content is None:
            logger.warning(
                "SkillPolicy COMPILE: '%s' skill_content could not be loaded, "
                "falling back to read_file",
                skill_name,
            )
            return _compile_instruction(skill_name)

    # All types go through LLM compile
    try:
        return await _llm_compile(
            skill_name, skill_type, user_query,
            skill_content, available_tools or [], llm,
            step_intent=step_intent,
            max_tool_calls=max_tool_calls,
        )
    except Exception as e:
        logger.error(
            "SkillPolicy COMPILE: LLM compile failed for '%s': %s, "
            "falling back to read_file",
            skill_name, e,
        )
        return _compile_instruction(skill_name)


# ---------------------------------------------------------------------------
# GUARD (pure function — unchanged)
# ---------------------------------------------------------------------------


def _tool_call_signature(plan: Dict[str, Any]) -> str:
    """Generate a deterministic signature for duplicate tool call detection."""
    tool = plan.get("tool", "")
    args = plan.get("args", {})
    sorted_args = json.dumps(args, sort_keys=True, ensure_ascii=False)
    return f"{tool}:{sorted_args}"


# Tool-skill_type matching: expected tool per skill_type.
# instruction type is not restricted (LLM free choice).
_TOOL_EXPECTATIONS = {
    "script": "terminal",
    "handler_module": "python_repl",
    "module": "python_repl",
}


def _find_main_script(skill_name: str) -> Optional[str]:
    """Find the main script file for a script-type skill.

    Returns relative path like 'data/skills/chart-plotter/scripts/plot.py',
    or None if not found.
    """
    skills_dir = _get_skills_dir()
    scripts_dir = skills_dir / skill_name / "scripts"
    if not scripts_dir.exists():
        return None
    py_files = [f for f in scripts_dir.glob("*.py") if f.name != "handler.py"]
    if not py_files:
        return None
    return f"data/skills/{skill_name}/scripts/{py_files[0].name}"


def _remap_args(
    skill_type: str,
    skill_name: str,
    current_args: Dict[str, Any],
    user_query: str,
) -> Dict[str, Any]:
    """Remap LLM-generated args to the correct format for the expected tool.

    Called when guard detects a tool-skill_type mismatch and auto-corrects.
    """
    if skill_type == "script":
        code = current_args.get("code", "")
        if code and "command" not in current_args:
            # LLM generated python_repl code for a script skill.
            # Save to temp script file and run via terminal.
            # This preserves LLM's parameter extraction while fixing the
            # output path double-nesting issue (terminal CWD = backend/,
            # so plt.savefig('outputs/xxx.png') resolves correctly).
            skills_dir = _get_skills_dir()
            temp_script = skills_dir / skill_name / "scripts" / "_llm_compiled.py"
            temp_script.write_text(code, encoding="utf-8")
            logger.info(
                "Guard _remap_args: saved LLM code to %s, running via terminal",
                temp_script,
            )
            return {"command": f'"{get_python_command()}" "{temp_script}"'}

        # No usable python_repl code — fall back to running the skill's main script
        script_path = _find_main_script(skill_name)
        if not script_path:
            logger.warning("Guard _remap_args: no script found for '%s'", skill_name)
            return {"command": f"echo 'Error: script not found for {skill_name}'"}
        try:
            from app.core.tot.skill_orchestrator import build_cli_command
            cmd = build_cli_command(script_path, user_query)
            return {"command": cmd}
        except Exception as e:
            logger.warning("Guard _remap_args: build_cli_command failed: %s", e)
            return {"command": f'"{get_python_command()}" {script_path}'}

    if skill_type == "handler_module":
        skills_dir = _get_skills_dir()
        handler_path = (skills_dir / skill_name / "scripts" / "handler.py").resolve()

        # Build importlib preamble to load handler.py
        importlib_preamble = (
            "import importlib.util, asyncio\n"
            f"spec = importlib.util.spec_from_file_location('handler', r'{handler_path}')\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(mod)\n"
            "_call = lambda fn, *a, **kw: asyncio.run(fn(*a, **kw)) if asyncio.iscoroutinefunction(fn) else fn(*a, **kw)\n"
        )

        code = current_args.get("code", "")
        if code and ("from handler import" in code or "import handler" in code):
            # LLM generated function calls with correct params but wrong import.
            # Replace only the import lines, keep function calls intact.
            import re
            # Extract imported names from "from handler import draw, draw_code"
            import_match = re.search(r'from handler import\s+([^\n]+)', code)
            imported_names = []
            if import_match:
                imported_names = [n.strip() for n in import_match.group(1).split(',') if n.strip()]
            # Remove direct import lines
            code = re.sub(r'^from handler import .*\n?', '', code, flags=re.MULTILINE)
            code = re.sub(r'^import handler\n?', '', code, flags=re.MULTILINE)
            # Replace handler.xxx references with mod.xxx
            code = re.sub(r'\bhandler\.', 'mod.', code)
            # Wrap async handler calls: mod.run(...) → _call(mod.run, ...)
            code = re.sub(r'\bmod\.run\(', '_call(mod.run, ', code)
            # Build alias assignments: draw = mod.draw
            aliases = "\n".join(f"{n} = mod.{n}" for n in imported_names) + "\n" if imported_names else ""
            # NOTE: Disabled backslash escaping — too fragile for code containing
            # LaTeX.  The LLM is responsible for correct Python string escaping;
            # handler.py's _safe_text() catches mathtext parse failures.
            # if "r'" not in code and 'r"' not in code:
            #     code = re.sub(r'\\(?=[tnrfvba xuU0-7])', r'\\\\', code)
            code = importlib_preamble + "\n" + aliases + code
        else:
            # No usable code from LLM — inject discovery template as fallback
            code = (
                importlib_preamble + "\n"
                "import json\n"
                "_funcs = [n for n in dir(mod) if not n.startswith('_') and callable(getattr(mod, n))]\n"
                f"print(json.dumps({{'available_functions': _funcs, 'skill': '{skill_name}', "
                f"'query': {user_query!r}}}))\n"
            )
        return {"code": code}

    if skill_type == "module":
        skills_dir = _get_skills_dir()
        handler_path = (skills_dir / skill_name / "scripts" / "handler.py").resolve()

        code = current_args.get("code", "")
        if code and ("from handler import" in code or "import handler" in code):
            # Same fix as handler_module: replace import with importlib
            import re
            import_match = re.search(r'from handler import\s+([^\n]+)', code)
            imported_names = []
            if import_match:
                imported_names = [n.strip() for n in import_match.group(1).split(',') if n.strip()]
            code = re.sub(r'^from handler import .*\n?', '', code, flags=re.MULTILINE)
            code = re.sub(r'^import handler\n?', '', code, flags=re.MULTILINE)
            code = re.sub(r'\bhandler\.', 'mod.', code)
            importlib_preamble = (
                "import importlib.util, asyncio\n"
                f"spec = importlib.util.spec_from_file_location('handler', r'{handler_path}')\n"
                "mod = importlib.util.module_from_spec(spec)\n"
                "spec.loader.exec_module(mod)\n"
                "_call = lambda fn, *a, **kw: asyncio.run(fn(*a, **kw)) if asyncio.iscoroutinefunction(fn) else fn(*a, **kw)\n"
            )
            aliases = "\n".join(f"{n} = mod.{n}" for n in imported_names) + "\n" if imported_names else ""
            code = code.replace('\\', '\\\\')
            return {"code": importlib_preamble + "\n" + aliases + code}

        if not code:
            # No code at all — inject run() template (async-safe)
            code = (
                "import importlib.util, asyncio\n"
                f"spec = importlib.util.spec_from_file_location('handler', r'{handler_path}')\n"
                "mod = importlib.util.module_from_spec(spec)\n"
                "spec.loader.exec_module(mod)\n"
                f"_r = mod.run(inputs={{'query': {user_query!r}}}, context={{}})\n"
                "if asyncio.iscoroutine(_r): _r = asyncio.run(_r)\n"
                "print(_r)"
            )
            return {"code": code}
        return {"code": code}

    return current_args


def guard_compiled_plan(
    tool_plans: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> GuardResult:
    """Static validation of the compiled plan.

    Includes: tool-skill_type matching with auto-correction, tool whitelist,
    path traversal, budget control, duplicate detection.
    """
    config = {**_DEFAULT_GUARD_CONFIG, **context.get("guard_config", {})}
    whitelist = _get_guard_tool_whitelist()
    user_query = context.get("user_query", "")
    issues: List[str] = []

    # 1. Tool-skill_type matching: auto-correct wrong tool selections FIRST
    #    so subsequent checks validate the corrected plan.
    for plan in tool_plans:
        skill_type = plan.pop("_source_skill_type", None)
        skill_name = plan.pop("_source_skill_name", None)
        if not skill_type or skill_type == "instruction":
            continue

        expected_tool = _TOOL_EXPECTATIONS.get(skill_type)
        actual_tool = plan.get("tool", "")

        if expected_tool and actual_tool != expected_tool:
            logger.info(
                "Guard TOOL-CORRECT: '%s' (type=%s) LLM chose '%s', expected '%s' — auto-correcting",
                skill_name, skill_type, actual_tool, expected_tool,
            )
            plan["tool"] = expected_tool
            plan["args"] = _remap_args(
                skill_type, skill_name or "",
                plan.get("args", {}), user_query,
            )
        elif skill_type in ("handler_module", "module") and actual_tool == "python_repl":
            # Tool is correct, but verify code uses importlib for handler loading.
            # LLM often generates direct import (e.g. "from handler import draw")
            # which fails because handler.py is in a non-standard path.
            code = plan.get("args", {}).get("code", "")
            if "importlib" not in code:
                logger.info(
                    "Guard ARGS-CORRECT: '%s' (type=%s) tool correct but code missing importlib — injecting template",
                    skill_name, skill_type,
                )
                plan["args"] = _remap_args(
                    skill_type, skill_name or "",
                    plan.get("args", {}), user_query,
                )
        elif skill_type == "script" and actual_tool == "terminal":
            # Tool is correct but LLM may use wrong field name or wrong path.
            args = plan.get("args", {})
            needs_fix = False

            # Fix 1: 'code' → 'command' (terminal expects 'command')
            if "code" in args and "command" not in args:
                args = {"command": args["code"]}
                needs_fix = True

            # Fix 2: correct script path (LLM often omits 'data/' prefix)
            cmd = args.get("command", "")
            correct_script = _find_main_script(skill_name)
            if correct_script and correct_script not in cmd:
                # LLM used wrong path, rebuild command with correct script
                from app.core.tot.skill_orchestrator import build_cli_command
                try:
                    args = {"command": build_cli_command(correct_script, user_query)}
                except Exception:
                    args = {"command": f'"{get_python_command()}" {correct_script}'}
                needs_fix = True

            if needs_fix:
                logger.info(
                    "Guard ARGS-CORRECT: '%s' script — fixed terminal args",
                    skill_name,
                )
                plan["args"] = args

        # Restore metadata for downstream (skill name display, executor propagation)
        if skill_type:
            plan["_source_skill_type"] = skill_type
        if skill_name:
            plan["_source_skill_name"] = skill_name

    # 2. Standard checks on the (now-corrected) plan
    for plan in tool_plans:
        tool_name = plan.get("tool", "")

        if tool_name not in whitelist:
            issues.append(f"Tool '{tool_name}' not in guard whitelist")

        if tool_name.startswith("skill."):
            issues.append(f"Residual skill reference: {tool_name}")

        args = plan.get("args", {})
        for _key, val in args.items():
            if isinstance(val, str) and ".." in val:
                issues.append(f"Path traversal detected in arg '{_key}': {val}")

    # Budget control
    if len(tool_plans) > config["max_tool_calls"]:
        issues.append(
            f"Tool plan exceeds max_tool_calls: {len(tool_plans)} > {config['max_tool_calls']}"
        )

    # Duplicate tool call detection — auto-fix by removing duplicates
    if config["detect_dead_loop"]:
        seen_calls: set = set()
        deduped_plans: List[Dict[str, Any]] = []
        dup_count = 0
        for plan in tool_plans:
            call_sig = _tool_call_signature(plan)
            if call_sig in seen_calls:
                dup_count += 1
                logger.info("Guard DEDUP: removing duplicate call %s", call_sig[:80])
            else:
                seen_calls.add(call_sig)
                deduped_plans.append(plan)
        if dup_count:
            logger.info("Guard DEDUP: removed %d duplicate call(s), %d remaining", dup_count, len(deduped_plans))
            tool_plans = deduped_plans

    # Duplicate URL detection — auto-fix by removing duplicates
    if config["detect_duplicate_url"]:
        urls: List[str] = []
        url_deduped: List[Dict[str, Any]] = []
        dup_url_count = 0
        for plan in tool_plans:
            args = plan.get("args", {})
            url = args.get("url") or args.get("address", "")
            if url:
                if url in urls:
                    dup_url_count += 1
                    logger.info("Guard DEDUP: removing duplicate URL %s", url[:80])
                    continue
                urls.append(url)
            url_deduped.append(plan)
        if dup_url_count:
            logger.info("Guard DEDUP: removed %d duplicate URL(s), %d remaining", dup_url_count, len(url_deduped))
            tool_plans = url_deduped

    if issues:
        return GuardResult(passed=False, issues=issues, final_plan=None)

    return GuardResult(passed=True, issues=[], final_plan=tool_plans)


# ---------------------------------------------------------------------------
# Unified entry point: run_skill_policy
# ---------------------------------------------------------------------------


async def run_skill_policy(
    policy_input: PolicyInput,
    llm: Optional[Any] = None,
) -> PolicyOutput:
    """Unified pipeline: Match → Gate → Compile(LLM) → Guard.

    Args:
        policy_input: Standardized input from any mode's adapter.
        llm: LLM instance (required for non-instruction skills).

    Returns:
        PolicyOutput with action and tool_plan.
    """
    skill_name = policy_input["skill_name"]
    skill_type = policy_input["skill_type"]

    # 1. MATCH
    candidates = match_skills(
        policy_input["user_query"],
        [{"skill_name": skill_name, "skill_type": skill_type}],
        {},
    )
    if not candidates:
        logger.info("SkillPolicy MATCH: '%s' no candidates", skill_name)
        return PolicyOutput(
            action="PASS_THROUGH",
            tool_plan=[],
            selected_skill=None,
            guardrails={},
            notes=f"MATCH miss for '{skill_name}'",
        )

    cand = candidates[0]
    logger.info(
        "SkillPolicy MATCH: '%s' → %d candidate(s), top=%s score=%.2f",
        skill_name, len(candidates), cand["skill_name"], cand["score"],
    )

    # 2. GATE
    gate_results = gate_skills(
        candidates,
        {"core_tools": policy_input["available_tools"]},
    )
    allowed = [g for g in gate_results if g.get("allowed")]
    if not allowed:
        reason = gate_results[0].get("reason", "unknown") if gate_results else "no results"
        logger.info("SkillPolicy GATE: '%s' blocked — %s", skill_name, reason)
        return PolicyOutput(
            action="BLOCK",
            tool_plan=[],
            selected_skill=None,
            guardrails={},
            notes=f"GATE blocked: {reason}",
        )

    # 3. COMPILE
    step_intent = policy_input.get("current_step", {}).get("intent", "")
    try:
        tool_plan = await compile_skill(
            skill_name=skill_name,
            skill_type=cand["skill_type"],
            user_query=policy_input["user_query"],
            llm=llm,
            skill_content=policy_input["skill_content"],
            available_tools=policy_input["available_tools"],
            step_intent=step_intent,
            max_tool_calls=10,
        )
    except Exception as e:
        logger.error("SkillPolicy COMPILE failed for '%s': %s", skill_name, e)
        return PolicyOutput(
            action="PASS_THROUGH",
            tool_plan=[],
            selected_skill={"skill_name": skill_name, "skill_type": skill_type},
            guardrails={},
            notes=f"COMPILE error: {e}",
        )

    # 4. GUARD
    guard = guard_compiled_plan(tool_plan, {"user_query": policy_input["user_query"]})
    if not guard["passed"]:
        logger.warning("SkillPolicy GUARD: '%s' failed — %s", skill_name, guard["issues"])
        return PolicyOutput(
            action="BLOCK",
            tool_plan=[],
            selected_skill={"skill_name": skill_name, "skill_type": skill_type},
            guardrails={},
            notes=f"GUARD failed: {guard['issues']}",
        )

    logger.info("SkillPolicy GUARD: '%s' passed", skill_name)

    logger.info(
        "SkillPolicy: '%s' → EXECUTE_TOOL_PLAN (%d step(s))",
        skill_name, len(tool_plan),
    )
    return PolicyOutput(
        action="EXECUTE_TOOL_PLAN",
        tool_plan=tool_plan,
        selected_skill={"skill_name": skill_name, "skill_type": cand["skill_type"]},
        guardrails={},
        notes="OK",
    )
