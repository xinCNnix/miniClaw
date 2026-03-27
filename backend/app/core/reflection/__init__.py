"""
Reflection Module

Provides unified evaluation framework for distinguishing between
LLM micro-reflections (not persisted) and Agent macro-reflections (persisted).
"""

from app.core.reflection.evaluator import (
    EvaluationResult,
    EvaluationType,
    UnifiedEvaluator,
    get_unified_evaluator,
    reset_unified_evaluator,
)

__all__ = [
    "EvaluationResult",
    "EvaluationType",
    "UnifiedEvaluator",
    "get_unified_evaluator",
    "reset_unified_evaluator",
]
