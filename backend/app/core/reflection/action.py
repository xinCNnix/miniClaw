"""Data structures for reflection-driven correction actions."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.memory.auto_learning.reflection.models import ReflectionResult


@dataclass
class ReflectionAction:
    """Result of evaluating agent output quality and optional correction.

    Attributes:
        should_correct: Whether quality is below threshold and correction is needed
        quality_score: Quality score from reflection (0.0-10.0)
        correction: Correction content if should_correct is True, else None
        reflection: Full reflection result from the reflection engine
        execution_mode: Which execution path produced this ("tot"|"perv"|"normal")
    """

    should_correct: bool
    quality_score: float
    correction: str | None
    reflection: ReflectionResult
    execution_mode: str = "normal"
