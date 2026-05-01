"""
Memory Repository - Database operations for memory and session data.
"""

import json
import uuid
import logging
from typing import List, Optional, Any

from sqlalchemy.orm import Session

from app.models.database import (
    SessionDB,
    MessageDB,
    MemoryDB,
    UserProfileDB,
    MemoryMetadataDB,
)

logger = logging.getLogger(__name__)


class MemoryRepository:
    """Repository for CRUD operations on memory-related database tables."""

    def __init__(self, db_session: Session):
        self.db = db_session

    # -- Session operations --

    def create_session(
        self,
        session_id: str,
        metadata: Optional[dict] = None,
    ) -> SessionDB:
        session = SessionDB(
            session_id=session_id,
            meta_data=json.dumps(metadata) if metadata else None,
        )
        self.db.add(session)
        self.db.flush()
        return session

    def get_session(self, session_id: str) -> Optional[SessionDB]:
        return self.db.query(SessionDB).filter(
            SessionDB.session_id == session_id
        ).first()

    def update_session_timestamp(self, session_id: str) -> None:
        from datetime import datetime
        session = self.get_session(session_id)
        if session:
            session.updated_at = datetime.utcnow()
            self.db.flush()

    # -- Message operations --

    def create_message(
        self,
        session_id: str,
        role: str,
        content: str,
        timestamp: Any = None,
        extra_data: Optional[dict] = None,
    ) -> MessageDB:
        from datetime import datetime
        msg = MessageDB(
            message_id=str(uuid.uuid4()),
            session_id=session_id,
            role=role,
            content=content,
            timestamp=timestamp or datetime.utcnow(),
            extra_data=json.dumps(extra_data) if extra_data else None,
        )
        self.db.add(msg)
        self.db.flush()
        return msg

    # -- Memory operations --

    def create_memory(
        self,
        session_id: Optional[str],
        memory_type: str,
        content: str,
        confidence: float = 0.0,
        importance_score: float = 0.0,
    ) -> MemoryDB:
        memory = MemoryDB(
            memory_id=str(uuid.uuid4()),
            session_id=session_id,
            type=memory_type,
            content=content,
            confidence=confidence,
            importance_score=importance_score,
        )
        self.db.add(memory)
        self.db.flush()
        return memory

    def get_memories(
        self,
        memory_type: Optional[str] = None,
        min_confidence: float = 0.0,
        created_after: Any = None,
        limit: int = 50,
    ) -> List[MemoryDB]:
        query = self.db.query(MemoryDB)
        if memory_type:
            query = query.filter(MemoryDB.type == memory_type)
        if min_confidence > 0:
            query = query.filter(MemoryDB.confidence >= min_confidence)
        if created_after:
            query = query.filter(MemoryDB.created_at >= created_after)
        return query.order_by(MemoryDB.created_at.desc()).limit(limit).all()

    # -- Profile operations --

    def create_profile_entry(
        self,
        category: str,
        content: str,
        source_memory_id: Optional[str] = None,
    ) -> UserProfileDB:
        entry = UserProfileDB(
            profile_id=str(uuid.uuid4()),
            category=category,
            content=content,
            source_memory_id=source_memory_id,
        )
        self.db.add(entry)
        self.db.flush()
        return entry
