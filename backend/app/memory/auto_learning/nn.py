"""Pattern Neural Network implementation.

This module implements a lightweight neural network for pattern recognition
using PyTorch. The network uses experience replay for incremental training.

Supports two modes:
- Basic mode: Simple MLP for pattern classification (backward compatible)
- Advanced mode: Transformer encoder + policy-value head for RL training
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import torch
import torch.nn as nn
import torch.optim as optim

from app.config import get_settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PatternNN(nn.Module):
    """Lightweight neural network for pattern recognition.

    Supports two operating modes:
    - Basic mode: Simple MLP (backward compatible with original implementation)
    - Advanced mode: Transformer encoder + policy-value head for RL training

    Architecture:
        Basic: Input (embed_dim) → 256 → 128 → num_patterns
        Advanced: TrajectoryEncoder + PolicyValueHead (dual-head: action + value)

    The network supports incremental training through experience replay,
    allowing it to learn continuously without catastrophic forgetting.

    Attributes:
        embed_dim: Input embedding dimension
        num_patterns: Number of pattern output neurons
        enable_advanced: Whether advanced RL mode is enabled
        training_mode: Current training mode ("basic" or "advanced")
        basic_net: Basic MLP network (always present for backward compatibility)
        trajectory_encoder: Transformer encoder (advanced mode only)
        policy_value_head: Policy-value dual-head network (advanced mode only)
        optimizer: Adam optimizer for training
        criterion: Cross entropy loss function
        buffer: Experience replay buffer (basic or enhanced)
        buffer_size: Maximum size of replay buffer
        batch_size: Training batch size
    """

    def __init__(
        self,
        embed_dim: int = 384,
        num_patterns: int = 64,
        buffer_size: int = 500,
        batch_size: int = 32,
        learning_rate: float = 1e-3,
        dropout: float = 0.1,
        enable_advanced: bool = False,
    ) -> None:
        """Initialize PatternNN neural network.

        Args:
            embed_dim: Input embedding dimension (default: 384 for all-MiniLM-L6-v2)
            num_patterns: Number of output pattern neurons
            buffer_size: Maximum size of experience replay buffer
            batch_size: Batch size for incremental training
            learning_rate: Learning rate for Adam optimizer
            dropout: Dropout rate for regularization
            enable_advanced: Enable advanced RL mode (default: False for backward compatibility)
        """
        super().__init__()

        self.embed_dim = embed_dim
        self.num_patterns = num_patterns
        self.buffer_size = buffer_size
        self.batch_size = batch_size
        self.enable_advanced = enable_advanced
        self.training_mode = "basic" if not enable_advanced else "advanced"

        # === Basic mode network (always present for backward compatibility) ===
        # Network architecture: embed_dim -> 256 -> 128 -> num_patterns
        self.basic_net = nn.Sequential(
            nn.Linear(embed_dim, 256),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Linear(128, num_patterns),
        )

        # === Advanced mode components (only if enabled) ===
        if enable_advanced:
            # Import advanced components
            from app.memory.auto_learning.advanced.trajectory_encoder import TrajectoryEncoder
            from app.memory.auto_learning.advanced.policy_head import PolicyValueHead
            from app.memory.auto_learning.advanced.buffer import EnhancedReplayBuffer

            # Trajectory encoder for action sequences
            self.trajectory_encoder = TrajectoryEncoder(
                vocab_size=10000,
                hidden_dim=128,
                num_heads=4,
                num_layers=2,
                max_seq_len=128,
                dropout=dropout,
            )

            # Policy-value dual-head network
            self.policy_value_head = PolicyValueHead(
                state_dim=embed_dim,
                latent_dim=128,
                hidden_dim=256,
                num_actions=num_patterns,
                dropout=dropout,
            )

            # Enhanced replay buffer for advanced mode
            self.buffer = EnhancedReplayBuffer(
                capacity=buffer_size,
                enable_trajectory=True,
                prioritized=False,
            )

            # AgentModel wrapper for unified forward interface
            from app.memory.auto_learning.advanced.agent_model import AgentModel
            self.agent_model = AgentModel(self.trajectory_encoder, self.policy_value_head)
        else:
            # Simple buffer for basic mode (backward compatible)
            self.buffer: list[tuple[torch.Tensor, int]] = []

        # Optimizer and loss function (shared)
        self.optimizer = optim.Adam(self.parameters(), lr=learning_rate)
        self.criterion = nn.CrossEntropyLoss()

        logger.info(
            f"Initialized PatternNN: embed_dim={embed_dim}, "
            f"num_patterns={num_patterns}, buffer_size={buffer_size}, "
            f"batch_size={batch_size}, enable_advanced={enable_advanced}"
        )

    def forward(
        self,
        x: torch.Tensor,
        return_value: bool = False,
    ) -> torch.Tensor | dict[str, torch.Tensor]:
        """Forward pass through the network.

        Args:
            x: Input tensor of shape (batch_size, embed_dim) or (embed_dim,)
            return_value: If True and in advanced mode, return dict with action_logits and value

        Returns:
            Basic mode: Output logits of shape (batch_size, num_patterns)
            Advanced mode with return_value=False: Output logits
            Advanced mode with return_value=True: Dict with {"action_logits": ..., "value": ...}

        Raises:
            ValueError: If input dimension doesn't match embed_dim
        """
        if x.dim() == 1:
            # Single input: (embed_dim,) -> (1, embed_dim)
            x = x.unsqueeze(0)

        if x.shape[-1] != self.embed_dim:
            raise ValueError(
                f"Input dimension mismatch: expected {self.embed_dim}, got {x.shape[-1]}"
            )

        # Route to appropriate forward method based on mode
        if self.training_mode == "basic":
            return self.basic_net(x)
        else:
            # Advanced mode: use policy-value head
            # For simple forward, use zero latent vector
            latent_z = torch.zeros(x.shape[0], self.trajectory_encoder.hidden_dim, device=x.device)
            output = self.policy_value_head(x, latent_z)

            if return_value:
                return output
            else:
                # Backward compatible: return only action logits
                return output["action_logits"]

    def update(
        self,
        embedding: torch.Tensor,
        label: int,
        trajectory: torch.Tensor | None = None,
        reward: float | None = None,
    ) -> float:
        """Incremental training with experience replay.

        Adds the new experience to the buffer and performs a training step
        using a random batch from the replay buffer.

        Args:
            embedding: Input embedding tensor of shape (embed_dim,)
            label: Pattern label (integer in [0, num_patterns))
            trajectory: Action trajectory (advanced mode only)
            reward: Reward signal (advanced mode only)

        Returns:
            Loss value from the training step

        Raises:
            ValueError: If label is out of valid range
        """
        if not 0 <= label < self.num_patterns:
            raise ValueError(f"Label {label} out of range [0, {self.num_patterns})")

        # Route to appropriate update method based on mode
        if self.training_mode == "basic":
            return self._basic_update(embedding, label)
        else:
            return self._advanced_update(embedding, label, trajectory, reward)

    def _basic_update(self, embedding: torch.Tensor, label: int) -> float:
        """Basic mode update (backward compatible).

        Args:
            embedding: Input embedding tensor
            label: Pattern label

        Returns:
            Loss value from training step
        """
        # Add new experience to buffer
        self.buffer.append((embedding.clone().detach(), label))

        # Maintain buffer size limit (FIFO)
        if len(self.buffer) > self.buffer_size:
            self.buffer.pop(0)

        logger.debug(f"Added experience to buffer (size={len(self.buffer)}/{self.buffer_size})")

        # Train on a batch from replay buffer
        loss = self._train_step()
        return loss

    def _advanced_update(
        self,
        embedding: torch.Tensor,
        label: int,
        trajectory: torch.Tensor | None = None,
        reward: float | None = None,
    ) -> float:
        """Advanced mode update with RL training.

        Args:
            embedding: Input embedding tensor
            label: Pattern label (action)
            trajectory: Action trajectory
            reward: Reward signal

        Returns:
            Loss value from training step
        """
        # Add to enhanced buffer
        self.buffer.add(
            trajectory=trajectory if trajectory is not None else torch.tensor([]),
            state=embedding,
            action=label,
            reward=reward if reward is not None else 0.0,
        )

        logger.debug(f"Added experience to buffer (size={len(self.buffer)}/{self.buffer_size})")

        # Train using RL logic if reward and trajectory are provided
        if reward is not None and trajectory is not None:
            loss = self._rl_train_step(trajectory, embedding, label, reward)
        else:
            # Fallback to basic training
            loss = self._train_step()

        return loss

    def _rl_train_step(
        self,
        trajectory: torch.Tensor,
        state: torch.Tensor,
        action: int,
        reward: float,
    ) -> float:
        """Execute one RL training step.

        Args:
            trajectory: Action trajectory
            state: Current state
            action: Action taken
            reward: Reward received

        Returns:
            Total loss
        """
        import torch.nn.functional as F

        self.train()

        # Encode trajectory
        latent_z = self.trajectory_encoder(trajectory)

        # Forward pass
        output = self.policy_value_head(state, latent_z)
        action_logits = output["action_logits"]
        value_pred = output["value"]

        # Compute losses
        # Policy loss
        target = torch.tensor([action], dtype=torch.long, device=state.device)
        policy_loss = F.cross_entropy(action_logits.unsqueeze(0), target)

        # Value loss
        reward_tensor = torch.tensor([reward], dtype=torch.float32, device=value_pred.device)
        value_loss = F.mse_loss(value_pred.unsqueeze(0), reward_tensor)

        # REINFORCE loss
        log_prob = F.log_softmax(action_logits.unsqueeze(0), dim=-1)
        selected_log_prob = log_prob[0, action]
        advantage = reward - value_pred.item()
        reinforce_loss = -selected_log_prob * advantage

        # Entropy bonus
        probs = F.softmax(action_logits.unsqueeze(0), dim=-1)
        log_probs = F.log_softmax(action_logits.unsqueeze(0), dim=-1)
        entropy = -(probs * log_probs).sum()

        # Combined loss
        total_loss = (
            policy_loss * 1.0  # policy_loss_coef
            + value_loss * 0.5  # value_loss_coef
            + reinforce_loss * 0.1  # reinforce_coef
            - entropy * 0.01  # entropy_coef
        )

        # Backward pass
        self.optimizer.zero_grad()
        total_loss.backward()
        self.optimizer.step()

        return total_loss.item()

    def _train_step(self) -> float:
        """Perform one training step using replay buffer.

        Returns:
            Average loss over the training batch
        """
        if len(self.buffer) == 0:
            return 0.0

        # Sample batch from buffer
        batch_size = min(self.batch_size, len(self.buffer))
        indices = torch.randperm(len(self.buffer))[:batch_size]

        self.train()  # Set to training mode
        total_loss = 0.0

        for idx in indices:
            emb, label = self.buffer[idx]

            # Forward pass
            self.optimizer.zero_grad()
            pred = self.forward(emb.unsqueeze(0))

            # Compute loss
            target = torch.tensor([label], dtype=torch.long)
            loss = self.criterion(pred, target)

            # Backward pass
            loss.backward()
            self.optimizer.step()

            total_loss += loss.item()

        avg_loss = total_loss / batch_size
        logger.debug(f"Training step completed: avg_loss={avg_loss:.4f}")

        return avg_loss

    def save(self, path: str | Path | None = None) -> None:
        """Save network weights to disk using atomic write.

        Args:
            path: Path to save weights. If None, uses default from settings.

        Raises:
            IOError: If save operation fails
        """
        settings = get_settings()

        if path is None:
            path = settings.data_dir + "/pattern_nn.pth"
        else:
            path = Path(path)

        try:
            # Prepare save data
            save_data = {
                "state_dict": self.state_dict(),
                "embed_dim": self.embed_dim,
                "num_patterns": self.num_patterns,
                "enable_advanced": self.enable_advanced,
                "training_mode": self.training_mode,
            }

            # Atomic write: save to temp file first, then rename
            with tempfile.NamedTemporaryFile(
                mode="wb", delete=False, suffix=".pth", dir=Path(path).parent
            ) as tmp_file:
                temp_path = Path(tmp_file.name)

            # Save to temp file (use weights_only for PyTorch 2.1+, fallback for older versions)
            try:
                torch.save(save_data, temp_path, weights_only=True)
            except TypeError:
                # PyTorch < 2.1 doesn't support weights_only
                torch.save(save_data, temp_path)

            # Atomic rename
            temp_path.replace(path)

            logger.info(f"Saved PatternNN weights to {path} (mode={self.training_mode})")

        except Exception as e:
            logger.error(f"Failed to save PatternNN weights: {e}")
            raise IOError(f"Failed to save weights to {path}: {e}") from e

    def load(self, path: str | Path | None = None) -> None:
        """Load network weights from disk.

        Args:
            path: Path to load weights from. If None, uses default from settings.

        Raises:
            FileNotFoundError: If weights file doesn't exist
            RuntimeError: If loaded weights don't match network architecture
        """
        settings = get_settings()

        if path is None:
            path = settings.data_dir + "/pattern_nn.pth"
        else:
            path = Path(path)

        if not Path(path).exists():
            logger.warning(f"Weights file not found: {path}")
            raise FileNotFoundError(f"Weights file not found: {path}")

        try:
            # Load checkpoint
            try:
                checkpoint = torch.load(path, weights_only=True)
            except TypeError:
                # PyTorch < 2.1 doesn't support weights_only
                checkpoint = torch.load(path)

            # Handle both old format (state_dict only) and new format (with metadata)
            if isinstance(checkpoint, dict):
                if "state_dict" in checkpoint:
                    # New format with metadata
                    state_dict = checkpoint["state_dict"]
                    saved_mode = checkpoint.get("training_mode", "basic")
                    saved_advanced = checkpoint.get("enable_advanced", False)

                    # Verify mode compatibility
                    if saved_advanced != self.enable_advanced:
                        logger.warning(
                            f"Mode mismatch: saved={saved_mode}, current={self.training_mode}. "
                            f"Loading anyway but behavior may be unexpected."
                        )
                else:
                    # Old format (just state_dict)
                    state_dict = checkpoint
            else:
                # Very old format (raw state dict)
                state_dict = checkpoint

            self.load_state_dict(state_dict)
            logger.info(f"Loaded PatternNN weights from {path} (mode={self.training_mode})")

        except Exception as e:
            logger.error(f"Failed to load PatternNN weights: {e}")
            raise RuntimeError(f"Failed to load weights from {path}: {e}") from e

    def predict(self, embedding: torch.Tensor, top_k: int = 1) -> torch.Tensor:
        """Predict pattern index(es) for given embedding.

        Args:
            embedding: Input embedding tensor of shape (embed_dim,)
            top_k: Number of top predictions to return

        Returns:
            Tensor of top-k pattern indices

        Raises:
            ValueError: If top_k is invalid or input dimension is wrong
        """
        if top_k < 1 or top_k > self.num_patterns:
            raise ValueError(f"top_k must be in [1, {self.num_patterns}], got {top_k}")

        self.eval()  # Set to evaluation mode

        with torch.no_grad():
            logits = self.forward(embedding)

        if logits.shape[0] > 1:
            # Batch input: return top_k for each batch item
            top_indices = torch.topk(logits, k=min(top_k, logits.shape[1]), dim=1).indices
        else:
            # Single input: flatten result
            top_indices = torch.topk(logits[0], k=top_k).indices

        logger.debug(f"Predicted top-{top_k} patterns: {top_indices}")
        return top_indices

    def get_buffer_size(self) -> int:
        """Get current size of experience replay buffer.

        Returns:
            Current number of experiences in buffer
        """
        return len(self.buffer)

    def clear_buffer(self) -> None:
        """Clear all experiences from replay buffer."""
        self.buffer.clear()
        logger.debug("Cleared experience replay buffer")

    def set_learning_rate(self, lr: float) -> None:
        """Update learning rate for optimizer.

        Args:
            lr: New learning rate
        """
        for param_group in self.optimizer.param_groups:
            param_group["lr"] = lr
        logger.debug(f"Updated learning rate to {lr}")

    # === Advanced mode methods (only available when enable_advanced=True) ===

    def predict_with_value(
        self,
        embedding: torch.Tensor,
        trajectory: torch.Tensor | None = None,
    ) -> dict[str, torch.Tensor]:
        """Predict action logits and value (advanced mode only).

        Args:
            embedding: Input embedding tensor
            trajectory: Action trajectory (optional)

        Returns:
            Dictionary with {"action_logits": ..., "value": ...}

        Raises:
            RuntimeError: If called in basic mode
        """
        if self.training_mode != "advanced":
            raise RuntimeError("predict_with_value only available in advanced mode")

        self.eval()

        with torch.no_grad():
            # Encode trajectory if provided
            if trajectory is not None:
                latent_z = self.trajectory_encoder(trajectory)
            else:
                # Default latent vector
                latent_z = torch.zeros(1, self.trajectory_encoder.hidden_dim, device=embedding.device)

            # Get action logits and value
            output = self.policy_value_head(embedding, latent_z)

            return {
                "action_logits": output["action_logits"],
                "value": output["value"],
            }

    def set_training_mode(self, mode: str) -> None:
        """Switch between basic and advanced training modes.

        Args:
            mode: Either "basic" or "advanced"

        Raises:
            ValueError: If mode is invalid
            RuntimeError: If trying to switch to advanced mode when not enabled
        """
        if mode not in ["basic", "advanced"]:
            raise ValueError(f"Invalid mode: {mode}. Must be 'basic' or 'advanced'")

        if mode == "advanced" and not self.enable_advanced:
            raise RuntimeError("Cannot switch to advanced mode: enable_advanced=False")

        self.training_mode = mode
        logger.info(f"Switched training mode to: {mode}")


_pattern_nn_instance: "PatternNN | None" = None


def get_pattern_nn(**kwargs) -> "PatternNN | None":
    """Get PatternNN singleton (advanced mode) for RL pipeline.

    Returns None if initialization fails.
    """
    global _pattern_nn_instance
    if _pattern_nn_instance is None:
        try:
            from app.config import get_settings
            settings = get_settings()
            _pattern_nn_instance = PatternNN(
                embed_dim=kwargs.pop("embed_dim", settings.pattern_nn_embed_dim),
                num_patterns=kwargs.pop("num_patterns", settings.pattern_nn_num_patterns),
                enable_advanced=True,
                **kwargs,
            )
            from pathlib import Path
            nn_path = Path(settings.data_dir) / "pattern_nn.pth"
            if nn_path.exists():
                _pattern_nn_instance.load(str(nn_path))
        except Exception as e:
            logger.warning(f"PatternNN init failed: {e}")
            return None
    return _pattern_nn_instance


def reset_pattern_nn():
    """Reset the PatternNN singleton."""
    global _pattern_nn_instance
    _pattern_nn_instance = None
