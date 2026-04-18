"""Pattern learner - main coordinator for reflection-driven learning."""

import logging
import uuid

from app.memory.auto_learning.extractor import PatternExtractor
from app.memory.auto_learning.models import Pattern
from app.memory.auto_learning.reflection.models import (
    LearningResult,
    ReflectionResult,
    RewardResult,
    ToolMetrics,
)
from app.memory.auto_learning.reflection.reflection_engine import ReflectionEngine
from app.memory.auto_learning.reflection.reward_model import RewardModel
from app.memory.auto_learning.reflection.strategy_mapper import StrategyMapper

logger = logging.getLogger(__name__)


class PatternLearner:
    """Main coordinator for reflection-driven pattern learning.

    This class integrates ReflectionEngine, RewardModel, and StrategyMapper
    to coordinate the learning loop from agent execution.

    Learning flow:
    1. Reflect on execution results
    2. Compute reward signal
    3. Extract and store patterns
    4. Trigger async training

    Attributes:
        reflection_engine: Engine for analyzing execution
        reward_model: Model for computing rewards
        pattern_extractor: Extractor for pattern extraction
        strategy_mapper: Mapper for action → prompt conversion
    """

    def __init__(
        self,
        reflection_engine: ReflectionEngine | None = None,
        reward_model: RewardModel | None = None,
        pattern_extractor: PatternExtractor | None = None,
        buffer = None,  # EnhancedReplayBuffer instance
        rl_trainer = None,  # RLTrainer instance
        enable_rl: bool = False,
    ) -> None:
        """Initialize PatternLearner.

        Args:
            reflection_engine: Optional reflection engine. If None, creates default.
            reward_model: Optional reward model. If None, creates default.
            pattern_extractor: Optional pattern extractor. If None, creates default.
            buffer: Optional replay buffer for RL training.
            rl_trainer: Optional RL trainer for neural network training.
            enable_rl: Whether to enable RL training.

        Examples:
            >>> learner = PatternLearner()
            >>> result = await learner.learn_from_execution(
            ...     session_id="session_123",
            ...     user_query="What is the weather?",
            ...     agent_output="The weather is sunny.",
            ...     tool_calls=[]
            ... )
        """
        self.reflection_engine = reflection_engine or ReflectionEngine()
        self.reward_model = reward_model or RewardModel()
        self.pattern_extractor = pattern_extractor or PatternExtractor()
        self.strategy_mapper = StrategyMapper()
        self.buffer = buffer
        self.rl_trainer = rl_trainer
        self.enable_rl = enable_rl

        logger.info(f"PatternLearner initialized (RL enabled: {enable_rl})")

    async def learn_from_execution(
        self,
        session_id: str,
        user_query: str,
        agent_output: str,
        tool_calls: list[dict],
        execution_time: float = 0.0,
    ) -> LearningResult:
        """Learn from agent execution.

        This is the main entry point for the learning loop. It coordinates
        reflection, reward computation, pattern extraction, and training.

        Args:
            session_id: Session identifier
            user_query: Original user query
            agent_output: Agent's output response
            tool_calls: List of tool call records
            execution_time: Execution time in seconds

        Returns:
            LearningResult with reflection, reward, and pattern info

        Examples:
            >>> learner = PatternLearner()
            >>> result = await learner.learn_from_execution(
            ...     session_id="session_123",
            ...     user_query="What is the weather?",
            ...     agent_output="The weather is sunny.",
            ...     tool_calls=[]
            ... )
            >>> print(result.reward.total_reward)
            0.75
        """
        logger.info(f"Starting learning for session {session_id}")

        try:
            # Step 1: Reflect on execution
            logger.debug("Step 1: Running reflection analysis")
            reflection = await self.reflection_engine.reflect(
                user_query=user_query,
                agent_output=agent_output,
                tool_calls=tool_calls,
                execution_time=execution_time,
            )

            # Step 2: Compute reward
            logger.debug("Step 2: Computing reward")
            tool_metrics = ToolMetrics.from_tool_calls(tool_calls)
            reward = await self.reward_model.compute_reward(
                user_query=user_query,
                agent_output=agent_output,
                reflection=reflection,
                tool_metrics=tool_metrics,
            )

            # Step 3: Extract pattern if execution was problematic
            pattern_extracted = False
            pattern_id = None

            if not reflection.completed or reflection.problems:
                logger.debug("Step 3: Extracting pattern from problematic execution")
                pattern_description = await self.pattern_extractor.extract(
                    situation=user_query,
                    outcome=agent_output,
                    fix="; ".join(reflection.suggestions) if reflection.suggestions else "No fix",
                )

                # Create pattern object (for future storage)
                pattern = Pattern(
                    id=str(uuid.uuid4())[:8],
                    description=pattern_description,
                    situation=user_query,
                    outcome=agent_output,
                    fix_action="; ".join(reflection.suggestions) if reflection.suggestions else "No fix",
                )

                pattern_extracted = True
                pattern_id = pattern.id

                logger.info(f"Extracted pattern {pattern_id}: {pattern_description[:50]}...")
            else:
                logger.debug("Step 3: Skipping pattern extraction (execution successful)")

            # Step 4: Store experience and trigger RL training
            training_triggered = False

            if self.enable_rl and self.buffer is not None and self.rl_trainer is not None:
                try:
                    import torch

                    from app.memory.auto_learning.nn import get_pattern_nn
                    from app.memory.auto_learning.reflection.strategy_scheduler import (
                        get_strategy_scheduler,
                    )

                    # Create trajectory tokens (simplified version)
                    # In production, this should be derived from actual tool call sequence
                    trajectory_tokens = torch.zeros(128, dtype=torch.long)  # Placeholder

                    # Encode state from user query
                    # Use simple hash-based encoding for now (production should use embedding manager)
                    state_embedding = torch.randn(256)  # Placeholder for actual embedding

                    # Map suggestion to action ID
                    if reflection.suggestions:
                        # Use first suggestion to determine action
                        suggestion_text = reflection.suggestions[0]
                        action_id = hash(suggestion_text) % 20  # Map to 0-19
                    else:
                        action_id = 0  # Default action

                    # Add to buffer
                    self.buffer.add(
                        trajectory=trajectory_tokens,
                        state=state_embedding,
                        action=action_id,
                        reward=reward.total_reward,
                        done=True,
                        episode_id=session_id,
                    )

                    # Trigger training when buffer has enough data
                    if len(self.buffer) >= 32:
                        batch = self.buffer.sample(32)
                        metrics = self.rl_trainer.train_batch(batch)

                        logger.info(
                            f"RL training completed: loss={metrics['total_loss']:.4f}, "
                            f"policy={metrics['policy_loss']:.4f}, "
                            f"value={metrics['value_loss']:.4f}"
                        )

                        # Save model
                        nn_instance = get_pattern_nn()
                        if nn_instance:
                            nn_instance.save()

                        # Update strategy scheduler episode count
                        scheduler = get_strategy_scheduler()
                        scheduler.update_episode_count(len(self.buffer.get_all_episode_ids()))

                        # Report performance to scheduler
                        strategy_type = "nn_prediction"  # Simplified
                        scheduler.report_performance(
                            strategy_type=strategy_type,
                            reward=reward.total_reward,
                            success=reward.total_reward > 0.5,
                        )

                        training_triggered = True

                except Exception as e:
                    logger.warning(f"RL training failed: {e}", exc_info=True)

            else:
                logger.debug("Step 4: RL training disabled or not configured")

            # Create learning result
            result = LearningResult(
                session_id=session_id,
                reflection=reflection,
                reward=reward,
                pattern_extracted=pattern_extracted,
                pattern_id=pattern_id,
                training_triggered=training_triggered,
            )

            logger.info(
                f"Learning completed for session {session_id}: "
                f"reward={reward.total_reward:.3f}, "
                f"pattern_extracted={pattern_extracted}"
            )

            return result

        except Exception as e:
            logger.error(f"Learning failed for session {session_id}: {e}", exc_info=True)

            # Return fallback result
            return LearningResult(
                session_id=session_id,
                reflection=ReflectionResult(
                    completed=False,
                    problems=["Learning failed"],
                    suggestions=[],
                    confidence=0.0,
                ),
                reward=RewardResult(
                    total_reward=0.0,
                    semantic_reward=0.0,
                    shaping_reward=0.0,
                ),
                pattern_extracted=False,
                pattern_id=None,
                training_triggered=False,
            )

    def get_strategy_prompt(self, action_id: int) -> str:
        """Get strategy prompt for action ID.

        Args:
            action_id: Action ID from policy network

        Returns:
            Strategy prompt string

        Examples:
            >>> learner = PatternLearner()
            >>> prompt = learner.get_strategy_prompt(0)
            >>> print(prompt)
            '简洁直接地回答。'
        """
        return self.strategy_mapper.get_prompt(action_id)

    def sample_strategy_action(self) -> int:
        """Sample random action ID for exploration.

        Returns:
            Random action ID in range [0, 19]

        Examples:
            >>> learner = PatternLearner()
            >>> action_id = learner.sample_strategy_action()
            >>> print(f"Sampled action: {action_id}")
            Sampled action: 5
        """
        return self.strategy_mapper.sample_random()


