"""
Unified Memory Retrieval Interface.

Defines the abstract interface that chat.py and upper modules depend on,
plus the UnifiedMemoryResult model that fuses KG facts + vector results
into a single context string ready for injection into the system prompt.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field


class UnifiedMemoryResult(BaseModel):
    """Fused retrieval result.

    Attributes:
        kg_facts: High-confidence KG facts as natural language strings.
        vector_docs: Semantically retrieved conversation snippets.
        wiki_pages: Wiki page IDs that contributed to the result.
        wiki_context: Wiki page context text.
        merged_context: Merged context text, directly injectable into system prompt.
        kg_source: Whether KG data contributed to the result.
        wiki_source: Whether Wiki data contributed to the result.
        metadata: Additional metadata for debugging and observability.
    """

    kg_facts: List[str] = Field(
        default_factory=list,
        description="KG high-confidence facts (natural language)",
    )
    vector_docs: List[str] = Field(
        default_factory=list,
        description="Vector semantic retrieval conversation snippets",
    )
    case_docs: List[str] = Field(
        default_factory=list,
        description="Case memory results (similar past task trajectories)",
    )
    procedure_docs: List[str] = Field(
        default_factory=list,
        description="Procedural memory results (reusable how-to steps)",
    )
    wiki_pages: List[str] = Field(
        default_factory=list,
        description="Wiki page IDs that matched the query",
    )
    wiki_context: str = Field(
        default="",
        description="Wiki page context text for injection",
    )
    merged_context: str = Field(
        default="",
        description="Merged context text, directly injectable into system prompt",
    )
    kg_source: Literal["kg", "none"] = "none"
    wiki_source: Literal["wiki", "none"] = "none"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MemoryRetrieverInterface(ABC):
    """Unified memory retrieval interface.

    This is the only retrieval interface that chat.py and upper modules
    depend on.  It orchestrates KG graph queries, vector semantic search,
    and text snippets, returning a single fused result.
    """

    @abstractmethod
    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        kg_top_k: int = 5,
        vector_top_k: int = 3,
    ) -> UnifiedMemoryResult:
        """Unified retrieval: KG priority + vector fallback.

        Args:
            query: The user's natural-language question.
            top_k: Generic limit.
            kg_top_k: Maximum KG facts to return.
            vector_top_k: Maximum vector docs to return.

        Returns:
            A UnifiedMemoryResult with merged context.
        """

    @abstractmethod
    async def health_check(self) -> Dict[str, bool]:
        """Check health of all data sources.

        Returns:
            A dict like {"kg": True, "vector": False}.
        """
