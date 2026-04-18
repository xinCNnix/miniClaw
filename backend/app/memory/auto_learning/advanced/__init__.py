"""Advanced pattern memory components for RL-based learning.

This package provides advanced components for reinforcement learning
on top of the base pattern memory system.
"""

from .models import Trajectory, TrainingMetrics, RLExperience
from .trajectory_encoder import TrajectoryEncoder
from .policy_head import PolicyValueHead
from .buffer import EnhancedReplayBuffer
from .rl_trainer import RLTrainer

__all__ = [
    # Models
    "Trajectory",
    "TrainingMetrics",
    "RLExperience",
    # Neural Components
    "TrajectoryEncoder",
    "PolicyValueHead",
    # Training Components
    "EnhancedReplayBuffer",
    "RLTrainer",
]

__version__ = "0.1.0"
