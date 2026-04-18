"""
Domain Profile Registry and Task Type Detection.

Provides a registry of all available domain profiles, a keyword-based
task type detector, and an LLM-based classifier for automatic profile
selection.
"""

import json
import logging
import re
from typing import Any, Dict, List, Tuple

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from .base import DomainProfile
from .generic import GENERIC_PROFILE
from .math_proof import MATH_PROOF_PROFILE
from .research_writing import RESEARCH_WRITING_PROFILE
from .coding_debug import CODING_DEBUG_PROFILE
from .product_design import PRODUCT_DESIGN_PROFILE

logger = logging.getLogger(__name__)

PROFILE_REGISTRY: Dict[str, DomainProfile] = {
    "generic": GENERIC_PROFILE,
    "math_proof": MATH_PROOF_PROFILE,
    "research_writing": RESEARCH_WRITING_PROFILE,
    "coding_debug": CODING_DEBUG_PROFILE,
    "product_design": PRODUCT_DESIGN_PROFILE,
}

TASK_KEYWORDS: Dict[str, List[str]] = {
    "math_proof": [
        # 英文
        "prove",
        "proof",
        "derive",
        "derivation",
        "theorem",
        "lemma",
        "corollary",
        "proposition",
        "induction",
        "contradiction",
        "counterexample",
        "quantifier",
        "formal logic",
        "axiom",
        # 中文
        "证明",
        "推导",
        "定理",
        "引理",
        "推论",
        "命题",
        "归纳",
        "反证",
        "公理",
        "数学归纳",
        "充分必要",
        "充要条件",
        "当且仅当",
        "恒等式",
        "不等式证明",
        "勾股定理",
        "费马",
        "欧拉",
        "黎曼",
    ],
    "research_writing": [
        # 英文
        "research report",
        "literature review",
        "survey",
        "systematic review",
        "meta-analysis",
        "state of the art",
        "comparative study",
        # 中文
        "研究报告",
        "文献综述",
        "综述报告",
        "系统性综述",
        "调研报告",
        "比较研究",
        "前沿综述",
        "现状分析",
        "综述性",
    ],
    "coding_debug": [
        # 英文
        "debug",
        "bug",
        "error",
        "traceback",
        "exception",
        "fix",
        "stack trace",
        "crash",
        "regression",
        "segmentation fault",
        "null pointer",
        # 中文
        "调试",
        "报错",
        "报错信息",
        "异常",
        "修复",
        "崩溃",
        "空指针",
        "段错误",
        "回溯",
        "堆栈",
        "堆栈跟踪",
        "代码报错",
        "运行报错",
    ],
    "product_design": [
        # 英文
        "PRD",
        "product design",
        "requirements document",
        "user story",
        "MVP",
        "product proposal",
        "feature specification",
        "product roadmap",
        # 中文
        "需求文档",
        "产品需求",
        "用户故事",
        "产品提案",
        "功能规格",
        "产品路线",
        "最小可行",
        "产品设计",
        "需求规格",
        "功能设计",
    ],
}


def detect_task_type(query: str) -> Tuple[str, Dict[str, any]]:
    """
    Detect task type from query using keyword matching.

    Scans the query for domain-specific keywords and returns the
    profile name with the highest keyword match count. Falls back
    to "generic" when no domain-specific keywords are found.

    Args:
        query: The user query text to classify.

    Returns:
        Tuple of (profile_name, match_details) where match_details contains:
          - "scores": dict mapping profile_name -> match count
          - "matched_keywords": dict mapping profile_name -> list of matched keywords
          - "selected": the selected profile name
          - "rationale": human-readable explanation
    """
    query_lower = query.lower()
    best_match: str = "generic"
    best_count: int = 0

    scores: Dict[str, int] = {}
    matched_keywords: Dict[str, List[str]] = {}

    for profile_name, keywords in TASK_KEYWORDS.items():
        matched = [kw for kw in keywords if kw.lower() in query_lower]
        count = len(matched)
        scores[profile_name] = count
        matched_keywords[profile_name] = matched
        if count > best_count:
            best_count = count
            best_match = profile_name

    # Build rationale
    if best_count == 0:
        rationale = "No domain-specific keywords matched. Using generic profile."
    else:
        matched_kw_str = ", ".join(matched_keywords[best_match])
        rationale = (
            f"Matched {best_count} keyword(s) for '{best_match}': {matched_kw_str}. "
            f"Scores: {', '.join(f'{k}={v}' for k, v in scores.items() if v > 0)}"
        )

    match_details = {
        "scores": scores,
        "matched_keywords": matched_keywords,
        "selected": best_match,
        "rationale": rationale,
    }

    logger.info(f"[ToT] Profile detection: {rationale}")

    return best_match, match_details


