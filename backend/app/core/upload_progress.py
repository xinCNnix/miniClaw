"""
Upload Progress Manager

Track and manage upload task progress for knowledge base documents.
"""

import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import Dict, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class UploadStatus(str, Enum):
    """Upload task status."""

    PENDING = "pending"
    VALIDATING = "validating"
    UPLOADING = "uploading"
    INDEXING = "indexing"
    COMPLETED = "completed"
    FAILED = "failed"


class UploadProgress(BaseModel):
    """Upload task progress information."""

    task_id: str
    filename: str
    status: UploadStatus
    progress: int  # 0-100
    message: str
    error: Optional[str] = None
    created_at: str
    updated_at: str


class UploadProgressManager:
    """
    Manager for tracking upload task progress.

    Uses in-memory storage for progress tracking.
    For production, consider using Redis or database.
    """

    def __init__(self):
        """Initialize the progress manager."""
        self._tasks: Dict[str, UploadProgress] = {}
        self._cleanup_interval = 3600  # 1 hour
        self._task_ttl = 86400  # 24 hours

    def create_task(
        self,
        task_id: str,
        filename: str,
    ) -> UploadProgress:
        """
        Create a new upload task.

        Args:
            task_id: Unique task identifier
            filename: Name of the file being uploaded

        Returns:
            Created upload progress
        """
        now = datetime.now().isoformat()

        progress = UploadProgress(
            task_id=task_id,
            filename=filename,
            status=UploadStatus.PENDING,
            progress=0,
            message="Upload task created",
            created_at=now,
            updated_at=now,
        )

        self._tasks[task_id] = progress
        logger.info(f"Created upload task: {task_id} for file: {filename}")

        return progress

    def update_task(
        self,
        task_id: str,
        status: Optional[UploadStatus] = None,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        error: Optional[str] = None,
    ) -> Optional[UploadProgress]:
        """
        Update an existing upload task.

        Args:
            task_id: Task identifier
            status: New status (optional)
            progress: Progress value 0-100 (optional)
            message: Status message (optional)
            error: Error message (optional)

        Returns:
            Updated progress or None if task not found
        """
        if task_id not in self._tasks:
            logger.warning(f"Task not found: {task_id}")
            return None

        task = self._tasks[task_id]

        if status is not None:
            task.status = status
        if progress is not None:
            task.progress = max(0, min(100, progress))
        if message is not None:
            task.message = message
        if error is not None:
            task.error = error

        task.updated_at = datetime.now().isoformat()

        logger.info(
            f"Updated task {task_id}: status={task.status}, progress={task.progress}"
        )

        return task

    def get_task(self, task_id: str) -> Optional[UploadProgress]:
        """
        Get upload task progress.

        Args:
            task_id: Task identifier

        Returns:
            Upload progress or None if not found
        """
        return self._tasks.get(task_id)

    def delete_task(self, task_id: str) -> bool:
        """
        Delete an upload task.

        Args:
            task_id: Task identifier

        Returns:
            True if deleted, False if not found
        """
        if task_id in self._tasks:
            del self._tasks[task_id]
            logger.info(f"Deleted task: {task_id}")
            return True
        return False

    def cleanup_old_tasks(self) -> int:
        """
        Clean up old completed/failed tasks.

        Returns:
            Number of tasks cleaned up
        """
        from datetime import timedelta

        now = datetime.now()
        to_delete = []

        for task_id, task in self._tasks.items():
            # Only clean up completed or failed tasks
            if task.status not in [UploadStatus.COMPLETED, UploadStatus.FAILED]:
                continue

            created_at = datetime.fromisoformat(task.created_at)
            age = now - created_at

            if age.total_seconds() > self._task_ttl:
                to_delete.append(task_id)

        for task_id in to_delete:
            del self._tasks[task_id]

        if to_delete:
            logger.info(f"Cleaned up {len(to_delete)} old tasks")

        return len(to_delete)


# Singleton instance
_upload_progress_manager: Optional[UploadProgressManager] = None


def get_upload_progress_manager() -> UploadProgressManager:
    """
    Get upload progress manager singleton instance.

    Returns:
        Upload progress manager instance
    """
    global _upload_progress_manager

    if _upload_progress_manager is None:
        _upload_progress_manager = UploadProgressManager()

    return _upload_progress_manager
