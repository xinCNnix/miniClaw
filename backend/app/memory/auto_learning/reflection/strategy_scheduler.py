"""Strategy scheduler for progressive NN strategy integration.

This module implements a 5-stage progressive transition from fixed baseline
strategies to neural network-generated continuous prompts.
"""

import logging
import random
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class StrategyScheduler:
    """Progressive strategy scheduler for NN policy integration.

    This scheduler manages the transition from fixed baseline strategies
    to neural network-generated strategies through 5 carefully designed stages.

    Design principles:
    1. Cold start: Use fixed baseline during initial training
    2. Progressive mixing: Gradually introduce NN predictions
    3. Performance protection: Monitor and rollback on degradation
    4. User transparency: Seamless experience without visible changes

    Stages:
        1. Baseline (0-100 episodes): 100% fixed baseline
        2. Conservative (100-300): 70% baseline, 30% NN
        3. NN-dominant (300-800): 20% baseline, 80% NN
        4. Transition (800-1500): 10% baseline, 70% discrete NN, 20% continuous
        5. Personalized (1500+): 10% baseline, 90% continuous NN

    Attributes:
        episode_count: Total number of episodes executed
        current_stage: Current stage name
        enable_auto_transition: Whether to automatically transition stages
        performance_threshold: Minimum performance improvement for transition
        rollback_on_degradation: Whether to rollback on performance drop
    """

    STAGES = {
        "baseline": {
            "min_episodes": 0,
            "max_episodes": 100,
            "baseline_ratio": 1.0,
            "nn_prediction_ratio": 0.0,
            "continuous_ratio": 0.0,
            "baseline_action_id": 0,  # "简洁直接地回答"
        },
        "conservative": {
            "min_episodes": 100,
            "max_episodes": 300,
            "baseline_ratio": 0.7,
            "nn_prediction_ratio": 0.3,
            "continuous_ratio": 0.0,
            "baseline_action_id": 0,
        },
        "nn_dominant": {
            "min_episodes": 300,
            "max_episodes": 800,
            "baseline_ratio": 0.2,
            "nn_prediction_ratio": 0.8,
            "continuous_ratio": 0.0,
            "baseline_action_id": 0,
        },
        "transition": {
            "min_episodes": 800,
            "max_episodes": 1500,
            "baseline_ratio": 0.1,
            "nn_prediction_ratio": 0.7,
            "continuous_ratio": 0.2,
            "baseline_action_id": 0,
        },
        "personalized": {
            "min_episodes": 1500,
            "max_episodes": float("inf"),
            "baseline_ratio": 0.1,
            "nn_prediction_ratio": 0.0,
            "continuous_ratio": 0.9,
            "baseline_action_id": 0,
        },
    }

    def __init__(
        self,
        enable_auto_transition: bool = True,
        performance_threshold: float = 0.1,
        rollback_on_degradation: bool = True,
    ) -> None:
        """Initialize StrategyScheduler.

        Args:
            enable_auto_transition: Automatically advance to next stage
            performance_threshold: Min performance improvement for transition
            rollback_on_degradation: Rollback on significant performance drop
        """
        self.episode_count = 0
        self.current_stage = "baseline"
        self.enable_auto_transition = enable_auto_transition
        self.performance_threshold = performance_threshold
        self.rollback_on_degradation = rollback_on_degradation

        # Performance tracking
        self.baseline_rewards: deque = deque(maxlen=100)
        self.nn_prediction_rewards: deque = deque(maxlen=100)
        self.continuous_rewards: deque = deque(maxlen=100)

        # User strategy history for consistency protection
        self.user_strategy_history: dict[str, list[int]] = {}
        self.max_history_length = 5

        logger.info(
            f"StrategyScheduler initialized: auto_transition={enable_auto_transition}, "
            f"performance_threshold={performance_threshold}, "
            f"rollback_on_degradation={rollback_on_degradation}"
        )

    def get_strategy(
        self,
        nn_model,  # AgentModel or PatternNN instance
        state,  # torch.Tensor
        trajectory,  # torch.Tensor
        prompt_decoder = None,
    ) -> dict:
        """Get strategy based on current stage.

        Args:
            nn_model: Neural network model for prediction
            state: State embedding tensor
            trajectory: Action trajectory tensor
            prompt_decoder: Optional prompt decoder for continuous mode

        Returns:
            Dictionary with:
                - strategy_type: "baseline", "nn_prediction", or "continuous"
                - action_id: int (only for baseline and nn_prediction)
                - prompt_text: str
                - confidence: float
                - stage: str
        """
        stage_info = self.STAGES[self.current_stage]

        # Decide which strategy source to use
        rand = random.random()

        # Priority: continuous > nn_prediction > baseline
        if rand < stage_info["continuous_ratio"] and prompt_decoder is not None:
            # Continuous soft prompt (stage 4+)
            return self._get_continuous_strategy(nn_model, state, trajectory, prompt_decoder)

        elif rand < stage_info["continuous_ratio"] + stage_info["nn_prediction_ratio"]:
            # NN prediction (stage 2+)
            return self._get_nn_prediction_strategy(nn_model, state, trajectory)

        else:
            # Fixed baseline strategy (all stages)
            return self._get_baseline_strategy()

    def _get_baseline_strategy(self) -> dict:
        """Get fixed baseline strategy (action_id=0: "简洁直接地回答").

        Returns:
            Baseline strategy dictionary
        """
        from .strategy_mapper import StrategyMapper

        stage_info = self.STAGES[self.current_stage]
        action_id = stage_info["baseline_action_id"]
        prompt_text = StrategyMapper.get_prompt(action_id)

        return {
            "strategy_type": "baseline",
            "action_id": action_id,
            "prompt_text": prompt_text,
            "confidence": 1.0,
            "stage": self.current_stage,
        }

    def _get_nn_prediction_strategy(
        self,
        nn_model,
        state,  # torch.Tensor
        trajectory,  # torch.Tensor
    ) -> dict:
        """Get NN prediction strategy (discrete action_id -> prompt).

        Args:
            nn_model: Neural network model
            state: State embedding
            trajectory: Action trajectory

        Returns:
            NN prediction strategy dictionary
        """
        import torch

        from .strategy_mapper import StrategyMapper

        with torch.no_grad():
            # Handle different model types
            if hasattr(nn_model, "forward") and "AgentModel" in str(type(nn_model)):
                # AgentModel wrapper
                output = nn_model(trajectory, state)
                action_logits = output["action_logits"]
            elif hasattr(nn_model, "predict_with_value"):
                # PatternNN with advanced mode
                output = nn_model.predict_with_value(state, trajectory)
                action_logits = output["action_logits"]
            else:
                # Basic PatternNN
                action_logits = nn_model(state)

            # Get predicted action_id
            if action_logits.dim() == 2:
                action_logits = action_logits.squeeze(0)

            action_id = torch.argmax(action_logits).item()
            confidence = torch.softmax(action_logits, dim=-1).max().item()

        # Map to strategy text
        prompt_text = StrategyMapper.get_prompt(action_id)

        return {
            "strategy_type": "nn_prediction",
            "action_id": action_id,
            "prompt_text": prompt_text,
            "confidence": confidence,
            "stage": self.current_stage,
        }

    def _get_continuous_strategy(
        self,
        nn_model,
        state,  # torch.Tensor
        trajectory,  # torch.Tensor
        prompt_decoder,
    ) -> dict:
        """Get continuous soft prompt strategy (z -> decoder -> text).

        Args:
            nn_model: Neural network model
            state: State embedding
            trajectory: Action trajectory
            prompt_decoder: Prompt decoder

        Returns:
            Continuous strategy dictionary
        """
        import torch

        with torch.no_grad():
            # Get latent z vector
            if hasattr(nn_model, "forward") and "AgentModel" in str(type(nn_model)):
                # AgentModel wrapper
                output = nn_model(trajectory, state)
                z = output["z"]
            elif hasattr(nn_model, "trajectory_encoder"):
                # PatternNN with advanced mode
                if trajectory.dim() == 1:
                    trajectory = trajectory.unsqueeze(0)
                z = nn_model.trajectory_encoder(trajectory)
                if z.dim() == 1:
                    z = z.unsqueeze(0)
            else:
                # Fallback
                z = torch.zeros(1, 128)

            # Decode to text (placeholder - actual implementation depends on decoder)
            if prompt_decoder is not None and hasattr(prompt_decoder, "decode"):
                prompt_text = prompt_decoder.decode(z)
            else:
                # Fallback: use strategy mapper with random action
                from .strategy_mapper import StrategyMapper
                action_id = random.randint(0, 19)
                prompt_text = StrategyMapper.get_prompt(action_id)

            # Confidence based on z norm
            confidence = torch.norm(z).item() / (torch.norm(z).item() + 1.0)

        return {
            "strategy_type": "continuous",
            "action_id": None,
            "prompt_text": prompt_text,
            "confidence": confidence,
            "stage": self.current_stage,
        }

    def report_performance(
        self,
        strategy_type: str,
        reward: float,
        success: bool,
        user_id: str = "default",
    ) -> None:
        """Report strategy execution performance.

        Args:
            strategy_type: "baseline", "nn_prediction", or "continuous"
            reward: Execution reward
            success: Whether execution was successful
            user_id: User identifier for consistency tracking
        """
        perf = {
            "reward": reward,
            "success": success,
            "user_id": user_id,
        }

        if strategy_type == "nn_prediction":
            self.nn_prediction_rewards.append(perf)
        elif strategy_type == "baseline":
            self.baseline_rewards.append(perf)
        elif strategy_type == "continuous":
            self.continuous_rewards.append(perf)

        # Check performance and rollback if needed
        if self.rollback_on_degradation:
            self._check_performance_and_rollback()

        logger.debug(
            f"Performance reported: strategy={strategy_type}, "
            f"reward={reward:.3f}, success={success}"
        )

    def update_episode_count(self, count: int) -> None:
        """Update episode count and auto-transition if ready.

        Args:
            count: Total episode count
        """
        self.episode_count = count

        if self.enable_auto_transition:
            self._try_transition_to_next_stage()

    def _try_transition_to_next_stage(self) -> bool:
        """Attempt transition to next stage.

        Returns:
            True if transition occurred, False otherwise
        """
        stage_order = [
            "baseline",
            "conservative",
            "nn_dominant",
            "transition",
            "personalized",
        ]
        current_idx = stage_order.index(self.current_stage)

        if current_idx >= len(stage_order) - 1:
            return False  # Already at final stage

        next_stage = stage_order[current_idx + 1]
        next_stage_info = self.STAGES[next_stage]

        # Check episode count
        if self.episode_count >= next_stage_info["min_episodes"]:
            # Check performance conditions
            if self._check_performance_ready_for_next_stage():
                old_stage = self.current_stage
                self.current_stage = next_stage
                logger.info(
                    f"Strategy scheduler transition: {old_stage} → {next_stage} "
                    f"(episodes={self.episode_count})"
                )
                return True

        return False

    def _check_performance_ready_for_next_stage(self) -> bool:
        """Check if performance is ready for next stage.

        Returns:
            True if ready to transition, False otherwise
        """
        stage_order = [
            "baseline",
            "conservative",
            "nn_dominant",
            "transition",
            "personalized",
        ]
        current_idx = stage_order.index(self.current_stage)

        # Stage 1 → 2: No performance check (fixed baseline)
        if current_idx == 0:
            return True

        # Stage 2 → 3: NN prediction must not be worse than baseline
        if current_idx == 1:
            if len(self.nn_prediction_rewards) < 10 or len(self.baseline_rewards) < 10:
                return False

            nn_avg = sum(r["reward"] for r in self.nn_prediction_rewards[-10:]) / 10
            baseline_avg = sum(r["reward"] for r in self.baseline_rewards[-10:]) / 10

            return nn_avg >= baseline_avg - 0.1

        # Stage 3 → 4: NN must be clearly better than baseline
        if current_idx == 2:
            if len(self.nn_prediction_rewards) < 20 or len(self.baseline_rewards) < 20:
                return False

            nn_avg = sum(r["reward"] for r in self.nn_prediction_rewards[-20:]) / 20
            baseline_avg = sum(r["reward"] for r in self.baseline_rewards[-20:]) / 20

            return nn_avg >= baseline_avg + self.performance_threshold

        # Stage 4 → 5: Continuous must not be worse than discrete
        if current_idx == 3:
            if len(self.continuous_rewards) < 10 or len(self.nn_prediction_rewards) < 10:
                return False

            continuous_avg = sum(r["reward"] for r in self.continuous_rewards[-10:]) / 10
            discrete_avg = sum(r["reward"] for r in self.nn_prediction_rewards[-10:]) / 10

            return continuous_avg >= discrete_avg - 0.05

        return False

    def _check_performance_and_rollback(self) -> None:
        """Check performance and rollback if degraded."""
        stage_order = [
            "baseline",
            "conservative",
            "nn_dominant",
            "transition",
            "personalized",
        ]
        current_idx = stage_order.index(self.current_stage)

        if current_idx <= 0:
            return  # Stage 1 has no rollback

        # Check rollback conditions for each stage
        if current_idx == 1:  # Conservative
            if len(self.nn_prediction_rewards) < 20 or len(self.baseline_rewards) < 20:
                return

            nn_avg = sum(r["reward"] for r in self.nn_prediction_rewards[-20:]) / 20
            baseline_avg = sum(r["reward"] for r in self.baseline_rewards[-20:]) / 20

            if nn_avg < baseline_avg - 0.2:
                self.current_stage = stage_order[0]
                logger.warning("NN performance too poor, rolling back to baseline")

        elif current_idx == 2:  # NN-dominant
            if len(self.nn_prediction_rewards) < 20 or len(self.baseline_rewards) < 20:
                return

            nn_avg = sum(r["reward"] for r in self.nn_prediction_rewards[-20:]) / 20
            baseline_avg = sum(r["reward"] for r in self.baseline_rewards[-20:]) / 20

            if nn_avg < baseline_avg + 0.05:
                self.current_stage = stage_order[1]
                logger.warning("NN advantage lost, rolling back to conservative")

        elif current_idx == 3:  # Transition
            if len(self.continuous_rewards) < 10 or len(self.nn_prediction_rewards) < 10:
                return

            continuous_avg = sum(r["reward"] for r in self.continuous_rewards[-10:]) / 10
            discrete_avg = sum(r["reward"] for r in self.nn_prediction_rewards[-10:]) / 10

            if continuous_avg < discrete_avg - 0.1:
                self.current_stage = stage_order[2]
                logger.warning("Continuous strategy underperforming, rolling back to nn_dominant")

        elif current_idx == 4:  # Personalized
            if len(self.continuous_rewards) < 20 or len(self.nn_prediction_rewards) < 20:
                return

            continuous_avg = sum(r["reward"] for r in self.continuous_rewards[-20:]) / 20
            discrete_avg = sum(r["reward"] for r in self.nn_prediction_rewards[-20:]) / 20

            if continuous_avg < discrete_avg - 0.15:
                self.current_stage = stage_order[3]
                logger.warning("Continuous strategy failed, rolling back to transition")

    def get_status(self) -> dict:
        """Get current scheduler status.

        Returns:
            Dictionary with status information
        """
        stage_info = self.STAGES[self.current_stage]

        return {
            "current_stage": self.current_stage,
            "episode_count": self.episode_count,
            "baseline_ratio": stage_info["baseline_ratio"],
            "nn_prediction_ratio": stage_info["nn_prediction_ratio"],
            "continuous_ratio": stage_info["continuous_ratio"],
            "baseline_samples": len(self.baseline_rewards),
            "nn_prediction_samples": len(self.nn_prediction_rewards),
            "continuous_samples": len(self.continuous_rewards),
        }

    def get_meta_policy_advice(
        self,
        nn_model,
        state_vec,
        trajectory,
        tool_index_map: dict | None = None,
        skill_index_map: dict | None = None,
        prompt_decoder=None,
    ) -> dict:
        """Get meta-policy advice from the strategy scheduler.

        Wraps get_strategy() and formats the result as MetaPolicyAdvice.

        Args:
            nn_model: Neural network model for prediction
            state_vec: State embedding tensor
            trajectory: Action trajectory tensor
            tool_index_map: Optional mapping of tool names to indices
            skill_index_map: Optional mapping of skill names to indices

        Returns:
            Dictionary with MetaPolicyAdvice fields:
                - strategy_type: str
                - action_id: int | None
                - prompt_text: str
                - confidence: float
                - stage: str
                - tool_suggestion: str | None
                - skill_suggestion: str | None
        """
        strategy = self.get_strategy(nn_model, state_vec, trajectory, prompt_decoder=prompt_decoder)

        # Map action_id back to tool/skill suggestions if maps provided
        tool_suggestion = None
        skill_suggestion = None
        action_id = strategy.get("action_id")

        if action_id is not None and tool_index_map:
            # Reverse lookup: find tool name from index
            for name, idx in tool_index_map.items():
                if idx == action_id:
                    tool_suggestion = name
                    break

        if action_id is not None and skill_index_map:
            for name, idx in skill_index_map.items():
                if idx == action_id:
                    skill_suggestion = name
                    break

        return {
            "strategy_type": strategy["strategy_type"],
            "action_id": action_id,
            "prompt_text": strategy.get("prompt_text", ""),
            "confidence": strategy.get("confidence", 0.0),
            "stage": strategy.get("stage", self.current_stage),
            "tool_suggestion": tool_suggestion,
            "skill_suggestion": skill_suggestion,
        }


# Singleton instance
_strategy_scheduler_instance: StrategyScheduler | None = None


def get_strategy_scheduler() -> StrategyScheduler:
    """Get the global strategy scheduler instance.

    Returns:
        StrategyScheduler: Global scheduler instance
    """
    global _strategy_scheduler_instance

    if _strategy_scheduler_instance is None:
        _strategy_scheduler_instance = StrategyScheduler()

    return _strategy_scheduler_instance


def reset_strategy_scheduler() -> None:
    """Reset the global strategy scheduler.

    This should be called when configuration is updated.
    """
    global _strategy_scheduler_instance
    _strategy_scheduler_instance = None
