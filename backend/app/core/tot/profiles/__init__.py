"""
Domain Profile System for Tree of Thoughts Framework.

Provides domain-specific evaluation profiles that guide ToT reasoning
with tailored scoring dimensions, fatal flaw detection, and method
preferences.
"""

from .base import DomainProfile
from .registry import (
    PROFILE_REGISTRY,
    TASK_KEYWORDS,
    detect_task_type,
    detect_task_type_llm,
    get_profile,
)
from .generic import GENERIC_PROFILE
from .math_proof import MATH_PROOF_PROFILE
from .research_writing import RESEARCH_WRITING_PROFILE
from .coding_debug import CODING_DEBUG_PROFILE
from .product_design import PRODUCT_DESIGN_PROFILE

__all__ = [
    "DomainProfile",
    "PROFILE_REGISTRY",
    "TASK_KEYWORDS",
    "detect_task_type",
    "detect_task_type_llm",
    "get_profile",
    "GENERIC_PROFILE",
    "MATH_PROOF_PROFILE",
    "RESEARCH_WRITING_PROFILE",
    "CODING_DEBUG_PROFILE",
    "PRODUCT_DESIGN_PROFILE",
]
