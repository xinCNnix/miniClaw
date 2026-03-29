"""AgentModel wrapper for unified neural network interface.

This module provides a unified wrapper around TrajectoryEncoder and PolicyValueHead
to simplify the RL training interface and provide batch processing capabilities.
"""

import logging
from typing import TYPE_CHECKING

import torch
import torch.nn as nn

if TYPE_CHECKING:
    from app.memory.auto_learning.advanced.policy_head import PolicyValueHead
    from app.memory.auto_learning.advanced.trajectory_encoder import TrajectoryEncoder

logger = logging.getLogger(__name__)


class AgentModel(nn.Module):
    """Unified wrapper for TrajectoryEncoder + PolicyValueHead.

    This class wraps the trajectory encoder and policy-value head into a single
    module with a simplified interface for RL training. It handles both single
    and batch inputs seamlessly.

    Architecture:
        token_ids [B, T] → TrajectoryEncoder → z [B, hidden_dim]
        state_vec [B, D] ─────────────────────────────┐
                                                      ↓
                                            PolicyValueHead
                                                      ↓
                                {action_logits [B, A], value [B, 1], z [B, H]}

    Attributes:
        trajectory_encoder: Transformer encoder for action sequences
        policy_value_head: Dual-head network for policy and value
        hidden_dim: Latent dimension from trajectory encoder
        device: Device where model is located
    """

    def __init__(
        self,
        trajectory_encoder: "TrajectoryEncoder",
        policy_value_head: "PolicyValueHead",
    ) -> None:
        """Initialize AgentModel wrapper.

        Args:
            trajectory_encoder: TrajectoryEncoder instance
            policy_value_head: PolicyValueHead instance

        Examples:
            >>> from app.memory.auto_learning.advanced.trajectory_encoder import TrajectoryEncoder
            >>> from app.memory.auto_learning.advanced.policy_head import PolicyValueHead
            >>> encoder = TrajectoryEncoder(vocab_size=10000, hidden_dim=128)
            >>> head = PolicyValueHead(state_dim=384, latent_dim=128, num_actions=20)
            >>> model = AgentModel(encoder, head)
            >>> output = model(torch.tensor([[1, 2, 3]]), torch.randn(1, 384))
        """
        super().__init__()

        self.trajectory_encoder = trajectory_encoder
        self.policy_value_head = policy_value_head
        self.hidden_dim = trajectory_encoder.hidden_dim
        self.device = next(self.parameters()).device

        logger.debug(
            f"AgentModel initialized: hidden_dim={self.hidden_dim}, "
            f"device={self.device}"
        )

    def forward(
        self,
        token_ids: torch.Tensor,
        state_vec: torch.Tensor,
    ) -> dict[str, torch.Tensor]:
        """Forward pass through the full model.

        This method handles both single samples and batches automatically.
        IMPORTANT: Output always preserves batch dimension for consistency.

        Args:
            token_ids: Action token IDs
                       - Single: [T,] or [1, T]
                       - Batch: [B, T]
            state_vec: State embedding vectors
                       - Single: [D,] or [1, D]
                       - Batch: [B, D]
                       where D is the state dimension (e.g., 384)

        Returns:
            Dictionary with (batch dimension ALWAYS preserved):
                - action_logits: [B, num_actions]
                - value: [B, 1]
                - z: [B, hidden_dim] (latent trajectory encoding)

        Raises:
            ValueError: If input dimensions are invalid

        Examples:
            >>> # Single sample
            >>> tokens = torch.tensor([1, 2, 3, 4, 5])
            >>> state = torch.randn(384)
            >>> output = model(tokens, state)
            >>> print(output["action_logits"].shape)  # [1, 20]
            >>> print(output["value"].shape)  # [1, 1]
            >>> print(output["z"].shape)  # [1, 128]

            >>> # Batch
            >>> tokens = torch.randint(0, 100, (32, 10))
            >>> states = torch.randn(32, 384)
            >>> output = model(tokens, states)
            >>> print(output["action_logits"].shape)  # [32, 20]
        """
        # Normalize input shapes
        token_ids = self._normalize_token_ids(token_ids)
        state_vec = self._normalize_state_vec(state_vec)

        batch_size = token_ids.shape[0]

        # Encode trajectory to latent vector z
        z = self.trajectory_encoder(token_ids)  # May be [hidden_dim,] for single sample

        # Ensure z has batch dimension
        if z.dim() == 1 and batch_size == 1:
            z = z.unsqueeze(0)  # [hidden_dim,] -> [1, hidden_dim]

        # Forward through policy-value head
        head_output = self.policy_value_head(state_vec, z)

        # Ensure batch dimension is preserved (PolicyValueHead may squeeze single samples)
        if batch_size == 1:
            if head_output["action_logits"].dim() == 1:
                head_output["action_logits"] = head_output["action_logits"].unsqueeze(0)
            if head_output["value"].dim() == 0:
                head_output["value"] = head_output["value"].unsqueeze(0).unsqueeze(-1)

        # Add latent vector to output (already has batch dim now)
        head_output["z"] = z

        logger.debug(
            f"AgentModel forward: batch_size={batch_size}, "
            f"action_logits={head_output['action_logits'].shape}, "
            f"value={head_output['value'].shape}, z={z.shape}"
        )

        return head_output

    def _normalize_token_ids(self, token_ids: torch.Tensor) -> torch.Tensor:
        """Normalize token_ids to batch format [B, T].

        Args:
            token_ids: Input tensor of various shapes

        Returns:
            Normalized tensor with shape [B, T] where B >= 1

        Raises:
            ValueError: If input has invalid number of dimensions
        """
        if token_ids.dim() == 1:
            # Single sequence: [T,] -> [1, T]
            return token_ids.unsqueeze(0)
        elif token_ids.dim() == 2:
            # Already batch format: [B, T]
            return token_ids
        else:
            raise ValueError(
                f"token_ids must be 1D or 2D, got {token_ids.dim()}D "
                f"with shape {token_ids.shape}"
            )

    def _normalize_state_vec(self, state_vec: torch.Tensor) -> torch.Tensor:
        """Normalize state_vec to batch format [B, D].

        Args:
            state_vec: Input tensor of various shapes

        Returns:
            Normalized tensor with shape [B, D] where B >= 1

        Raises:
            ValueError: If input has invalid number of dimensions
        """
        if state_vec.dim() == 1:
            # Single state: [D,] -> [1, D]
            return state_vec.unsqueeze(0)
        elif state_vec.dim() == 2:
            # Already batch format: [B, D]
            return state_vec
        else:
            raise ValueError(
                f"state_vec must be 1D or 2D, got {state_vec.dim()}D "
                f"with shape {state_vec.shape}"
            )

    def freeze_encoder(self) -> None:
        """Freeze trajectory encoder parameters.

        This prevents the encoder from being updated during training,
        which is useful for preventing catastrophic forgetting or
        when using pre-trained encoders.

        Examples:
            >>> model.freeze_encoder()
            >>> # Encoder parameters now have requires_grad=False
        """
        for param in self.trajectory_encoder.parameters():
            param.requires_grad = False
        logger.debug("TrajectoryEncoder frozen")

    def unfreeze_encoder(self) -> None:
        """Unfreeze trajectory encoder parameters.

        Allows the encoder to be updated during training.

        Examples:
            >>> model.unfreeze_encoder()
            >>> # Encoder parameters now have requires_grad=True
        """
        for param in self.trajectory_encoder.parameters():
            param.requires_grad = True
        logger.debug("TrajectoryEncoder unfrozen")

    def freeze_head(self) -> None:
        """Freeze policy-value head parameters.

        This prevents the head from being updated during training,
        which is useful for fine-tuning only the encoder.

        Examples:
            >>> model.freeze_head()
            >>> # Head parameters now have requires_grad=False
        """
        for param in self.policy_value_head.parameters():
            param.requires_grad = False
        logger.debug("PolicyValueHead frozen")

    def unfreeze_head(self) -> None:
        """Unfreeze policy-value head parameters.

        Allows the head to be updated during training.

        Examples:
            >>> model.unfreeze_head()
            >>> # Head parameters now have requires_grad=True
        """
        for param in self.policy_value_head.parameters():
            param.requires_grad = True
        logger.debug("PolicyValueHead unfrozen")

    def is_encoder_frozen(self) -> bool:
        """Check if encoder parameters are frozen.

        Returns:
            True if encoder is frozen, False otherwise
        """
        return all(not p.requires_grad for p in self.trajectory_encoder.parameters())

    def is_head_frozen(self) -> bool:
        """Check if head parameters are frozen.

        Returns:
            True if head is frozen, False otherwise
        """
        return all(not p.requires_grad for p in self.policy_value_head.parameters())

    def get_num_params(self) -> dict[str, int]:
        """Get number of trainable parameters in each component.

        Returns:
            Dictionary with parameter counts:
                - encoder: Number of encoder parameters
                - head: Number of head parameters
                - total: Total number of parameters

        Examples:
            >>> counts = model.get_num_params()
            >>> print(f"Encoder: {counts['encoder']}, Head: {counts['head']}")
        """
        encoder_params = sum(p.numel() for p in self.trajectory_encoder.parameters())
        head_params = sum(p.numel() for p in self.policy_value_head.parameters())
        total_params = encoder_params + head_params

        return {
            "encoder": encoder_params,
            "head": head_params,
            "total": total_params,
        }

    def get_trainable_params(self) -> dict[str, int]:
        """Get number of trainable (non-frozen) parameters.

        Returns:
            Dictionary with trainable parameter counts

        Examples:
            >>> trainable = model.get_trainable_params()
            >>> print(f"Trainable: {trainable['total']}")
        """
        encoder_trainable = sum(
            p.numel() for p in self.trajectory_encoder.parameters() if p.requires_grad
        )
        head_trainable = sum(
            p.numel() for p in self.policy_value_head.parameters() if p.requires_grad
        )
        total_trainable = encoder_trainable + head_trainable

        return {
            "encoder": encoder_trainable,
            "head": head_trainable,
            "total": total_trainable,
        }
