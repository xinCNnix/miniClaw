"""
Knowledge Graph Store Abstract Base Class.

Upper-layer logic (extractor, retriever, conflict resolver) depends only on
this interface. Concrete implementations can be SQLite, Neo4j, PostgreSQL AGE, etc.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.memory.kg.models import KGEntity, KGGraphResult, KGRelation


class KGStoreInterface(ABC):
    """Knowledge graph storage abstract interface.

    Upper-layer logic (extractor, retriever, conflict_resolver) only depends
    on this interface. Concrete implementations can be SQLite, Neo4j,
    PostgreSQL AGE, etc.
    """

    # --- Lifecycle ---

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize storage (create tables, indexes, connections, etc.)."""

    @abstractmethod
    async def close(self) -> None:
        """Close connections / release resources."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the store is healthy and usable."""

    # --- Entity Operations ---

    @abstractmethod
    async def upsert_entity(
        self,
        name: str,
        entity_type: str,
        *,
        canonical_name: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
        confidence: float = 0.7,
        source_doc_id: Optional[str] = None,
    ) -> str:
        """Create or update an entity. Returns entity_id."""

    @abstractmethod
    async def find_entity(self, name: str) -> Optional[KGEntity]:
        """Find an entity by name or alias."""

    @abstractmethod
    async def get_entity(self, entity_id: str) -> Optional[KGEntity]:
        """Get an entity by its ID."""

    @abstractmethod
    async def search_entities(
        self,
        query: str,
        entity_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[KGEntity]:
        """Fuzzy-search entities (name contains query)."""

    # --- Relation Operations ---

    @abstractmethod
    async def upsert_relation(
        self,
        subject_id: str,
        predicate: str,
        object_id: str,
        *,
        qualifiers: Optional[Dict[str, str]] = None,
        confidence: float = 0.7,
        source_doc_id: Optional[str] = None,
    ) -> str:
        """Create or update a relation. Returns relation_id."""

    @abstractmethod
    async def find_active_relations(
        self,
        subject_id: Optional[str] = None,
        predicate: Optional[str] = None,
        object_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[KGRelation]:
        """Find active relations (supports any combination of filters)."""

    @abstractmethod
    async def deactivate_relation(self, relation_id: str) -> None:
        """Soft-delete a relation (is_active=False, valid_to=now)."""

    # --- Alias Operations ---

    @abstractmethod
    async def add_alias(self, entity_id: str, alias_name: str) -> None:
        """Add an alias for an entity."""

    @abstractmethod
    async def find_entity_by_alias(self, alias_name: str) -> Optional[KGEntity]:
        """Find an entity by its alias."""

    # --- Graph Queries (multi-hop capability) ---

    @abstractmethod
    async def get_entity_graph(
        self,
        entity_id: str,
        depth: int = 1,
        max_nodes: int = 50,
    ) -> KGGraphResult:
        """Get the sub-graph centered on an entity (supports multi-hop traversal)."""

    @abstractmethod
    async def find_path(
        self,
        from_entity_id: str,
        to_entity_id: str,
        max_depth: int = 3,
    ) -> List[List[KGRelation]]:
        """Find paths between two entities (multi-hop BFS)."""

    @abstractmethod
    async def get_relations_between(
        self,
        entity_a_id: str,
        entity_b_id: str,
    ) -> List[KGRelation]:
        """Get direct relations between two entities."""

    # --- Batch / Statistics ---

    @abstractmethod
    async def get_entity_count(self, entity_type: Optional[str] = None) -> int:
        """Get the total entity count, optionally filtered by type."""

    @abstractmethod
    async def get_recent_relations(
        self,
        limit: int = 20,
        since_hours: int = 24,
    ) -> List[KGRelation]:
        """Get recently created relations."""
