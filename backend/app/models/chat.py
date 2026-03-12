"""
Chat Models - Pydantic models for chat API
"""

from typing import List, Optional, Any
from pydantic import BaseModel, Field


class Message(BaseModel):
    """Chat message."""

    role: str = Field(
        ...,
        description="Message role: 'user', 'assistant', or 'tool'",
    )

    content: str = Field(
        ...,
        description="Message content",
    )

    tool_calls: Optional[List[dict]] = Field(
        default=None,
        description="Tool calls (for role='tool')",
    )

    timestamp: Optional[str] = Field(
        default=None,
        description="Message timestamp (ISO 8601)",
    )

    images: Optional[List[dict]] = Field(
        default=None,
        description="Image attachments (for multimodal LLMs)",
    )


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    message: str = Field(
        ...,
        description="User message",
    )

    session_id: Optional[str] = Field(
        default="default",
        description="Session ID (for conversation history)",
    )

    stream: bool = Field(
        default=True,
        description="Whether to stream the response",
    )

    context: Optional[dict] = Field(
        default=None,
        description="Additional context for the Agent",
    )

    images: Optional[List[dict]] = Field(
        default=None,
        description="Image attachments for multimodal LLMs",
    )


class ToolCall(BaseModel):
    """Tool call information."""

    id: str = Field(..., description="Tool call ID")
    name: str = Field(..., description="Tool name")
    arguments: dict = Field(..., description="Tool arguments")


class ChatEvent(BaseModel):
    """SSE event for streaming."""

    type: str = Field(
        ...,
        description="Event type: 'thinking_start', 'tool_call', 'content_delta', 'error', 'done'",
    )

    content: Optional[str] = Field(
        default=None,
        description="Content (for content_delta events)",
    )

    tool_calls: Optional[List[ToolCall]] = Field(
        default=None,
        description="Tool calls (for tool_call events)",
    )

    error: Optional[str] = Field(
        default=None,
        description="Error message (for error events)",
    )


class ChatResponse(BaseModel):
    """Response model for chat endpoint (non-streaming)."""

    role: str = Field(
        default="assistant",
        description="Response role",
    )

    content: str = Field(
        ...,
        description="Response content",
    )

    tool_calls: Optional[List[ToolCall]] = Field(
        default=None,
        description="Tool calls made",
    )
