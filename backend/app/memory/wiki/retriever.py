"""
WikiRetriever — Page-level Wiki retrieval via ChromaDB vector search.

Searches the wiki_pages collection, reads MD files, and extracts
relevant sections. Falls back to RAGEngine for non-Wiki results.
"""

import json
import logging
from typing import List, Optional

from app.memory.wiki.models import WikiRetrievalResult

logger = logging.getLogger(__name__)


class WikiRetriever:
    """Wiki page-level retriever using ChromaDB ANN search."""

    def __init__(self, wiki_store, rag_engine=None) -> None:
        self._wiki_store = wiki_store
        self._rag_engine = rag_engine

    async def retrieve(self, query: str, top_k: int = 5) -> WikiRetrievalResult:
        """Retrieve Wiki pages matching the query.

        Args:
            query: Search query
            top_k: Maximum number of pages to return

        Returns:
            WikiRetrievalResult with page IDs and context
        """
        page_ids = await self.search_index(query, top_k)
        if not page_ids:
            return WikiRetrievalResult(source="none")

        # Read pages and extract relevant sections
        contexts = []
        confidence_scores = {}

        for pid in page_ids:
            page = await self._wiki_store.read(pid)
            if page is None:
                continue

            # Extract relevant sections from page content
            relevant = self.extract_relevant_sections(page.content, query)
            if relevant:
                header = f"## Wiki: {page.title}"
                if page.summary:
                    header += f"\n> {page.summary}"
                contexts.append(f"{header}\n\n{relevant}")
                confidence_scores[pid] = page.confidence

        if not contexts:
            return WikiRetrievalResult(source="none")

        wiki_context = "\n\n---\n\n".join(contexts)
        return WikiRetrievalResult(
            page_ids=list(confidence_scores.keys()),
            wiki_context=wiki_context,
            confidence_scores=confidence_scores,
            source="wiki",
        )

    async def search_index(self, query: str, top_k: int = 5) -> List[str]:
        """Search the ChromaDB wiki_pages collection.

        Args:
            query: Search query
            top_k: Maximum results

        Returns:
            List of matching page IDs
        """
        if self._wiki_store._chroma_collection is None:
            return []

        try:
            from app.core.embedding_manager import get_embedding_manager

            mgr = get_embedding_manager()
            model = mgr.get_model()
            if model is None:
                logger.debug("Embedding model not ready for wiki search")
                return []

            query_embedding = model.encode([query]).tolist()

            results = self._wiki_store._chroma_collection.query(
                query_embeddings=query_embedding,
                n_results=min(top_k, 10),
                include=["metadatas", "distances"],
            )

            if not results or not results.get("ids") or not results["ids"][0]:
                return []

            return results["ids"][0]

        except Exception as e:
            logger.warning(f"Wiki search failed: {e}")
            return []

    def extract_relevant_sections(self, md: str, query: str) -> str:
        """Extract sections from MD relevant to the query.

        Simple keyword matching against section headings and content.

        Args:
            md: Full Markdown content
            query: Search query

        Returns:
            Relevant sections concatenated
        """
        query_lower = query.lower()
        query_words = [w for w in query_lower.split() if len(w) > 2]

        if not query_words:
            # Return summary section if no meaningful words
            return self._get_summary_section(md)

        lines = md.split("\n")
        current_section = ""
        current_content: List[str] = []
        relevant_sections: List[str] = []

        for line in lines:
            if line.startswith("## "):
                # Check if previous section was relevant
                section_text = "\n".join(current_content)
                if self._is_relevant(current_section, section_text, query_words):
                    relevant_sections.append(
                        f"### {current_section}\n{section_text.strip()}"
                    )
                current_section = line.strip("# ").strip()
                current_content = []
            else:
                current_content.append(line)

        # Don't forget the last section
        section_text = "\n".join(current_content)
        if self._is_relevant(current_section, section_text, query_words):
            relevant_sections.append(
                f"### {current_section}\n{section_text.strip()}"
            )

        if relevant_sections:
            return "\n\n".join(relevant_sections)

        # Fallback: return summary section
        return self._get_summary_section(md)

    async def retrieve_with_fallback(self, query: str, top_k: int = 5) -> str:
        """Retrieve from Wiki first, fall back to vector search if insufficient.

        Args:
            query: Search query
            top_k: Maximum results

        Returns:
            Ready-to-inject context text
        """
        # Try Wiki first
        wiki_result = await self.retrieve(query, top_k)

        if wiki_result.source == "wiki" and wiki_result.wiki_context:
            return wiki_result.wiki_context

        # Fallback to RAG engine vector search
        if self._rag_engine is not None:
            try:
                results = await self._rag_engine.search_conversations(query, top_k=top_k)
                if results:
                    parts = []
                    for r in results:
                        content = r.get("content", "")
                        if content:
                            parts.append(content)
                    if parts:
                        return "## Retrieved Conversation Memory\n\n" + "\n\n".join(parts)
            except Exception as e:
                logger.warning(f"Wiki fallback search failed: {e}")

        return ""

    def _is_relevant(self, section_title: str, section_text: str, query_words: List[str]) -> bool:
        """Check if a section is relevant to the query words."""
        combined = (section_title + " " + section_text).lower()
        matching = sum(1 for w in query_words if w in combined)
        return matching >= max(1, len(query_words) // 3)

    def _get_summary_section(self, md: str) -> str:
        """Extract the Summary section from MD."""
        from app.memory.wiki.patch import WikiPatcher

        patcher = WikiPatcher()
        summary = patcher.extract_section(md, "Summary")
        if summary:
            return f"### Summary\n{summary}"

        # Fallback: first 500 chars
        return md[:500]


# Singleton
_wiki_retriever_instance: WikiRetriever | None = None


def get_wiki_retriever() -> WikiRetriever:
    """Get or create the global WikiRetriever singleton."""
    global _wiki_retriever_instance
    if _wiki_retriever_instance is None:
        from app.memory.wiki.store import get_wiki_store
        from app.core.rag_engine import get_rag_engine

        wiki_store = get_wiki_store()
        rag_engine = get_rag_engine()
        _wiki_retriever_instance = WikiRetriever(wiki_store, rag_engine)
    return _wiki_retriever_instance


def reset_wiki_retriever() -> None:
    """Reset the WikiRetriever singleton."""
    global _wiki_retriever_instance
    _wiki_retriever_instance = None
