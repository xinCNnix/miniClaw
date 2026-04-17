"""
Database Models - SQLAlchemy ORM Models for Memory System

This module defines all database models for the SQLite memory storage.
"""

from sqlalchemy import Column, String, Integer, Float, DateTime, Text, Boolean, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class SessionDB(Base):
    """
    Database model for conversation sessions.

    Attributes:
        session_id: Primary key, UUID
        created_at: Session creation timestamp
        updated_at: Last update timestamp
        meta_data: JSON string with additional session data
    """
    __tablename__ = "sessions"

    session_id = Column(String(36), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    meta_data = Column(Text, nullable=True)  # JSON string

    # Relationships
    messages = relationship("MessageDB", back_populates="session", cascade="all, delete-orphan")
    memories = relationship("MemoryDB", back_populates="session", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_sessions_created_at", "created_at"),
        Index("idx_sessions_updated_at", "updated_at"),
    )


class MessageDB(Base):
    """
    Database model for chat messages.

    Attributes:
        message_id: Primary key
        session_id: Foreign key to sessions
        role: Message role (user/assistant/system)
        content: Message content
        timestamp: Message timestamp
        extra_data: JSON string with additional data (images, etc.)
    """
    __tablename__ = "messages"

    message_id = Column(String(36), primary_key=True)
    session_id = Column(String(36), ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    extra_data = Column(Text, nullable=True)  # JSON string for images, etc.

    # Relationships
    session = relationship("SessionDB", back_populates="messages")

    __table_args__ = (
        Index("idx_messages_session_id", "session_id"),
        Index("idx_messages_timestamp", "timestamp"),
    )


class MemoryDB(Base):
    """
    Database model for extracted memories.

    Attributes:
        memory_id: Primary key, UUID
        session_id: Foreign key to sessions
        type: Memory type (fact/preference/context/pattern)
        content: Memory content
        confidence: Confidence score (0.0-1.0)
        created_at: Extraction timestamp
        vector_id: ID in vector store (Chroma)
        importance_score: Computed importance (0.0-1.0)
        md_included: Whether this memory is included in MD files
    """
    __tablename__ = "memories"

    memory_id = Column(String(36), primary_key=True)
    session_id = Column(String(36), ForeignKey("sessions.session_id", ondelete="SET NULL"), nullable=True)
    type = Column(String(20), nullable=False)  # fact, preference, context, pattern
    content = Column(Text, nullable=False)
    confidence = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    vector_id = Column(String(100), nullable=True)  # Chroma vector ID
    importance_score = Column(Float, default=0.0, nullable=False)
    md_included = Column(Boolean, default=False, nullable=False)

    # Relationships
    session = relationship("SessionDB", back_populates="memories")
    profile_entries = relationship("UserProfileDB", back_populates="source_memory")

    __table_args__ = (
        Index("idx_memories_session_id", "session_id"),
        Index("idx_memories_type", "type"),
        Index("idx_memories_confidence", "confidence"),
        Index("idx_memories_created_at", "created_at"),
        Index("idx_memories_md_included", "md_included"),
    )


class UserProfileDB(Base):
    """
    Database model for user profile entries.

    Attributes:
        profile_id: Primary key
        category: Profile category (communication_style/technical_preferences/etc)
        content: Profile content
        updated_at: Last update timestamp
        source_memory_id: Foreign key to the memory that generated this entry
    """
    __tablename__ = "user_profile"

    profile_id = Column(String(36), primary_key=True)
    category = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    source_memory_id = Column(String(36), ForeignKey("memories.memory_id", ondelete="SET NULL"), nullable=True)

    # Relationships
    source_memory = relationship("MemoryDB", back_populates="profile_entries")

    __table_args__ = (
        Index("idx_user_profile_category", "category"),
        Index("idx_user_profile_updated_at", "updated_at"),
    )


class MemoryMetadataDB(Base):
    """
    Database model for memory metadata tracking.

    This table tracks metadata for syncing with MD files.

    Attributes:
        metadata_id: Primary key
        key: Metadata key (last_md_sync/user_profile_count/etc)
        value: Metadata value (JSON string)
        updated_at: Last update timestamp
    """
    __tablename__ = "memory_metadata"

    metadata_id = Column(String(36), primary_key=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=False)  # JSON string
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_memory_metadata_key", "key"),
    )


# ============================================================================
# Memory Engine Models (Phase 2-3)
# ============================================================================


class EventLogDB(Base):
    """Append-only event log for the memory engine.

    Every conversation turn, tool call, and external source is recorded here.
    SHA256 hash field enforces dedup (红线1).

    source_type is a free-form string matching MemoryEvidence.source_type,
    so new skills don't require schema changes.
    """
    __tablename__ = "event_log"

    event_id = Column(String(100), primary_key=True)
    ts = Column(Float, nullable=False)
    session_id = Column(String(100), nullable=False, index=True)
    user_id = Column(String(100), nullable=False, default="")
    event_type = Column(String(30), nullable=False)  # user_msg, assistant_msg, tool_call, session_archived, ...
    source_type = Column(String(50), default="conversation")
    payload_json = Column(Text, nullable=False)
    hash = Column(String(64), nullable=False, unique=True)  # SHA256 dedup
    parent_id = Column(String(100), nullable=True)
    source_ref = Column(String(2000), nullable=True)  # URL / file_path / trace_id
    meta_json = Column(Text, default="{}")             # Extensible metadata (JSON dict)

    __table_args__ = (
        Index("idx_event_log_session_id", "session_id"),
        Index("idx_event_log_ts", "ts"),
        Index("idx_event_log_event_type", "event_type"),
    )


class WikiPageDB(Base):
    """Wiki page metadata (content stored in MD files).

    Consolidated from wiki/store.py raw SQL into ORM.
    """
    __tablename__ = "wiki_pages"

    page_id = Column(String(100), primary_key=True)
    title = Column(String(200), unique=True, nullable=False)
    aliases_json = Column(Text, default="[]")
    tags_json = Column(Text, default="[]")
    summary = Column(Text, default="")
    file_path = Column(String(500), nullable=True)
    content_hash = Column(String(64), nullable=True)
    evidence_json = Column(Text, default="[]")
    confidence = Column(Float, default=0.0)
    access_count = Column(Integer, default=0)
    source = Column(String(20), default="extracted")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_wiki_pages_title", "title"),
    )


