"""Task Complexity Analyzer (TCA) — 任务分解决策网络。

TCA 使用 Transformer Encoder 分析任务复杂度，输出：
- 是否需要分解 (decompose_head)
- 复杂度级别 (complexity_head): low / medium / high
- 建议子任务数 (subtask_count_head): 1-5
- 涉及的能力建议 (capability_hint_head): multi-hot over tool+skill slots

TCA 只提供决策指导信号，具体分解由 LLM 完成。
"""

import logging
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# 特殊 token ID
CLS_TOKEN_ID = 0
CTX_TOKEN_ID = 1
SEP_TOKEN_ID = 2
TOOL_PREFIX_ID = 3
SKILL_PREFIX_ID = 4
# 实际内容 token 从 5 开始
CONTENT_TOKEN_OFFSET = 5

MAX_SEQ_LEN = 64


class DecompositionDecision(BaseModel):
    """TCA 分解决策结果。"""

    should_decompose: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    complexity: str = "low"
    suggested_subtask_count: int = Field(default=1, ge=1, le=5)
    capability_hints: List[str] = Field(default_factory=list)
    injection_text: str = ""

    @field_validator("complexity")
    @classmethod
    def validate_complexity(cls, v: str) -> str:
        if v not in ("low", "medium", "high"):
            raise ValueError(f"complexity must be low/medium/high, got {v}")
        return v


