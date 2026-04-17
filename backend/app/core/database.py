"""
Database Manager - SQLite Database Initialization and Management

This module handles database initialization, connection management,
and provides utility functions for database operations.
"""

import logging
import os
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.models.database import Base
from app.config import get_settings, Settings

logger = logging.getLogger(__name__)


# Global engine and session factory
_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = None


def get_database_path(settings: Optional[Settings] = None) -> Path:
    """
    Get the database file path.

    Args:
        settings: Application settings (uses default if not provided)

    Returns:
        Path to the SQLite database file
    """
    if settings is None:
        settings = get_settings()

    db_path = Path(settings.memory_db_path)

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    return db_path


def get_engine(settings: Optional[Settings] = None) -> Engine:
    """
    Get or create the database engine.

    Args:
        settings: Application settings

    Returns:
        SQLAlchemy engine instance
    """
    global _engine

    if _engine is None:
        if settings is None:
            settings = get_settings()

        db_path = get_database_path(settings)

        # Create SQLite engine with connection pooling
        # StaticPool is recommended for SQLite to avoid thread-safety issues
        _engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={
                "check_same_thread": False,  # Allow multi-threading
            },
            poolclass=StaticPool,  # Single connection pool
            echo=settings.debug,  # Log SQL queries in debug mode
        )

        logger.info(f"Database engine created: {db_path}")

    return _engine


def init_database(settings: Optional[Settings] = None) -> None:
    """
    Initialize the database by creating all tables.

    Args:
        settings: Application settings
    """
    try:
        engine = get_engine(settings)

        # Create all tables
        Base.metadata.create_all(engine)

        logger.info("Database initialized successfully")

        # Log table information
        from app.models.database import SessionDB, MessageDB, MemoryDB, UserProfileDB, MemoryMetadataDB
        logger.info(f"Tables created: sessions, messages, memories, user_profile, memory_metadata")

    except Exception as e:
        logger.error(f"Failed to initialize database: {e}", exc_info=True)
        raise


def get_session_factory(settings: Optional[Settings] = None) -> sessionmaker:
    """
    Get or create the session factory.

    Args:
        settings: Application settings

    Returns:
        SQLAlchemy session factory
    """
    global _session_factory

    if _session_factory is None:
        engine = get_engine(settings)
        _session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine
        )

    return _session_factory


@contextmanager
def get_db_session(settings: Optional[Settings] = None):
    """
    Context manager for database sessions.

    Usage:
        with get_db_session() as session:
            session.query(...).all()

    Args:
        settings: Application settings

    Yields:
        SQLAlchemy session
    """
    session_factory = get_session_factory(settings)
    session = session_factory()

    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database session error: {e}", exc_info=True)
        raise
    finally:
        session.close()


def get_session(settings: Optional[Settings] = None) -> Session:
    """
    Get a new database session (manual management).

    Warning: Remember to commit/rollback and close the session.

    Args:
        settings: Application settings

    Returns:
        SQLAlchemy session
    """
    session_factory = get_session_factory(settings)
    return session_factory()


def database_exists(settings: Optional[Settings] = None) -> bool:
    """
    Check if the database file exists.

    Args:
        settings: Application settings

    Returns:
        True if database file exists
    """
    db_path = get_database_path(settings)
    return db_path.exists()


def backup_database(backup_path: Optional[Path] = None, settings: Optional[Settings] = None) -> Path:
    """
    Create a backup of the database.

    Args:
        backup_path: Custom backup path (default: data/memory.db.backup)
        settings: Application settings

    Returns:
        Path to the backup file
    """
    import shutil
    from datetime import datetime

    db_path = get_database_path(settings)

    if backup_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = db_path.parent / f"{db_path.stem}.{timestamp}.backup"

    # Copy database file
    shutil.copy2(db_path, backup_path)

    logger.info(f"Database backup created: {backup_path}")

    return backup_path


def get_database_info(settings: Optional[Settings] = None) -> dict:
    """
    Get database information and statistics.

    Args:
        settings: Application settings

    Returns:
        Dictionary with database stats
    """
    from app.models.database import (
        SessionDB, MessageDB, MemoryDB,
        UserProfileDB, MemoryMetadataDB
    )

    db_path = get_database_path(settings)
    info = {
        "path": str(db_path),
        "exists": db_path.exists(),
        "size_bytes": db_path.stat().st_size if db_path.exists() else 0,
        "tables": {},
    }

    if db_path.exists():
        with get_db_session(settings) as session:
            info["tables"]["sessions"] = session.query(SessionDB).count()
            info["tables"]["messages"] = session.query(MessageDB).count()
            info["tables"]["memories"] = session.query(MemoryDB).count()
            info["tables"]["user_profile"] = session.query(UserProfileDB).count()
            info["tables"]["memory_metadata"] = session.query(MemoryMetadataDB).count()

    return info


# Convenience function to initialize database on import
def ensure_database(settings: Optional[Settings] = None) -> None:
    """
    Ensure database is initialized (creates if not exists).

    Args:
        settings: Application settings
    """
    if not database_exists(settings):
        init_database(settings)
        logger.info("Database created and initialized")
    else:
        logger.info("Database already exists, skipping initialization")


def reset_engine() -> None:
    """Reset the global engine and session factory.

    Used by tests to ensure clean state between test runs.
    """
    global _engine, _session_factory
    _engine = None
    _session_factory = None
    logger.debug("Database engine and session factory reset")