# Singleton instance
_pattern_learner_instance: PatternLearner | None = None


def get_pattern_learner() -> PatternLearner:
    """Get the global pattern learner instance.

    Reads RL training configuration from Settings to determine
    whether to enable RL-based learning.

    Returns:
        PatternLearner: Global pattern learner instance

    Examples:
        >>> learner = get_pattern_learner()
        >>> result = await learner.learn_from_execution(...)
    """
    global _pattern_learner_instance

    if _pattern_learner_instance is None:
        from app.config import get_settings
        settings = get_settings()
        enable_rl = getattr(settings, "enable_rl_training", False)

        buffer = None
        rl_trainer = None
        if enable_rl:
            try:
                from app.memory.auto_learning.advanced.buffer import EnhancedReplayBuffer
                from app.memory.auto_learning.advanced.rl_trainer import RLTrainer
                from app.memory.auto_learning.nn import get_pattern_nn
                nn_model = get_pattern_nn()
                buffer = EnhancedReplayBuffer(
                    capacity=getattr(settings, "rl_batch_size", 32),
                    enable_trajectory=True,
                    prioritized=True,
                )
                rl_trainer = RLTrainer(model=nn_model)
            except ImportError as e:
                import logging
                logging.getLogger(__name__).warning(
                    f"[auto_learning] RL components not available, disabling RL: {e}"
                )
                enable_rl = False

        _pattern_learner_instance = PatternLearner(
            buffer=buffer,
            rl_trainer=rl_trainer,
            enable_rl=enable_rl,
        )
        logger.info(f"[auto_learning] PatternLearner initialized with enable_rl={enable_rl}")

    return _pattern_learner_instance


def reset_pattern_learner() -> None:
    """Reset the global pattern learner to force recreation on next access.

    This should be called when configuration is updated to ensure
    the new configuration is picked up immediately.

    Examples:
        >>> reset_pattern_learner()
        >>> learner = get_pattern_learner()  # New instance
    """
    global _pattern_learner_instance
    _pattern_learner_instance = None


__all__ = [
    "PatternLearner",
    "get_pattern_learner",
    "reset_pattern_learner",
]
