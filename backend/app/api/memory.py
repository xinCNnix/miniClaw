"""
Memory Management API

This module provides REST API endpoints for managing memories,
including listing, searching, and triggering extraction.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.memory.memory_manager import get_memory_manager, MemoryManager
from app.memory.session import get_session_manager
from app.memory.auto_learning import get_pattern_memory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])


# ============================================================================
# Request/Response Models
# ============================================================================

class MemoryItemResponse(BaseModel):
    """Response model for a single memory item."""

    type: str = Field(description="Type of memory")
    content: str = Field(description="Memory content")
    confidence: float = Field(description="Confidence score")
    timestamp: str = Field(description="Extraction timestamp")
    session_id: str = Field(description="Source session ID")


class MemoryListResponse(BaseModel):
    """Response model for memory list."""

    memories: List[MemoryItemResponse] = Field(description="List of memories")
    total: int = Field(description="Total count")


class SearchResultResponse(BaseModel):
    """Response model for semantic search results."""

    content: str = Field(description="Result content")
    session_id: str = Field(description="Source session ID")
    similarity: float = Field(description="Similarity score")


class ExtractionTriggerResponse(BaseModel):
    """Response model for extraction trigger."""

    success: bool = Field(description="Whether trigger was successful")
    message: str = Field(description="Status message")
    memories_count: int = Field(description="Number of memories extracted")


class MemoryStatsResponse(BaseModel):
    """Response model for memory statistics."""

    total_sessions: int = Field(description="Total number of sessions")
    total_messages: int = Field(description="Total messages across sessions")
    indexed_conversations: int = Field(description="Number of indexed conversations")


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/patterns")
async def get_patterns(
    query: str = Query("", description="Search query for patterns"),
    top_k: int = Query(10, ge=1, le=50, description="Number of patterns to return"),
) -> dict:
    """
    Get learned patterns from Pattern Memory.

    Returns patterns that have been extracted and learned from previous
    task executions. Can optionally filter by query.

    ## Query Parameters
    - **query**: Optional search query to find relevant patterns
    - **top_k**: Maximum number of patterns to return (1-50, default: 10)

    ## Response
    ```json
    {
      "patterns": [
        {
          "id": "pattern_001",
          "description": "Handle API timeout by increasing timeout",
          "situation": "API timeout error",
          "outcome": "Failed after 30s",
          "fix_action": "Increased timeout to 60s",
          "similarity": 0.85
        }
      ],
      "total": 1
    }
    ```

    Args:
        query: Optional search query
        top_k: Maximum patterns to return

    Returns:
        Dictionary with patterns list and total count
    """
    try:
        pattern_memory = get_pattern_memory()

        # Get patterns
        if query:
            # Search with query
            patterns = pattern_memory.get_top_patterns(query, top_k=top_k)
        else:
            # Get all patterns (limited by top_k)
            all_patterns = pattern_memory.patterns[:top_k]
            patterns = [
                {
                    "id": p.id,
                    "description": p.description,
                    "situation": p.situation,
                    "outcome": p.outcome,
                    "fix_action": p.fix_action,
                    "similarity": 1.0,  # Full similarity for direct listing
                }
                for p in all_patterns
            ]

        return {
            "patterns": patterns,
            "total": len(patterns),
        }

    except Exception as e:
        logger.error(f"Failed to get patterns: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve patterns: {str(e)}",
        )


@router.get("/stats", response_model=MemoryStatsResponse)
async def get_memory_stats() -> MemoryStatsResponse:
    """
    Get memory system statistics.

    Returns statistics about the memory system including session counts,
    message counts, and indexed conversations.

    ## Response
    ```json
    {
      "total_sessions": 10,
      "total_messages": 250,
      "indexed_conversations": 8
    }
    ```

    Returns:
        Memory statistics
    """
    try:
        session_manager = get_session_manager()
        sessions = session_manager.list_sessions()

        total_messages = sum(s.get("message_count", 0) for s in sessions)

        # Get indexed conversations count from RAG engine
        # (This would require extending RAGEngine to provide stats)
        indexed_conversations = len([s for s in sessions if s.get("message_count", 0) > 0])

        return MemoryStatsResponse(
            total_sessions=len(sessions),
            total_messages=total_messages,
            indexed_conversations=indexed_conversations,
        )

    except Exception as e:
        logger.error(f"Failed to get memory stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve statistics: {str(e)}",
        )


@router.post("/extract", response_model=ExtractionTriggerResponse)
async def trigger_extraction(
    session_id: str = Query(..., description="Session ID to extract memories from"),
) -> ExtractionTriggerResponse:
    """
    Manually trigger memory extraction for a session.

    This endpoint forces memory extraction for the specified session,
    regardless of the automatic extraction schedule.

    ## Query Parameters
    - **session_id**: Session ID to process

    ## Response
    ```json
    {
      "success": true,
      "message": "Memory extraction completed",
      "memories_count": 5
    }
    ```

    Args:
        session_id: Session ID to extract memories from

    Returns:
        Extraction result

    Raises:
        HTTPException: If session not found or extraction fails
    """
    try:
        memory_manager = get_memory_manager()

        # Verify session exists
        session_manager = get_session_manager()
        session = session_manager.load_session(session_id)

        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session not found: {session_id}",
            )

        # Perform extraction
        result = await memory_manager.extract_and_store(session_id)

        return ExtractionTriggerResponse(
            success=True,
            message="Memory extraction completed successfully",
            memories_count=len(result.memories),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Memory extraction failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Memory extraction failed: {str(e)}",
        )


@router.get("/search", response_model=List[SearchResultResponse])
async def search_memories(
    query: str = Query(..., min_length=1, description="Search query"),
    top_k: int = Query(5, ge=1, le=20, description="Number of results"),
) -> List[SearchResultResponse]:
    """
    Semantic search of conversation history.

    Searches through indexed conversations using semantic similarity
    to find relevant past discussions.

    ## Query Parameters
    - **query**: Search query text
    - **top_k**: Number of results to return (1-20, default: 5)

    ## Response
    ```json
    [
      {
        "content": "User discussed React hooks...",
        "session_id": "session_123",
        "similarity": 0.85
      }
    ]
    ```

    Args:
        query: Search query
        top_k: Number of results

    Returns:
        List of search results
    """
    try:
        memory_manager = get_memory_manager()
        results = await memory_manager.search_relevant_history(query, top_k=top_k)

        return [
            SearchResultResponse(
                content=r["content"],
                session_id=r["session_id"],
                similarity=r.get("similarity", 0.0),
            )
            for r in results
        ]

    except Exception as e:
        logger.error(f"Memory search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}",
        )


@router.get("/sessions", response_model=List[dict])
async def list_sessions(
    limit: int = Query(20, ge=1, le=100, description="Max sessions to return"),
) -> List[dict]:
    """
    List all conversation sessions.

    Returns a list of all conversation sessions with basic metadata.

    ## Query Parameters
    - **limit**: Maximum number of sessions to return (1-100, default: 20)

    ## Response
    ```json
    [
      {
        "session_id": "session_123",
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T01:00:00",
        "message_count": 15,
        "metadata": {}
      }
    ]
    ```

    Args:
        limit: Maximum sessions to return

    Returns:
        List of session information
    """
    try:
        session_manager = get_session_manager()
        sessions = session_manager.list_sessions()

        # Apply limit
        sessions = sessions[:limit]

        return sessions

    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list sessions: {str(e)}",
        )


@router.get("/sessions/{session_id}", response_model=dict)
async def get_session(session_id: str) -> dict:
    """
    Get detailed information about a session.

    Returns full session details including all messages.

    ## Path Parameters
    - **session_id**: Session ID

    ## Response
    ```json
    {
      "session_id": "session_123",
      "messages": [...],
      "metadata": {},
      "created_at": "2024-01-01T00:00:00",
      "updated_at": "2024-01-01T01:00:00"
    }
    ```

    Args:
        session_id: Session ID

    Returns:
        Full session details

    Raises:
        HTTPException: If session not found
    """
    try:
        session_manager = get_session_manager()
        session = session_manager.load_session(session_id)

        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session not found: {session_id}",
            )

        return session

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve session: {str(e)}",
        )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str) -> None:
    """
    Delete a session.

    Permanently deletes a session and all its messages.

    ## Path Parameters
    - **session_id**: Session ID to delete

    Args:
        session_id: Session ID to delete

    Raises:
        HTTPException: If session not found or deletion fails
    """
    try:
        session_manager = get_session_manager()
        success = session_manager.delete_session(session_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session not found: {session_id}",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete session: {str(e)}",
        )
