"""Pattern Memory - Pattern learning component for miniClaw.

This module provides pattern extraction, storage, and retrieval
for AI agents using neural networks and LLM-based extraction.

Supports two modes:
- Basic mode: Simple pattern matching (backward compatible)
- Advanced mode: RL-based learning with trajectories
- Reflection mode: Reflection-driven learning (Stage 2)
"""

from .models import Pattern, PatternExtractionResult
from .nn import PatternNN
from .extractor import PatternExtractor, extract_pattern
from .memory import PatternMemory, get_pattern_memory, reset_pattern_memory

# Stage 2: Reflection-driven learning
from .reflection import (
    PatternLearner,
    ReflectionEngine,
    ReflectionResult,
    RewardModel,
    RewardResult,
    StrategyMapper,
    ToolMetrics,
    get_pattern_learner,
    get_strategy_prompt,
    reset_pattern_learner,
    sample_strategy_action,
)

__all__ = [
    # Models
    "Pattern",
    "PatternExtractionResult",
    # Core Components
    "PatternNN",
    "PatternExtractor",
    "PatternMemory",
    # Utils
    "get_pattern_memory",
    "reset_pattern_memory",
    # Convenience
    "extract_pattern",
    # Stage 2: Reflection-driven learning
    "ReflectionEngine",
    "RewardModel",
    "StrategyMapper",
    "PatternLearner",
    "ReflectionResult",
    "RewardResult",
    "ToolMetrics",
    "get_pattern_learner",
    "reset_pattern_learner",
    "get_strategy_prompt",
    "sample_strategy_action",
]

__version__ = "1.0.0"
