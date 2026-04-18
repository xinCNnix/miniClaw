"""Engine node stubs — passthrough implementations.

Each node is initially a passthrough that returns state unchanged.
Subsequent phases will fill in real logic.
"""

from app.memory.engine.nodes.ingest import ingest_eventlog, chunk_and_embed
from app.memory.engine.nodes.extract import extract_entities_facts
from app.memory.engine.nodes.distill import distill_summaries
from app.memory.engine.nodes.score import score_and_prune
from app.memory.engine.nodes.write import write_memory_stores
from app.memory.engine.nodes.route import route_query
from app.memory.engine.nodes.retrieve import multi_retrieve
from app.memory.engine.nodes.filter import evidence_filter
from app.memory.engine.nodes.fuse import fuse_and_pack_context

__all__ = [
    "ingest_eventlog",
    "chunk_and_embed",
    "extract_entities_facts",
    "distill_summaries",
    "score_and_prune",
    "write_memory_stores",
    "route_query",
    "multi_retrieve",
    "evidence_filter",
    "fuse_and_pack_context",
]