def get_profile(task_type: str) -> DomainProfile:
    """
    Get a domain profile by task type name.

    Args:
        task_type: Profile name string (e.g. "math_proof", "generic").

    Returns:
        The matching DomainProfile, or GENERIC_PROFILE if not found.
    """
    return PROFILE_REGISTRY.get(task_type, GENERIC_PROFILE)


# ---------------------------------------------------------------------------
# LLM-based task classification
# ---------------------------------------------------------------------------

_TASK_CLASSIFICATION_SYSTEM_PROMPT = """\
You are a task-type classifier for an AI reasoning system.  Classify the user \
query into exactly ONE of these categories:

- "research"         -- deep research, comprehensive investigation, literature review, \
systematic analysis requiring evidence gathering and source citation
- "math_proof"       -- mathematical proofs, derivations, theorems, formal logic
- "research_writing" -- research reports, literature reviews, surveys, analysis
- "coding_debug"     -- debugging, error diagnosis, code fixing, stack traces
- "product_design"   -- PRDs, product proposals, feature specs, user stories

If the query does not clearly fit any category, respond with "generic".

IMPORTANT: Use "research" when the query asks for deep investigation, systematic \
review, or evidence-based analysis. Use "research_writing" only for writing-focused \
research output tasks.

Return ONLY a JSON object with exactly these keys:
{
  "task_type": "<one of: research, math_proof, research_writing, coding_debug, product_design, generic>",
  "confidence": <float between 0.0 and 1.0>,
  "rationale": "<one-sentence explanation>"
}

Do not include any text outside the JSON object."""

_VALID_TASK_TYPES = set(PROFILE_REGISTRY.keys()) | {"research"}


def _parse_json_output(text: str) -> dict:
    """Extract JSON object from LLM text output."""
    # Try direct parse first
    text = text.strip()
    if text.startswith("```"):
        # Strip code fences
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try to find JSON object in text
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}


async def detect_task_type_llm(
    query: str,
    llm: BaseChatModel,
) -> Tuple[str, Dict[str, Any]]:
    """Classify a user query into a domain profile using the LLM.

    Sends a single-shot classification request to the LLM and parses the
    JSON response.  On any failure (LLM error, parse error, unknown
    category) falls back to the keyword-based :func:`detect_task_type`.

    Args:
        query: The user query text to classify (any language).
        llm: A LangChain ``BaseChatModel`` instance used for classification.

    Returns:
        Tuple of ``(profile_name, match_details)`` with the same shape as
        :func:`detect_task_type`.
    """
    try:
        messages = [
            SystemMessage(content=_TASK_CLASSIFICATION_SYSTEM_PROMPT),
            HumanMessage(content=f"Query: {query}"),
        ]
        response = await llm.ainvoke(messages)
        raw_text = response.content if hasattr(response, "content") else str(response)

        parsed = _parse_json_output(raw_text)
        task_type = parsed.get("task_type", "")
        confidence = float(parsed.get("confidence", 0.0))
        rationale = parsed.get("rationale", "")

        if task_type in _VALID_TASK_TYPES:
            match_details: Dict[str, Any] = {
                "selected": task_type,
                "confidence": confidence,
                "rationale": (
                    f"[LLM] {rationale} (confidence={confidence:.2f})"
                    if rationale
                    else f"[LLM] Classified as '{task_type}' (confidence={confidence:.2f})"
                ),
                "method": "llm_classification",
            }
            logger.info(f"[ToT] LLM profile detection: {match_details['rationale']}")
            return task_type, match_details

        logger.warning(
            f"[ToT] LLM returned unknown task_type '{task_type}', "
            f"falling back to keyword detection"
        )

    except Exception as exc:
        logger.warning(
            f"[ToT] LLM task classification failed, falling back to "
            f"keyword detection: {exc}"
        )

    # Fallback: use the existing keyword-based detector.
    task_type, match_details = detect_task_type(query)
    match_details["method"] = "keyword_fallback"
    return task_type, match_details
