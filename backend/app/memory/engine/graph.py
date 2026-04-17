"""MemoryEngine graph builder — two compiled LangGraph chains.

Ingest Pipeline:  ingest_eventlog → chunk_and_embed → extract → distill → score → write
Retrieval Pipeline: route_query → multi_retrieve → evidence_filter → fuse
"""

from langgraph.graph import StateGraph, END

from app.memory.engine.state import MemoryState
from app.memory.engine.nodes.ingest import ingest_eventlog, chunk_and_embed
from app.memory.engine.nodes.extract import extract_entities_facts
from app.memory.engine.nodes.distill import distill_summaries
from app.memory.engine.nodes.score import score_and_prune
from app.memory.engine.nodes.write import write_memory_stores
from app.memory.engine.nodes.route import route_query
from app.memory.engine.nodes.retrieve import multi_retrieve
from app.memory.engine.nodes.filter import evidence_filter
from app.memory.engine.nodes.fuse import fuse_and_pack_context


def build_ingest_chain():
    """Build the ingest pipeline graph.

    Flow: ingest_eventlog → chunk_and_embed → extract → distill → score → write → END
    """
    g = StateGraph(MemoryState)
    g.add_node("ingest_eventlog", ingest_eventlog)
    g.add_node("chunk_and_embed", chunk_and_embed)
    g.add_node("extract_entities_facts", extract_entities_facts)
    g.add_node("distill_summaries", distill_summaries)
    g.add_node("score_and_prune", score_and_prune)
    g.add_node("write_memory_stores", write_memory_stores)

    g.add_edge("ingest_eventlog", "chunk_and_embed")
    g.add_edge("chunk_and_embed", "extract_entities_facts")
    g.add_edge("extract_entities_facts", "distill_summaries")
    g.add_edge("distill_summaries", "score_and_prune")
    g.add_edge("score_and_prune", "write_memory_stores")
    g.add_edge("write_memory_stores", END)
    g.set_entry_point("ingest_eventlog")

    return g.compile()


def build_retrieval_chain():
    """Build the retrieval pipeline graph.

    Flow: route_query → multi_retrieve → evidence_filter → fuse → END
    """
    g = StateGraph(MemoryState)
    g.add_node("route_query", route_query)
    g.add_node("multi_retrieve", multi_retrieve)
    g.add_node("evidence_filter", evidence_filter)
    g.add_node("fuse_and_pack_context", fuse_and_pack_context)

    g.add_edge("route_query", "multi_retrieve")
    g.add_edge("multi_retrieve", "evidence_filter")
    g.add_edge("evidence_filter", "fuse_and_pack_context")
    g.add_edge("fuse_and_pack_context", END)
    g.set_entry_point("route_query")

    return g.compile()


# --- Singleton engine instances ---
_ingest_chain = None
_retrieval_chain = None


def get_ingest_chain():
    """Get or create the singleton ingest chain."""
    global _ingest_chain
    if _ingest_chain is None:
        _ingest_chain = build_ingest_chain()
    return _ingest_chain


def get_retrieval_chain():
    """Get or create the singleton retrieval chain."""
    global _retrieval_chain
    if _retrieval_chain is None:
        _retrieval_chain = build_retrieval_chain()
    return _retrieval_chain


def get_memory_engine():
    """Return dict with both chains."""
    return {
        "ingest": get_ingest_chain(),
        "retrieve": get_retrieval_chain(),
    }


def reset_memory_engine():
    """Reset singleton chains (for testing / hot-switch)."""
    global _ingest_chain, _retrieval_chain
    _ingest_chain = None
    _retrieval_chain = None