class TaskComplexityAnalyzer(nn.Module):
    """Task Complexity Analyzer — Transformer Encoder 网络。

    输入序列: [CLS] + task_emb + [CTX] + ctx_emb + [TOOL] + tool_embs + [SKILL] + skill_embs + [SEP]
    取 [CLS] 输出接各输出头。
    """

    def __init__(
        self,
        embed_dim: int = 384,
        hidden_dim: int = 256,
        num_heads: int = 4,
        num_layers: int = 4,
        max_tool_slots: int = 20,
        max_skill_slots: int = 30,
        max_subtasks: int = 5,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()

        self.embed_dim = embed_dim
        self.hidden_dim = hidden_dim
        self.num_heads = num_heads
        self.num_layers = num_layers
        self.max_tool_slots = max_tool_slots
        self.max_skill_slots = max_skill_slots
        self.max_subtasks = max_subtasks
        self.total_capability_slots = max_tool_slots + max_skill_slots

        # 输入投影: embed_dim -> hidden_dim
        self.input_proj = nn.Linear(embed_dim, hidden_dim)

        # 位置编码: learned
        self.position_embedding = nn.Embedding(MAX_SEQ_LEN, hidden_dim)

        # 特殊 token embedding (5 个特殊 token)
        self.special_token_embedding = nn.Embedding(CONTENT_TOKEN_OFFSET, hidden_dim)

        # Transformer Encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=num_heads,
            dim_feedforward=hidden_dim * 2,
            dropout=dropout,
            activation="gelu",
            batch_first=True,
        )
        self.transformer_encoder = nn.TransformerEncoder(
            encoder_layer,
            num_layers=num_layers,
        )

        # Layer Norm
        self.layer_norm = nn.LayerNorm(hidden_dim)

        # 输出头
        self.decompose_head = nn.Linear(hidden_dim, 2)
        self.complexity_head = nn.Linear(hidden_dim, 3)
        self.subtask_count_head = nn.Linear(hidden_dim, max_subtasks)
        self.capability_hint_head = nn.Linear(hidden_dim, self.total_capability_slots)

        self._init_weights()

    def _init_weights(self) -> None:
        """Xavier 初始化。"""
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.xavier_uniform_(module.weight)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
            elif isinstance(module, nn.Embedding):
                nn.init.normal_(module.weight, std=0.02)

    def _build_input_sequence(
        self,
        task_emb: torch.Tensor,
        ctx_emb: Optional[torch.Tensor] = None,
        tool_embs: Optional[torch.Tensor] = None,
        skill_embs: Optional[torch.Tensor] = None,
    ) -> tuple:
        """构建 Transformer 输入序列。

        Returns:
            (sequence, attention_mask) — shape [B, seq_len, hidden_dim] and [B, seq_len]
        """
        batch_size = task_emb.shape[0] if task_emb.dim() > 1 else 1

        # 投影到 hidden_dim
        task_proj = self.input_proj(task_emb)  # [B, hidden_dim] or [hidden_dim]

        if task_proj.dim() == 1:
            task_proj = task_proj.unsqueeze(0)  # [1, hidden_dim]
        batch_size = task_proj.shape[0]

        # 特殊 tokens
        cls_emb = self.special_token_embedding(
            torch.tensor([CLS_TOKEN_ID], device=task_proj.device)
        ).unsqueeze(0).expand(batch_size, -1, -1)  # [B, 1, hidden_dim]

        sep_emb = self.special_token_embedding(
            torch.tensor([SEP_TOKEN_ID], device=task_proj.device)
        ).unsqueeze(0).expand(batch_size, -1, -1)  # [B, 1, hidden_dim]

        tokens = [cls_emb, task_proj.unsqueeze(1)]  # [CLS], [TASK]

        # [CTX] + ctx_emb
        if ctx_emb is not None:
            ctx_proj = self.input_proj(ctx_emb)
            if ctx_proj.dim() == 1:
                ctx_proj = ctx_proj.unsqueeze(0)
            ctx_token = self.special_token_embedding(
                torch.tensor([CTX_TOKEN_ID], device=task_proj.device)
            ).unsqueeze(0).expand(batch_size, -1, -1)
            tokens.append(ctx_token)
            tokens.append(ctx_proj.unsqueeze(1))

        # [TOOL] + tool_embs
        if tool_embs is not None and tool_embs.numel() > 0:
            tool_proj = self.input_proj(tool_embs)  # [N, hidden_dim]
            if tool_proj.dim() == 1:
                tool_proj = tool_proj.unsqueeze(0)
            # tool_proj: [N, hidden_dim] → expand to [B, N, hidden_dim]
            tool_proj_batch = tool_proj.unsqueeze(0).expand(batch_size, -1, -1)
            tool_token = self.special_token_embedding(
                torch.tensor([TOOL_PREFIX_ID], device=task_proj.device)
            ).unsqueeze(0).expand(batch_size, -1, -1)
            tokens.append(tool_token)
            tokens.append(tool_proj_batch)

        # [SKILL] + skill_embs
        if skill_embs is not None and skill_embs.numel() > 0:
            skill_proj = self.input_proj(skill_embs)  # [M, hidden_dim]
            if skill_proj.dim() == 1:
                skill_proj = skill_proj.unsqueeze(0)
            # skill_proj: [M, hidden_dim] → expand to [B, M, hidden_dim]
            skill_proj_batch = skill_proj.unsqueeze(0).expand(batch_size, -1, -1)
            skill_token = self.special_token_embedding(
                torch.tensor([SKILL_PREFIX_ID], device=task_proj.device)
            ).unsqueeze(0).expand(batch_size, -1, -1)
            tokens.append(skill_token)
            tokens.append(skill_proj_batch)

        tokens.append(sep_emb)  # [SEP]

        # 拼接: [B, seq_len, hidden_dim]
        sequence = torch.cat(tokens, dim=1)

        # 截断到 MAX_SEQ_LEN
        if sequence.shape[1] > MAX_SEQ_LEN:
            sequence = sequence[:, :MAX_SEQ_LEN]

        seq_len = sequence.shape[1]

        # 位置编码
        positions = torch.arange(seq_len, device=sequence.device).unsqueeze(0).expand(batch_size, -1)
        pos_emb = self.position_embedding(positions)
        sequence = sequence + pos_emb

        # attention_mask: 全 1 (所有 token 有效)
        attention_mask = torch.ones(batch_size, seq_len, device=sequence.device)

        return sequence, attention_mask

    def forward(
        self,
        task_emb: torch.Tensor,
        ctx_emb: Optional[torch.Tensor] = None,
        tool_embs: Optional[torch.Tensor] = None,
        skill_embs: Optional[torch.Tensor] = None,
    ) -> Dict[str, torch.Tensor]:
        """前向传播。

        Args:
            task_emb: 任务嵌入 [B, embed_dim] 或 [embed_dim]
            ctx_emb: 上下文嵌入 (可选)
            tool_embs: 工具描述嵌入 (可选)
            skill_embs: 技能描述嵌入 (可选)

        Returns:
            dict with keys: decompose_logits, complexity_logits, subtask_count_logits,
                           capability_hint_logits, cls_output
        """
        sequence, _ = self._build_input_sequence(task_emb, ctx_emb, tool_embs, skill_embs)

        # Transformer Encoder
        encoded = self.transformer_encoder(sequence)  # [B, seq_len, hidden_dim]

        # 取 [CLS] 输出 (第一个 token)
        cls_output = self.layer_norm(encoded[:, 0, :])  # [B, hidden_dim]

        # 各输出头
        return {
            "decompose_logits": self.decompose_head(cls_output),       # [B, 2]
            "complexity_logits": self.complexity_head(cls_output),     # [B, 3]
            "subtask_count_logits": self.subtask_count_head(cls_output),  # [B, max_subtasks]
            "capability_hint_logits": self.capability_hint_head(cls_output),  # [B, total_capability_slots]
            "cls_output": cls_output,  # [B, hidden_dim]
        }

    @torch.no_grad()
    def analyze(
        self,
        task_emb: torch.Tensor,
        ctx_emb: Optional[torch.Tensor] = None,
        tool_embs: Optional[torch.Tensor] = None,
        skill_embs: Optional[torch.Tensor] = None,
        capability_map: Optional[object] = None,
        decompose_threshold: float = 0.5,
    ) -> DecompositionDecision:
        """分析任务，返回 DecompositionDecision。

        Args:
            task_emb: 任务嵌入
            ctx_emb: 上下文嵌入 (可选)
            tool_embs: 工具嵌入 (可选)
            skill_embs: 技能嵌入 (可选)
            capability_map: CapabilityMap 实例，用于将 capability slot 映射回名称
            decompose_threshold: 分解决策阈值
        """
        self.eval()

        # 确保输入有 batch 维度
        if task_emb.dim() == 1:
            task_emb = task_emb.unsqueeze(0)

        output = self.forward(task_emb, ctx_emb, tool_embs, skill_embs)

        # decompose: sigmoid on class 1
        decompose_probs = F.softmax(output["decompose_logits"], dim=-1)
        decompose_prob = decompose_probs[0, 1].item()  # P(decompose)
        should_decompose = decompose_prob > decompose_threshold
        confidence = abs(decompose_prob - 0.5) * 2  # 映射到 [0, 1]

        # complexity: argmax
        complexity_idx = output["complexity_logits"][0].argmax().item()
        complexity_labels = ["low", "medium", "high"]
        complexity = complexity_labels[min(complexity_idx, 2)]

        # subtask_count: argmax + 1
        subtask_count = output["subtask_count_logits"][0].argmax().item() + 1

        # capability_hints: sigmoid > 0.5 的 slot 映射回名称
        capability_hints = []
        if capability_map is not None:
            cap_probs = torch.sigmoid(output["capability_hint_logits"][0])
            active_slots = (cap_probs > 0.5).nonzero(as_tuple=True)[0].tolist()
            for slot in active_slots:
                if slot < self.max_tool_slots:
                    name = capability_map.get_tool_name(slot)
                else:
                    name = capability_map.get_skill_name(slot - self.max_tool_slots)
                if name:
                    capability_hints.append(name)

        return DecompositionDecision(
            should_decompose=should_decompose,
            confidence=round(confidence, 3),
            complexity=complexity,
            suggested_subtask_count=subtask_count,
            capability_hints=capability_hints,
            injection_text="",
        )

    def compute_loss(
        self,
        predictions: Dict[str, torch.Tensor],
        targets: Dict[str, torch.Tensor],
    ) -> Dict[str, torch.Tensor]:
        """计算多任务损失。

        Args:
            predictions: forward() 输出
            targets: {
                "decompose_label": [B] (0 or 1),
                "complexity_label": [B] (0, 1, 2),
                "subtask_count_label": [B] (0-4),
                "capability_label": [B, total_capability_slots] (multi-hot 0/1),
            }

        Returns:
            dict with total_loss and individual losses
        """
        decompose_loss = F.cross_entropy(
            predictions["decompose_logits"], targets["decompose_label"]
        )
        complexity_loss = F.cross_entropy(
            predictions["complexity_logits"], targets["complexity_label"]
        )
        subtask_count_loss = F.cross_entropy(
            predictions["subtask_count_logits"], targets["subtask_count_label"]
        )
        capability_loss = F.binary_cross_entropy_with_logits(
            predictions["capability_hint_logits"],
            targets["capability_label"].float(),
        )

        # 熵正则化 (从 decompose_head)
        decompose_probs = F.softmax(predictions["decompose_logits"], dim=-1)
        entropy = -(decompose_probs * torch.log(decompose_probs + 1e-8)).sum(dim=-1).mean()

        total_loss = (
            decompose_loss * 1.0
            + complexity_loss * 0.5
            + subtask_count_loss * 0.3
            + capability_loss * 0.3
            - entropy * 0.01
        )

        return {
            "total_loss": total_loss,
            "decompose_loss": decompose_loss,
            "complexity_loss": complexity_loss,
            "subtask_count_loss": subtask_count_loss,
            "capability_loss": capability_loss,
            "entropy": entropy,
        }

    def save(self, path: str | Path | None = None) -> None:
        """原子保存模型。"""
        if path is None:
            from app.config import get_settings
            settings = get_settings()
            path = settings.tca_model_path

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        save_data = {
            "state_dict": self.state_dict(),
            "embed_dim": self.embed_dim,
            "hidden_dim": self.hidden_dim,
            "num_heads": self.num_heads,
            "num_layers": self.num_layers,
            "max_tool_slots": self.max_tool_slots,
            "max_skill_slots": self.max_skill_slots,
            "max_subtasks": self.max_subtasks,
        }

        # 原子写入
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=".pth", dir=str(path.parent)
        ) as f:
            temp_path = f.name
        try:
            torch.save(save_data, temp_path, weights_only=True)
        except TypeError:
            # PyTorch < 2.1 不支持 weights_only
            torch.save(save_data, temp_path)
        Path(temp_path).replace(path)
        logger.info("[TCA] Model saved to %s", path)

    def load(self, path: str | Path | None = None) -> bool:
        """加载模型，支持向后兼容。

        Returns:
            True if loaded successfully, False otherwise.
        """
        if path is None:
            from app.config import get_settings
            settings = get_settings()
            path = settings.tca_model_path

        path = Path(path)
        if not path.exists():
            logger.debug("[TCA] No saved model at %s", path)
            return False

        try:
            data = torch.load(path, map_location="cpu", weights_only=True)
        except TypeError:
            data = torch.load(path, map_location="cpu")

        if isinstance(data, dict) and "state_dict" in data:
            self.load_state_dict(data["state_dict"], strict=False)
            logger.info("[TCA] Model loaded from %s", path)
        else:
            # 兼容: 直接是 state_dict
            self.load_state_dict(data, strict=False)
            logger.info("[TCA] Model loaded (legacy format) from %s", path)

        return True

    def get_num_parameters(self) -> int:
        """返回可训练参数总数。"""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
