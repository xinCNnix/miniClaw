"""
Memory Module - Conversation and Prompt Management

This module handles System Prompt construction and session management.

Components:
- Prompts: 6-component System Prompt builder
- Session: Conversation session storage
- Truncation: Text truncation strategies
"""

from .prompts import (
    PromptComponent,
    SystemPromptBuilder,
    build_system_prompt,
)

from .session import (
    SessionManager,
    get_session_manager,
)

from .truncation import (
    TextTruncator,
    truncate_prompt,
    truncate_message_list,
)

__all__ = [
    # Prompts
    "PromptComponent",
    "SystemPromptBuilder",
    "build_system_prompt",

    # Session
    "SessionManager",
    "get_session_manager",

    # Truncation
    "TextTruncator",
    "truncate_prompt",
    "truncate_message_list",
]
