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
