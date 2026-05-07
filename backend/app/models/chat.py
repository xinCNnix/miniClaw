"""
Chat Models - Pydantic models for chat API
"""

from typing import List, Optional, Any
from pydantic import BaseModel, Field, model_validator


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

    attachments: Optional[List[dict]] = Field(
        default=None,
        description="File attachments (image/document/audio/video)",
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

    attachments: Optional[List[dict]] = Field(
        default=None,
        description="File attachments (image/document/audio/video)",
    )

    images: Optional[List[dict]] = Field(
        default=None,
        description="Legacy image attachments (mapped to attachments)",
    )

    @model_validator(mode="before")
    @classmethod
    def _map_legacy_images(cls, values: dict) -> dict:
        if values.get("images") and not values.get("attachments"):
            values["attachments"] = values["images"]
        return values


class ToolCall(BaseModel):
    """Tool call information."""

    id: str = Field(..., description="Tool call ID")
    name: str = Field(..., description="Tool name")
    arguments: dict = Field(..., description="Tool arguments")


class ChatEvent(BaseModel):
    """SSE event for streaming."""

    model_config = {"extra": "allow"}

    type: str = Field(
        ...,
        description="Event type: 'thinking_start', 'tool_call', 'tool_output', 'content_delta', 'error', 'done'",
    )

    content: Optional[str] = Field(
        default=None,
        description="Content (for content_delta events)",
    )

    tool_calls: Optional[List[ToolCall]] = Field(
        default=None,
        description="Tool calls (for tool_call events)",
    )

    tool_name: Optional[str] = Field(
        default=None,
        description="Tool name (for tool_output events)",
    )

    output: Optional[str] = Field(
        default=None,
        description="Tool output (for tool_output events)",
    )

    status: Optional[str] = Field(
        default=None,
        description="Status (for tool_output events: 'success' or 'error')",
    )

    error: Optional[str] = Field(
        default=None,
        description="Error message (for error events)",
    )

    # ToT events
    mode: Optional[str] = Field(default=None)
    max_depth: Optional[int] = Field(default=None)
    depth: Optional[int] = Field(default=None)
    count: Optional[int] = Field(default=None)
    thoughts: Optional[list] = Field(default=None)
    best_path: Optional[list] = Field(default=None)
    best_score: Optional[float] = Field(default=None)
    thought_id: Optional[str] = Field(default=None)
    tool_count: Optional[int] = Field(default=None)
    # tree: Optional[dict] = Field(default=None)  # BUG: _build_tree_structure() returns list, not dict
    tree: Optional[list] = Field(default=None)
    reason: Optional[str] = Field(default=None)
    score: Optional[float] = Field(default=None)
    final_answer: Optional[str] = Field(default=None)
    total_thoughts: Optional[int] = Field(default=None)
    message: Optional[str] = Field(default=None)
    tool_count_events: Optional[int] = Field(default=None)
    generated_images: Optional[List[dict]] = Field(
        default=None,
        description="Generated images metadata: [{media_id, api_url, name, mime_type}]",
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
