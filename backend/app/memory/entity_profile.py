"""Entity Profile Store — entity-centric memory management.

Each entity (person, project, tool, concept) has a profile with:
- summary: natural language description
- attributes: structured key-value pairs
- confidence: how well we know this entity
- conflict tracking: mutable vs immutable attributes
"""

import json
import logging
import time
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)


class EntityProfileStore:
    """Manage entity profiles in SQLite."""

    async def create_profile(
        self,
        entity_id: str,
        entity_type: str,
        name: str,
        summary: str = "",
        attributes: dict | None = None,
        confidence: float = 0.5,
    ) -> bool:
        """Create a new entity profile.

        Returns False if the entity already exists.
        """
        try:
            from app.core.database import get_db_session
            from sqlalchemy import text

            with get_db_session() as session:
                # Check if exists
                existing = session.execute(
                    text("SELECT 1 FROM entity_profiles WHERE entity_id = :eid"),
                    {"eid": entity_id},
                )
                if existing.scalar() is not None:
                    return False

                session.execute(
                    text(
                        "INSERT INTO entity_profiles "
                        "(entity_id, entity_type, name, summary, attributes_json, last_updated, confidence) "
                        "VALUES (:eid, :etype, :name, :summary, :attrs, :ts, :conf)"
                    ),
                    {
                        "eid": entity_id,
                        "etype": entity_type,
                        "name": name,
                        "summary": summary,
                        "attrs": json.dumps(attributes or {}, ensure_ascii=False),
                        "ts": time.time(),
                        "conf": confidence,
                    },
                )
                session.commit()
                logger.info(f"Created entity profile: {entity_id} ({name})")
                return True
        except Exception as e:
            logger.error(f"Failed to create entity profile {entity_id}: {e}")
            return False

    async def upsert_profile(
        self,
        entity_id: str,
        entity_type: str,
        name: str,
        summary: str = "",
        attributes: dict | None = None,
        confidence: float = 0.5,
    ) -> bool:
        """Create or update an entity profile.

        If the entity exists, merges attributes and updates confidence/conflict tracking.
        If not, creates a new profile.
        """
        existing = await self.get_profile(entity_id)
        if existing:
            # Merge attributes
            merged_attrs = existing.get("attributes", {})
            if attributes:
                for key, value in attributes.items():
                    old_value = merged_attrs.get(key)
                    if old_value is not None and old_value != value:
                        logger.info(
                            f"Entity {entity_id} attr '{key}' conflict: "
                            f"'{old_value}' → '{value}'"
                        )
                    merged_attrs[key] = value

            # Update summary if new one is longer or has higher confidence
            new_summary = summary or existing.get("summary", "")
            if summary and existing.get("summary") and len(summary) > len(existing["summary"]):
                new_summary = summary

            new_confidence = max(confidence, existing.get("confidence", 0))

            try:
                from app.core.database import get_db_session
                from sqlalchemy import text

                with get_db_session() as session:
                    session.execute(
                        text(
                            "UPDATE entity_profiles SET "
                            "entity_type = :etype, name = :name, summary = :summary, "
                            "attributes_json = :attrs, last_updated = :ts, confidence = :conf "
                            "WHERE entity_id = :eid"
                        ),
                        {
                            "etype": entity_type,
                            "name": name or existing.get("name", ""),
                            "summary": new_summary,
                            "attrs": json.dumps(merged_attrs, ensure_ascii=False),
                            "ts": time.time(),
                            "conf": new_confidence,
                            "eid": entity_id,
                        },
                    )
                    session.commit()
                return True
            except Exception as e:
                logger.error(f"Failed to upsert entity profile {entity_id}: {e}")
                return False
        else:
            return await self.create_profile(
                entity_id, entity_type, name, summary, attributes, confidence
            )

    async def delete_profile(self, entity_id: str) -> bool:
        """Delete an entity profile."""
        try:
            from app.core.database import get_db_session
            from sqlalchemy import text

            with get_db_session() as session:
                session.execute(
                    text("DELETE FROM entity_profiles WHERE entity_id = :eid"),
                    {"eid": entity_id},
                )
                session.commit()
                logger.info(f"Deleted entity profile: {entity_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to delete entity profile {entity_id}: {e}")
            return False

    async def get_profile(self, entity_id: str) -> Optional[dict]:
        """Get an entity profile by ID."""
        try:
            from app.core.database import get_db_session
            from sqlalchemy import text

            with get_db_session() as session:
                result = session.execute(
                    text(
                        "SELECT entity_id, entity_type, name, summary, "
                        "attributes_json, last_updated, confidence "
                        "FROM entity_profiles WHERE entity_id = :eid"
                    ),
                    {"eid": entity_id},
                )
                row = result.fetchone()
                if not row:
                    return None
                return {
                    "entity_id": row[0],
                    "entity_type": row[1],
                    "name": row[2],
                    "summary": row[3],
                    "attributes": json.loads(row[4] or "{}"),
                    "last_updated": row[5],
                    "confidence": row[6],
                }
        except Exception as e:
            logger.error(f"Failed to get entity profile {entity_id}: {e}")
            return None

    async def search_entities(self, query: str, entity_type: str = "", top_k: int = 10) -> list[dict]:
        """Search entities by name or summary."""
        try:
            from app.core.database import get_db_session
            from sqlalchemy import text

            with get_db_session() as session:
                sql = (
                    "SELECT entity_id, entity_type, name, summary, confidence "
                    "FROM entity_profiles WHERE name LIKE :q OR summary LIKE :q"
                )
                params = {"q": f"%{query}%"}

                if entity_type:
                    sql += " AND entity_type = :etype"
                    params["etype"] = entity_type

                sql += " ORDER BY confidence DESC LIMIT :limit"
                params["limit"] = top_k

                result = session.execute(text(sql), params)
                rows = result.fetchall()
                return [
                    {
                        "entity_id": r[0],
                        "entity_type": r[1],
                        "name": r[2],
                        "summary": r[3],
                        "confidence": r[4],
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error(f"Entity search failed: {e}")
            return []

    async def update_attribute(
        self, entity_id: str, key: str, value: str, confidence: float = 0.8
    ) -> bool:
        """Update a single attribute on an entity profile.

        If the attribute already exists with different value, this is a potential conflict.
        Higher confidence values overwrite lower ones.
        """
        profile = await self.get_profile(entity_id)
        if not profile:
            return False

        attrs = profile["attributes"]
        old_value = attrs.get(key)

        if old_value == value:
            return True  # No change needed

        if old_value is not None and old_value != value:
            logger.info(
                f"Entity {entity_id} attribute '{key}' changed: "
                f"'{old_value}' → '{value}'"
            )

        attrs[key] = value

        try:
            from app.core.database import get_db_session
            from sqlalchemy import text

            with get_db_session() as session:
                session.execute(
                    text(
                        "UPDATE entity_profiles SET attributes_json = :attrs, "
                        "last_updated = :ts, confidence = :conf WHERE entity_id = :eid"
                    ),
                    {
                        "attrs": json.dumps(attrs, ensure_ascii=False),
                        "ts": time.time(),
                        "conf": confidence,
                        "eid": entity_id,
                    },
                )
                session.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update entity attribute: {e}")
            return False

    async def get_stats(self) -> dict:
        """Get entity profile statistics."""
        try:
            from app.core.database import get_db_session
            from sqlalchemy import text

            with get_db_session() as session:
                result = session.execute(
                    text("SELECT COUNT(*), entity_type FROM entity_profiles GROUP BY entity_type")
                )
                rows = result.fetchall()
                by_type = {r[1]: r[0] for r in rows}
                total = sum(by_type.values())
                return {"total": total, "by_type": by_type}
        except Exception:
            return {"total": 0, "by_type": {}}


# Singleton
_store: EntityProfileStore | None = None


def get_entity_profile_store() -> EntityProfileStore:
    global _store
    if _store is None:
        _store = EntityProfileStore()
    return _store
