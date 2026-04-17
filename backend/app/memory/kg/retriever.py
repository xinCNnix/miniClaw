"""
Knowledge Graph Retriever — KG-specific retrieval layer.

Handles the flow:
1. Intent recognition — LLM outputs KGQueryIntent(intent, entities, use_kg)
2. Template matching — templates.get_template(intent) to get the query template
3. Parameterized query — execute template via store interface (no direct SQL)
4. Result formatting — convert KGRelation list to natural language facts
"""

import json
import logging
from typing import List

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm import get_default_llm
from app.memory.kg.models import KGQueryIntent, KGRetrievalResult, KGRelation
from app.memory.kg.prompts import QUERY_ROUTE_PROMPT
from app.memory.kg.store_interface import KGStoreInterface
from app.memory.kg.templates import get_template

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


def _format_relation_as_fact(relation: KGRelation) -> str:
    """Convert a single KGRelation to a human-readable fact string.

    Args:
        relation: A KGRelation from the store.

    Returns:
        A natural-language fact string, e.g.
        ``"张三 HAS_ROLE 技术总监 (confidence: 0.90)"``
    """
    parts = [f"{relation.subject_name} {relation.predicate} {relation.object_name}"]

    if relation.qualifiers:
        qualifier_str = ", ".join(
            f"{k}: {v}" for k, v in relation.qualifiers.items()
        )
        parts.append(f"({qualifier_str})")

    parts.append(f"[confidence: {relation.confidence:.2f}]")
    return " ".join(parts)


class KGRetriever:
    """KG-specific retriever. Only handles graph queries, no vector.

    Args:
        store: A KGStoreInterface implementation (e.g. SQLiteKGStore).
        llm: Optional LangChain BaseChatModel.  When None the default
             provider from app.core.llm is used.
    """

    def __init__(
        self,
        store: KGStoreInterface,
        llm: BaseChatModel | None = None,
    ) -> None:
        self.store = store
        self.llm: BaseChatModel = llm or get_default_llm()

    async def retrieve(self, query: str) -> KGRetrievalResult:
        """Retrieve KG facts for a user query.

        Internal flow:
        1. LLM intent recognition -> KGQueryIntent
        2. Template matching -> QueryTemplate
        3. Execute template via store interface
        4. Format results as natural-language facts

        Args:
            query: The user's natural-language question.

        Returns:
            A ``KGRetrievalResult`` with formatted facts and raw relations.
        """
        try:
            intent = await self._recognize_intent(query)
        except Exception as exc:
            logger.warning("Intent recognition failed: %s", exc, exc_info=True)
            return KGRetrievalResult(facts=[], raw_relations=[], source="none")

        if not intent.use_kg:
            logger.debug("LLM decided use_kg=False for query: %s", query)
            return KGRetrievalResult(facts=[], raw_relations=[], source="none")

        template = get_template(intent.intent)
        if template is None:
            logger.warning("No template found for intent: %s", intent.intent)
            return KGRetrievalResult(facts=[], raw_relations=[], source="none")

        try:
            relations: List[KGRelation] = await template.execute(
                self.store, intent.entities
            )
        except Exception as exc:
            logger.warning(
                "Template %s execution failed: %s", template.name, exc, exc_info=True
            )
            return KGRetrievalResult(facts=[], raw_relations=[], source="none")

        if not relations:
            return KGRetrievalResult(facts=[], raw_relations=[], source="none")

        facts = [_format_relation_as_fact(r) for r in relations]
        return KGRetrievalResult(
            facts=facts,
            raw_relations=relations,
            source="kg",
        )

    async def _recognize_intent(self, query: str) -> KGQueryIntent:
        """Call the LLM to classify the query intent and extract entities.

        Args:
            query: The user's natural-language question.

        Returns:
            A parsed ``KGQueryIntent``.

        Raises:
            ValueError: If the LLM output cannot be parsed.
        """
        messages = [
            SystemMessage(content=QUERY_ROUTE_PROMPT),
            HumanMessage(content=query),
        ]
        response = await self.llm.ainvoke(messages)
        raw = _strip_markdown_fences(response.content)
        data = json.loads(raw)
        return KGQueryIntent(**data)
