"""
WikiAwareMemoryRetriever — Unified retriever combining Wiki + KG + Vector.

Composes WikiRetriever as first-priority source, falling back to
the inner HybridMemoryRetriever (KG + Vector) when Wiki is insufficient.
"""

import asyncio
import logging
from typing import Any, Dict

from app.memory.retriever_interface import MemoryRetrieverInterface, UnifiedMemoryResult

logger = logging.getLogger(__name__)


class WikiAwareMemoryRetriever(MemoryRetrieverInterface):
    """Unified retriever: Wiki → KG + Vector fallback."""

    def __init__(self, wiki_retriever, inner_retriever) -> None:
        """Initialize with a Wiki retriever and an inner retriever.

        Args:
            wiki_retriever: WikiRetriever instance
            inner_retriever: HybridMemoryRetriever (KG + Vector) instance
        """
        self._wiki_retriever = wiki_retriever
        self._inner_retriever = inner_retriever

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        kg_top_k: int = 5,
        vector_top_k: int = 5,
    ) -> UnifiedMemoryResult:
        """Retrieve from Wiki first, then KG + Vector if needed.

        Args:
            query: Search query
            top_k: Total results budget
            kg_top_k: KG results budget
            vector_top_k: Vector results budget

        Returns:
            UnifiedMemoryResult with all sources combined
        """
        # Run Wiki and inner retriever in parallel
        wiki_task = self._wiki_retriever.retrieve(query, top_k=top_k)
        inner_task = self._inner_retriever.retrieve(
            query, top_k=top_k, kg_top_k=kg_top_k, vector_top_k=vector_top_k
        )

        results = await asyncio.gather(
            wiki_task, inner_task, return_exceptions=True
        )

        # Parse Wiki result
        wiki_result = results[0] if not isinstance(results[0], Exception) else None
        if isinstance(results[0], Exception):
            logger.warning(f"Wiki retrieval failed: {results[0]}")

        # Parse inner result
        inner_result = results[1] if not isinstance(results[1], Exception) else None
        if isinstance(results[1], Exception):
            logger.warning(f"Inner retrieval failed: {results[1]}")
            inner_result = UnifiedMemoryResult(
                merged_context="", kg_source="none"
            )

        # Merge results
        wiki_pages = []
        wiki_context = ""
        wiki_source = "none"

        if wiki_result and wiki_result.source == "wiki":
            wiki_pages = wiki_result.page_ids
            wiki_context = wiki_result.wiki_context
            wiki_source = "wiki"

        # Build merged context: Wiki first, then KG + Vector
        parts = []
        if wiki_context:
            parts.append(wiki_context)
        if inner_result.merged_context:
            parts.append(inner_result.merged_context)

        merged_context = "\n\n---\n\n".join(parts) if parts else ""

        return UnifiedMemoryResult(
            kg_facts=inner_result.kg_facts,
            vector_docs=inner_result.vector_docs,
            wiki_pages=wiki_pages,
            wiki_context=wiki_context,
            merged_context=merged_context,
            kg_source=inner_result.kg_source,
            wiki_source=wiki_source,
            metadata=inner_result.metadata,
        )

    async def health_check(self) -> Dict[str, bool]:
        """Check health of all retrieval sources."""
        inner_health = await self._inner_retriever.health_check()

        wiki_healthy = False
        try:
            from app.memory.wiki.store import get_wiki_store
            store = get_wiki_store()
            wiki_healthy = await store.health_check()
        except Exception:
            pass

        return {
            **inner_health,
            "wiki": wiki_healthy,
        }
