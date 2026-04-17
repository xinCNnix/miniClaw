"""
Knowledge Graph Extractor — LLM-based triple extraction and classification.

Uses the same SystemMessage + HumanMessage + JSON-parse + retry pattern as
`app.memory.extractor.MemoryExtractor`.
"""

import asyncio
import json
import logging
from typing import List

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.core.llm import get_default_llm
from app.memory.kg.models import KGTriple
from app.memory.kg.prompts import (
    MEMORY_CLASSIFY_PROMPT,
    TRIPLE_EXTRACT_PROMPT,
    VALID_PREDICATES,
)

logger = logging.getLogger(__name__)


def _strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` wrappers that LLMs sometimes add."""
    s = text.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        start = 1
        end = len(lines)
        for i in range(start, len(lines)):
            if lines[i].strip().startswith("```"):
                end = i
                break
        s = "\n".join(lines[start:end]).strip()
    return s


class KGExtractor:
    """Extract knowledge-graph triples from conversation text using an LLM.

    Args:
        llm: Optional LangChain ``BaseChatModel``.  When *None* the default
             provider from ``app.core.llm`` is used.  Inject a mock for tests.
        max_retries: How many times to retry on JSON-parse failure (default 2).
    """

    def __init__(
        self,
        llm: BaseChatModel | None = None,
        max_retries: int = 2,
    ) -> None:
        self.llm: BaseChatModel = llm or get_default_llm()
        self.max_retries = max_retries

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def should_store(self, conversation_text: str) -> bool:
        """Decide whether *conversation_text* contains facts worth storing.

        Args:
            conversation_text: Full conversation turn or summary.

        Returns:
            ``True`` if the text is worth persisting in the KG.
        """
        settings = get_settings()
        max_retries = self.max_retries

        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                raw = await self._call_llm(MEMORY_CLASSIFY_PROMPT, conversation_text)
                data = json.loads(_strip_markdown_fences(raw))
                result = bool(data.get("should_store", False))
                if attempt > 0:
                    logger.info("should_store succeeded on retry %d", attempt + 1)
                return result
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "should_store attempt %d/%d failed: %s",
                    attempt + 1,
                    max_retries + 1,
                    exc,
                )
                if attempt < max_retries:
                    await asyncio.sleep(0.5 * (2 ** attempt))

        logger.error(
            "should_store failed after %d attempts: %s",
            max_retries + 1,
            last_error,
        )
        # Conservative default: do not store on failure
        return False

    async def extract_triples(self, conversation_text: str) -> List[KGTriple]:
        """Extract KG triples from *conversation_text*.

        The number of returned triples is capped at
        ``settings.kg_max_triples_per_turn`` and those below
        ``settings.kg_confidence_threshold`` are discarded.

        Args:
            conversation_text: Full conversation turn or summary.

        Returns:
            A list of validated ``KGTriple`` objects.
        """
        settings = get_settings()
        max_triples = settings.kg_max_triples_per_turn
        confidence_threshold = settings.kg_confidence_threshold

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                raw = await self._call_llm(TRIPLE_EXTRACT_PROMPT, conversation_text)
                items = json.loads(_strip_markdown_fences(raw))

                if not isinstance(items, list):
                    raise ValueError(
                        f"Expected JSON array, got {type(items).__name__}"
                    )

                triples: List[KGTriple] = []
                for item in items[:max_triples]:
                    predicate = item.get("predicate", "")
                    if predicate not in VALID_PREDICATES:
                        logger.debug("Skipping triple with invalid predicate: %s", predicate)
                        continue
                    triple = KGTriple(
                        subject=item["subject"],
                        subject_type=item.get("subject_type", "Other"),
                        predicate=predicate,
                        object=item["object"],
                        object_type=item.get("object_type", "Other"),
                        qualifiers=item.get("qualifiers", {}),
                        confidence=float(item.get("confidence", 0.7)),
                    )
                    if triple.confidence < confidence_threshold:
                        logger.debug(
                            "Skipping triple below threshold: conf=%.2f < %.2f",
                            triple.confidence,
                            confidence_threshold,
                        )
                        continue
                    triples.append(triple)

                if attempt > 0:
                    logger.info(
                        "extract_triples succeeded on retry %d", attempt + 1
                    )

                return triples

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "extract_triples attempt %d/%d failed: %s",
                    attempt + 1,
                    self.max_retries + 1,
                    exc,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(0.5 * (2 ** attempt))

        logger.error(
            "extract_triples failed after %d attempts: %s",
            self.max_retries + 1,
            last_error,
        )
        return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _call_llm(self, system_prompt: str, user_text: str) -> str:
        """Invoke the LLM with a system + user message pair.

        Args:
            system_prompt: Instruction prompt.
            user_text: Conversation text to analyse.

        Returns:
            The raw string content of the LLM response.
        """
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_text),
        ]
        response = await self.llm.ainvoke(messages)
        return response.content
