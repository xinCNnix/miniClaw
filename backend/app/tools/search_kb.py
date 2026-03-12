"""
Search KB Tool - Knowledge Base Search

Integrates with RAGEngine for hybrid vector + BM25 search.
"""

import asyncio
import logging
from typing import List, Optional
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SearchKBInput(BaseModel):
    """Input schema for Search KB tool."""
    query: str = Field(..., description="Search query for the knowledge base")
    top_k: int = Field(default=5, description="Number of results to return")


class SearchKBTool(BaseTool):
    """Search knowledge base tool with RAG."""
    name: str = "search_kb"
    description: str = (
        "Search the knowledge base for relevant information. "
        "Use this when you need to find information from uploaded documents."
    )
    args_schema: type[SearchKBInput] = SearchKBInput

    def __init__(self):
        """Initialize with RAG Engine."""
        super().__init__()
        self._rag_engine = None

    def _get_rag_engine(self):
        """Lazy load RAG Engine."""
        if self._rag_engine is None:
            from app.core.rag_engine import get_rag_engine
            self._rag_engine = get_rag_engine()
        return self._rag_engine

    def _run(self, query: str, top_k: int = 5) -> str:
        """
        Search knowledge base synchronously.

        Args:
            query: Search query
            top_k: Number of results

        Returns:
            Formatted search results
        """
        try:
            rag_engine = self._get_rag_engine()
            # RAGEngine.search() is async, run it synchronously
            results = asyncio.run(rag_engine.search(query, top_k=top_k))
            return self._format_results(query, results)
        except Exception as e:
            logger.error(f"Knowledge base search failed: {e}", exc_info=True)
            return f"Failed to search knowledge base: {str(e)}"

    def _format_results(self, query: str, results: List[dict]) -> str:
        """Format search results for LLM consumption."""
        if not results:
            return f"No relevant information found in knowledge base for query: {query}"

        formatted = [
            f"Knowledge Base Search Results for: {query}\n",
            f"Found {len(results)} relevant passages:\n",
        ]

        for i, result in enumerate(results, 1):
            content = result.get("content", "")
            metadata = result.get("metadata", {})
            score = result.get("score")

            formatted.append(f"\n--- Result {i} ---")
            if score is not None:
                formatted.append(f"Relevance: {score:.3f}")
            if "file_name" in metadata:
                formatted.append(f"Source: {metadata['file_name']}")
            formatted.append(f"\n{content}")

        return "\n".join(formatted)


search_kb_tool = SearchKBTool()
