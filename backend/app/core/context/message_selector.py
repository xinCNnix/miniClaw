"""Selects messages from session history within token budget."""
from __future__ import annotations

import logging

from app.core.context.token_estimator import TokenEstimator

logger = logging.getLogger(__name__)


class MessageSelector:
    """Selects the most relevant messages from session history within a token budget.

    Strategy (3 layers):
    1. Recent messages (mandatory, from end backwards)
    2. Tool call chains (kept intact, never split)
    3. Current message (always included)
    """

    def select(
        self,
        session_messages: list[dict],
        current_message: dict,
        budget: int,
        estimator: TokenEstimator,
    ) -> tuple[list[dict], int]:
        current_tokens = estimator.estimate_messages_tokens([current_message])
        remaining = budget - current_tokens

        if remaining <= 0:
            logger.warning("Current message exceeds budget, returning it alone")
            return [current_message], current_tokens

        if not session_messages:
            return [current_message], current_tokens

        groups = self._group_tool_chains(session_messages)

        selected_groups: list[list[dict]] = []
        used = 0

        for group in reversed(groups):
            group_tokens = estimator.estimate_messages_tokens(group)
            if used + group_tokens <= remaining:
                selected_groups.insert(0, group)
                used += group_tokens
            else:
                break

        selected = []
        for group in selected_groups:
            selected.extend(group)

        selected.append(current_message)
        total_used = used + current_tokens

        logger.info(
            f"MessageSelector: {len(session_messages)} history → "
            f"{len(selected)} selected, {total_used} tokens / {budget} budget"
        )

        return selected, total_used

    def _group_tool_chains(self, messages: list[dict]) -> list[list[dict]]:
        """Group messages so tool_call/tool_result chains stay together."""
        groups: list[list[dict]] = []
        current_group: list[dict] = []

        for msg in messages:
            role = msg.get("role", "")

            if role == "user":
                if current_group:
                    groups.append(current_group)
                current_group = [msg]

            elif role == "assistant" and msg.get("tool_calls"):
                if not current_group or current_group[-1].get("role") == "tool":
                    if current_group:
                        groups.append(current_group)
                    current_group = [msg]
                else:
                    current_group.append(msg)

            elif role == "assistant":
                if current_group and current_group[-1].get("role") != "tool":
                    current_group.append(msg)
                else:
                    if current_group:
                        groups.append(current_group)
                    current_group = [msg]

            elif role == "tool":
                current_group.append(msg)

            else:
                if current_group:
                    groups.append(current_group)
                current_group = [msg]

        if current_group:
            groups.append(current_group)

        return groups
