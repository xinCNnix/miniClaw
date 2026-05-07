"""
FastAPI Dependencies

This module provides dependency injection functions for FastAPI routes.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings, Settings


# Dependency for settings
def get_settings_dependency() -> Settings:
    """
    Get application settings.

    This can be used as a FastAPI dependency to inject settings.

    Returns:
        Settings instance

    Examples:
        >>> @app.get("/config")
        >>> async def get_config(settings: Settings = Depends(get_settings_dependency)):
        ...     return settings
    """
    return get_settings()


# Dependency for session manager
def get_session_manager_dependency():
    """
    Get session manager instance.

    Returns:
        SessionManager instance

    Examples:
        >>> @app.get("/sessions")
        >>> async def list_sessions(manager = Depends(get_session_manager_dependency())):
        ...     return manager.list_sessions()
    """
    from app.memory.session import get_session_manager
    return get_session_manager()


# Dependency for agent manager
async def get_agent_dependency():
    """
    Get agent manager instance.

    Returns:
        AgentManager instance

    Raises:
        HTTPException: If agent initialization fails
    """
    from fastapi import HTTPException, status
    from app.core.llm import get_agent_manager

    try:
        return get_agent_manager()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize agent: {str(e)}",
        )


# Async context manager for database sessions (if needed)
@asynccontextmanager
async def get_db_session() -> AsyncGenerator:
    """
    Async database session context manager.

    This can be used when adding database support.

    Yields:
        AsyncSession instance
    """
    # Placeholder for future database integration
    # For now, we use file-based storage
    yield None
