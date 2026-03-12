"""
Database Memory Manager - Memory Management with SQLite Backend

This module extends the existing MemoryManager with database storage support.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from app.memory.memory_manager import MemoryManager
from app.config import get_settings, Settings
from app.core.database import get_db_session, ensure_database
from app.repositories.memory_repository import MemoryRepository
from app.generators.markdown_generator import MarkdownGenerator
from app.models.memory import Memory, MemoryExtractionResult

logger = logging.getLogger(__name__)


class DatabaseMemoryManager(MemoryManager):
    """
    Enhanced memory manager with database support.

    This manager extends the file-based MemoryManager with SQLite database
    storage, enabling efficient querying and Markdown file generation.
    """

    def __init__(
        self,
        use_database: Optional[bool] = None,
        auto_sync_md: Optional[bool] = None,
        settings: Optional[Settings] = None,
    ):
        """
        Initialize the database memory manager.

        Args:
            use_database: Force database on/off. If None, uses settings.
            auto_sync_md: Auto-sync Markdown files. If None, uses settings.
            settings: Optional custom settings object (for testing)
        """
        super().__init__()

        self.settings = settings or get_settings()
        self._use_database = use_database if use_database is not None else self.settings.use_sqlite
        self._auto_sync_md = auto_sync_md if auto_sync_md is not None else self.settings.md_auto_sync

        if self._use_database:
            ensure_database(self.settings)
            logger.info("Database memory manager initialized with SQLite backend")

        # Track MD sync counter
        self._memory_write_count = 0

    async def extract_and_store(self, session_id: str) -> MemoryExtractionResult:
        """
        Extract memories from a session and store them (database + MD files).

        This is the primary method for memory extraction. It:
        1. Extracts structured memories using LLM
        2. Stores memories in database (if enabled)
        3. Stores conversation in vector store
        4. Updates USER.md and MEMORY.md (if auto-sync enabled)

        Args:
            session_id: Session ID to process

        Returns:
            MemoryExtractionResult with extracted memories
        """
        # Step 1: Extract memories using LLM (parent class)
        extraction_result = await self.extractor.extract(session_id)

        if not extraction_result.memories:
            logger.info(f"No memories extracted from session {session_id}")
            return extraction_result

        logger.info(
            f"Extracted {len(extraction_result.memories)} memories from session {session_id}"
        )

        # Step 2: Store memories in database (if enabled)
        if self._use_database:
            await self._store_memories_in_db(session_id, extraction_result.memories)

        # Step 3: Store conversation in vector store
        if self.settings.enable_semantic_search:
            await self.store_conversation_vector(session_id)
            logger.info(f"Stored conversation in vector store: {session_id}")

        # Step 4: Update user profile (if enabled)
        if self.settings.enable_user_profile_learning:
            await self.update_user_profile(session_id, extraction_result.memories)
            logger.info(f"Updated user profile from session {session_id}")

        # Step 5: Update long-term memory (if enabled)
        if self.settings.enable_long_term_memory:
            await self.update_long_term_memory(extraction_result.memories)
            logger.info(f"Updated long-term memory from session {session_id}")

        # Step 6: Sync Markdown files (if auto-sync enabled)
        if self._use_database and self._auto_sync_md:
            self._memory_write_count += 1
            if self._memory_write_count >= self.settings.md_sync_interval:
                await self.sync_markdown_files()
                self._memory_write_count = 0

        return extraction_result

    async def _store_memories_in_db(
        self,
        session_id: str,
        memories: List[Memory],
    ) -> None:
        """
        Store extracted memories in database.

        Args:
            session_id: Session ID
            memories: List of extracted memories
        """
        try:
            with get_db_session(self.settings) as db_session:
                repo = MemoryRepository(db_session)

                for memory in memories:
                    # Calculate importance score
                    importance_score = self._calculate_importance(memory)

                    # Create memory in database
                    repo.create_memory(
                        session_id=session_id,
                        memory_type=memory.type,
                        content=memory.content,
                        confidence=memory.confidence,
                        importance_score=importance_score,
                    )

                logger.info(f"Stored {len(memories)} memories in database")

        except Exception as e:
            logger.error(f"Failed to store memories in database: {e}", exc_info=True)

    async def search_relevant_history(
        self,
        query: str,
        top_k: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search of conversation history.

        Uses vector store (Chroma) for semantic search, then enriches
        results with database metadata if available.

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of relevant conversation chunks
        """
        # Use parent class method (vector store search)
        results = await super().search_relevant_history(query, top_k)

        # Enrich with database metadata if enabled
        if self._use_database and results:
            try:
                with get_db_session(self.settings) as db_session:
                    repo = MemoryRepository(db_session)

                    for result in results:
                        session_id = result.get("session_id")
                        if session_id:
                            # Get additional session metadata from database
                            session = repo.get_session(session_id)
                            if session:
                                result["session_metadata"] = session.meta_data

            except Exception as e:
                logger.warning(f"Failed to enrich search results: {e}")

        return results

    async def search_memories(
        self,
        query_type: Optional[str] = None,
        min_confidence: float = 0.0,
        days: int = 90,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Search memories in database by type, confidence, and time.

        Args:
            query_type: Optional memory type filter
            min_confidence: Minimum confidence threshold
            days: Number of days to look back
            limit: Maximum number of results

        Returns:
            List of memory dicts
        """
        if not self._use_database:
            logger.warning("Database not enabled, memory search not available")
            return []

        try:
            from datetime import timedelta

            since_date = None if days <= 0 else (
                datetime.now() - timedelta(days=days)
            )

            with get_db_session(self.settings) as db_session:
                repo = MemoryRepository(db_session)

                memories_db = repo.get_memories(
                    memory_type=query_type,
                    min_confidence=min_confidence,
                    created_after=since_date,
                    limit=limit,
                )

                # Convert to dicts
                memories = [
                    {
                        "memory_id": m.memory_id,
                        "session_id": m.session_id,
                        "type": m.type,
                        "content": m.content,
                        "confidence": m.confidence,
                        "created_at": m.created_at.isoformat(),
                        "importance": m.importance_score,
                    }
                    for m in memories_db
                ]

                logger.info(f"Found {len(memories)} memories in database")
                return memories

        except Exception as e:
            logger.error(f"Failed to search memories: {e}", exc_info=True)
            return []

    async def update_user_profile(self, session_id: str, memories: List[Memory]) -> None:
        """
        Update USER.md with new preferences (database + MD file).

        Args:
            session_id: Session ID
            memories: Extracted memories
        """
        # Filter for preference memories only
        preferences = [m for m in memories if m.type == "preference"]

        if not preferences:
            return

        # Store in database if enabled
        if self._use_database:
            try:
                with get_db_session(self.settings) as db_session:
                    repo = MemoryRepository(db_session)

                    # Categorize preferences
                    categories = self._categorize_preferences(preferences)

                    # Create profile entries
                    for category, prefs in categories.items():
                        for pref in prefs[:3]:  # Top 3 per category
                            repo.create_profile_entry(
                                category=category,
                                content=pref.content,
                                source_memory_id=pref.memory_id,
                            )

                    logger.info(f"Updated {len(preferences)} preferences in database")

            except Exception as e:
                logger.error(f"Failed to update user profile in database: {e}")

        # Update USER.md file (parent class)
        await super().update_user_profile(session_id, memories)

    async def update_long_term_memory(self, memories: List[Memory]) -> None:
        """
        Update MEMORY.md with long-term memories (database + MD file).

        Args:
            memories: Extracted memories
        """
        # Parent class handles MD file update
        await super().update_long_term_memory(memories)

        # Database is already updated in _store_memories_in_db
        logger.info("Long-term memories stored in database")

    async def sync_markdown_files(self) -> None:
        """
        Synchronize USER.md and MEMORY.md from database.

        This method regenerates both Markdown files from the database,
        applying time and confidence filters.
        """
        if not self._use_database:
            logger.warning("Database not enabled, cannot sync Markdown files")
            return

        try:
            with get_db_session(self.settings) as db_session:
                generator = MarkdownGenerator(db_session, self.settings)
                generator.sync_markdown_files()

            logger.info("Markdown files synchronized from database")

        except Exception as e:
            logger.error(f"Failed to sync Markdown files: {e}", exc_info=True)

    def _calculate_importance(self, memory: Memory) -> float:
        """
        Calculate importance score for a memory.

        Args:
            memory: Memory object

        Returns:
            Importance score (0.0-1.0)
        """
        # Base importance from confidence
        importance = memory.confidence

        # Boost based on type
        type_boosts = {
            "preference": 0.1,
            "fact": 0.05,
            "context": 0.15,
            "pattern": 0.2,
        }

        importance += type_boosts.get(memory.type, 0.0)

        # Clamp to [0, 1]
        return max(0.0, min(1.0, importance))

    @staticmethod
    def _categorize_preferences(preferences: List[Memory]) -> Dict[str, List[Memory]]:
        """Categorize preference memories."""
        categories: Dict[str, List[Memory]] = {}

        for pref in preferences:
            content_lower = pref.content.lower()

            if any(word in content_lower for word in ["沟通", "交流", "communication"]):
                cat = "communication_style"
            elif any(word in content_lower for word in ["技术", "代码", "technical"]):
                cat = "technical_preferences"
            elif any(word in content_lower for word in ["工作", "效率", "work"]):
                cat = "work_style"
            else:
                cat = "other"

            if cat not in categories:
                categories[cat] = []
            categories[cat].append(pref)

        return categories


# Singleton instance
_memory_manager_instance: Optional[DatabaseMemoryManager] = None


def get_memory_manager() -> DatabaseMemoryManager:
    """
    Get the global memory manager instance.

    Returns:
        DatabaseMemoryManager instance
    """
    global _memory_manager_instance

    if _memory_manager_instance is None:
        _memory_manager_instance = DatabaseMemoryManager()

    return _memory_manager_instance
