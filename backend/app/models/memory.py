"""
Memory Models - Data structures for memory extraction and storage.

This module defines Pydantic models for memory extraction, storage, and retrieval.
"""

from pydantic import BaseModel, Field
from typing import Literal, List, Optional
from datetime import datetime


class Memory(BaseModel):
    """
    Single extracted memory item.

    Memories represent structured information extracted from conversations,
    categorized by type and assigned a confidence score.
    """

    memory_id: Optional[str] = Field(
        default=None,
        description="Unique memory ID (generated when stored in database)",
    )
    type: Literal["preference", "fact", "context", "pattern"] = Field(
        description="Type of memory: preference (user likes), fact (objective info), context (situational), pattern (recurring behavior)"
    )
    content: str = Field(
        description="The actual memory content",
        min_length=1,
        max_length=1000,
    )
    confidence: float = Field(
        description="Confidence score from 0.0 to 1.0",
        ge=0.0,
        le=1.0,
    )
    timestamp: str = Field(
        description="ISO format timestamp when memory was extracted",
    )
    session_id: str = Field(
        description="Session ID where memory was extracted",
    )

    def model_dump(self, **kwargs):
        """Override to ensure datetime serialization."""
        data = super().model_dump(**kwargs)
        return data


class MemoryExtractionResult(BaseModel):
    """
    Result of memory extraction from a conversation.

    Contains extracted memories, conversation summary, and identified topics.
    """

    memories: List[Memory] = Field(
        default_factory=list,
        description="List of extracted memories",
    )
    summary: str = Field(
        default="",
        description="Brief summary of the conversation",
        max_length=2000,
    )
    topics: List[str] = Field(
        default_factory=list,
        description="Main topics discussed in the conversation",
    )


class MemorySearchResult(BaseModel):
    """
    Result from semantic memory search.

    Represents a single memory/item retrieved from vector search.
    """

    content: str = Field(
        description="The content of the memory",
    )
    session_id: str = Field(
        description="Session ID where this memory originated",
    )
    timestamp: str = Field(
        description="ISO format timestamp",
    )
    similarity: float = Field(
        description="Similarity score from 0.0 to 1.0",
        ge=0.0,
        le=1.0,
    )
    metadata: Optional[dict] = Field(
        default=None,
        description="Additional metadata about the memory",
    )


class ConversationChunk(BaseModel):
    """
    A chunk of conversation for vector indexing.

    Conversations are split into chunks for efficient vector storage and retrieval.
    """

    content: str = Field(
        description="The conversation text",
    )
    session_id: str = Field(
        description="Session ID",
    )
    start_message_idx: int = Field(
        description="Index of the first message in this chunk",
    )
    end_message_idx: int = Field(
        description="Index of the last message in this chunk",
    )
    timestamp: str = Field(
        description="ISO format timestamp",
    )
    message_count: int = Field(
        description="Number of messages in this chunk",
    )
    topics: List[str] = Field(
        default_factory=list,
        description="Topics discussed in this chunk",
    )
