"""
Memory Manager - Coordinator for all memory operations.

This module provides the main interface for memory extraction, storage,
and retrieval, coordinating between extractor, RAG engine, and updaters.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.models.memory import Memory, MemoryExtractionResult, MemorySearchResult
from app.memory.extractor import MemoryExtractor, get_memory_extractor
from app.memory.session import get_session_manager, SessionManager
from app.core.rag_engine import RAGEngine, get_rag_engine
from app.config import get_settings

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    Memory system coordinator.

    This class manages all memory operations including:
    - Extracting memories from conversations
    - Storing conversations in vector store
    - Semantic search of conversation history
    - Updating user profile (USER.md)
    - Updating long-term memory (MEMORY.md)
    """

    def __init__(
        self,
        extractor: MemoryExtractor | None = None,
        rag_engine: RAGEngine | None = None,
        session_manager: SessionManager | None = None,
    ):
        """
        Initialize the memory manager.

        Args:
            extractor: Optional memory extractor instance
            rag_engine: Optional RAG engine instance
            session_manager: Optional session manager instance
        """
        self.extractor = extractor or get_memory_extractor()
        self.rag_engine = rag_engine or get_rag_engine()
        self.session_manager = session_manager or get_session_manager()
        self.settings = get_settings()

    async def extract_and_store(self, session_id: str) -> MemoryExtractionResult:
        """
        Extract memories from a session and store them (main entry point).

        This is the primary method for memory extraction. It:
        1. Extracts structured memories using LLM
        2. Stores conversation in vector store for semantic search
        3. Updates USER.md with new preferences
        4. Updates MEMORY.md with long-term memories

        Args:
            session_id: Session ID to process

        Returns:
            MemoryExtractionResult with extracted memories

        Note:
            This method is designed to be run as a background task.
            Failures are logged but don't affect the chat response.
        """
        try:
            logger.info(f"Starting memory extraction for session: {session_id}")

            # Step 1: Extract memories using LLM
            extraction_result = await self.extractor.extract(session_id)

            if not extraction_result.memories:
                logger.info(f"No memories extracted from session {session_id}")
                return extraction_result

            logger.info(
                f"Extracted {len(extraction_result.memories)} memories, "
                f"summary: {extraction_result.summary[:100]}..."
            )

            # Step 2: Store conversation in vector store
            if self.settings.enable_semantic_search:
                await self.store_conversation_vector(session_id)
                logger.info(f"Stored conversation in vector store: {session_id}")

            # Step 3: Update user profile (if enabled)
            if self.settings.enable_user_profile_learning:
                await self.update_user_profile(session_id, extraction_result.memories)
                logger.info(f"Updated user profile from session {session_id}")

            # Step 4: Update long-term memory (if enabled)
            if self.settings.enable_long_term_memory:
                await self.update_long_term_memory(extraction_result.memories)
                logger.info(f"Updated long-term memory from session {session_id}")

            return extraction_result

        except Exception as e:
            logger.error(f"Memory extraction failed for session {session_id}: {e}", exc_info=True)
            # Return empty result on failure
            return MemoryExtractionResult(memories=[], summary="", topics=[])

    async def store_conversation_vector(self, session_id: str) -> None:
        """
        Store conversation in vector store for semantic search.

        Args:
            session_id: Session ID to store
        """
        session = self.session_manager.load_session(session_id)

        if not session:
            logger.warning(f"Session not found for vector storage: {session_id}")
            return

        messages = session.get("messages", [])

        if not messages:
            logger.warning(f"No messages in session for vector storage: {session_id}")
            return

        # Use RAG engine's conversation indexing
        await self.rag_engine.index_conversation(session_id, messages)

    async def search_relevant_history(
        self,
        query: str,
        top_k: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search of conversation history.

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of relevant conversation chunks
        """
        try:
            results = await self.rag_engine.search_conversations(query, top_k=top_k)

            # Format results
            formatted = []
            for result in results:
                formatted.append({
                    "content": result.get("content", ""),
                    "session_id": result.get("metadata", {}).get("session_id", ""),
                    "similarity": result.get("score", 0.0),
                })

            return formatted

        except Exception as e:
            logger.error(f"Semantic search failed: {e}", exc_info=True)
            return []

    async def update_user_profile(self, session_id: str, memories: List[Memory]) -> None:
        """
        Update USER.md with new preferences.

        Args:
            session_id: Session ID
            memories: Extracted memories
        """
        # Filter for preference memories only
        preferences = [m for m in memories if m.type == "preference"]

        if not preferences:
            return

        # Import here to avoid circular dependency
        from app.memory.profile_updater import UserProfileUpdater

        updater = UserProfileUpdater()
        await updater.update_from_memories(preferences)

    async def update_long_term_memory(self, memories: List[Memory]) -> None:
        """
        Update MEMORY.md with long-term memories.

        Args:
            memories: Extracted memories
        """
        # Filter for fact, context, and pattern memories
        long_term_memories = [
            m for m in memories
            if m.type in ["fact", "context", "pattern"]
            and m.confidence >= self.settings.memory_min_confidence
        ]

        if not long_term_memories:
            return

        # Import here to avoid circular dependency
        from app.memory.long_term_updater import LongTermMemoryUpdater

        updater = LongTermMemoryUpdater()
        await updater.update_from_memories(long_term_memories)


# Singleton instance
_memory_manager_instance: MemoryManager | None = None


def get_memory_manager() -> MemoryManager:
    """
    Get the global memory manager instance.

    Returns:
        MemoryManager instance
    """
    global _memory_manager_instance

    if _memory_manager_instance is None:
        _memory_manager_instance = MemoryManager()

    return _memory_manager_instance
