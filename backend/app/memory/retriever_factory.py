"""
Memory Retriever Factory.

Returns the appropriate MemoryRetrieverInterface implementation based on
application configuration.  When KG is enabled, returns a
HybridMemoryRetriever; otherwise returns a VectorOnlyMemoryRetriever.
"""

import logging

from app.config import get_settings
from app.core.rag_engine import get_rag_engine
from app.memory.kg import get_kg_store
from app.memory.retriever_interface import MemoryRetrieverInterface

logger = logging.getLogger(__name__)

# Module-level singleton
_retriever_instance: MemoryRetrieverInterface | None = None


def get_memory_retriever() -> MemoryRetrieverInterface:
    """Global factory: return unified retriever based on config.

    When ``settings.enable_kg`` is ``True`` the returned instance
    orchestrates both KG graph queries and vector semantic search.
    When ``False`` a lighter wrapper that only calls the existing
    RAGEngine is returned.

    Returns:
        A ``MemoryRetrieverInterface`` implementation.
    """
    global _retriever_instance

    if _retriever_instance is not None:
        return _retriever_instance

    settings = get_settings()
    rag_engine = get_rag_engine()

    if settings.enable_wiki:
        try:
            from app.memory.wiki.retriever import get_wiki_retriever
            from app.memory.wiki.unified_retriever import WikiAwareMemoryRetriever

            wiki_retriever = get_wiki_retriever()

            # Build inner retriever (KG + Vector or Vector-only)
            if settings.enable_kg:
                try:
                    from app.memory.hybrid_retriever import HybridMemoryRetriever

                    kg_store = get_kg_store()
                    inner = HybridMemoryRetriever(
                        kg_store=kg_store,
                        rag_engine=rag_engine,
                    )
                except Exception as exc:
                    logger.warning("KG init failed in wiki branch: %s", exc)
                    inner = _make_vector_only(rag_engine)
            else:
                inner = _make_vector_only(rag_engine)

            _retriever_instance = WikiAwareMemoryRetriever(
                wiki_retriever=wiki_retriever,
                inner_retriever=inner,
            )
            logger.info("Initialized WikiAwareMemoryRetriever (Wiki + KG + vector)")
        except Exception as exc:
            logger.warning(
                "Failed to initialize Wiki retriever, falling back: %s", exc
            )
            _retriever_instance = _make_inner_retriever(settings, rag_engine)
    elif settings.enable_kg:
        try:
            from app.memory.hybrid_retriever import HybridMemoryRetriever

            kg_store = get_kg_store()
            _retriever_instance = HybridMemoryRetriever(
                kg_store=kg_store,
                rag_engine=rag_engine,
            )
            logger.info("Initialized HybridMemoryRetriever (KG + vector)")
        except Exception as exc:
            logger.warning(
                "Failed to initialize KG, falling back to vector-only: %s", exc
            )
            _retriever_instance = _make_vector_only(rag_engine)
    else:
        _retriever_instance = _make_vector_only(rag_engine)
        logger.info("Initialized VectorOnlyMemoryRetriever (KG disabled)")

    return _retriever_instance


def reset_memory_retriever() -> None:
    """Reset the singleton so the next call to get_memory_retriever()
    creates a fresh instance.

    Should be called when configuration changes (e.g. LLM hot-switch).
    """
    global _retriever_instance
    _retriever_instance = None


def _make_vector_only(rag_engine) -> MemoryRetrieverInterface:
    """Create a VectorOnlyMemoryRetriever, handling import inline."""
    from app.memory.hybrid_retriever import VectorOnlyMemoryRetriever
    return VectorOnlyMemoryRetriever(rag_engine)


def _make_inner_retriever(settings, rag_engine) -> MemoryRetrieverInterface:
    """Build the inner retriever (KG + Vector or Vector-only)."""
    if settings.enable_kg:
        try:
            from app.memory.hybrid_retriever import HybridMemoryRetriever

            kg_store = get_kg_store()
            return HybridMemoryRetriever(kg_store=kg_store, rag_engine=rag_engine)
        except Exception as exc:
            logger.warning("KG init failed: %s", exc)
            return _make_vector_only(rag_engine)
    return _make_vector_only(rag_engine)
