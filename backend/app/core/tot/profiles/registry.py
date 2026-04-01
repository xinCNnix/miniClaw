"""
Domain Profile Registry and Task Type Detection.

Provides a registry of all available domain profiles and a keyword-based
task type detector for automatic profile selection.
"""

import logging
from typing import Dict, List, Tuple

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
    ],
    "research_writing": [
        "research report",
        "literature review",
        "survey",
        "systematic review",
        "meta-analysis",
        "state of the art",
        "comparative study",
    ],
    "coding_debug": [
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
    ],
    "product_design": [
        "PRD",
        "product design",
        "requirements document",
        "user story",
        "MVP",
        "product proposal",
        "feature specification",
        "product roadmap",
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
