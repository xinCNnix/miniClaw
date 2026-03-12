"""
Memory Repository - Database Operations for Memory System

This module provides high-level database operations for sessions,
messages, and memories.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc

from app.models.database import SessionDB, MessageDB, MemoryDB, UserProfileDB, MemoryMetadataDB
from app.models.memory import Memory

logger = logging.getLogger(__name__)


class MemoryRepository:
    """
    Repository for memory-related database operations.

    This class provides methods for CRUD operations on sessions,
    messages, and memories.
    """

    def __init__(self, session: Session):
        """
        Initialize repository with a database session.

        Args:
            session: SQLAlchemy session
        """
        self.session = session

    # ========== Session Operations ==========

    def create_session(
        self,
        session_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> SessionDB:
        """
        Create a new session.

        Args:
            session_id: Optional custom session ID
            metadata: Optional session metadata

        Returns:
            Created session object
        """
        if session_id is None:
            session_id = str(uuid.uuid4())

        session_db = SessionDB(
            session_id=session_id,
            metadata=self._serialize_json(metadata),
        )

        self.session.add(session_db)
        self.session.flush()

        logger.debug(f"Created session: {session_id}")
        return session_db

    def get_session(self, session_id: str) -> Optional[SessionDB]:
        """
        Get a session by ID.

        Args:
            session_id: Session ID

        Returns:
            Session object or None
        """
        return self.session.query(SessionDB).filter(
            SessionDB.session_id == session_id
        ).first()

    def update_session_timestamp(self, session_id: str) -> bool:
        """
        Update session's updated_at timestamp.

        Args:
            session_id: Session ID

        Returns:
            True if updated, False if not found
        """
        session_db = self.get_session(session_id)
        if session_db:
            session_db.updated_at = datetime.utcnow()
            self.session.flush()
            return True
        return False

    def list_sessions(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> List[SessionDB]:
        """
        List sessions with pagination.

        Args:
            limit: Maximum number of sessions to return
            offset: Number of sessions to skip

        Returns:
            List of session objects
        """
        return self.session.query(SessionDB).order_by(
            desc(SessionDB.updated_at)
        ).limit(limit).offset(offset).all()

    # ========== Message Operations ==========

    def create_message(
        self,
        session_id: str,
        role: str,
        content: str,
        timestamp: Optional[datetime] = None,
        extra_data: Optional[Dict] = None,
    ) -> MessageDB:
        """
        Create a new message.

        Args:
            session_id: Session ID
            role: Message role (user/assistant/system)
            content: Message content
            timestamp: Message timestamp (default: now)
            extra_data: Optional extra data (images, etc.)

        Returns:
            Created message object
        """
        message_db = MessageDB(
            message_id=str(uuid.uuid4()),
            session_id=session_id,
            role=role,
            content=content,
            timestamp=timestamp or datetime.utcnow(),
            extra_data=self._serialize_json(extra_data),
        )

        self.session.add(message_db)
        self.session.flush()

        # Update session timestamp
        self.update_session_timestamp(session_id)

        logger.debug(f"Created message in session {session_id}")
        return message_db

    def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
    ) -> List[MessageDB]:
        """
        Get all messages for a session.

        Args:
            session_id: Session ID
            limit: Optional maximum number of messages

        Returns:
            List of message objects
        """
        query = self.session.query(MessageDB).filter(
            MessageDB.session_id == session_id
        ).order_by(MessageDB.timestamp)

        if limit:
            query = query.limit(limit)

        return query.all()

    # ========== Memory Operations ==========

    def create_memory(
        self,
        session_id: str,
        memory_type: str,
        content: str,
        confidence: float,
        vector_id: Optional[str] = None,
        importance_score: float = 0.0,
    ) -> MemoryDB:
        """
        Create a new memory.

        Args:
            session_id: Session ID
            memory_type: Memory type (fact/preference/context/pattern)
            content: Memory content
            confidence: Confidence score (0.0-1.0)
            vector_id: Optional vector store ID
            importance_score: Computed importance score

        Returns:
            Created memory object
        """
        memory_db = MemoryDB(
            memory_id=str(uuid.uuid4()),
            session_id=session_id,
            type=memory_type,
            content=content,
            confidence=confidence,
            created_at=datetime.utcnow(),
            vector_id=vector_id,
            importance_score=importance_score,
            md_included=False,  # Will be updated during MD sync
        )

        self.session.add(memory_db)
        self.session.flush()

        logger.debug(f"Created memory: {memory_db.memory_id}")
        return memory_db

    def get_memories(
        self,
        session_id: Optional[str] = None,
        memory_type: Optional[str] = None,
        min_confidence: float = 0.0,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[MemoryDB]:
        """
        Query memories with filters.

        Args:
            session_id: Optional session filter
            memory_type: Optional type filter
            min_confidence: Minimum confidence threshold
            created_after: Optional start date
            created_before: Optional end date
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of memory objects
        """
        query = self.session.query(MemoryDB)

        # Apply filters
        if session_id:
            query = query.filter(MemoryDB.session_id == session_id)

        if memory_type:
            query = query.filter(MemoryDB.type == memory_type)

        if min_confidence > 0:
            query = query.filter(MemoryDB.confidence >= min_confidence)

        if created_after:
            query = query.filter(MemoryDB.created_at >= created_after)

        if created_before:
            query = query.filter(MemoryDB.created_at <= created_before)

        # Order by confidence and creation time
        query = query.order_by(
            desc(MemoryDB.confidence),
            desc(MemoryDB.created_at)
        )

        return query.limit(limit).offset(offset).all()

    def get_memories_for_md(
        self,
        days: int = 30,
        min_confidence: float = 0.7,
        max_items: int = 50,
        memory_type: Optional[str] = None,
    ) -> List[MemoryDB]:
        """
        Get memories suitable for Markdown file generation.

        Args:
            days: Number of days to look back
            min_confidence: Minimum confidence threshold
            max_items: Maximum number of items per type
            memory_type: Optional memory type filter

        Returns:
            List of memory objects
        """
        since_date = datetime.utcnow() - timedelta(days=days)

        query = self.session.query(MemoryDB).filter(
            and_(
                MemoryDB.created_at >= since_date,
                MemoryDB.confidence >= min_confidence,
            )
        )

        if memory_type:
            query = query.filter(MemoryDB.type == memory_type)

        return query.order_by(
            desc(MemoryDB.confidence),
            desc(MemoryDB.created_at)
        ).limit(max_items).all()

    def update_memory_md_included(
        self,
        memory_ids: List[str],
        included: bool = True,
    ) -> int:
        """
        Update md_included flag for memories.

        Args:
            memory_ids: List of memory IDs
            included: Whether these memories are included in MD

        Returns:
            Number of updated records
        """
        count = self.session.query(MemoryDB).filter(
            MemoryDB.memory_id.in_(memory_ids)
        ).update(
            {"md_included": included},
            synchronize_session=False,
        )

        self.session.flush()
        return count

    def count_memories(
        self,
        memory_type: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> int:
        """
        Count memories with optional filters.

        Args:
            memory_type: Optional memory type filter
            session_id: Optional session filter

        Returns:
            Count of memories
        """
        query = self.session.query(MemoryDB)

        if memory_type:
            query = query.filter(MemoryDB.type == memory_type)

        if session_id:
            query = query.filter(MemoryDB.session_id == session_id)

        return query.count()

    # ========== User Profile Operations ==========

    def create_profile_entry(
        self,
        category: str,
        content: str,
        source_memory_id: Optional[str] = None,
    ) -> UserProfileDB:
        """
        Create a user profile entry.

        Args:
            category: Profile category
            content: Profile content
            source_memory_id: Optional source memory ID

        Returns:
            Created profile entry
        """
        profile_db = UserProfileDB(
            profile_id=str(uuid.uuid4()),
            category=category,
            content=content,
            source_memory_id=source_memory_id,
        )

        self.session.add(profile_db)
        self.session.flush()

        logger.debug(f"Created profile entry: {profile_db.profile_id}")
        return profile_db

    def get_profile_entries(
        self,
        category: Optional[str] = None,
        limit: int = 100,
    ) -> List[UserProfileDB]:
        """
        Get user profile entries.

        Args:
            category: Optional category filter
            limit: Maximum number of entries

        Returns:
            List of profile entries
        """
        query = self.session.query(UserProfileDB)

        if category:
            query = query.filter(UserProfileDB.category == category)

        return query.order_by(
            desc(UserProfileDB.updated_at)
        ).limit(limit).all()

    # ========== Metadata Operations ==========

    def set_metadata(self, key: str, value: Any) -> None:
        """
        Set a metadata value.

        Args:
            key: Metadata key
            value: Metadata value (will be JSON serialized)
        """
        metadata = self.session.query(MemoryMetadataDB).filter(
            MemoryMetadataDB.key == key
        ).first()

        serialized_value = self._serialize_json(value)

        if metadata:
            metadata.value = serialized_value
            metadata.updated_at = datetime.utcnow()
        else:
            metadata = MemoryMetadataDB(
                metadata_id=str(uuid.uuid4()),
                key=key,
                value=serialized_value,
            )
            self.session.add(metadata)

        self.session.flush()

    def get_metadata(self, key: str) -> Optional[Any]:
        """
        Get a metadata value.

        Args:
            key: Metadata key

        Returns:
            Metadata value or None
        """
        metadata = self.session.query(MemoryMetadataDB).filter(
            MemoryMetadataDB.key == key
        ).first()

        if metadata:
            return self._deserialize_json(metadata.value)

        return None

    # ========== Utility Methods ==========

    @staticmethod
    def _serialize_json(data: Any) -> Optional[str]:
        """Convert data to JSON string."""
        if data is None:
            return None
        import json
        return json.dumps(data, ensure_ascii=False)

    @staticmethod
    def _deserialize_json(json_str: str) -> Any:
        """Parse JSON string to Python object."""
        import json
        return json.loads(json_str)

    @staticmethod
    def memory_db_to_model(memory_db: MemoryDB) -> Memory:
        """
        Convert MemoryDB to Memory model.

        Args:
            memory_db: Database memory object

        Returns:
            Memory model
        """
        return Memory(
            memory_id=memory_db.memory_id,
            session_id=memory_db.session_id,
            type=memory_db.type,
            content=memory_db.content,
            confidence=memory_db.confidence,
            timestamp=memory_db.created_at.isoformat(),
        )
