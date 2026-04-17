"""
Knowledge Graph Entity Resolver.

Maps a natural-language entity name to an internal entity_id by looking up
the KG store's entities table and alias table in priority order.
"""

import logging
from typing import Optional

from app.memory.kg.store_interface import KGStoreInterface

logger = logging.getLogger(__name__)


class EntityResolver:
    """Resolve entity names to IDs using the KG store.

    Resolution strategy (priority order):
      1. Exact match on ``kg_entities.name``
      2. Match on ``kg_entity_aliases.alias_name``
      3. Return ``None`` if not found

    Args:
        store: A ``KGStoreInterface`` implementation (e.g. ``SQLiteKGStore``).
    """

    def __init__(self, store: KGStoreInterface) -> None:
        self.store = store

    async def resolve(self, name: str, entity_type: str) -> Optional[str]:
        """Resolve *name* to an ``entity_id``.

        Args:
            name: The entity name to look up (e.g. "张三", "阿里").
            entity_type: Expected entity type hint (e.g. "Person", "Org").
                         Currently unused for matching but reserved for
                         future disambiguation.

        Returns:
            The ``entity_id`` string if a match is found, otherwise ``None``.
        """
        # Priority 1: exact match on entity name
        entity = await self.store.find_entity(name)
        if entity is not None:
            logger.debug("Resolved '%s' via exact name match -> %s", name, entity.entity_id)
            return entity.entity_id

        # Priority 2: match on alias
        entity = await self.store.find_entity_by_alias(name)
        if entity is not None:
            logger.debug("Resolved '%s' via alias match -> %s", name, entity.entity_id)
            return entity.entity_id

        # Not found
        logger.debug("Could not resolve entity '%s' (type=%s)", name, entity_type)
        return None
