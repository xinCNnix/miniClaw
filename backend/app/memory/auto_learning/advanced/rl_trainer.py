"""Reinforcement learning trainer for pattern memory."""

import copy
import logging
from typing import TYPE_CHECKING

import torch
import torch.nn.functional as F
import torch.optim as optim

if TYPE_CHECKING:
    from app.memory.auto_learning.nn import PatternNN

logger = logging.getLogger(__name__)


class RLTrainer:
    """Reinforcement learning trainer for PatternNN.

    This trainer implements Policy Gradient + Value learning using:
    - Policy loss: Cross-entropy for action classification
    - Value loss: MSE for value prediction
    - REINFORCE loss: Policy gradient with advantage
    - Entropy bonus: Encourage exploration
    - KL loss: Prevent policy drift
    - Prompt consistency loss: Ensure action aligns with strategy

    Advanced features:
    - Target network for stable value learning
    - Separate optimizers for transformer and MLP components
    - Batch training with gradient clipping

    Attributes:
        model: PatternNN instance to train
        target_model: Target network for stable TD-learning
        gamma: Discount factor for future rewards
        entropy_coef: Coefficient for entropy regularization
        policy_loss_coef: Weight for policy loss
        value_loss_coef: Weight for value loss
        reinforce_coef: Weight for REINFORCE loss
        kl_coef: Weight for KL divergence loss
        prompt_consistency_coef: Weight for prompt consistency loss
        target_update_freq: Frequency of target network updates
        tau: Soft update coefficient for target network
        gradient_clip: Max norm for gradient clipping
    """

    def __init__(
        self,
        model: "PatternNN",
        gamma: float = 0.99,
        entropy_coef: float = 0.01,
        policy_loss_coef: float = 1.0,
        value_loss_coef: float = 0.5,
        reinforce_coef: float = 0.1,
        kl_coef: float = 0.01,
        prompt_consistency_coef: float = 0.05,
        target_update_freq: int = 100,
        tau: float = 0.005,
        transformer_lr: float = 1e-4,
        mlp_lr: float = 1e-3,
        gradient_clip: float = 1.0,
        enable_target_network: bool = True,
    ) -> None:
        """Initialize RLTrainer.

        Args:
            model: PatternNN instance to train
            gamma: Discount factor for future rewards (0-1)
            entropy_coef: Entropy bonus coefficient
            policy_loss_coef: Policy loss weight
            value_loss_coef: Value loss weight
            reinforce_coef: REINFORCE loss weight
            kl_coef: KL divergence loss weight
            prompt_consistency_coef: Prompt consistency loss weight
            target_update_freq: Update target network every N steps
            tau: Soft update coefficient (0-1)
            transformer_lr: Learning rate for transformer encoder
            mlp_lr: Learning rate for MLP head
            gradient_clip: Max gradient norm for clipping
            enable_target_network: Whether to use target network
        """
        self.model = model
        self.gamma = gamma
        self.entropy_coef = entropy_coef
        self.policy_loss_coef = policy_loss_coef
        self.value_loss_coef = value_loss_coef
        self.reinforce_coef = reinforce_coef
        self.kl_coef = kl_coef
        self.prompt_consistency_coef = prompt_consistency_coef
        self.target_update_freq = target_update_freq
        self.tau = tau
        self.gradient_clip = gradient_clip
        self.enable_target_network = enable_target_network

        # Training step counter
        self.training_step = 0

        # Create target network if enabled
        if enable_target_network and model.enable_advanced:
            self.target_model = copy.deepcopy(model)
            # Freeze target network parameters
            for param in self.target_model.parameters():
                param.requires_grad = False
            logger.debug("Target network created and frozen")
        else:
            self.target_model = None

        # Create separate optimizers for different components
        if model.enable_advanced:
            # Transformer encoder optimizer
            self.transformer_optimizer = optim.Adam(
                model.trajectory_encoder.parameters(),
                lr=transformer_lr,
            )
            # MLP head optimizer
            self.mlp_optimizer = optim.Adam(
                model.policy_value_head.parameters(),
                lr=mlp_lr,
            )
            logger.debug(
                f"Created separate optimizers: transformer_lr={transformer_lr}, "
                f"mlp_lr={mlp_lr}"
            )
        else:
            # Single optimizer for basic mode
            self.transformer_optimizer = None
            self.mlp_optimizer = model.optimizer
            logger.debug("Using single optimizer for basic mode")

        logger.info(
            f"Initialized RLTrainer: gamma={gamma}, "
            f"entropy_coef={entropy_coef}, policy_loss_coef={policy_loss_coef}, "
            f"value_loss_coef={value_loss_coef}, reinforce_coef={reinforce_coef}, "
            f"kl_coef={kl_coef}, prompt_consistency_coef={prompt_consistency_coef}, "
            f"target_update_freq={target_update_freq}, tau={tau}, "
            f"gradient_clip={gradient_clip}"
        )

    def train_step(
        self,
        trajectory: torch.Tensor,
        state: torch.Tensor,
        action: int,
        reward: float,
    ) -> float:
        """Execute one training step.

        Args:
            trajectory: Action trajectory tensor
            state: Current state embedding
            action: Action taken
            reward: Reward received

        Returns:
            Total loss value
        """
        self.model.train()

        # Forward pass with value prediction
        output = self._forward_with_value(state, trajectory)
        action_logits = output["action_logits"]
        value_pred = output["value"]

        # Compute individual losses
        policy_loss = self._compute_policy_loss(action_logits, action)
        value_loss = self._compute_value_loss(value_pred, reward)
        reinforce_loss = self._compute_reinforce_loss(
            action_logits, action, value_pred, reward
        )
        entropy = self._compute_entropy(action_logits)

        # Combine losses
        total_loss = (
            policy_loss * self.policy_loss_coef
            + value_loss * self.value_loss_coef
            + reinforce_loss * self.reinforce_coef
            - entropy * self.entropy_coef
        )

        # Backward pass
        self.model.optimizer.zero_grad()
        total_loss.backward()
        self.model.optimizer.step()

        logger.debug(
            f"Training step: total_loss={total_loss.item():.4f}, "
            f"policy={policy_loss.item():.4f}, value={value_loss.item():.4f}, "
            f"reinforce={reinforce_loss.item():.4f}, entropy={entropy.item():.4f}"
        )

        return total_loss.item()

    def _forward_with_value(
        self,
        state: torch.Tensor,
        trajectory: torch.Tensor | None = None,
    ) -> dict[str, torch.Tensor]:
        """Forward pass through model with value prediction.

        Args:
            state: State embedding
            trajectory: Action trajectory (optional)

        Returns:
            Dictionary with action_logits and value
        """
        # Encode trajectory if provided
        if trajectory is not None and self.model.enable_advanced:
            latent_z = self.model.trajectory_encoder(trajectory)
        else:
            # Default latent vector
            latent_z = torch.zeros(1, self.model.trajectory_encoder.hidden_dim)

        # Get action logits and value
        output = self.model.policy_value_head(state, latent_z)

        return output

    def _compute_policy_loss(
        self,
        action_logits: torch.Tensor,
        action: int,
    ) -> torch.Tensor:
        """Compute policy loss (cross-entropy).

        Args:
            action_logits: Action logits from model
            action: Ground truth action

        Returns:
            Policy loss tensor
        """
        target = torch.tensor([action], dtype=torch.long, device=action_logits.device)
        return F.cross_entropy(action_logits.unsqueeze(0), target)

    def _compute_value_loss(
        self,
        value_pred: torch.Tensor,
        reward: float,
    ) -> torch.Tensor:
        """Compute value loss (MSE).

        Args:
            value_pred: Predicted value
            reward: Actual reward

        Returns:
            Value loss tensor
        """
        target = torch.tensor([reward], dtype=torch.float32, device=value_pred.device)
        return F.mse_loss(value_pred.unsqueeze(0), target)

    def _compute_reinforce_loss(
        self,
        action_logits: torch.Tensor,
        action: int,
        value_pred: torch.Tensor,
        reward: float,
    ) -> torch.Tensor:
        """Compute REINFORCE loss with advantage.

        Args:
            action_logits: Action logits from model
            action: Action taken
            value_pred: Predicted value (for advantage)
            reward: Actual reward

        Returns:
            REINFORCE loss tensor
        """
        # Get log probability of taken action
        log_prob = F.log_softmax(action_logits.unsqueeze(0), dim=-1)
        selected_log_prob = log_prob[0, action]

        # Compute advantage = reward - baseline(value)
        advantage = reward - value_pred.item()

        # REINFORCE loss: -log_prob * advantage
        return -selected_log_prob * advantage

    def _compute_entropy(self, action_logits: torch.Tensor) -> torch.Tensor:
        """Compute entropy for exploration bonus.

        Args:
            action_logits: Action logits from model

        Returns:
            Entropy tensor
        """
        probs = F.softmax(action_logits.unsqueeze(0), dim=-1)
        log_probs = F.log_softmax(action_logits.unsqueeze(0), dim=-1)
        return -(probs * log_probs).sum()

    def compute_discounted_return(
        self,
        rewards: list[float],
    ) -> float:
        """Compute discounted return from reward sequence.

        Args:
            rewards: List of rewards

        Returns:
            Discounted return
        """
        total_return = 0.0
        for i, reward in enumerate(rewards):
            total_return += (self.gamma**i) * reward
        return total_return

    def compute_advantage(
        self,
        reward: float,
        value_pred: torch.Tensor,
    ) -> float:
        """Compute advantage estimate.

        Args:
            reward: Actual reward
            value_pred: Predicted value

        Returns:
            Advantage (reward - value)
        """
        return reward - value_pred.item()

    def _compute_kl_loss(
        self,
        action_logits: torch.Tensor,
        old_logits: torch.Tensor,
    ) -> torch.Tensor:
        """Compute KL divergence loss to prevent policy drift.

        Args:
            action_logits: Current policy logits
            old_logits: Old policy logits (from previous iteration)

        Returns:
            KL divergence loss tensor
        """
        # Compute KL divergence
        probs_old = F.softmax(old_logits, dim=-1)
        log_probs_new = F.log_softmax(action_logits, dim=-1)

        # KL = sum(p_old * log(p_old / p_new))
        kl_div = probs_old * (torch.log(probs_old + 1e-8) - log_probs_new)
        return kl_div.sum()

    def _compute_prompt_consistency_loss(
        self,
        action_logits: torch.Tensor,
        trajectory: torch.Tensor,
    ) -> torch.Tensor:
        """Compute prompt consistency loss.

        Ensures that the chosen action is consistent with the strategy
        suggested by the trajectory context.

        Args:
            action_logits: Action logits from model
            trajectory: Action trajectory (context)

        Returns:
            Prompt consistency loss tensor
        """
        # For now, use entropy as a proxy for consistency
        # Low entropy = high consistency with prompt
        # This can be enhanced with more sophisticated metrics
        entropy = self._compute_entropy(action_logits)
        return entropy

    def _update_target_network(self, method: str = "soft") -> None:
        """Update target network parameters.

        Args:
            method: "soft" for polyak averaging, "hard" for hard update
        """
        if self.target_model is None:
            return

        if method == "soft":
            # Soft update: θ_target = τ * θ_local + (1 - τ) * θ_target
            with torch.no_grad():
                for target_param, local_param in zip(
                    self.target_model.parameters(), self.model.parameters()
                ):
                    target_param.data.copy_(
                        self.tau * local_param.data + (1 - self.tau) * target_param.data
                    )
            logger.debug(f"Soft update target network (tau={self.tau})")

        elif method == "hard":
            # Hard update: θ_target = θ_local
            with torch.no_grad():
                for target_param, local_param in zip(
                    self.target_model.parameters(), self.model.parameters()
                ):
                    target_param.data.copy_(local_param.data)
            logger.debug("Hard update target network")

    def train_batch(self, batch: list[dict]) -> dict[str, float]:
        """Train on a batch of experiences.

        This method performs the full training loop:
        1. Forward pass for all experiences
        2. Compute all loss components
        3. Backward pass with gradient clipping
        4. Update both optimizers
        5. Update target network if needed

        Args:
            batch: List of experience dictionaries with keys:
                - trajectory: torch.Tensor
                - state: torch.Tensor
                - action: int
                - reward: float
                - next_state: torch.Tensor (optional)
                - done: bool

        Returns:
            Dictionary with training metrics:
                - total_loss: Average total loss
                - policy_loss: Average policy loss
                - value_loss: Average value loss
                - reinforce_loss: Average REINFORCE loss
                - kl_loss: Average KL loss (if applicable)
                - prompt_consistency_loss: Average prompt consistency loss
                - entropy: Average entropy
        """
        self.model.train()
        batch_size = len(batch)

        # Accumulate losses over the batch
        total_policy_loss = 0.0
        total_value_loss = 0.0
        total_reinforce_loss = 0.0
        total_kl_loss = 0.0
        total_prompt_consistency_loss = 0.0
        total_entropy = 0.0

        # Store loss tensors for backward pass
        policy_losses = []
        value_losses = []
        reinforce_losses = []
        kl_losses = []
        prompt_consistency_losses = []
        entropies = []

        # Forward pass for all experiences
        for exp in batch:
            trajectory = exp["trajectory"]
            state = exp["state"]
            action = exp["action"]
            reward = exp["reward"]

            # Forward pass
            output = self._forward_with_value(state, trajectory)
            action_logits = output["action_logits"]
            value_pred = output["value"]

            # Compute losses
            policy_loss = self._compute_policy_loss(action_logits, action)
            value_loss = self._compute_value_loss(value_pred, reward)
            reinforce_loss = self._compute_reinforce_loss(
                action_logits, action, value_pred, reward
            )
            entropy = self._compute_entropy(action_logits)

            # KL loss (if we have old logits - for now skip)
            kl_loss = torch.tensor(0.0, device=policy_loss.device)

            # Prompt consistency loss
            prompt_consistency_loss = self._compute_prompt_consistency_loss(
                action_logits, trajectory
            )

            # Store tensors
            policy_losses.append(policy_loss)
            value_losses.append(value_loss)
            reinforce_losses.append(reinforce_loss)
            kl_losses.append(kl_loss)
            prompt_consistency_losses.append(prompt_consistency_loss)
            entropies.append(entropy)

            # Accumulate for logging
            total_policy_loss += policy_loss.item()
            total_value_loss += value_loss.item()
            total_reinforce_loss += reinforce_loss.item()
            total_kl_loss += kl_loss.item()
            total_prompt_consistency_loss += prompt_consistency_loss.item()
            total_entropy += entropy.item()

        # Compute average losses (for logging)
        avg_policy_loss = total_policy_loss / batch_size
        avg_value_loss = total_value_loss / batch_size
        avg_reinforce_loss = total_reinforce_loss / batch_size
        avg_kl_loss = total_kl_loss / batch_size
        avg_prompt_consistency_loss = total_prompt_consistency_loss / batch_size
        avg_entropy = total_entropy / batch_size

        # Compute total loss as sum of all loss tensors (for backward pass)
        total_loss = (
            sum(policy_losses) * self.policy_loss_coef / batch_size
            + sum(value_losses) * self.value_loss_coef / batch_size
            + sum(reinforce_losses) * self.reinforce_coef / batch_size
            + sum(kl_losses) * self.kl_coef / batch_size
            + sum(prompt_consistency_losses) * self.prompt_consistency_coef / batch_size
            - sum(entropies) * self.entropy_coef / batch_size
        )

        # Backward pass
        if self.model.enable_advanced:
            # Zero gradients for both optimizers
            self.transformer_optimizer.zero_grad()
            self.mlp_optimizer.zero_grad()

            # Backward pass
            total_loss.backward()

            # Gradient clipping
            if self.gradient_clip > 0:
                torch.nn.utils.clip_grad_norm_(
                    self.model.parameters(), self.gradient_clip
                )

            # Update both optimizers
            self.transformer_optimizer.step()
            self.mlp_optimizer.step()
        else:
            # Single optimizer for basic mode
            self.mlp_optimizer.zero_grad()
            total_loss.backward()

            if self.gradient_clip > 0:
                torch.nn.utils.clip_grad_norm_(
                    self.model.parameters(), self.gradient_clip
                )

            self.mlp_optimizer.step()

        # Update target network
        self.training_step += 1
        if (
            self.enable_target_network
            and self.target_model is not None
            and self.training_step % self.target_update_freq == 0
        ):
            self._update_target_network(method="soft")

        # Log metrics
        logger.debug(
            f"Batch training (step={self.training_step}): "
            f"total_loss={total_loss.item():.4f}, "
            f"policy={avg_policy_loss:.4f}, value={avg_value_loss:.4f}, "
            f"reinforce={avg_reinforce_loss:.4f}, entropy={avg_entropy:.4f}"
        )

        return {
            "total_loss": total_loss.item(),
            "policy_loss": avg_policy_loss,
            "value_loss": avg_value_loss,
            "reinforce_loss": avg_reinforce_loss,
            "kl_loss": avg_kl_loss,
            "prompt_consistency_loss": avg_prompt_consistency_loss,
            "entropy": avg_entropy,
        }

