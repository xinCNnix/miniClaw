"""
SQLite Knowledge Graph Store Implementation.

Uses the existing SQLAlchemy database infrastructure (get_db_session) for
SQLite storage. Supports entity/relation CRUD, alias management, and
multi-hop graph traversal via recursive CTEs.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.config import Settings
from app.core.database import get_db_session, ensure_database
from app.memory.kg.models import KGEntity, KGGraphResult, KGRelation
from app.memory.kg.store_interface import KGStoreInterface

logger = logging.getLogger(__name__)


def _to_iso(val: Any) -> Optional[str]:
    """Convert a datetime or string to ISO format string."""
    if val is None:
        return None
    if isinstance(val, str):
        return val
    return val.isoformat()


def _row_to_entity(row: Any) -> KGEntity:
    """Convert a database row to a KGEntity model."""
    props = row.properties if row.properties else {}
    if isinstance(props, str):
        props = json.loads(props)
    return KGEntity(
        entity_id=row.entity_id,
        name=row.name,
        canonical_name=row.canonical_name,
        entity_type=row.entity_type,
        properties=props,
        confidence=row.confidence,
        source_doc_id=row.source_doc_id,
    )


def _row_to_relation(row: Any, subject_name: str = "", object_name: str = "") -> KGRelation:
    """Convert a database row to a KGRelation model."""
    quals = row.qualifiers if row.qualifiers else {}
    if isinstance(quals, str):
        quals = json.loads(quals)
    return KGRelation(
        relation_id=row.relation_id,
        subject_id=row.subject_id,
        subject_name=subject_name or getattr(row, "subject_name", ""),
        predicate=row.predicate,
        object_id=row.object_id,
        object_name=object_name or getattr(row, "object_name", ""),
        object_type=getattr(row, "object_type", None),
        qualifiers=quals,
        confidence=row.confidence,
        source_doc_id=row.source_doc_id,
        is_active=bool(row.is_active),
        created_at=_to_iso(row.created_at),
        updated_at=_to_iso(row.updated_at),
    )


class SQLiteKGStore(KGStoreInterface):
    """SQLite-backed knowledge graph store.

    Uses the existing SQLAlchemy infrastructure (get_db_session) so that
    KG tables live in the same SQLite database as other memory data.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Create KG tables if they do not yet exist."""
        ensure_database(self._settings)
        with get_db_session(self._settings) as session:
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS kg_entities (
                    entity_id      TEXT PRIMARY KEY,
                    name           TEXT    NOT NULL,
                    canonical_name TEXT,
                    entity_type    TEXT    NOT NULL,
                    properties     TEXT    DEFAULT '{}',
                    confidence     REAL    DEFAULT 0.7,
                    source_doc_id  TEXT,
                    created_at     TEXT    DEFAULT (datetime('now')),
                    updated_at     TEXT    DEFAULT (datetime('now')),
                    UNIQUE(entity_type, name)
                )
            """))
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS kg_relations (
                    relation_id   TEXT PRIMARY KEY,
                    subject_id    TEXT    NOT NULL,
                    predicate     TEXT    NOT NULL,
                    object_id     TEXT    NOT NULL,
                    qualifiers    TEXT    DEFAULT '{}',
                    confidence    REAL    DEFAULT 0.7,
                    source_doc_id TEXT,
                    is_active     INTEGER DEFAULT 1,
                    valid_from    TEXT    DEFAULT (datetime('now')),
                    valid_to      TEXT,
                    created_at    TEXT    DEFAULT (datetime('now')),
                    updated_at    TEXT    DEFAULT (datetime('now')),
                    FOREIGN KEY (subject_id) REFERENCES kg_entities(entity_id) ON DELETE CASCADE,
                    FOREIGN KEY (object_id)  REFERENCES kg_entities(entity_id) ON DELETE CASCADE
                )
            """))
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS kg_entity_aliases (
                    alias_id  TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL,
                    alias_name TEXT NOT NULL UNIQUE,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (entity_id) REFERENCES kg_entities(entity_id) ON DELETE CASCADE
                )
            """))
            # Indexes
            session.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_kg_relations_subject  ON kg_relations(subject_id)"
            ))
            session.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_kg_relations_object   ON kg_relations(object_id)"
            ))
            session.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_kg_relations_predicate ON kg_relations(predicate)"
            ))
            session.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_kg_relations_active   ON kg_relations(is_active)"
            ))
            session.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_kg_aliases_entity     ON kg_entity_aliases(entity_id)"
            ))
            session.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_kg_entities_type      ON kg_entities(entity_type)"
            ))
        logger.info("KG tables initialized")

    async def close(self) -> None:
        """No-op: sessions are managed by get_db_session context manager."""

    async def health_check(self) -> bool:
        """Return True if the kg_entities table is accessible."""
        try:
            with get_db_session(self._settings) as session:
                session.execute(text("SELECT 1 FROM kg_entities LIMIT 1"))
            return True
        except Exception as exc:
            logger.error("KG health check failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Entity Operations
    # ------------------------------------------------------------------

    async def upsert_entity(
        self,
        name: str,
        entity_type: str,
        *,
        canonical_name: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
        confidence: float = 0.7,
        source_doc_id: Optional[str] = None,
    ) -> str:
        """Create or update an entity using SQLite UPSERT.

        Returns the entity_id (existing or newly generated).
        """
        props_json = json.dumps(properties or {}, ensure_ascii=False)
        entity_id = str(uuid.uuid4())

        with get_db_session(self._settings) as session:
            # Try to find an existing entity with the same (entity_type, name).
            row = session.execute(
                text("SELECT entity_id FROM kg_entities WHERE entity_type = :etype AND name = :name"),
                {"etype": entity_type, "name": name},
            ).fetchone()

            if row is not None:
                # Update existing entity
                existing_id = row.entity_id
                session.execute(
                    text("""
                        UPDATE kg_entities
                        SET canonical_name = COALESCE(:canonical, canonical_name),
                            properties     = :props,
                            confidence     = :confidence,
                            source_doc_id  = COALESCE(:source, source_doc_id),
                            updated_at     = datetime('now')
                        WHERE entity_id = :eid
                    """),
                    {
                        "canonical": canonical_name,
                        "props": props_json,
                        "confidence": confidence,
                        "source": source_doc_id,
                        "eid": existing_id,
                    },
                )
                return existing_id

            # Insert new entity
            now = datetime.utcnow().isoformat()
            session.execute(
                text("""
                    INSERT INTO kg_entities (entity_id, name, canonical_name, entity_type,
                                             properties, confidence, source_doc_id,
                                             created_at, updated_at)
                    VALUES (:eid, :name, :canonical, :etype, :props, :confidence, :source,
                            :now, :now)
                """),
                {
                    "eid": entity_id,
                    "name": name,
                    "canonical": canonical_name,
                    "etype": entity_type,
                    "props": props_json,
                    "confidence": confidence,
                    "source": source_doc_id,
                    "now": now,
                },
            )
            return entity_id

    async def find_entity(self, name: str) -> Optional[KGEntity]:
        """Find an entity by name, falling back to alias lookup."""
        with get_db_session(self._settings) as session:
            # Direct name lookup
            row = session.execute(
                text("SELECT * FROM kg_entities WHERE name = :name LIMIT 1"),
                {"name": name},
            ).fetchone()
            if row is not None:
                return _row_to_entity(row)

            # Alias fallback
            row = session.execute(
                text("""
                    SELECT e.* FROM kg_entities e
                    JOIN kg_entity_aliases a ON a.entity_id = e.entity_id
                    WHERE a.alias_name = :alias
                    LIMIT 1
                """),
                {"alias": name},
            ).fetchone()
            if row is not None:
                return _row_to_entity(row)

            return None

    async def get_entity(self, entity_id: str) -> Optional[KGEntity]:
        """Get an entity by its primary key."""
        with get_db_session(self._settings) as session:
            row = session.execute(
                text("SELECT * FROM kg_entities WHERE entity_id = :eid LIMIT 1"),
                {"eid": entity_id},
            ).fetchone()
            if row is None:
                return None
            return _row_to_entity(row)

    async def search_entities(
        self,
        query: str,
        entity_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[KGEntity]:
        """Fuzzy-search entities whose name contains *query*."""
        with get_db_session(self._settings) as session:
            if entity_type:
                rows = session.execute(
                    text("""
                        SELECT * FROM kg_entities
                        WHERE name LIKE :q AND entity_type = :etype
                        ORDER BY confidence DESC
                        LIMIT :lim
                    """),
                    {"q": f"%{query}%", "etype": entity_type, "lim": limit},
                ).fetchall()
            else:
                rows = session.execute(
                    text("""
                        SELECT * FROM kg_entities
                        WHERE name LIKE :q
                        ORDER BY confidence DESC
                        LIMIT :lim
                    """),
                    {"q": f"%{query}%", "lim": limit},
                ).fetchall()
            return [_row_to_entity(r) for r in rows]

    # ------------------------------------------------------------------
    # Relation Operations
    # ------------------------------------------------------------------

    async def upsert_relation(
        self,
        subject_id: str,
        predicate: str,
        object_id: str,
        *,
        qualifiers: Optional[Dict[str, str]] = None,
        confidence: float = 0.7,
        source_doc_id: Optional[str] = None,
    ) -> str:
        """Create or update a relation. Returns the relation_id."""
        quals_json = json.dumps(qualifiers or {}, ensure_ascii=False)
        relation_id = str(uuid.uuid4())

        with get_db_session(self._settings) as session:
            # Check for an existing active relation with same subject/predicate/object
            row = session.execute(
                text("""
                    SELECT relation_id FROM kg_relations
                    WHERE subject_id = :sid AND predicate = :pred AND object_id = :oid
                      AND is_active = 1
                    LIMIT 1
                """),
                {"sid": subject_id, "pred": predicate, "oid": object_id},
            ).fetchone()

            if row is not None:
                existing_id = row.relation_id
                session.execute(
                    text("""
                        UPDATE kg_relations
                        SET qualifiers    = :quals,
                            confidence    = :confidence,
                            source_doc_id = COALESCE(:source, source_doc_id),
                            updated_at    = datetime('now')
                        WHERE relation_id = :rid
                    """),
                    {
                        "quals": quals_json,
                        "confidence": confidence,
                        "source": source_doc_id,
                        "rid": existing_id,
                    },
                )
                return existing_id

            now = datetime.utcnow().isoformat()
            session.execute(
                text("""
                    INSERT INTO kg_relations
                        (relation_id, subject_id, predicate, object_id,
                         qualifiers, confidence, source_doc_id,
                         is_active, valid_from, created_at, updated_at)
                    VALUES (:rid, :sid, :pred, :oid, :quals, :confidence, :source,
                            1, :now, :now, :now)
                """),
                {
                    "rid": relation_id,
                    "sid": subject_id,
                    "pred": predicate,
                    "oid": object_id,
                    "quals": quals_json,
                    "confidence": confidence,
                    "source": source_doc_id,
                    "now": now,
                },
            )
            return relation_id

    async def find_active_relations(
        self,
        subject_id: Optional[str] = None,
        predicate: Optional[str] = None,
        object_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[KGRelation]:
        """Find active relations with optional filters."""
        conditions = ["is_active = 1"]
        params: Dict[str, Any] = {"lim": limit}

        if subject_id:
            conditions.append("subject_id = :sid")
            params["sid"] = subject_id
        if predicate:
            conditions.append("predicate = :pred")
            params["pred"] = predicate
        if object_id:
            conditions.append("object_id = :oid")
            params["oid"] = object_id

        where = " AND ".join(conditions)

        with get_db_session(self._settings) as session:
            rows = session.execute(
                text(f"""
                    SELECT r.*,
                           s.name AS subject_name,
                           o.name AS object_name,
                           o.entity_type AS object_type
                    FROM kg_relations r
                    JOIN kg_entities s ON s.entity_id = r.subject_id
                    JOIN kg_entities o ON o.entity_id = r.object_id
                    WHERE {where}
                    ORDER BY r.created_at DESC
                    LIMIT :lim
                """),
                params,
            ).fetchall()

            return [
                _row_to_relation(r, subject_name=r.subject_name, object_name=r.object_name)
                for r in rows
            ]

    async def deactivate_relation(self, relation_id: str) -> None:
        """Soft-delete a relation."""
        with get_db_session(self._settings) as session:
            session.execute(
                text("""
                    UPDATE kg_relations
                    SET is_active = 0, valid_to = datetime('now'), updated_at = datetime('now')
                    WHERE relation_id = :rid
                """),
                {"rid": relation_id},
            )

    # ------------------------------------------------------------------
    # Alias Operations
    # ------------------------------------------------------------------

    async def add_alias(self, entity_id: str, alias_name: str) -> None:
        """Add an alias for an entity (idempotent)."""
        alias_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        with get_db_session(self._settings) as session:
            session.execute(
                text("""
                    INSERT OR IGNORE INTO kg_entity_aliases (alias_id, entity_id, alias_name, created_at)
                    VALUES (:aid, :eid, :alias, :now)
                """),
                {"aid": alias_id, "eid": entity_id, "alias": alias_name, "now": now},
            )

    async def find_entity_by_alias(self, alias_name: str) -> Optional[KGEntity]:
        """Find an entity by one of its aliases."""
        with get_db_session(self._settings) as session:
            row = session.execute(
                text("""
                    SELECT e.* FROM kg_entities e
                    JOIN kg_entity_aliases a ON a.entity_id = e.entity_id
                    WHERE a.alias_name = :alias
                    LIMIT 1
                """),
                {"alias": alias_name},
            ).fetchone()
            if row is None:
                return None
            return _row_to_entity(row)

    # ------------------------------------------------------------------
    # Graph Queries (multi-hop)
    # ------------------------------------------------------------------

    async def get_entity_graph(
        self,
        entity_id: str,
        depth: int = 1,
        max_nodes: int = 50,
    ) -> KGGraphResult:
        """Get the sub-graph centered on *entity_id* using recursive CTE."""
        with get_db_session(self._settings) as session:
            # Recursive CTE to collect reachable entity IDs within *depth* hops
            cte_sql = text(f"""
                WITH RECURSIVE hop AS (
                    -- base case: the seed entity
                    SELECT :eid AS eid, 0 AS d
                    UNION ALL
                    -- expand one hop via active relations (either direction)
                    SELECT
                        CASE
                            WHEN r.subject_id = hop.eid THEN r.object_id
                            ELSE r.subject_id
                        END,
                        hop.d + 1
                    FROM kg_relations r, hop
                    WHERE r.is_active = 1
                      AND (r.subject_id = hop.eid OR r.object_id = hop.eid)
                      AND hop.d < :depth
                )
                SELECT DISTINCT eid FROM hop LIMIT :max_nodes
            """)
            eid_rows = session.execute(
                cte_sql,
                {"eid": entity_id, "depth": depth, "max_nodes": max_nodes},
            ).fetchall()

            entity_ids = [r.eid for r in eid_rows]

            if not entity_ids:
                return KGGraphResult(entities=[], relations=[], depth=depth)

            # Fetch entities
            placeholders = ",".join(f":e{i}" for i in range(len(entity_ids)))
            params: Dict[str, Any] = {f"e{i}": eid for i, eid in enumerate(entity_ids)}

            entity_rows = session.execute(
                text(f"SELECT * FROM kg_entities WHERE entity_id IN ({placeholders})"),
                params,
            ).fetchall()
            entities = [_row_to_entity(r) for r in entity_rows]

            # Fetch active relations between collected entities
            rel_rows = session.execute(
                text(f"""
                    SELECT r.*,
                           s.name AS subject_name,
                           o.name AS object_name,
                           o.entity_type AS object_type
                    FROM kg_relations r
                    JOIN kg_entities s ON s.entity_id = r.subject_id
                    JOIN kg_entities o ON o.entity_id = r.object_id
                    WHERE r.is_active = 1
                      AND r.subject_id IN ({placeholders})
                      AND r.object_id  IN ({placeholders})
                """),
                {**params, **{f"k{i}": eid for i, eid in enumerate(entity_ids)}},
            ).fetchall()
            relations = [
                _row_to_relation(r, subject_name=r.subject_name, object_name=r.object_name)
                for r in rel_rows
            ]

            return KGGraphResult(entities=entities, relations=relations, depth=depth)

    async def find_path(
        self,
        from_entity_id: str,
        to_entity_id: str,
        max_depth: int = 3,
    ) -> List[List[KGRelation]]:
        """Find all shortest paths between two entities using BFS via recursive CTE."""
        with get_db_session(self._settings) as session:
            # Recursive CTE that accumulates the path as JSON arrays of relation IDs
            cte_sql = text("""
                WITH RECURSIVE bfs AS (
                    -- seed: start entity (no relations yet)
                    SELECT
                        :from_eid AS current_eid,
                        '[]'      AS path_rids,
                        0         AS d
                    UNION ALL
                    SELECT
                        CASE
                            WHEN r.subject_id = bfs.current_eid THEN r.object_id
                            ELSE r.subject_id
                        END,
                        json_insert(bfs.path_rids, '$[#]', r.relation_id),
                        bfs.d + 1
                    FROM kg_relations r, bfs
                    WHERE r.is_active = 1
                      AND (r.subject_id = bfs.current_eid OR r.object_id = bfs.current_eid)
                      AND bfs.d < :max_depth
                      AND json_array_length(bfs.path_rids) < 20
                )
                SELECT path_rids FROM bfs
                WHERE current_eid = :to_eid
                ORDER BY d ASC
                LIMIT 5
            """)
            path_rows = session.execute(
                cte_sql,
                {"from_eid": from_entity_id, "to_eid": to_entity_id, "max_depth": max_depth},
            ).fetchall()

            if not path_rows:
                return []

            # Decode each path (list of relation_id strings) and fetch full relations
            result: List[List[KGRelation]] = []
            for prow in path_rows:
                rids: List[str] = json.loads(prow.path_rids)
                if not rids:
                    continue
                rid_placeholders = ",".join(f":r{i}" for i in range(len(rids)))
                rid_params = {f"r{i}": rid for i, rid in enumerate(rids)}

                rel_rows = session.execute(
                    text(f"""
                        SELECT r.*,
                               s.name AS subject_name,
                               o.name AS object_name,
                               o.entity_type AS object_type
                        FROM kg_relations r
                        JOIN kg_entities s ON s.entity_id = r.subject_id
                        JOIN kg_entities o ON o.entity_id = r.object_id
                        WHERE r.relation_id IN ({rid_placeholders})
                        ORDER BY CASE r.relation_id
                            {' '.join(f'WHEN :ord{i} THEN {i}' for i in range(len(rids)))}
                            ELSE {len(rids)} END
                    """),
                    {**rid_params, **{f"ord{i}": rid for i, rid in enumerate(rids)}},
                ).fetchall()
                path_rels = [
                    _row_to_relation(r, subject_name=r.subject_name, object_name=r.object_name)
                    for r in rel_rows
                ]
                result.append(path_rels)

            return result

    async def get_relations_between(
        self,
        entity_a_id: str,
        entity_b_id: str,
    ) -> List[KGRelation]:
        """Get all direct active relations between two entities (either direction)."""
        with get_db_session(self._settings) as session:
            rows = session.execute(
                text("""
                    SELECT r.*,
                           s.name AS subject_name,
                           o.name AS object_name,
                           o.entity_type AS object_type
                    FROM kg_relations r
                    JOIN kg_entities s ON s.entity_id = r.subject_id
                    JOIN kg_entities o ON o.entity_id = r.object_id
                    WHERE r.is_active = 1
                      AND (
                          (r.subject_id = :a AND r.object_id = :b)
                          OR (r.subject_id = :b AND r.object_id = :a)
                      )
                    ORDER BY r.created_at DESC
                """),
                {"a": entity_a_id, "b": entity_b_id},
            ).fetchall()
            return [
                _row_to_relation(r, subject_name=r.subject_name, object_name=r.object_name)
                for r in rows
            ]

    # ------------------------------------------------------------------
    # Batch / Statistics
    # ------------------------------------------------------------------

    async def get_entity_count(self, entity_type: Optional[str] = None) -> int:
        """Count entities, optionally filtered by type."""
        with get_db_session(self._settings) as session:
            if entity_type:
                row = session.execute(
                    text("SELECT COUNT(*) AS cnt FROM kg_entities WHERE entity_type = :etype"),
                    {"etype": entity_type},
                ).fetchone()
            else:
                row = session.execute(
                    text("SELECT COUNT(*) AS cnt FROM kg_entities")
                ).fetchone()
            return row.cnt if row else 0

    async def get_recent_relations(
        self,
        limit: int = 20,
        since_hours: int = 24,
    ) -> List[KGRelation]:
        """Get relations created within the last *since_hours* hours."""
        with get_db_session(self._settings) as session:
            rows = session.execute(
                text("""
                    SELECT r.*,
                           s.name AS subject_name,
                           o.name AS object_name,
                           o.entity_type AS object_type
                    FROM kg_relations r
                    JOIN kg_entities s ON s.entity_id = r.subject_id
                    JOIN kg_entities o ON o.entity_id = r.object_id
                    WHERE r.is_active = 1
                      AND r.created_at >= datetime('now', :hours_neg || ' hours')
                    ORDER BY r.created_at DESC
                    LIMIT :lim
                """),
                {"hours_neg": f"-{since_hours}", "lim": limit},
            ).fetchall()
            return [
                _row_to_relation(r, subject_name=r.subject_name, object_name=r.object_name)
                for r in rows
            ]
