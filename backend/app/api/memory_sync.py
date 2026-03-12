"""
Memory Sync API - Endpoints for Markdown file synchronization

This module provides API endpoints for manually triggering Markdown file
synchronization from the database.
"""

import logging
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from app.memory.database_memory import get_memory_manager
from app.core.database import get_database_info

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])


class SyncResponse(BaseModel):
    """Response for Markdown sync operation."""

    success: bool = Field(..., description="Sync success status")
    message: str = Field(..., description="Status message")
    files_updated: list[str] = Field(default_factory=list, description="List of updated files")


class DatabaseStatsResponse(BaseModel):
    """Response for database statistics."""

    database_exists: bool = Field(..., description="Whether database file exists")
    size_bytes: int = Field(..., description="Database file size in bytes")
    tables: Dict[str, int] = Field(..., description="Table row counts")


@router.post("/sync", response_model=SyncResponse)
async def sync_markdown_files():
    """
    Manually trigger Markdown file synchronization from database.

    This endpoint regenerates USER.md and MEMORY.md from the database,
    applying configured time and confidence filters.

    Returns:
        SyncResponse with operation result
    """
    try:
        manager = get_memory_manager()

        # Check if database is enabled
        if not manager._use_database:
            raise HTTPException(
                status_code=400,
                detail="Database storage is not enabled. Enable with use_sqlite=True",
            )

        # Synchronize files
        await manager.sync_markdown_files()

        return SyncResponse(
            success=True,
            message="Markdown files synchronized successfully",
            files_updated=["USER.md", "MEMORY.md"],
        )

    except Exception as e:
        logger.error(f"Failed to sync Markdown files: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to sync Markdown files: {str(e)}",
        )


@router.get("/stats", response_model=DatabaseStatsResponse)
async def get_database_stats():
    """
    Get database statistics and information.

    Returns:
        DatabaseStatsResponse with database information
    """
    try:
        info = get_database_info()

        return DatabaseStatsResponse(
            database_exists=info["exists"],
            size_bytes=info["size_bytes"],
            tables=info["tables"],
        )

    except Exception as e:
        logger.error(f"Failed to get database stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get database stats: {str(e)}",
        )


@router.post("/migrate")
async def migrate_from_json():
    """
    Migrate existing JSON files to database.

    This endpoint reads all existing session JSON files and memory
    metadata files, then imports them into the database.

    Returns:
        Migration result
    """
    try:
        manager = get_memory_manager()

        # Check if database is enabled
        if not manager._use_database:
            raise HTTPException(
                status_code=400,
                detail="Database storage is not enabled",
            )

        from app.memory.migration import migrate_json_to_database

        result = await migrate_json_to_database()

        return {
            "success": True,
            "message": "Migration completed successfully",
            **result,
        }

    except Exception as e:
        logger.error(f"Failed to migrate from JSON: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Migration failed: {str(e)}",
        )
