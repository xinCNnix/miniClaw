"""
Knowledge Graph Module.

Provides a pluggable KG storage layer behind KGStoreInterface. The default
backend is SQLite; switching to Neo4j requires only a config change
(`kg_store_backend = "neo4j"`).
"""

from app.config import get_settings
from app.memory.kg.models import (
    KGEntity,
    KGGraphResult,
    KGQueryIntent,
    KGRelation,
    KGRetrievalResult,
    KGTriple,
)
from app.memory.kg.store_interface import KGStoreInterface


def get_kg_store() -> KGStoreInterface:
    """Factory: return a KG store instance based on config.

    Currently supported backends:
    - "sqlite"  -> SQLiteKGStore (default, zero-deploy)
    - "neo4j"   -> (not yet implemented)

    Raises:
        NotImplementedError: if an unsupported backend is configured.
    """
    settings = get_settings()

    if settings.kg_store_backend == "sqlite":
        from app.memory.kg.sqlite_store import SQLiteKGStore
        return SQLiteKGStore(settings)
    elif settings.kg_store_backend == "neo4j":
        raise NotImplementedError("Neo4jKGStore not yet implemented")
    else:
        raise ValueError(f"Unknown KG store backend: {settings.kg_store_backend}")


__all__ = [
    "get_kg_store",
    "KGStoreInterface",
    "KGEntity",
    "KGRelation",
    "KGTriple",
    "KGQueryIntent",
    "KGRetrievalResult",
    "KGGraphResult",
    "ConflictResolver",
    "MUTABLE_PREDICATES",
    "KGWritePipeline",
]
