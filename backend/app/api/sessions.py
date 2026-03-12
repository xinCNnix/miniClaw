"""
Sessions API - Session Management Endpoints

This module provides endpoints for managing conversation sessions.
"""

from typing import List
from fastapi import APIRouter, HTTPException, status

from app.models.sessions import (
    SessionListResponse,
    SessionInfo,
    SessionDetailResponse,
    SessionCreateRequest,
)

from app.memory.session import get_session_manager


router = APIRouter(tags=["sessions"])


@router.get("")
async def list_sessions() -> SessionListResponse:
    """
    List all conversation sessions.

    ## Response Format
    ```json
    {
      "sessions": [
        {
          "session_id": "uuid",
          "created_at": "2024-03-04T10:00:00",
          "updated_at": "2024-03-04T10:05:00",
          "message_count": 5,
          "metadata": {"title": "Chat about Python"}
        }
      ],
      "total": 10
    }
    ```

    ## Example Usage
    ```bash
    curl http://localhost:8002/api/sessions
    ```

    Returns:
        SessionListResponse with all sessions

    Raises:
        HTTPException: If listing fails
    """
    try:
        session_manager = get_session_manager()
        sessions = session_manager.list_sessions()

        return SessionListResponse(
            sessions=sessions,
            total=len(sessions),
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list sessions: {str(e)}",
        )


@router.post("")
async def create_session(request: SessionCreateRequest) -> SessionInfo:
    """
    Create a new conversation session.

    ## Request Format
    ```json
    {
      "session_id": "custom-id",  // optional
      "metadata": {
        "title": "Weather queries",
        "description": "Conversations about weather"
      }
    }
    ```

    ## Response Format
    ```json
    {
      "session_id": "uuid",
      "created_at": "2024-03-04T10:00:00",
      "updated_at": "2024-03-04T10:00:00",
      "message_count": 0,
      "metadata": {...}
    }
    ```

    ## Example Usage
    ```bash
    curl -X POST http://localhost:8002/api/sessions \
      -H "Content-Type: application/json" \
      -d '{"metadata": {"title": "My Chat"}}'
    ```

    Args:
        request: Session creation request

    Returns:
        SessionInfo for created session

    Raises:
        HTTPException: If creation fails
    """
    try:
        session_manager = get_session_manager()
        session = session_manager.create_session(
            session_id=request.session_id,
            metadata=request.metadata,
        )

        return SessionInfo(
            session_id=session["session_id"],
            created_at=session["created_at"],
            updated_at=session["updated_at"],
            message_count=len(session["messages"]),
            metadata=session.get("metadata", {}),
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create session: {str(e)}",
        )


@router.get("/{session_id}")
async def get_session(session_id: str) -> SessionDetailResponse:
    """
    Get detailed information about a session.

    ## Path Parameters
    - **session_id**: Session ID

    ## Response Format
    ```json
    {
      "session_id": "uuid",
      "messages": [
        {"role": "user", "content": "...", "timestamp": "..."},
        {"role": "assistant", "content": "...", "timestamp": "..."}
      ],
      "created_at": "2024-03-04T10:00:00",
      "updated_at": "2024-03-04T10:05:00",
      "metadata": {},
      "stats": {
        "total_messages": 5,
        "user_messages": 2,
        "assistant_messages": 2,
        "tool_messages": 1
      }
    }
    ```

    ## Example Usage
    ```bash
    curl http://localhost:8002/api/sessions/some-session-id
    ```

    Args:
        session_id: Session ID

    Returns:
        SessionDetailResponse with full session data

    Raises:
        HTTPException: If session not found or loading fails
    """
    try:
        session_manager = get_session_manager()
        session = session_manager.load_session(session_id)

        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session not found: {session_id}",
            )

        # Get stats
        stats = session_manager.get_session_stats(session_id)

        return SessionDetailResponse(
            session_id=session["session_id"],
            messages=session["messages"],
            created_at=session["created_at"],
            updated_at=session["updated_at"],
            metadata=session.get("metadata", {}),
            stats=stats,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load session: {str(e)}",
        )


@router.delete("/{session_id}")
async def delete_session(session_id: str) -> dict:
    """
    Delete a conversation session.

    ## Path Parameters
    - **session_id**: Session ID

    ## Response Format
    ```json
    {
      "success": true,
      "message": "Session deleted successfully"
    }
    ```

    ## Example Usage
    ```bash
    curl -X DELETE http://localhost:8002/api/sessions/some-session-id
    ```

    Args:
        session_id: Session ID

    Returns:
        Dict with success status

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

        return {
            "success": True,
            "message": f"Session deleted successfully: {session_id}",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete session: {str(e)}",
        )


@router.get("/{session_id}/messages")
async def get_session_messages(session_id: str, limit: int = 100):
    """
    Get messages from a session.

    ## Path Parameters
    - **session_id**: Session ID

    ## Query Parameters
    - **limit**: Maximum number of messages to return (default: 100)

    ## Response Format
    ```json
    {
      "session_id": "uuid",
      "messages": [
        {"role": "user", "content": "...", "timestamp": "..."},
        ...
      ],
      "total": 50
    }
    ```

    ## Example Usage
    ```bash
    curl "http://localhost:8002/api/sessions/some-session-id/messages?limit=10"
    ```

    Args:
        session_id: Session ID
        limit: Maximum messages to return

    Returns:
        Dict with messages

    Raises:
        HTTPException: If session not found
    """
    try:
        session_manager = get_session_manager()
        messages = session_manager.get_messages(session_id)

        # Apply limit
        if limit and len(messages) > limit:
            messages = messages[-limit:]

        return {
            "session_id": session_id,
            "messages": messages,
            "total": len(messages),
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get messages: {str(e)}",
        )
