"""Token budget estimation for context window management."""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_DEFAULT_RESERVED = 4000


class TokenEstimator:
    """Estimates token usage for text, messages, and budget allocation."""

    def estimate_text_tokens(self, text: str) -> int:
        """Estimate tokens for a text string.

        Uses chars/4 for English, chars/2 for CJK characters.
        """
        if not text:
            return 0

        cjk_count = len(re.findall(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]', text))
        non_cjk_count = len(text) - cjk_count

        return max(1, (cjk_count + 1) // 2 + non_cjk_count // 4)

    def estimate_messages_tokens(self, messages: list[dict]) -> int:
        """Estimate total tokens across a list of message dicts."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.estimate_text_tokens(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        total += self.estimate_text_tokens(part.get("text", ""))

            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                for tc in tool_calls:
                    args = tc.get("arguments", "")
                    total += self.estimate_text_tokens(str(args))
                    total += self.estimate_text_tokens(tc.get("name", ""))

        return total

    def get_available_budget(
        self,
        llm_config: object,
        system_prompt_tokens: int,
    ) -> int:
        """Calculate available token budget for messages.

        Args:
            llm_config: The LLM configuration (contains context_window).
            system_prompt_tokens: Token count of the system prompt.

        Returns:
            Available tokens for message history.
        """
        context_window = getattr(llm_config, "context_window", 128_000)
        reserved = _DEFAULT_RESERVED
        budget = max(0, context_window - reserved - system_prompt_tokens)
        logger.debug(
            f"TokenEstimator: context_window={context_window}, "
            f"reserved={reserved}, system_tokens={system_prompt_tokens}, "
            f"message_budget={budget}"
        )
        return budget
