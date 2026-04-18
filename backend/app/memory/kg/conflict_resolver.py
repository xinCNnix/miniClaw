"""
Knowledge Graph Conflict Resolver.

Handles conflict resolution when upserting relations into the KG.
Mutable relations (roles, preferences, habits) are overwritten by
deactivating old values before inserting new ones. Immutable relations
(belongings, temporal facts) are idempotently upserted.
"""

import logging
from typing import Optional, Set

from app.memory.kg.models import KGTriple
from app.memory.kg.store_interface import KGStoreInterface

logger = logging.getLogger(__name__)

MUTABLE_PREDICATES: Set[str] = {
    "HAS_ROLE",
    "HAS_PREFERENCE",
    "HAS_HABIT",
    "RESPONSIBLE_FOR",
    "WORKS_AT",
}


class ConflictResolver:
    """Resolve conflicts when writing KG relations.

    For *mutable* predicates (e.g. HAS_ROLE, WORKS_AT) there can be only one
    active relation for a given (subject, predicate) pair. Older relations are
    soft-deleted (``deactivate_relation``) before the new one is inserted.

    For *immutable* predicates (e.g. BELONGS_TO, AT_TIME) the upsert is
    idempotent -- an existing active relation with the same (subject, predicate,
    object) will simply be updated in place.

    All operations carry ``source_doc_id`` and timestamps for full traceability.
    """

    def __init__(self, store: KGStoreInterface) -> None:
        self.store = store

    async def resolve_and_upsert(
        self,
        triple: KGTriple,
        doc_id: str,
    ) -> Optional[str]:
        """Resolve any conflicts and upsert a triple as a relation.

        Args:
            triple: The extracted (subject, predicate, object) triple.
            doc_id: Source document / session identifier for traceability.

        Returns:
            The relation_id of the written relation, or None on failure.
        """
        # Resolve subject and object entities first.
        subject_entity = await self.store.find_entity(triple.subject)
        object_entity = await self.store.find_entity(triple.object)

        if subject_entity is None:
            logger.warning(
                "ConflictResolver: subject entity '%s' not found; "
                "skipping relation '%s'",
                triple.subject,
                triple.predicate,
            )
            return None

        if object_entity is None:
            logger.warning(
                "ConflictResolver: object entity '%s' not found; "
                "skipping relation '%s'",
                triple.object,
                triple.predicate,
            )
            return None

        subject_id = subject_entity.entity_id
        object_id = object_entity.entity_id
        predicate = triple.predicate

        try:
            if predicate in MUTABLE_PREDICATES:
                return await self._handle_mutable(
                    subject_id, predicate, object_id, triple, doc_id,
                )
            else:
                return await self._handle_immutable(
                    subject_id, predicate, object_id, triple, doc_id,
                )
        except Exception:
            logger.exception(
                "ConflictResolver: failed to upsert relation "
                "(%s)-[%s]->(%s)",
                triple.subject,
                predicate,
                triple.object,
            )
            return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _handle_mutable(
        self,
        subject_id: str,
        predicate: str,
        object_id: str,
        triple: KGTriple,
        doc_id: str,
    ) -> str:
        """Deactivate existing active relations with same subject+predicate,
        then create the new relation."""
        existing = await self.store.find_active_relations(
            subject_id=subject_id,
            predicate=predicate,
        )

        for rel in existing:
            await self.store.deactivate_relation(rel.relation_id)
            logger.info(
                "ConflictResolver: deactivated old mutable relation %s "
                "(%s)-[%s]->(%s)",
                rel.relation_id,
                triple.subject,
                predicate,
                rel.object_name,
            )

        relation_id = await self.store.upsert_relation(
            subject_id=subject_id,
            predicate=predicate,
            object_id=object_id,
            qualifiers=triple.qualifiers,
            confidence=triple.confidence,
            source_doc_id=doc_id,
        )
        logger.info(
            "ConflictResolver: created mutable relation %s "
            "(%s)-[%s]->(%s)",
            relation_id,
            triple.subject,
            predicate,
            triple.object,
        )
        return relation_id

    async def _handle_immutable(
        self,
        subject_id: str,
        predicate: str,
        object_id: str,
        triple: KGTriple,
        doc_id: str,
    ) -> str:
        """Idempotent upsert for immutable predicates.

        If an active relation with the same (subject, predicate, object)
        already exists it is updated in place; otherwise a new one is created.
        """
        relation_id = await self.store.upsert_relation(
            subject_id=subject_id,
            predicate=predicate,
            object_id=object_id,
            qualifiers=triple.qualifiers,
            confidence=triple.confidence,
            source_doc_id=doc_id,
        )
        logger.debug(
            "ConflictResolver: upserted immutable relation %s "
            "(%s)-[%s]->(%s)",
            relation_id,
            triple.subject,
            predicate,
            triple.object,
        )
        return relation_id
