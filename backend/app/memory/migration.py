"""
Data Migration - Migrate from JSON files to Database

This module handles migration of existing JSON-based session and memory
data to the SQLite database.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

from app.config import get_settings
from app.core.database import get_db_session, ensure_database
from app.repositories.memory_repository import MemoryRepository

logger = logging.getLogger(__name__)


async def migrate_json_to_database(
    backup: bool = True,
) -> Dict[str, Any]:
    """
    Migrate all JSON files to database.

    This function:
    1. Creates a backup of existing JSON files
    2. Reads all session JSON files
    3. Reads memory metadata JSON
    4. Imports everything into the database
    5. Optionally renames old JSON files with .bak extension

    Args:
        backup: Whether to backup JSON files before migration

    Returns:
        Dictionary with migration statistics
    """
    settings = get_settings()
    stats = {
        "sessions_imported": 0,
        "messages_imported": 0,
        "memories_imported": 0,
        "errors": [],
    }

    logger.info("Starting JSON to database migration...")

    # Ensure database exists
    ensure_database(settings)

    # Backup JSON files if requested
    if backup:
        logger.info("Creating backup of JSON files...")
        _backup_json_files(settings)
        stats["backup_created"] = True
    else:
        stats["backup_created"] = False

    # Migrate sessions
    try:
        with get_db_session(settings) as db_session:
            repo = MemoryRepository(db_session)

            # Migrate session files
            sessions_imported, messages_imported = await _migrate_sessions(
                repo, settings
            )
            stats["sessions_imported"] = sessions_imported
            stats["messages_imported"] = messages_imported

            # Migrate memory metadata
            memories_imported = await _migrate_memory_metadata(repo, settings)
            stats["memories_imported"] = memories_imported

    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        stats["errors"].append(str(e))
        raise

    logger.info(f"Migration completed: {stats}")
    return stats


async def _migrate_sessions(
    repo: MemoryRepository,
    settings,
) -> tuple[int, int]:
    """
    Migrate session JSON files to database.

    Args:
        repo: Memory repository
        settings: Application settings

    Returns:
        Tuple of (sessions_imported, messages_imported)
    """
    sessions_dir = Path(settings.sessions_dir)

    if not sessions_dir.exists():
        logger.warning(f"Sessions directory not found: {sessions_dir}")
        return 0, 0

    session_files = list(sessions_dir.glob("*.json"))
    sessions_imported = 0
    messages_imported = 0

    logger.info(f"Found {len(session_files)} session files to migrate")

    for session_file in session_files:
        try:
            # Read session JSON
            content = session_file.read_text(encoding="utf-8")
            session_data = json.loads(content)

            session_id = session_data.get("session_id", session_file.stem)

            # Create session in database
            repo.create_session(
                session_id=session_id,
                metadata=session_data.get("metadata", {}),
            )
            sessions_imported += 1

            # Import messages
            messages = session_data.get("messages", [])
            for msg in messages:
                repo.create_message(
                    session_id=session_id,
                    role=msg.get("role", "user"),
                    content=msg.get("content", ""),
                    timestamp=_parse_timestamp(msg.get("timestamp")),
                    extra_data=_build_extra_data(msg),
                )
                messages_imported += 1

            logger.debug(f"Migrated session {session_id} with {len(messages)} messages")

        except Exception as e:
            logger.error(f"Failed to migrate session {session_file.name}: {e}")

    return sessions_imported, messages_imported


async def _migrate_memory_metadata(
    repo: MemoryRepository,
    settings,
) -> int:
    """
    Migrate memory_metadata.json to database.

    Args:
        repo: Memory repository
        settings: Application settings

    Returns:
        Number of memories imported
    """
    metadata_file = Path(settings.data_dir) / "memory_metadata.json"

    if not metadata_file.exists():
        logger.info("No memory_metadata.json found, skipping")
        return 0

    try:
        content = metadata_file.read_text(encoding="utf-8")
        metadata = json.loads(content)

        memories_imported = 0

        # Import each category
        for category, memories in metadata.items():
            if not isinstance(memories, list):
                continue

            for mem in memories:
                try:
                    # Map category to memory type
                    memory_type = _map_category_to_type(category)

                    # Create memory in database
                    repo.create_memory(
                        session_id=mem.get("session_id"),
                        memory_type=memory_type,
                        content=mem.get("content", ""),
                        confidence=mem.get("confidence", 0.6),
                        importance_score=mem.get("confidence", 0.6),  # Use confidence as importance
                    )
                    memories_imported += 1

                except Exception as e:
                    logger.error(f"Failed to import memory: {e}")

        logger.info(f"Migrated {memories_imported} memories from metadata")
        return memories_imported

    except Exception as e:
        logger.error(f"Failed to migrate memory metadata: {e}")
        return 0


def _backup_json_files(settings) -> None:
    """Backup all JSON files."""
    import shutil
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Backup sessions
    sessions_dir = Path(settings.sessions_dir)
    if sessions_dir.exists():
        backup_dir = sessions_dir.parent / f"sessions_backup_{timestamp}"
        shutil.copytree(sessions_dir, backup_dir)
        logger.info(f"Backed up sessions to: {backup_dir}")

    # Backup memory metadata
    metadata_file = Path(settings.data_dir) / "memory_metadata.json"
    if metadata_file.exists():
        backup_file = metadata_file.parent / f"memory_metadata_backup_{timestamp}.json"
        shutil.copy2(metadata_file, backup_file)
        logger.info(f"Backed up memory metadata to: {backup_file}")


def _parse_timestamp(timestamp_str: str | None) -> datetime | None:
    """Parse timestamp string to datetime object."""
    if not timestamp_str:
        return None
    try:
        return datetime.fromisoformat(timestamp_str)
    except Exception:
        return datetime.now()


def _build_extra_data(message: Dict) -> Dict | None:
    """Build extra_data dict from message."""
    extra = {}

    if "tool_calls" in message:
        extra["tool_calls"] = message["tool_calls"]

    if "images" in message:
        extra["images"] = message["images"]

    return extra if extra else None


def _map_category_to_type(category: str) -> str:
    """Map metadata category to memory type."""
    mapping = {
        "previous_interactions": "fact",
        "learned_preferences": "preference",
        "important_context": "context",
    }
    return mapping.get(category, "fact")
