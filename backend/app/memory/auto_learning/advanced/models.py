"""Data models for advanced RL-based pattern learning."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Trajectory(BaseModel):
    """Agent execution trajectory for RL training.

    A trajectory represents a sequence of actions taken by the agent,
    along with their associated observations and rewards.

    Attributes:
        token_ids: Sequence of action/tool token IDs
        rewards: Reward at each timestep
        actions: Action indices at each timestep
        length: Length of trajectory
        episode_id: Unique identifier for episode
    """

    token_ids: list[int] = Field(default_factory=list, description="Action token sequence")
    rewards: list[float] = Field(default_factory=list, description="Rewards per timestep")
    actions: list[int] = Field(default_factory=list, description="Action indices")
    length: int = Field(default=0, description="Trajectory length")
    episode_id: str | None = Field(default=None, description="Episode identifier")

    def __len__(self) -> int:
        """Get trajectory length."""
        return self.length

    def add_step(self, token_id: int, reward: float, action: int) -> None:
        """Add a step to the trajectory.

        Args:
            token_id: Action/tool token ID
            reward: Reward received
            action: Action index
        """
        self.token_ids.append(token_id)
        self.rewards.append(reward)
        self.actions.append(action)
        self.length += 1

    def get_return(self) -> float:
        """Get total return (sum of rewards).

        Returns:
            Total discounted return
        """
        return sum(self.rewards)


class TrainingMetrics(BaseModel):
    """Training metrics for RL training.

    Attributes:
        episode: Episode number
        total_loss: Total combined loss
        policy_loss: Policy gradient loss
        value_loss: Value function loss
        reinforce_loss: REINFORCE loss
        entropy: Entropy bonus
        reward: Episode reward
        episode_length: Number of steps in episode
        timestamp: When metrics were recorded
    """

    episode: int = Field(description="Episode number")
    total_loss: float = Field(description="Total training loss")
    policy_loss: float | None = Field(default=None, description="Policy loss")
    value_loss: float | None = Field(default=None, description="Value loss")
    reinforce_loss: float | None = Field(default=None, description="REINFORCE loss")
    entropy: float | None = Field(default=None, description="Entropy bonus")
    reward: float = Field(description="Episode total reward")
    episode_length: int = Field(description="Steps in episode")
    timestamp: datetime = Field(default_factory=datetime.now, description="Timestamp")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging.

        Returns:
            Dictionary representation of metrics
        """
        return {
            "episode": self.episode,
            "total_loss": self.total_loss,
            "policy_loss": self.policy_loss,
            "value_loss": self.value_loss,
            "reinforce_loss": self.reinforce_loss,
            "entropy": self.entropy,
            "reward": self.reward,
            "episode_length": self.episode_length,
            "timestamp": self.timestamp.isoformat(),
        }


class RLExperience(BaseModel):
    """Single RL experience for replay buffer.

    Represents a state-action-reward-next_state tuple for RL training.

    Attributes:
        state: Current state embedding
        action: Action taken
        reward: Reward received
        next_state: Next state embedding (optional)
        done: Whether episode terminated
        trajectory: Full trajectory (optional, for advanced training)
        priority: Priority score for prioritized replay (optional)
        timestamp: When experience was recorded
    """

    state: list[float] = Field(description="State embedding")
    action: int = Field(description="Action taken")
    reward: float = Field(description="Reward received")
    next_state: list[float] | None = Field(default=None, description="Next state")
    done: bool = Field(default=False, description="Episode terminated")
    trajectory: Trajectory | None = Field(default=None, description="Full trajectory")
    priority: float | None = Field(default=None, description="Priority score")
    timestamp: datetime = Field(default_factory=datetime.now, description="Timestamp")

    def __hash__(self) -> int:
        """Make experience hashable for set operations."""
        return hash((tuple(self.state), self.action, self.reward, self.done))
