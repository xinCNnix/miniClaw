"""Policy-value dual-head network for RL-based learning."""

import logging
from typing import TYPE_CHECKING

import torch
import torch.nn as nn

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PolicyValueHead(nn.Module):
    """Dual-head network for policy and value prediction.

    This network takes a state vector and a latent trajectory vector
    as input, and produces both:
    - Action logits (policy distribution over actions)
    - Value estimate (state value for RL)

    Architecture:
        State + Latent → Shared Backbone → Action Head (policy)
                                          → Value Head (value)

    Attributes:
        state_dim: State embedding dimension
        latent_dim: Latent trajectory vector dimension
        hidden_dim: Hidden layer dimension
        num_actions: Number of discrete actions
        dropout: Dropout rate
    """

    def __init__(
        self,
        state_dim: int = 384,
        latent_dim: int = 128,
        hidden_dim: int = 256,
        num_actions: int = 64,
        dropout: float = 0.1,
        # Meta policy extensions
        enable_meta_policy: bool = False,
        max_tool_slots: int = 20,
        max_skill_slots: int = 30,
    ) -> None:
        """Initialize PolicyValueHead.

        Args:
            state_dim: State embedding dimension (e.g., 384 for sentence embeddings)
            latent_dim: Latent trajectory vector dimension
            hidden_dim: Hidden layer dimension
            num_actions: Number of discrete action outputs
            dropout: Dropout rate for regularization
            enable_meta_policy: Enable tool/skill selection heads
            max_tool_slots: Maximum tool slots (current 6 + 14 reserved)
            max_skill_slots: Maximum skill slots (current 14 + 16 reserved)
        """
        super().__init__()

        self.state_dim = state_dim
        self.latent_dim = latent_dim
        self.hidden_dim = hidden_dim
        self.num_actions = num_actions
        self.enable_meta_policy = enable_meta_policy

        # Input dimension = state_dim + latent_dim
        input_dim = state_dim + latent_dim

        # Shared backbone network
        self.backbone = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
        )

        # Action head (policy) - outputs logits over discrete actions
        self.action_head = nn.Linear(hidden_dim, num_actions)

        # Value head - outputs scalar value estimate
        self.value_head = nn.Linear(hidden_dim, 1)

        # === Meta policy heads (tool/skill selection) ===
        if enable_meta_policy:
            self.tool_head = nn.Linear(hidden_dim, max_tool_slots)
            self.skill_head = nn.Linear(hidden_dim, max_skill_slots)
            self._max_tool_slots = max_tool_slots
            self._max_skill_slots = max_skill_slots

        logger.info(
            f"Initialized PolicyValueHead: state_dim={state_dim}, "
            f"latent_dim={latent_dim}, hidden_dim={hidden_dim}, "
            f"num_actions={num_actions}, enable_meta_policy={enable_meta_policy}"
        )

    def forward(
        self,
        state_vec: torch.Tensor,
        latent_z: torch.Tensor,
    ) -> dict[str, torch.Tensor]:
        """Forward pass through policy-value network.

        Args:
            state_vec: State vector of shape [B, state_dim] or [state_dim,]
            latent_z: Latent trajectory vector of shape [B, latent_dim] or [latent_dim,]

        Returns:
            Dictionary containing:
                - action_logits: [B, num_actions] or [num_actions,]
                - value: [B,] or scalar

        Raises:
            ValueError: If input dimensions don't match expected shapes
        """
        # Handle single sample input
        if state_vec.dim() == 1:
            state_vec = state_vec.unsqueeze(0)  # [state_dim,] -> [1, state_dim]
        if latent_z.dim() == 1:
            latent_z = latent_z.unsqueeze(0)  # [latent_dim,] -> [1, latent_dim]

        batch_size = state_vec.shape[0]

        # Validate dimensions
        if state_vec.shape[-1] != self.state_dim:
            raise ValueError(
                f"State dimension mismatch: expected {self.state_dim}, "
                f"got {state_vec.shape[-1]}"
            )

        if latent_z.shape[-1] != self.latent_dim:
            raise ValueError(
                f"Latent dimension mismatch: expected {self.latent_dim}, "
                f"got {latent_z.shape[-1]}"
            )

        # Concatenate state and latent vectors
        x = torch.cat([state_vec, latent_z], dim=-1)  # [B, state_dim + latent_dim]

        # Pass through shared backbone
        h = self.backbone(x)  # [B, hidden_dim]

        # Compute action logits and value
        action_logits = self.action_head(h)  # [B, num_actions]
        value = self.value_head(h).squeeze(-1)  # [B,]

        # Remove batch dimension if input was single sample
        if batch_size == 1:
            action_logits = action_logits.squeeze(0)
            value = value.squeeze(0)

        output = {
            "action_logits": action_logits,
            "value": value,
        }

        # Meta policy heads: tool and skill selection
        if self.enable_meta_policy:
            tool_logits = self.tool_head(h)  # [B, max_tool_slots]
            skill_logits = self.skill_head(h)  # [B, max_skill_slots]
            if batch_size == 1:
                tool_logits = tool_logits.squeeze(0)
                skill_logits = skill_logits.squeeze(0)
            output["tool_logits"] = tool_logits
            output["skill_logits"] = skill_logits

        return output

    def get_action_probs(
        self,
        state_vec: torch.Tensor,
        latent_z: torch.Tensor,
    ) -> torch.Tensor:
        """Get action probability distribution.

        Args:
            state_vec: State vector
            latent_z: Latent trajectory vector

        Returns:
            Action probabilities (softmax over logits)
        """
        with torch.no_grad():
            output = self.forward(state_vec, latent_z)
            action_logits = output["action_logits"]
            probs = torch.softmax(action_logits, dim=-1)
        return probs

    def get_value(
        self,
        state_vec: torch.Tensor,
        latent_z: torch.Tensor,
    ) -> torch.Tensor:
        """Get state value estimate.

        Args:
            state_vec: State vector
            latent_z: Latent trajectory vector

        Returns:
            State value estimate
        """
        with torch.no_grad():
            output = self.forward(state_vec, latent_z)
            value = output["value"]
        return value

    def get_num_parameters(self) -> int:
        """Get total number of trainable parameters.

        Returns:
            Number of trainable parameters
        """
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
