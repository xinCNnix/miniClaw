"""
Knowledge Graph Pydantic Business Models.

Defines the data structures used by the KG store interface and upper-layer
logic (extractor, retriever, conflict resolver).
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel


class KGEntity(BaseModel):
    """A knowledge graph entity (node)."""

    entity_id: str
    name: str
    canonical_name: Optional[str] = None
    entity_type: Literal[
        "Person", "Org", "Project", "Client", "Event", "Preference", "Time", "Other"
    ]
    properties: Dict[str, Any] = {}
    confidence: float = 0.7
    source_doc_id: Optional[str] = None


class KGRelation(BaseModel):
    """A knowledge graph relation (edge) between two entities."""

    relation_id: str
    subject_id: str
    subject_name: str
    predicate: str
    object_id: str
    object_name: str
    object_type: Optional[str] = None
    qualifiers: Dict[str, str] = {}
    confidence: float = 0.7
    source_doc_id: Optional[str] = None
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class KGTriple(BaseModel):
    """LLM extraction output representing a subject-predicate-object triple."""

    subject: str
    subject_type: str
    predicate: str
    object: str
    object_type: str
    qualifiers: Dict[str, str] = {}
    confidence: float = 0.7


class KGQueryIntent(BaseModel):
    """LLM intent recognition output for KG queries."""

    intent: str
    entities: Dict[str, str]
    use_kg: bool = True


class KGRetrievalResult(BaseModel):
    """Result of a KG retrieval operation."""

    facts: List[str]
    raw_relations: List[KGRelation]
    source: Literal["kg", "none"]


class KGGraphResult(BaseModel):
    """Sub-graph query result centered on an entity."""

    entities: List[KGEntity]
    relations: List[KGRelation]
    depth: int
