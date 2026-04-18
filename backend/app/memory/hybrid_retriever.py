"""
Hybrid Memory Retriever -- orchestrates KG + vector + case + procedural + text.

Combines the KG-specific KGRetriever with the existing RAGEngine,
CaseMemoryStore, and ProcedureStore.
The RAGEngine is **not modified** -- it is only called as a data source.
Error isolation ensures that a failure in either source does not affect
the other.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from langchain_core.language_models import BaseChatModel

from app.config import get_settings
from app.core.rag_engine import RAGEngine
from app.memory.kg.models import KGRetrievalResult
from app.memory.kg.retriever import KGRetriever
from app.memory.kg.store_interface import KGStoreInterface
from app.memory.retriever_interface import (
    MemoryRetrieverInterface,
    UnifiedMemoryResult,
)

logger = logging.getLogger(__name__)


class HybridMemoryRetriever(MemoryRetrieverInterface):
    """Hybrid memory retriever -- orchestrates KG + vector + case + procedural.

    The existing RAGEngine is treated as a black-box data source and is
    not modified.  KGRetriever handles graph queries.  CaseMemoryStore
    and ProcedureStore provide case/procedural retrieval.
    All sources run in parallel via asyncio.gather with return_exceptions=True
    for error isolation.

    Args:
        kg_store: A KGStoreInterface implementation.
        rag_engine: The existing RAGEngine singleton (read-only).
        llm: Optional LangChain BaseChatModel override.
    """

    def __init__(
        self,
        kg_store: KGStoreInterface,
        rag_engine: RAGEngine,
        llm: Optional[BaseChatModel] = None,
    ) -> None:
        self.kg_retriever = KGRetriever(kg_store, llm)
        self.rag_engine = rag_engine
        self._case_store = None
        self._procedure_store = None

    def _get_case_store(self):
        """Lazy-load case memory store."""
        if self._case_store is None:
            try:
                from app.memory.case_memory import get_case_memory_store
                self._case_store = get_case_memory_store()
            except Exception:
                pass
        return self._case_store

    def _get_procedure_store(self):
        """Lazy-load procedure store."""
        if self._procedure_store is None:
            try:
                from app.memory.procedural import get_procedure_store
                self._procedure_store = get_procedure_store()
            except Exception:
                pass
        return self._procedure_store

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        kg_top_k: int = 5,
        vector_top_k: int = 3,
    ) -> UnifiedMemoryResult:
        """Unified retrieval: KG + vector + case + procedural in parallel.

        All enabled sources run in parallel.  Either source failing does not
        affect the others (error isolation).

        Args:
            query: The user's natural-language question.
            top_k: Generic limit.
            kg_top_k: Maximum KG facts to return.
            vector_top_k: Maximum vector docs to return.

        Returns:
            A UnifiedMemoryResult with merged context.
        """
        settings = get_settings()
        coros = []
        labels = []

        # KG retrieval
        coros.append(self.kg_retriever.retrieve(query))
        labels.append("kg")

        # Vector retrieval
        coros.append(self.rag_engine.search_conversations(query, top_k=vector_top_k))
        labels.append("vector")

        # Case memory retrieval
        if settings.enable_case_memory:
            case_store = self._get_case_store()
            if case_store:
                coros.append(case_store.search_cases(query, top_k=3))
                labels.append("case")

        # Procedural memory retrieval
        if settings.enable_procedural_memory:
            proc_store = self._get_procedure_store()
            if proc_store:
                coros.append(proc_store.search_procedures(query, top_k=3))
                labels.append("procedural")

        results = await asyncio.gather(*coros, return_exceptions=True)

        # Parse results
        kg_facts: List[str] = []
        vector_docs: List[str] = []
        case_docs: List[str] = []
        procedure_docs: List[str] = []

        for label, result in zip(labels, results):
            if isinstance(result, BaseException):
                logger.warning("%s retrieval failed: %s", label, result)
                continue

            if label == "kg":
                if isinstance(result, KGRetrievalResult):
                    kg_facts = result.facts[:kg_top_k]
            elif label == "vector":
                if isinstance(result, list):
                    vector_docs = [
                        r.get("content", "")
                        for r in result
                        if isinstance(r, dict) and r.get("content")
                    ]
            elif label == "case":
                if isinstance(result, list):
                    case_docs = [
                        f"[Case: {c.get('title', 'untitled')}] {c.get('context', '')}"
                        for c in result
                        if isinstance(c, dict)
                    ]
            elif label == "procedural":
                if isinstance(result, list):
                    procedure_docs = [
                        f"[Procedure: {p.get('name', 'unnamed')}] {p.get('description', '')} "
                        f"Steps: {'; '.join(p.get('steps', []))}"
                        for p in result
                        if isinstance(p, dict)
                    ]

        merged = self._merge(kg_facts, vector_docs, case_docs, procedure_docs)

        return UnifiedMemoryResult(
            kg_facts=kg_facts,
            vector_docs=vector_docs,
            case_docs=case_docs,
            procedure_docs=procedure_docs,
            merged_context=merged,
            kg_source="kg" if kg_facts else "none",
            metadata={
                "kg_fact_count": len(kg_facts),
                "vector_doc_count": len(vector_docs),
                "case_doc_count": len(case_docs),
                "procedure_doc_count": len(procedure_docs),
            },
        )

    def _merge(
        self,
        kg_facts: List[str],
        vector_docs: List[str],
        case_docs: List[str],
        procedure_docs: List[str],
    ) -> str:
        """Merge all sources into a single context string.

        KG facts are prioritized; other sources supplement.

        Args:
            kg_facts: High-confidence KG facts.
            vector_docs: Semantically retrieved conversation snippets.
            case_docs: Case memory results.
            procedure_docs: Procedure memory results.

        Returns:
            A formatted context string.
        """
        parts: List[str] = []
        if kg_facts:
            parts.append("=== Knowledge Graph Facts ===")
            parts.extend(f"- {f}" for f in kg_facts)
        if vector_docs:
            parts.append("=== Retrieved Conversation Memory ===")
            parts.extend(f"- {d}" for d in vector_docs)
        if case_docs:
            parts.append("=== Similar Past Cases ===")
            parts.extend(f"- {d}" for d in case_docs)
        if procedure_docs:
            parts.append("=== Relevant Procedures ===")
            parts.extend(f"- {d}" for d in procedure_docs)
        if kg_facts:
            parts.append(
                "Note: KG Facts take priority over conversation snippets. "
                "In case of conflict, prefer the fact with higher confidence "
                "and more recent update time."
            )
        return "\n".join(parts)

    async def health_check(self) -> Dict[str, bool]:
        """Check health of all data sources.

        Returns:
            A dict like {"kg": True, "vector": False, "case": True, "procedural": False}.
        """
        kg_healthy = False
        try:
            kg_healthy = await self.kg_retriever.store.health_check()
        except Exception as exc:
            logger.warning("KG health check failed: %s", exc)

        vector_healthy = self.rag_engine is not None

        case_healthy = self._get_case_store() is not None
        procedure_healthy = self._get_procedure_store() is not None

        return {
            "kg": kg_healthy,
            "vector": vector_healthy,
            "case": case_healthy,
            "procedural": procedure_healthy,
        }


class VectorOnlyMemoryRetriever(MemoryRetrieverInterface):
    """Fallback retriever when KG is disabled.

    Wraps the existing RAGEngine to satisfy MemoryRetrieverInterface
    without any KG dependency.

    Args:
        rag_engine: The existing RAGEngine singleton.
    """

    def __init__(self, rag_engine: RAGEngine) -> None:
        self.rag_engine = rag_engine

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        kg_top_k: int = 5,
        vector_top_k: int = 3,
    ) -> UnifiedMemoryResult:
        """Vector-only retrieval (no KG).

        Args:
            query: The user's question.
            top_k: Generic limit.
            kg_top_k: Ignored (no KG).
            vector_top_k: Number of vector results.

        Returns:
            A UnifiedMemoryResult with only vector docs populated.
        """
        try:
            results = await self.rag_engine.search_conversations(
                query, top_k=vector_top_k
            )
        except Exception as exc:
            logger.warning("Vector-only retrieval failed: %s", exc)
            results = []

        vector_docs: List[str] = [
            r.get("content", "") for r in results if r.get("content")
        ]

        merged = ""
        if vector_docs:
            merged = "=== Retrieved Conversation Memory ===\n"
            merged += "\n".join(f"- {d}" for d in vector_docs)

        return UnifiedMemoryResult(
            kg_facts=[],
            vector_docs=vector_docs,
            merged_context=merged,
            kg_source="none",
            metadata={"vector_doc_count": len(vector_docs)},
        )

    async def health_check(self) -> Dict[str, bool]:
        """Health check (vector only).

        Returns:
            A dict with "kg": False and "vector" health flag.
        """
        return {"kg": False, "vector": self.rag_engine is not None}
