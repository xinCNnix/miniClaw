"""MemoryState — shared state dict for MemoryEngine LangGraph nodes."""

from typing import TypedDict, List


class MemoryState(TypedDict, total=False):
    """Shared state flowing through both ingest and retrieval chains.

    Fields are optional (total=False) because each chain only populates
    a subset of the fields.
    """

    # --- Input ---
    query: str
    user_id: str
    session_id: str
    new_events: List[dict]

    # --- Ingest pipeline intermediate state ---
    chunks: List[dict]
    extracted: dict               # entities + facts + relations
    distilled: dict               # summaries + updates
    scored: List[dict]            # importance + confidence + ttl

    # --- Retrieval pipeline intermediate state ---
    routed_to: str                # semantic | episodic | procedural | case | hybrid
    retrieved_chunks: List[dict]
    retrieved_entities: List[dict]
    retrieved_graph: List[dict]
    retrieved_cases: List[dict]
    retrieved_procedures: List[dict]

    # --- Output ---
    memory_context: str           # MemoryContextPack injected into LLM
    logs: List[str]
