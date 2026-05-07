"""
Database Session Manager - Session Management with SQLite Backend

This module extends the existing SessionManager with database storage support,
enabling dual-write mode for backward compatibility.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.config import get_settings, Settings
from app.memory.session import SessionManager
from app.core.database import get_db_session, ensure_database
from app.repositories.memory_repository import MemoryRepository

logger = logging.getLogger(__name__)


class DatabaseSessionManager(SessionManager):
    """
    Enhanced session manager with database support.

    This manager extends the file-based SessionManager with SQLite database
    storage, supporting dual-write mode for backward compatibility.
    """

    def __init__(self, use_database: Optional[bool] = None, settings: Optional[Settings] = None):
        """
        Initialize the database session manager.

        Args:
            use_database: Force database on/off. If None, uses settings.
            settings: Optional custom settings object (for testing)
        """
        super().__init__()

        self.settings = settings or get_settings()
        self._use_database = use_database if use_database is not None else self.settings.use_sqlite

        # Initialize database if needed
        if self._use_database:
            ensure_database(self.settings)
            logger.info("Database session manager initialized with SQLite backend")
        else:
            logger.info("Database session manager initialized in file-only mode")

    def create_session(
        self,
        session_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Create a new session (dual-write: file + database).

        Args:
            session_id: Optional custom session ID
            metadata: Optional metadata for the session

        Returns:
            Session dict
        """
        import uuid

        # Generate UUID only once
        if session_id is None:
            session_id = str(uuid.uuid4())

        # Create session dict
        now = datetime.now().isoformat()
        session = {
            "session_id": session_id,
            "messages": [],
            "metadata": metadata or {},
            "created_at": now,
            "updated_at": now,
        }

        # Create in database first if enabled
        if self._use_database:
            try:
                with get_db_session(self.settings) as db_session:
                    repo = MemoryRepository(db_session)
                    repo.create_session(
                        session_id=session_id,
                        metadata=metadata,
                    )
                    logger.debug(f"Session {session_id} created in database")
            except Exception as e:
                logger.error(f"Failed to create session in database: {e}")
                # If database creation fails, still create file
                # This maintains backward compatibility

        # Save to file (call parent's save_session directly)
        self.save_session(session)

        return session

    def load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Load a session by ID (prioritize database, fallback to file).

        Args:
            session_id: Session ID

        Returns:
            Session dict or None if not found
        """
        # Try database first if enabled
        if self._use_database:
            try:
                with get_db_session(self.settings) as db_session:
                    from app.models.database import SessionDB, MessageDB

                    session_db = db_session.query(SessionDB).filter(
                        SessionDB.session_id == session_id
                    ).first()

                    if session_db:
                        # Load messages from database
                        messages_db = db_session.query(MessageDB).filter(
                            MessageDB.session_id == session_id
                        ).order_by(MessageDB.timestamp).all()

                        # Convert to dict format (for backward compatibility)
                        session = {
                            "session_id": session_db.session_id,
                            "metadata": self._parse_json(session_db.meta_data) if session_db.meta_data else {},
                            "created_at": session_db.created_at.isoformat(),
                            "updated_at": session_db.updated_at.isoformat(),
                            "messages": [
                                {
                                    "role": msg.role,
                                    "content": msg.content,
                                    "timestamp": msg.timestamp.isoformat(),
                                    "tool_calls": self._parse_json(msg.extra_data) if msg.extra_data else None,
                                }
                                for msg in messages_db
                            ],
                        }
                        logger.debug(f"Loaded session {session_id} from database")
                        return session
            except Exception as e:
                logger.warning(f"Failed to load session from database: {e}")

        # Fallback to file-based loading
        return super().load_session(session_id)

    def save_session(self, session: Dict[str, Any]) -> None:
        """
        Save a session (dual-write: file + database).

        Args:
            session: Session dict

        Raises:
            ValueError: If session is invalid
        """
        # Save to file (parent class)
        super().save_session(session)

        # Also update in database if enabled
        if self._use_database:
            try:
                with get_db_session(self.settings) as db_session:
                    from app.models.database import SessionDB

                    repo = MemoryRepository(db_session)

                    # Check if session exists in database
                    session_db = db_session.query(SessionDB).filter(
                        SessionDB.session_id == session["session_id"]
                    ).first()

                    if session_db:
                        # Update timestamp
                        repo.update_session_timestamp(session["session_id"])
                    else:
                        # Create new session in database
                        repo.create_session(
                            session_id=session["session_id"],
                            metadata=session.get("metadata"),
                        )

                    logger.debug(f"Session {session['session_id']} also updated in database")
            except Exception as e:
                logger.error(f"Failed to update session in database: {e}")

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_calls: Optional[List[Dict]] = None,
        images: Optional[List[Dict]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Add a message to a session (dual-write: file + database).

        Args:
            session_id: Session ID
            role: Message role (user/assistant/tool)
            content: Message content
            tool_calls: Optional tool calls
            images: Optional image attachments

        Returns:
            Updated session or None if session not found
        """
        # Load session (will try database first)
        session = self.load_session(session_id)

        if not session:
            logger.warning(f"Session not found: {session_id}")
            return None

        # Create message dict
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }

        if tool_calls:
            message["tool_calls"] = tool_calls

        if images:
            message["images"] = images

        # Add to session
        session["messages"].append(message)

        # Save session (dual-write)
        self.save_session(session)

        # Also save message to database separately if enabled
        if self._use_database:
            try:
                with get_db_session(self.settings) as db_session:
                    repo = MemoryRepository(db_session)

                    extra_data = {}
                    if tool_calls:
                        extra_data["tool_calls"] = tool_calls
                    if images:
                        extra_data["images"] = images

                    repo.create_message(
                        session_id=session_id,
                        role=role,
                        content=content,
                        extra_data=extra_data if extra_data else None,
                    )

                    logger.debug(f"Message also stored in database")
            except Exception as e:
                logger.error(f"Failed to create message in database: {e}")

        return session

    def list_sessions(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        List all sessions (prioritize database, fallback to files).

        Args:
            limit: Maximum number of sessions to return
            offset: Number of sessions to skip

        Returns:
            List of session dicts
        """
        # Try database first if enabled
        if self._use_database:
            try:
                with get_db_session(self.settings) as db_session:
                    from app.models.database import SessionDB

                    sessions_db = db_session.query(SessionDB).order_by(
                        SessionDB.updated_at.desc()
                    ).limit(limit).offset(offset).all()

                    if sessions_db:
                        # Get message count for each session
                        from sqlalchemy import func
                        from app.models.database import MessageDB

                        message_counts = db_session.query(
                            MessageDB.session_id,
                            func.count(MessageDB.message_id).label("count")
                        ).group_by(MessageDB.session_id).all()

                        count_map = {sid: count for sid, count in message_counts}

                        sessions = [
                            {
                                "session_id": s.session_id,
                                "metadata": self._parse_json(s.meta_data) if s.meta_data else {},
                                "created_at": s.created_at.isoformat(),
                                "updated_at": s.updated_at.isoformat(),
                                "message_count": count_map.get(s.session_id, 0),
                            }
                            for s in sessions_db
                        ]

                        logger.debug(f"Listed {len(sessions)} sessions from database")
                        return sessions
            except Exception as e:
                logger.warning(f"Failed to list sessions from database: {e}")

        # Fallback to file-based listing
        sessions = []
        session_files = list(self.sessions_dir.glob("*.json"))

        # Sort by modification time
        session_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        # Apply pagination
        start = offset
        end = offset + limit
        for session_file in session_files[start:end]:
            try:
                session = self.load_session(session_file.stem)
                if session:
                    session["message_count"] = len(session.get("messages", []))
                    sessions.append(session)
            except Exception as e:
                logger.warning(f"Failed to load session {session_file.name}: {e}")

        return sessions

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session (file + database).

        Args:
            session_id: Session ID

        Returns:
            True if deleted, False if not found
        """
        if "/" in session_id or "\\" in session_id or ".." in session_id:
            logger.warning(f"Invalid session_id rejected: {session_id}")
            return False
        deleted = False

        # Delete from file
        session_file = self.sessions_dir / f"{session_id}.json"
        if session_file.exists():
            session_file.unlink()
            deleted = True
            logger.info(f"Deleted session file: {session_id}")

        # Also delete from database if enabled
        if self._use_database:
            try:
                with get_db_session(self.settings) as db_session:
                    from app.models.database import SessionDB

                    session_db = db_session.query(SessionDB).filter(
                        SessionDB.session_id == session_id
                    ).first()

                    if session_db:
                        db_session.delete(session_db)
                        deleted = True
                        logger.info(f"Deleted session from database: {session_id}")
            except Exception as e:
                logger.error(f"Failed to delete session from database: {e}")

        return deleted

    @staticmethod
    def _parse_json(json_str: Optional[str]) -> Any:
        """Parse JSON string safely."""
        if not json_str:
            return None
        try:
            import json
            return json.loads(json_str)
        except Exception:
            return None


# Singleton instance
_session_manager_instance: Optional[DatabaseSessionManager] = None


def get_session_manager() -> DatabaseSessionManager:
    """
    Get the global session manager instance.

    Returns:
        DatabaseSessionManager instance
    """
    global _session_manager_instance

    if _session_manager_instance is None:
        _session_manager_instance = DatabaseSessionManager()

    return _session_manager_instance
