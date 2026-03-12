"""
Sessions Models - Pydantic models for session API
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class SessionInfo(BaseModel):
    """Information about a session."""

    session_id: str = Field(..., description="Session ID")
    created_at: str = Field(..., description="Creation time (ISO 8601)")
    updated_at: str = Field(..., description="Last update time (ISO 8601)")
    message_count: int = Field(..., description="Number of messages")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Session metadata",
    )


class SessionListResponse(BaseModel):
    """Response model for session listing."""

    sessions: List[SessionInfo] = Field(
        ...,
        description="List of sessions",
    )

    total: int = Field(
        ...,
        description="Total number of sessions",
    )


class SessionCreateRequest(BaseModel):
    """Request model for creating a session."""

    session_id: Optional[str] = Field(
        default=None,
        description="Custom session ID (optional)",
    )

    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Session metadata",
    )


class SessionDetailResponse(BaseModel):
    """Response model for session details."""

    session_id: str = Field(..., description="Session ID")
    messages: List[dict] = Field(..., description="Messages in the session")
    created_at: str = Field(..., description="Creation time")
    updated_at: str = Field(..., description="Last update time")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Session metadata",
    )

    stats: Optional[Dict[str, int]] = Field(
        default=None,
        description="Session statistics",
    )
