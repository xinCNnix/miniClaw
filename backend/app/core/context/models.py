"""Data models for the context management system."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

_VALID_ACTIONS = {"normal", "compressed", "checkpoint"}


@dataclass
class ContextResult:
    """Result of context preparation."""

    messages: list[dict]
    action: Literal["normal", "compressed", "checkpoint"]
    checkpoint_id: str | None = None

    def __post_init__(self):
        if self.action not in _VALID_ACTIONS:
            raise ValueError(f"Invalid action: {self.action!r}. Must be one of {_VALID_ACTIONS}")