class EntityProfileDB(Base):
    """Entity-centric memory — one row per entity (user, project, tool, etc.).

    Attributes are stored as a JSON dict with conflict tracking.
    """
    __tablename__ = "entity_profiles"

    entity_id = Column(String(200), primary_key=True)
    entity_type = Column(String(50), nullable=False)  # person, project, tool, concept
    name = Column(String(200), nullable=False)
    summary = Column(Text, default="")
    attributes_json = Column(Text, default="{}")
    last_updated = Column(Float, default=0.0)
    confidence = Column(Float, default=0.0)

    __table_args__ = (
        Index("idx_entity_profiles_type", "entity_type"),
        Index("idx_entity_profiles_name", "name"),
    )


class CaseRecordDB(Base):
    """Case memory — stores completed task trajectories for reuse.

    Extracted from execution logs (PEVR/ToT/Agent) at task completion.
    """
    __tablename__ = "case_records"

    case_id = Column(String(100), primary_key=True)
    ts = Column(Float, nullable=False)
    title = Column(String(500), nullable=False)
    context = Column(Text, default="")
    problem = Column(Text, default="")
    plan = Column(Text, default="")
    actions_json = Column(Text, default="[]")
    result = Column(Text, default="")
    reflection = Column(Text, default="")
    success_score = Column(Float, default=0.0)
    tags_json = Column(Text, default="[]")
    entities_json = Column(Text, default="[]")
    evidence_json = Column(Text, default="[]")

    __table_args__ = (
        Index("idx_case_records_ts", "ts"),
        Index("idx_case_records_success", "success_score"),
    )


class ProcedureDB(Base):
    """Procedural memory — reusable step-by-step procedures.

    Auto-extracted from successful task completions.
    """
    __tablename__ = "procedures"

    proc_id = Column(String(100), primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    trigger_conditions = Column(Text, default="")
    steps_json = Column(Text, default="[]")
    success_rate = Column(Float, default=0.0)
    last_used = Column(Float, default=0.0)

    __table_args__ = (
        Index("idx_procedures_name", "name"),
    )
