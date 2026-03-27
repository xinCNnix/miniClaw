"""Transformer-based trajectory encoder for action sequences."""

import logging
from typing import TYPE_CHECKING

import torch
import torch.nn as nn

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class TrajectoryEncoder(nn.Module):
    """Transformer-based encoder for action sequences.

    This encoder processes sequences of action/tool tokens and produces
    a fixed-length latent representation using a Transformer architecture
    with CLS token pooling.

    Architecture:
        Token Embedding → Positional Encoding → Transformer Encoder → CLS Token

    Attributes:
        vocab_size: Size of action/tool vocabulary
        hidden_dim: Hidden dimension for Transformer
        num_heads: Number of attention heads
        num_layers: Number of Transformer layers
        max_seq_len: Maximum sequence length
        dropout: Dropout rate
    """

    def __init__(
        self,
        vocab_size: int = 10000,
        hidden_dim: int = 128,
        num_heads: int = 4,
        num_layers: int = 2,
        max_seq_len: int = 128,
        dropout: float = 0.1,
    ) -> None:
        """Initialize TrajectoryEncoder.

        Args:
            vocab_size: Size of action/tool vocabulary
            hidden_dim: Hidden dimension for Transformer
            num_heads: Number of attention heads (must divide hidden_dim)
            num_layers: Number of Transformer layers
            max_seq_len: Maximum sequence length
            dropout: Dropout rate for regularization
        """
        super().__init__()

        self.vocab_size = vocab_size
        self.hidden_dim = hidden_dim
        self.num_heads = num_heads
        self.num_layers = num_layers
        self.max_seq_len = max_seq_len

        # Token embedding layer
        self.token_emb = nn.Embedding(vocab_size, hidden_dim)

        # Positional encoding (learned)
        self.pos_emb = nn.Embedding(max_seq_len, hidden_dim)

        # Transformer encoder layer
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=num_heads,
            dim_feedforward=hidden_dim * 4,
            dropout=dropout,
            batch_first=True,
        )

        # Stack encoder layers
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers)

        # Learnable CLS token (used for sequence pooling)
        self.cls_token = nn.Parameter(torch.randn(1, 1, hidden_dim))

        logger.info(
            f"Initialized TrajectoryEncoder: vocab_size={vocab_size}, "
            f"hidden_dim={hidden_dim}, num_heads={num_heads}, "
            f"num_layers={num_layers}, max_seq_len={max_seq_len}"
        )

    def forward(self, token_ids: torch.Tensor) -> torch.Tensor:
        """Encode trajectory to latent vector.

        Args:
            token_ids: Input token IDs of shape [B, T] or [T,]
                where B is batch size and T is sequence length

        Returns:
            Latent vector z of shape [B, hidden_dim] or [hidden_dim,]
                representing the encoded trajectory (CLS token output)

        Raises:
            ValueError: If sequence length exceeds max_seq_len
        """
        # Handle single sequence input
        if token_ids.dim() == 1:
            token_ids = token_ids.unsqueeze(0)  # [T,] -> [1, T]

        batch_size, seq_len = token_ids.shape

        # Validate sequence length
        if seq_len > self.max_seq_len:
            raise ValueError(
                f"Sequence length {seq_len} exceeds max_seq_len {self.max_seq_len}"
            )

        # Create embeddings
        # Token embeddings: [B, T, hidden_dim]
        token_emb = self.token_emb(token_ids)

        # Positional encoding: [1, T, hidden_dim]
        positions = torch.arange(seq_len, device=token_ids.device).unsqueeze(0)
        pos_emb = self.pos_emb(positions)

        # Combine embeddings: [B, T, hidden_dim]
        x = token_emb + pos_emb

        # Prepend CLS token: [B, 1, hidden_dim]
        cls_tokens = self.cls_token.expand(batch_size, -1, -1)
        x = torch.cat([cls_tokens, x], dim=1)  # [B, T+1, hidden_dim]

        # Transformer encoding: [B, T+1, hidden_dim]
        out = self.transformer(x)

        # Extract CLS token output: [B, hidden_dim]
        z = out[:, 0, :]

        # Remove batch dimension if input was single sequence
        if batch_size == 1:
            z = z.squeeze(0)  # [1, hidden_dim] -> [hidden_dim,]

        return z

    def freeze(self) -> None:
        """Freeze all parameters (for transfer learning)."""
        for param in self.parameters():
            param.requires_grad = False
        logger.debug("Froze TrajectoryEncoder parameters")

    def unfreeze(self) -> None:
        """Unfreeze all parameters."""
        for param in self.parameters():
            param.requires_grad = True
        logger.debug("Unfroze TrajectoryEncoder parameters")

    def get_num_parameters(self) -> int:
        """Get total number of trainable parameters.

        Returns:
            Number of trainable parameters
        """
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
