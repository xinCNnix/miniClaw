"""Soft prompt generator: z → soft prompt embedding sequence."""

import torch
import torch.nn as nn


class PromptGenerator(nn.Module):
    """Map z vector to soft prompt embedding sequence.

    z [B, z_dim] → MLP → reshape → soft_prompt [B, prompt_len, hidden_dim]
    """

    def __init__(self, z_dim: int = 128, prompt_len: int = 10, hidden_dim: int = 128):
        super().__init__()
        self.prompt_len = prompt_len
        self.mlp = nn.Sequential(
            nn.Linear(z_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, prompt_len * hidden_dim),
        )

    def forward(self, z: torch.Tensor) -> torch.Tensor:
        """Generate soft prompt from latent z.

        Args:
            z: Latent vector of shape [B, z_dim]

        Returns:
            Soft prompt of shape [B, prompt_len, hidden_dim]
        """
        B = z.size(0)
        out = self.mlp(z)  # [B, prompt_len * hidden]
        return out.view(B, self.prompt_len, -1)  # [B, prompt_len, hidden]
