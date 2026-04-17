"""Backward-compatible alias: app.memory.pattern_memory -> app.memory.auto_learning

This module re-exports everything from auto_learning for backward compatibility.
All new code should import from app.memory.auto_learning directly.
"""

from app.memory.auto_learning import *  # noqa: F401, F403
from app.memory.auto_learning import (
    Pattern,
    PatternExtractionResult,
    PatternNN,
    PatternExtractor,
    PatternMemory,
    get_pattern_memory,
    reset_pattern_memory,
    extract_pattern,
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

# Re-export reflection submodule
from app.memory.auto_learning import reflection  # noqa: F401
