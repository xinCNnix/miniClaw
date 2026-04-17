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
                # Don't return early - still need to index conversation for semantic search
            else:
                logger.info(
                    f"Extracted {len(extraction_result.memories)} memories, "
                    f"summary: {extraction_result.summary[:100]}..."
                )

            # Step 2: Store conversation in vector store (always do this, even if extraction fails)
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

            # Step 5: Write to Wiki (if enabled)
            if self.settings.enable_wiki and extraction_result.memories:
                await self.write_to_wiki(session_id, extraction_result)
                logger.info(f"Wrote to Wiki from session {session_id}")

            # Step 6: Write to KG (if enabled)
            if self.settings.enable_kg and extraction_result.memories:
                await self.write_to_kg(session_id, extraction_result)
                logger.info(f"Wrote to KG from session {session_id}")

            return extraction_result

        except Exception as e:
            logger.error(f"Memory extraction failed for session {session_id}: {e}", exc_info=True)
            # Return empty result on failure
            return MemoryExtractionResult(memories=[], summary="", topics=[])

    async def store_conversation_vector(self, session_id: str) -> None:
        """
        Store conversation in vector store for semantic search.

        This method includes retry logic to handle cases where the embedding
        model is not yet ready (e.g., still warming up).

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

        # Retry logic for embedding model not ready
        max_retries = self.settings.vector_indexing_max_retries
        retry_delay = self.settings.vector_indexing_retry_delay

        for attempt in range(max_retries):
            try:
                # Use RAG engine's conversation indexing
                await self.rag_engine.index_conversation(session_id, messages)
                logger.info(f"Successfully indexed conversation for session {session_id}")
                return  # Success, exit retry loop

            except Exception as e:
                if attempt < max_retries - 1:
                    # Check if error is due to embedding model not ready
                    error_msg = str(e).lower()
                    if "embedding model not ready" in error_msg or "not ready" in error_msg:
                        logger.warning(
                            f"Embedding model not ready for indexing session {session_id} "
                            f"(attempt {attempt + 1}/{max_retries}), retrying in {retry_delay:.1f}s..."
                        )
                        import asyncio
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 1.5  # Exponential backoff
                        continue
                    else:
                        # Other errors, don't retry
                        logger.error(
                            f"Failed to index conversation for session {session_id}: {e}",
                            exc_info=True
                        )
                        break
                else:
                    # Final attempt failed
                    logger.error(
                        f"Failed to index conversation for session {session_id} after {max_retries} attempts: {e}",
                        exc_info=True
                    )

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

    async def write_to_wiki(self, session_id: str, extraction_result) -> None:
        """Write conversation content to LLM Wiki if appropriate.

        Args:
            session_id: Session ID
            extraction_result: MemoryExtractionResult from extractor
        """
        try:
            from app.memory.wiki.store import get_wiki_store
            from app.memory.wiki.write_judge import WikiWriteJudge

            wiki_store = get_wiki_store()
            await wiki_store.initialize()

            # Load conversation text
            session = self.session_manager.load_session(session_id)
            if not session:
                return

            messages = session.get("messages", [])
            conversation_text = "\n".join(
                f"{m.get('role', 'user')}: {m.get('content', '')}"
                for m in messages[-20:]  # Last 20 messages
            )

            if not conversation_text.strip():
                return

            # Get existing pages summary
            existing_pages_summary = await wiki_store.get_pages_summary()

            # Judge whether to write
            judge = WikiWriteJudge()
            decision = await judge.judge(conversation_text, existing_pages_summary)

            if not decision.should_write:
                logger.info(f"Wiki judge decided not to write for session {session_id}")
                return

            if decision.confidence < self.settings.wiki_write_threshold:
                logger.info(
                    f"Wiki write confidence {decision.confidence:.2f} "
                    f"below threshold {self.settings.wiki_write_threshold}"
                )
                return

            # Anti-hallucination validation
            if self.settings.wiki_evidence_required:
                await judge.validate_evidence(decision, conversation_text)

            if decision.is_new_page:
                # Create new page
                content = judge.build_new_page_content(decision)
                from app.memory.wiki.models import WikiPage

                page = WikiPage(
                    title=decision.title,
                    summary=decision.summary,
                    content=content,
                    tags=decision.tags,
                    aliases=decision.aliases,
                    confidence=decision.confidence,
                )
                await wiki_store.create_page(page)
                logger.info(f"Wiki page created: {decision.title}")
            else:
                # Update existing page
                if decision.page_id:
                    await wiki_store.update_page(decision.page_id, decision.ops)
                    # Check if consolidation needed
                    await wiki_store.consolidate_page(decision.page_id)
                    logger.info(f"Wiki page updated: {decision.page_id}")

        except Exception as e:
            logger.error(f"Wiki write failed for session {session_id}: {e}", exc_info=True)

    async def write_to_kg(self, session_id: str, extraction_result) -> None:
        """Write conversation content to Knowledge Graph.

        Uses the existing KGWritePipeline which orchestrates:
        extractor → entity_resolver → conflict_resolver → store.

        Args:
            session_id: Session ID
            extraction_result: MemoryExtractionResult from extractor
        """
        try:
            from app.memory.kg.write_pipeline import KGWritePipeline
            from app.memory.kg import get_kg_store

            kg_store = get_kg_store()
            if kg_store is None:
                logger.warning("KG store not available, skipping KG write")
                return

            # Build conversation text from session
            session = self.session_manager.load_session(session_id)
            if not session:
                return

            messages = session.get("messages", [])
            conversation_text = "\n".join(
                f"{m.get('role', 'user')}: {m.get('content', '')}"
                for m in messages[-20:]
            )

            if not conversation_text.strip():
                return

            pipeline = KGWritePipeline()
            await pipeline.process_conversation(conversation_text, session_id)
            logger.info(f"KG write pipeline completed for session {session_id}")

        except Exception as e:
            logger.error(f"KG write failed for session {session_id}: {e}", exc_info=True)


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


def reset_memory_manager() -> None:
    """
    Reset the global memory manager to force recreation on next access.

    This should be called when LLM configuration is updated to ensure
    the new configuration is picked up immediately.
    """
    global _memory_manager_instance
    _memory_manager_instance = None
    # Also reset the extractor since it holds an LLM instance
    from app.memory.extractor import reset_memory_extractor
    reset_memory_extractor()
