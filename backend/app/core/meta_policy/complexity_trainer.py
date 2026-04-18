"""TCA 训练器 — 管理 Task Complexity Analyzer 的训练和渐进部署。

4阶段部署:
1. 数据收集期 (0-200 次): TCA 不参与决策，仅收集训练数据
2. Shadow 模式 (200-500 次): TCA 分析但不影响执行，仅记录差异
3. 混合决策 (500-1000 次): 50% 概率使用 TCA 决策
4. TCA 主导 (1000+ 次): 80%+ 使用 TCA 决策
"""

import json
import logging
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

import torch
from torch.optim import Adam

from app.core.meta_policy.task_complexity import TaskComplexityAnalyzer

logger = logging.getLogger(__name__)

# 阶段配置
DEPLOYMENT_PHASES = {
    "collection": {"min_episodes": 0, "max_episodes": 200, "inject_ratio": 0.0},
    "shadow": {"min_episodes": 200, "max_episodes": 500, "inject_ratio": 0.0},
    "mixed": {"min_episodes": 500, "max_episodes": 1000, "inject_ratio": 0.5},
    "dominant": {"min_episodes": 1000, "max_episodes": float("inf"), "inject_ratio": 0.8},
}


class ComplexityTrainer:
    """TCA 训练器 — 管理训练、数据收集和渐进部署。"""

    def __init__(
        self,
        model: TaskComplexityAnalyzer,
        learning_rate: float = 5e-4,
        gradient_clip: float = 1.0,
        training_data_dir: str = "data/complexity_training",
    ) -> None:
        self.model = model
        self.optimizer = Adam(model.parameters(), lr=learning_rate)
        self.gradient_clip = gradient_clip
        self.training_data_dir = Path(training_data_dir)

        self._episode_count = 0
        self._training_data: List[Dict[str, Any]] = []
        self._batch_size = 16

        # 尝试加载已有模型
        self._try_load_model()
        self._try_load_episode_count()

    def _try_load_model(self) -> None:
        """尝试从磁盘加载模型。"""
        try:
            loaded = self.model.load()
            if loaded:
                logger.info("[TCA Trainer] Loaded existing model")
        except Exception as e:
            logger.debug("[TCA Trainer] Could not load model: %s", e)

    def _try_load_episode_count(self) -> None:
        """尝试从磁盘加载 episode 计数。"""
        counter_path = self.training_data_dir / "episode_count.json"
        if counter_path.exists():
            try:
                with open(counter_path) as f:
                    data = json.load(f)
                    self._episode_count = data.get("count", 0)
                logger.info("[TCA Trainer] Loaded episode count: %d", self._episode_count)
            except Exception:
                pass

    def _save_episode_count(self) -> None:
        """持久化 episode 计数。"""
        self.training_data_dir.mkdir(parents=True, exist_ok=True)
        counter_path = self.training_data_dir / "episode_count.json"
        try:
            with open(counter_path, "w") as f:
                json.dump({"count": self._episode_count}, f)
        except Exception as e:
            logger.debug("[TCA Trainer] Failed to save episode count: %s", e)

    def record_episode(
        self,
        task_emb: torch.Tensor,
        decompose_label: int,
        complexity_label: int,
        subtask_count_label: int,
        capability_label: Optional[torch.Tensor] = None,
        ctx_emb: Optional[torch.Tensor] = None,
        tool_embs: Optional[torch.Tensor] = None,
        skill_embs: Optional[torch.Tensor] = None,
    ) -> None:
        """记录训练数据。从 PERV/ToT 执行日志提取标签后调用。

        Args:
            task_emb: 任务嵌入
            decompose_label: 0=不分解, 1=分解
            complexity_label: 0=low, 1=medium, 2=high
            subtask_count_label: 0-4 (实际子任务数 - 1)
            capability_label: multi-hot tensor [total_capability_slots]
            ctx_emb: 上下文嵌入 (可选)
            tool_embs: 工具嵌入 (可选)
            skill_embs: 技能嵌入 (可选)
        """
        episode = {
            "task_emb": task_emb.detach().cpu(),
            "decompose_label": decompose_label,
            "complexity_label": complexity_label,
            "subtask_count_label": subtask_count_label,
        }

        if capability_label is not None:
            episode["capability_label"] = capability_label.detach().cpu()
        else:
            total_slots = self.model.max_tool_slots + self.model.max_skill_slots
            episode["capability_label"] = torch.zeros(total_slots)

        if ctx_emb is not None:
            episode["ctx_emb"] = ctx_emb.detach().cpu()
        if tool_embs is not None:
            episode["tool_embs"] = tool_embs.detach().cpu()
        if skill_embs is not None:
            episode["skill_embs"] = skill_embs.detach().cpu()

        self._training_data.append(episode)
        self._episode_count += 1
        self._save_episode_count()

        # Shadow 模式下记录预测 vs 实际
        phase = self.get_deployment_phase()
        if phase == "shadow":
            self._log_shadow_prediction(task_emb, decompose_label, episode)

        # 数据积累足够时触发训练
        if len(self._training_data) >= self._batch_size * 4:
            self._try_train()

    def _log_shadow_prediction(
        self, task_emb: torch.Tensor, actual_label: int, episode: Dict
    ) -> None:
        """Shadow 模式: 记录预测 vs 实际。"""
        try:
            self.model.eval()
            output = self.model(task_emb.unsqueeze(0) if task_emb.dim() == 1 else task_emb)
            predicted = output["decompose_logits"][0].argmax().item()
            match = predicted == actual_label
            logger.debug(
                "[TCA Shadow] predicted=%d, actual=%d, match=%s",
                predicted, actual_label, match,
            )
        except Exception as e:
            logger.debug("[TCA Shadow] prediction failed: %s", e)

    def _try_train(self) -> None:
        """尝试从缓存数据训练一步。"""
        if len(self._training_data) < self._batch_size:
            return

        try:
            batch = self._training_data[:self._batch_size]
            self._training_data = self._training_data[self._batch_size:]

            losses = self.train_step(batch)
            if losses:
                logger.debug(
                    "[TCA Train] total_loss=%.4f, decompose=%.4f",
                    losses["total_loss"],
                    losses.get("decompose_loss", 0),
                )

                # 训练后保存模型
                self.model.save()

        except Exception as e:
            logger.warning("[TCA Train] Training step failed: %s", e)

    def train_step(self, batch: List[Dict[str, Any]]) -> Dict[str, float]:
        """单步训练。

        Args:
            batch: list of episode dicts from record_episode()

        Returns:
            dict with loss values
        """
        self.model.train()

        # 组装 batch tensors
        task_embs = torch.stack([e["task_emb"] for e in batch])
        decompose_labels = torch.tensor(
            [e["decompose_label"] for e in batch], dtype=torch.long
        )
        complexity_labels = torch.tensor(
            [e["complexity_label"] for e in batch], dtype=torch.long
        )
        subtask_count_labels = torch.tensor(
            [e["subtask_count_label"] for e in batch], dtype=torch.long
        )
        capability_labels = torch.stack([e["capability_label"] for e in batch])

        # 可选输入
        ctx_emb = None
        if "ctx_emb" in batch[0]:
            ctx_emb = torch.stack([e["ctx_emb"] for e in batch])

        # Forward
        predictions = self.model(task_embs, ctx_emb)

        # Compute loss
        targets = {
            "decompose_label": decompose_labels,
            "complexity_label": complexity_labels,
            "subtask_count_label": subtask_count_labels,
            "capability_label": capability_labels,
        }
        losses = self.model.compute_loss(predictions, targets)

        # Backward
        self.optimizer.zero_grad()
        losses["total_loss"].backward()

        # Gradient clipping
        if self.gradient_clip > 0:
            torch.nn.utils.clip_grad_norm_(
                self.model.parameters(), self.gradient_clip
            )

        self.optimizer.step()

        return {k: v.item() if isinstance(v, torch.Tensor) else v for k, v in losses.items()}

    @property
    def episode_count(self) -> int:
        """已记录的 episode 总数。"""
        return self._episode_count

    def get_deployment_phase(self) -> str:
        """获取当前部署阶段。"""
        for phase_name, config in DEPLOYMENT_PHASES.items():
            if self._episode_count < config["max_episodes"]:
                return phase_name
        return "dominant"

    def should_inject(self) -> bool:
        """当前是否应注入 TCA 决策到执行路径。"""
        phase = self.get_deployment_phase()
        config = DEPLOYMENT_PHASES[phase]
        inject_ratio = config["inject_ratio"]

        if inject_ratio <= 0:
            return False
        return random.random() < inject_ratio


# === Singleton ===

_tca_trainer: Optional[ComplexityTrainer] = None


def get_tca_trainer() -> ComplexityTrainer:
    """获取全局 TCA 训练器单例。"""
    global _tca_trainer
    if _tca_trainer is None:
        from app.config import get_settings
        settings = get_settings()

        model = TaskComplexityAnalyzer(
            embed_dim=settings.tca_embed_dim,
            hidden_dim=settings.tca_hidden_dim,
            num_heads=settings.tca_num_heads,
            num_layers=settings.tca_num_layers,
            max_tool_slots=getattr(settings, "meta_policy_max_tool_slots", 20),
            max_skill_slots=getattr(settings, "meta_policy_max_skill_slots", 30),
            max_subtasks=settings.tca_max_subtasks,
        )

        _tca_trainer = ComplexityTrainer(
            model=model,
            learning_rate=settings.tca_learning_rate,
            training_data_dir=settings.tca_training_data_dir,
        )

    return _tca_trainer


def reset_tca_trainer() -> None:
    """重置 TCA 训练器单例。"""
    global _tca_trainer
    _tca_trainer = None
