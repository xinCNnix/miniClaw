"""Retrieve node — parallel multi-path recall.

Implements parallel asyncio.gather for all enabled retrievers.
Fixes "不足3": replaces serial fallback with true parallel recall.
"""

import asyncio
import logging
import time

from app.memory.engine.state import MemoryState

logger = logging.getLogger(__name__)


async def multi_retrieve(state: MemoryState) -> MemoryState:
    """Retrieve from multiple memory stores in parallel.

    Based on routed_to intent, enables/disables specific retrieval paths.
    All enabled paths run concurrently via asyncio.gather.
    """
    query = state.get("query", "")
    routed_to = state.get("routed_to", "hybrid")
    logs = state.get("logs", [])

    if not query:
        return state

    from app.config import get_settings
    settings = get_settings()

    # Determine which paths to activate based on routing
    enable_wiki = settings.enable_wiki and routed_to in ("semantic", "hybrid")
    enable_kg = settings.enable_kg and routed_to in ("semantic", "hybrid")
    enable_vector = True  # Always enabled
    enable_case = getattr(settings, "enable_case_memory", False) and routed_to in ("case", "hybrid")
    enable_procedural = (
        getattr(settings, "enable_procedural_memory", False)
        and routed_to in ("procedural", "hybrid")
    )
    enable_episodic = routed_to in ("episodic", "hybrid")

    # Build parallel tasks
    tasks = []
    task_names = []

    if enable_wiki:
        tasks.append(_retrieve_wiki(query, settings))
        task_names.append("wiki")

    if enable_kg:
        tasks.append(_retrieve_kg(query, settings))
        task_names.append("kg")

    if enable_vector:
        tasks.append(_retrieve_vector(query, settings))
        task_names.append("vector")

    if enable_case:
        tasks.append(_retrieve_cases(query, settings))
        task_names.append("case")

    if enable_procedural:
        tasks.append(_retrieve_procedures(query, settings))
        task_names.append("procedural")

    if not tasks:
        logs.append("[multi_retrieve] No retrieval paths enabled")
        state["logs"] = logs
        return state

    # Execute all retrievals in parallel
    start_time = time.time()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = time.time() - start_time

    # Process results
    state["retrieved_chunks"] = []
    state["retrieved_entities"] = []
    state["retrieved_graph"] = []
    state["retrieved_cases"] = []
    state["retrieved_procedures"] = []

    for i, result in enumerate(results):
        name = task_names[i] if i < len(task_names) else f"task_{i}"

        if isinstance(result, Exception):
            logs.append(f"[multi_retrieve] {name} failed: {result}")
            continue

        if not result:
            continue

        # Route results to the correct state field
        if name == "wiki":
            state["retrieved_graph"].extend(result)  # Wiki results treated as graph/facts
        elif name == "kg":
            state["retrieved_graph"].extend(result)
        elif name == "vector":
            state["retrieved_chunks"].extend(result)
        elif name == "case":
            state["retrieved_cases"].extend(result)
        elif name == "procedural":
            state["retrieved_procedures"].extend(result)

    total = (
        len(state["retrieved_chunks"])
        + len(state["retrieved_entities"])
        + len(state["retrieved_graph"])
        + len(state["retrieved_cases"])
        + len(state["retrieved_procedures"])
    )
    logs.append(
        f"[multi_retrieve] paths={task_names}, total_results={total}, "
        f"elapsed={elapsed:.2f}s"
    )
    state["logs"] = logs
    return state


async def _retrieve_wiki(query: str, settings) -> list[dict]:
    """Retrieve from Wiki."""
    try:
        from app.memory.wiki.retriever import get_wiki_retriever

        retriever = get_wiki_retriever()
        result = await retriever.retrieve(query, top_k=5)

        items = []
        if result and result.page_ids:
            for i, page_id in enumerate(result.page_ids):
                conf = result.confidence_scores.get(page_id, 0.5)
                items.append({
                    "source": "wiki",
                    "page_id": page_id,
                    "text": result.wiki_context[:500] if result.wiki_context else "",
                    "weight": conf,
                    "confidence": conf,
                })
        return items
    except Exception as e:
        logger.warning(f"Wiki retrieval failed: {e}")
        return []


async def _retrieve_kg(query: str, settings) -> list[dict]:
    """Retrieve from Knowledge Graph."""
    try:
        from app.memory.kg.retriever import KGRetriever

        retriever = KGRetriever()
        result = await retriever.retrieve(query)

        items = []
        if result and result.facts:
            for fact in result.facts:
                items.append({
                    "source": "kg",
                    "text": fact,
                    "weight": 0.7,
                    "confidence": 0.7,
                })
        return items
    except Exception as e:
        logger.warning(f"KG retrieval failed: {e}")
        return []


async def _retrieve_vector(query: str, settings) -> list[dict]:
    """Retrieve from vector store (RAG)."""
    try:
        from app.core.rag_engine import get_rag_engine

        rag = get_rag_engine()
        results = await rag.search_conversations(query, top_k=5)

        items = []
        for r in results:
            items.append({
                "source": "vector",
                "text": r.get("content", ""),
                "weight": r.get("score", 0.5),
                "confidence": r.get("score", 0.5),
                "ts": r.get("metadata", {}).get("timestamp", ""),
            })
        return items
    except Exception as e:
        logger.warning(f"Vector retrieval failed: {e}")
        return []


async def _retrieve_cases(query: str, settings) -> list[dict]:
    """Retrieve from case memory."""
    try:
        from app.memory.case_memory import get_case_memory_store

        store = get_case_memory_store()
        results = await store.search_cases(query, top_k=3)

        items = []
        for r in results:
            r["source"] = "case"
            items.append(r)
        return items
    except Exception as e:
        logger.warning(f"Case retrieval failed: {e}")
        return []


async def _retrieve_procedures(query: str, settings) -> list[dict]:
    """Retrieve from procedural memory."""
    try:
        from app.memory.procedural import get_procedure_store

        store = get_procedure_store()
        results = await store.search_procedures(query, top_k=3)

        items = []
        for r in results:
            r["source"] = "procedural"
            items.append(r)
        return items
    except Exception as e:
        logger.warning(f"Procedural retrieval failed: {e}")
        return []
