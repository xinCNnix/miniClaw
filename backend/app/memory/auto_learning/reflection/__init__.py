"""Reflection-driven learning system for pattern memory.

This module provides components for reflection-based learning:
- ReflectionEngine: LLM-based execution analysis
- RewardModel: Scalar reward computation
- StrategyMapper: Action → Prompt mapping
- PatternLearner: Main learning coordinator
"""

from app.memory.auto_learning.reflection.learner import (
    PatternLearner,
    get_pattern_learner,
    reset_pattern_learner,
)
from app.memory.auto_learning.reflection.models import (
    LearningResult,
    ReflectionResult,
    RewardResult,
    ToolMetrics,
)
from app.memory.auto_learning.reflection.reflection_engine import ReflectionEngine
from app.memory.auto_learning.reflection.reward_model import RewardModel
from app.memory.auto_learning.reflection.strategy_mapper import (
    ACTION_PROMPT_MAP,
    StrategyMapper,
    get_strategy_prompt,
    sample_strategy_action,
)
from app.memory.auto_learning.reflection.strategy_scheduler import (
    StrategyScheduler,
    get_strategy_scheduler,
)

__all__ = [
    # Models
    "ReflectionResult",
    "ToolMetrics",
    "RewardResult",
    "LearningResult",
    # Core Components
    "ReflectionEngine",
    "RewardModel",
    "StrategyMapper",
    "PatternLearner",
    # Strategy Mapping
    "ACTION_PROMPT_MAP",
    "get_strategy_prompt",
    "sample_strategy_action",
    # Strategy Scheduler
    "StrategyScheduler",
    "get_strategy_scheduler",
    # Singletons
    "get_pattern_learner",
    "reset_pattern_learner",
]

__version__ = "0.1.0"
