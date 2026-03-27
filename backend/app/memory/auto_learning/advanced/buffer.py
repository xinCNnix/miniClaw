"""Enhanced replay buffer for RL training."""

import logging
from typing import TYPE_CHECKING

import torch

from app.memory.auto_learning.advanced.models import RLExperience, Trajectory

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class EnhancedReplayBuffer:
    """Enhanced experience replay buffer supporting multiple modes.

    This buffer supports two operating modes:
    - Basic mode: Stores (embedding, label) tuples for backward compatibility
    - Advanced mode: Stores full RL experiences with trajectories

    The buffer can optionally use prioritized replay for more efficient learning.

    Attributes:
        capacity: Maximum number of experiences to store
        enable_trajectory: Whether to use advanced mode with trajectory storage
        prioritized: Whether to use prioritized replay
        alpha: Priority exponent for prioritization
    """

    def __init__(
        self,
        capacity: int = 500,
        enable_trajectory: bool = False,
        prioritized: bool = False,
        alpha: float = 0.6,
    ) -> None:
        """Initialize EnhancedReplayBuffer.

        Args:
            capacity: Maximum buffer capacity
            enable_trajectory: Enable advanced mode with trajectory storage
            prioritized: Enable prioritized experience replay
            alpha: Priority exponent (higher = more prioritization)
        """
        self.capacity = capacity
        self.enable_trajectory = enable_trajectory
        self.prioritized = prioritized
        self.alpha = alpha

        # Choose buffer type based on mode
        if enable_trajectory:
            self.buffer: list[dict] = []  # Advanced mode: store full experiences
            logger.debug("Initialized replay buffer in ADVANCED mode (trajectory enabled)")
        else:
            self.buffer: list[tuple] = []  # Basic mode: backward compatible
            logger.debug("Initialized replay buffer in BASIC mode (backward compatible)")

        logger.info(
            f"EnhancedReplayBuffer initialized: capacity={capacity}, "
            f"enable_trajectory={enable_trajectory}, prioritized={prioritized}, "
            f"alpha={alpha}"
        )

    def add(self, *args, **kwargs) -> None:
        """Add experience to buffer (mode-aware).

        This method automatically routes to the appropriate add method
        based on the buffer mode.

        For basic mode: add(embedding, label)
        For advanced mode: add(trajectory, state, action, reward, ...)
        """
        if self.enable_trajectory:
            self._add_advanced(*args, **kwargs)
        else:
            self._add_basic(*args, **kwargs)

    def _add_basic(
        self,
        embedding: torch.Tensor,
        label: int,
    ) -> None:
        """Add experience in basic mode (backward compatible).

        Args:
            embedding: State embedding tensor
            label: Action label (integer)
        """
        experience = (embedding.clone().detach(), label)
        self.buffer.append(experience)

        # Maintain capacity (FIFO eviction)
        if len(self.buffer) > self.capacity:
            self.buffer.pop(0)

        logger.debug(f"Added basic experience (buffer size: {len(self.buffer)}/{self.capacity})")

    def _add_advanced(
        self,
        trajectory: torch.Tensor | Trajectory,
        state: torch.Tensor,
        action: int,
        reward: float,
        next_state: torch.Tensor | None = None,
        done: bool = False,
        priority: float | None = None,
        episode_id: str | None = None,
    ) -> None:
        """Add experience in advanced mode (full RL experience).

        Args:
            trajectory: Action trajectory (token IDs or Trajectory object)
            state: State embedding tensor
            action: Action taken
            reward: Reward received
            next_state: Next state embedding (optional)
            done: Whether episode terminated
            priority: Manual priority score (optional, auto-computed if None)
            episode_id: Episode identifier (optional)
        """
        # Convert trajectory to tensor if needed
        if isinstance(trajectory, Trajectory):
            traj_tensor = torch.tensor(trajectory.token_ids, dtype=torch.long)
        else:
            traj_tensor = trajectory

        experience = {
            "trajectory": traj_tensor.clone().detach(),
            "state": state.clone().detach(),
            "action": action,
            "reward": reward,
            "next_state": next_state.clone().detach() if next_state is not None else None,
            "done": done,
            "episode_id": episode_id,
        }

        # Compute priority if using prioritized replay
        if self.prioritized:
            if priority is None:
                # Default priority: absolute reward ^ alpha
                priority = abs(reward) ** self.alpha
            experience["priority"] = priority

        self.buffer.append(experience)

        # Maintain capacity
        if len(self.buffer) > self.capacity:
            if self.prioritized:
                # Remove lowest priority experience
                self.buffer.sort(key=lambda x: x.get("priority", 0.0))
                self.buffer.pop(0)
            else:
                self.buffer.pop(0)

        logger.debug(
            f"Added advanced experience with reward={reward:.3f} "
            f"(buffer size: {len(self.buffer)}/{self.capacity})"
        )

    def sample(self, batch_size: int = 32) -> list:
        """Sample a batch of experiences.

        Args:
            batch_size: Number of experiences to sample

        Returns:
            List of sampled experiences

        Raises:
            ValueError: If batch_size exceeds buffer size
        """
        if batch_size > len(self.buffer):
            raise ValueError(
                f"batch_size ({batch_size}) exceeds buffer size ({len(self.buffer)})"
            )

        if self.enable_trajectory:
            return self._sample_advanced(batch_size)
        else:
            return self._sample_basic(batch_size)

    def _sample_basic(self, batch_size: int) -> list[tuple]:
        """Sample in basic mode (uniform random).

        Args:
            batch_size: Number of experiences to sample

        Returns:
            List of (embedding, label) tuples
        """
        indices = torch.randperm(len(self.buffer))[:batch_size]
        return [self.buffer[i] for i in indices]

    def _sample_advanced(self, batch_size: int) -> list[dict]:
        """Sample in advanced mode (supports prioritized replay).

        Args:
            batch_size: Number of experiences to sample

        Returns:
            List of experience dictionaries
        """
        if self.prioritized and len(self.buffer) > 0:
            # Sample according to priority distribution
            priorities = torch.tensor(
                [exp.get("priority", 1.0) for exp in self.buffer], dtype=torch.float32
            )
            probs = priorities / priorities.sum()
            indices = torch.multinomial(probs, batch_size, replacement=False)
        else:
            # Uniform random sampling
            indices = torch.randperm(len(self.buffer))[:batch_size]

        return [self.buffer[i] for i in indices]

    def __len__(self) -> int:
        """Get current buffer size.

        Returns:
            Number of experiences in buffer
        """
        return len(self.buffer)

    def is_empty(self) -> bool:
        """Check if buffer is empty.

        Returns:
            True if buffer has no experiences
        """
        return len(self.buffer) == 0

    def is_full(self) -> bool:
        """Check if buffer is at capacity.

        Returns:
            True if buffer has reached capacity
        """
        return len(self.buffer) >= self.capacity

    def clear(self) -> None:
        """Clear all experiences from buffer."""
        self.buffer.clear()
        logger.debug("Cleared replay buffer")

    def get_average_reward(self) -> float:
        """Get average reward of experiences in buffer (advanced mode only).

        Returns:
            Average reward, or 0.0 if not in advanced mode or buffer is empty
        """
        if not self.enable_trajectory or len(self.buffer) == 0:
            return 0.0

        total_reward = sum(exp.get("reward", 0.0) for exp in self.buffer)
        return total_reward / len(self.buffer)

    def update_priorities(
        self,
        indices: list[int] | torch.Tensor,
        td_errors: torch.Tensor,
    ) -> None:
        """Update priorities based on TD-errors.

        This method updates the priority of experiences based on their
        temporal-difference errors, which indicates how "surprising"
        or informative the experience was.

        Args:
            indices: Indices of experiences to update
            td_errors: TD-error values for each experience

        Raises:
            ValueError: If prioritized replay is not enabled
        """
        if not self.prioritized:
            raise ValueError("Prioritized replay is not enabled")

        # Convert to list if tensor
        if isinstance(indices, torch.Tensor):
            indices = indices.tolist()

        if isinstance(td_errors, torch.Tensor):
            td_errors = td_errors.detach().cpu().numpy()

        # Update priorities
        for idx, td_error in zip(indices, td_errors):
            if 0 <= idx < len(self.buffer):
                # Priority = |TD-error| ^ alpha
                new_priority = abs(td_error) ** self.alpha
                self.buffer[idx]["priority"] = new_priority

        logger.debug(
            f"Updated priorities for {len(indices)} experiences "
            f"(avg TD-error: {abs(td_errors).mean():.4f})"
        )

    def get_episode(self, episode_id: str) -> list[dict]:
        """Get all experiences from a specific episode.

        Args:
            episode_id: Episode identifier

        Returns:
            List of experiences from the episode, or empty list if not found
        """
        if not self.enable_trajectory:
            return []

        episode_experiences = [
            exp for exp in self.buffer
            if exp.get("episode_id") == episode_id
        ]

        logger.debug(
            f"Retrieved episode {episode_id}: {len(episode_experiences)} experiences"
        )

        return episode_experiences

    def sample_episodes(self, num_episodes: int) -> list[list[dict]]:
        """Sample complete episodes from the buffer.

        This is useful for Monte Carlo learning methods that need
        complete trajectories.

        Args:
            num_episodes: Number of episodes to sample

        Returns:
            List of episodes, where each episode is a list of experiences

        Raises:
            ValueError: If num_episodes exceeds available episodes
        """
        if not self.enable_trajectory:
            raise ValueError("Episode sampling requires advanced mode")

        # Get all unique episode IDs
        episode_ids = list(set(
            exp.get("episode_id")
            for exp in self.buffer
            if exp.get("episode_id") is not None
        ))

        if len(episode_ids) < num_episodes:
            raise ValueError(
                f"Requested {num_episodes} episodes but only {len(episode_ids)} available"
            )

        # Sample episode IDs
        import random
        sampled_ids = random.sample(episode_ids, num_episodes)

        # Retrieve episodes
        episodes = [self.get_episode(eid) for eid in sampled_ids]

        logger.debug(
            f"Sampled {len(episodes)} episodes "
            f"(avg length: {sum(len(e) for e in episodes) / len(episodes):.1f})"
        )

        return episodes

    def get_td_errors(
        self,
        experiences: list[dict],
        model: "nn.Module",  # type: ignore
        gamma: float = 0.99,
    ) -> torch.Tensor:
        """Compute TD-errors for a batch of experiences.

        TD-error = |r + γ * V(s') - V(s)|
        Measures how much the value prediction was off.

        Args:
            experiences: List of experience dictionaries
            model: Neural network model for value prediction
            gamma: Discount factor

        Returns:
            Tensor of TD-errors for each experience
        """
        import torch.nn.functional as F

        td_errors = []

        for exp in experiences:
            state = exp["state"]
            reward = exp["reward"]
            next_state = exp.get("next_state")
            done = exp.get("done", False)

            # Get value prediction for current state
            with torch.no_grad():
                if hasattr(model, "policy_value_head"):
                    # Advanced mode: use policy-value head
                    if hasattr(model, "trajectory_encoder"):
                        # Encode trajectory if available
                        trajectory = exp.get("trajectory")
                        if trajectory is not None:
                            if trajectory.dim() == 1:
                                trajectory = trajectory.unsqueeze(0)
                            latent_z = model.trajectory_encoder(trajectory)
                            if latent_z.dim() == 1:
                                latent_z = latent_z.unsqueeze(0)
                        else:
                            latent_z = torch.zeros(1, model.trajectory_encoder.hidden_dim)

                        if state.dim() == 1:
                            state = state.unsqueeze(0)

                        output = model.policy_value_head(state, latent_z)
                        value_pred = output["value"]
                        if value_pred.dim() == 0:
                            value_pred = value_pred.unsqueeze(0)
                    else:
                        value_pred = torch.tensor([0.0])
                else:
                    # Basic mode: no value prediction
                    value_pred = torch.tensor([0.0])

                # Get value prediction for next state
                if next_state is not None and not done:
                    if hasattr(model, "policy_value_head"):
                        if next_state.dim() == 1:
                            next_state = next_state.unsqueeze(0)
                        # Use same latent z for simplicity
                        output_next = model.policy_value_head(next_state, latent_z)
                        next_value_pred = output_next["value"]
                        if next_value_pred.dim() == 0:
                            next_value_pred = next_value_pred.unsqueeze(0)
                    else:
                        next_value_pred = torch.tensor([0.0])
                else:
                    next_value_pred = torch.tensor([0.0])

            # Compute TD-error: |r + γ * V(s') - V(s)|
            td_target = reward + gamma * next_value_pred.item()
            td_error = abs(td_target - value_pred.item())

            td_errors.append(td_error)

        return torch.tensor(td_errors, dtype=torch.float32)

    def get_all_episode_ids(self) -> list[str]:
        """Get all unique episode IDs in the buffer.

        Returns:
            List of unique episode IDs
        """
        if not self.enable_trajectory:
            return []

        episode_ids = set()
        for exp in self.buffer:
            if exp.get("episode_id") is not None:
                episode_ids.add(exp["episode_id"])

        return sorted(list(episode_ids))

    def get_episode_count(self) -> int:
        """Get number of unique episodes in the buffer.

        Returns:
            Number of unique episodes
        """
        return len(self.get_all_episode_ids())

