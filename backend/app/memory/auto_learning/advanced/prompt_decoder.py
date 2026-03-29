"""Decode soft prompt embeddings to natural language strategy text."""

import torch
import torch.nn as nn


class PromptDecoder(nn.Module):
    """Decode soft prompt embeddings to strategy text.

    Uses simplified template matching. Can be replaced with GRU/Transformer
    decoder in the future.
    """

    STRATEGY_TEMPLATES: list[str] = [
        "请用简洁直接的方式回答",
        "请提供详细的步骤说明",
        "请使用工具收集更多信息",
        "请深入分析问题",
        "请考虑多种替代方案",
        "请验证结果并确认",
        "请提供代码示例",
        "请给出实用可执行的建议",
        "请注意边缘情况和异常处理",
        "请参考历史背景信息",
        "请用类比方式解释",
        "请组织信息结构化呈现",
        "请进行系统化推理",
        "请对比不同方案的优劣",
        "请提供逐步推导过程",
        "请关注格式和结构化输出",
        "请整合多源信息综合分析",
        "请重点关注关键注意事项",
        "请从用户角度思考问题",
        "请总结最佳实践和常见陷阱",
    ]

    def __init__(self, hidden_dim: int = 128, vocab_size: int = 10000):
        super().__init__()
        self.template_proj = nn.Linear(hidden_dim, len(self.STRATEGY_TEMPLATES))

    def decode(self, soft_prompt: torch.Tensor) -> str:
        """Decode soft prompt to strategy text.

        Args:
            soft_prompt: Soft prompt embeddings of shape [1, P, H]

        Returns:
            Strategy text string
        """
        with torch.no_grad():
            avg = soft_prompt.mean(dim=1)  # [1, H]
            logits = self.template_proj(avg)  # [1, num_templates]
            idx = torch.argmax(logits, dim=-1).item()
            return self.STRATEGY_TEMPLATES[idx]

    def decode_latent(self, z: torch.Tensor) -> str:
        """Decode latent z to strategy text.

        Convenience method pending integration with PromptGenerator.
        """
        raise NotImplementedError("Pending integration with PromptGenerator")
