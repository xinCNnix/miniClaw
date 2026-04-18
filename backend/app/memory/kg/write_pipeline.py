"""
Knowledge Graph Write Pipeline.

Orchestrates the full KG write flow:
  extractor.should_store() -> extractor.extract_triples()
      -> entity_resolver.resolve() -> conflict_resolver.resolve_and_upsert()

This is the single entry-point for writing conversation data into the KG.
"""

import logging
from typing import List, Optional

from app.memory.kg.conflict_resolver import ConflictResolver
from app.memory.kg.models import KGTriple
from app.memory.kg.store_interface import KGStoreInterface

logger = logging.getLogger(__name__)


class KGWritePipeline:
    """KG write orchestrator: extractor -> resolver -> conflict_resolver -> store.

    Usage::

        pipeline = KGWritePipeline(store, extractor, entity_resolver, conflict_resolver)
        relation_ids = await pipeline.process_conversation(text, session_id)
    """

    def __init__(
        self,
        store: KGStoreInterface,
        extractor: "KGExtractor",           # noqa: F821 – Phase 2 type
        entity_resolver: "EntityResolver",   # noqa: F821 – Phase 2 type
        conflict_resolver: ConflictResolver,
    ) -> None:
        self.store = store
        self.extractor = extractor
        self.entity_resolver = entity_resolver
        self.conflict_resolver = conflict_resolver

    async def process_conversation(
        self,
        conversation_text: str,
        session_id: str,
    ) -> List[str]:
        """Process a conversation and write extracted triples into the KG.

        Args:
            conversation_text: The full conversation text to analyse.
            session_id: The originating session identifier (used as source
                doc for traceability).

        Returns:
            A list of relation_ids that were written to the store.
        """
        # Step 1: Decide whether this conversation is worth storing.
        if not await self.extractor.should_store(conversation_text):
            logger.info(
                "KGWritePipeline: conversation %s skipped by should_store()",
                session_id,
            )
            return []

        # Step 2: Extract triples via LLM.
        triples: List[KGTriple] = await self.extractor.extract_triples(
            conversation_text,
        )

        if not triples:
            logger.info(
                "KGWritePipeline: no triples extracted from session %s",
                session_id,
            )
            return []

        logger.info(
            "KGWritePipeline: extracted %d triples from session %s",
            len(triples),
            session_id,
        )

        # Step 3: Resolve entities and write relations.
        written_ids: List[str] = []

        for triple in triples:
            try:
                relation_id = await self._process_single_triple(triple, session_id)
                if relation_id is not None:
                    written_ids.append(relation_id)
            except Exception:
                logger.exception(
                    "KGWritePipeline: failed to process triple "
                    "(%s)-[%s]->(%s) in session %s",
                    triple.subject,
                    triple.predicate,
                    triple.object,
                    session_id,
                )
                # Continue processing remaining triples.
                continue

        logger.info(
            "KGWritePipeline: wrote %d / %d relations for session %s",
            len(written_ids),
            len(triples),
            session_id,
        )
        return written_ids

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _process_single_triple(
        self,
        triple: KGTriple,
        session_id: str,
    ) -> Optional[str]:
        """Resolve subject/object entities, then delegate to ConflictResolver.

        Returns the relation_id written, or None if the triple could not be
        processed (e.g. entity resolution failed).
        """
        # Resolve / create subject entity.
        subject_id = await self.entity_resolver.resolve(
            triple.subject,
            triple.subject_type,
        )
        if subject_id is None:
            # Fallback: create entity directly via store.
            subject_id = await self.store.upsert_entity(
                name=triple.subject,
                entity_type=triple.subject_type,
                confidence=triple.confidence,
                source_doc_id=session_id,
            )
            logger.info(
                "KGWritePipeline: created subject entity '%s' (id=%s)",
                triple.subject,
                subject_id,
            )

        # Resolve / create object entity.
        object_id = await self.entity_resolver.resolve(
            triple.object,
            triple.object_type,
        )
        if object_id is None:
            # Fallback: create entity directly via store.
            object_id = await self.store.upsert_entity(
                name=triple.object,
                entity_type=triple.object_type,
                confidence=triple.confidence,
                source_doc_id=session_id,
            )
            logger.info(
                "KGWritePipeline: created object entity '%s' (id=%s)",
                triple.object,
                object_id,
            )

        # Delegate conflict resolution + upsert.
        return await self.conflict_resolver.resolve_and_upsert(
            triple,
            doc_id=session_id,
        )
