"""MemoryEngine — LangGraph-based memory subsystem.

Provides two compiled LangGraph chains:
- Ingest Pipeline: EventLog → Chunk → Extract → Distill → Score → Write
- Retrieval Pipeline: Route → MultiRetrieve → EvidenceFilter → Fuse

Four-layer memory:
- Episodic: EventLog (SQLite) + Chunks (ChromaDB)
- Semantic: Wiki (MD+SQLite) + KG (SQLite) + EntityProfile (SQLite)
- Procedural: Procedures (SQLite)
- Case: CaseRecords (SQLite) + Trajectory (ChromaDB)
"""

from app.memory.engine.state import MemoryState
from app.memory.engine.evidence_registry import (
    MemoryEvidence,
    SOURCE_CONFIDENCE,
    get_source_confidence,
)
from app.memory.engine.graph import (
    get_memory_engine,
    get_ingest_chain,
    get_retrieval_chain,
    reset_memory_engine,
)
from app.memory.engine.cron import MemoryJanitor, get_memory_janitor

__all__ = [
    "MemoryState",
    "MemoryEvidence",
    "SOURCE_CONFIDENCE",
    "get_source_confidence",
    "get_memory_engine",
    "get_ingest_chain",
    "get_retrieval_chain",
    "reset_memory_engine",
    "MemoryJanitor",
    "get_memory_janitor",
]
