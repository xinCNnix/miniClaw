"""Dream prompt templates for Judge, Distiller, and Consolidator."""

from app.core.dream.prompts.judge import (
    STRONG_JUDGE_SYSTEM,
    STRONG_JUDGE_USER,
    format_judge_prompt,
)
from app.core.dream.prompts.distiller import (
    DISTILLER_SYSTEM,
    DISTILLER_USER,
    format_distiller_prompt,
)
from app.core.dream.prompts.consolidator import (
    CONSOLIDATOR_SYSTEM,
    CONSOLIDATOR_USER,
    format_consolidator_prompt,
)

__all__ = [
    "STRONG_JUDGE_SYSTEM",
    "STRONG_JUDGE_USER",
    "format_judge_prompt",
    "DISTILLER_SYSTEM",
    "DISTILLER_USER",
    "format_distiller_prompt",
    "CONSOLIDATOR_SYSTEM",
    "CONSOLIDATOR_USER",
    "format_consolidator_prompt",
]
