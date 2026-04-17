"""
Wiki Migration Tool — One-time migration from memories table to Wiki pages.

Reads high-confidence fact memories from the memories table, clusters them
by topic using LLM, and generates Wiki pages.
"""

import json
import logging
from typing import Any, Dict, List

from app.config import get_settings
from app.core.database import get_db_session
from sqlalchemy import text

logger = logging.getLogger(__name__)


async def migrate_memories_to_wiki(
    min_confidence: float = 0.8,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Migrate high-confidence fact memories to Wiki pages.

    Args:
        min_confidence: Minimum confidence threshold for migration
        dry_run: If True, only plan without writing

    Returns:
        Migration statistics
    """
    settings = get_settings()

    # Read high-confidence memories
    with get_db_session(settings) as session:
        rows = session.execute(
            text("""
                SELECT id, content, memory_type, confidence, metadata
                FROM memories
                WHERE confidence >= :min_conf
                AND memory_type IN ('fact', 'context', 'pattern')
                ORDER BY confidence DESC
            """),
            {"min_conf": min_confidence},
        ).fetchall()

    if not rows:
        logger.info("No memories to migrate")
        return {"migrated": 0, "pages_created": 0, "status": "no_memories"}

    # Parse memories
    memories = []
    for row in rows:
        meta = row.metadata if row.metadata else {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                meta = {}
        memories.append({
            "id": row.id,
            "content": row.content,
            "type": row.memory_type,
            "confidence": row.confidence,
            "topic": meta.get("topic", "general"),
        })

    logger.info(f"Found {len(memories)} memories for migration")

    if dry_run:
        return {
            "migrated": 0,
            "pages_created": 0,
            "candidates": len(memories),
            "status": "dry_run",
            "sample": memories[:5],
        }

    # Cluster by topic
    topic_groups: Dict[str, List[Dict]] = {}
    for m in memories:
        topic = m["topic"]
        if topic not in topic_groups:
            topic_groups[topic] = []
        topic_groups[topic].append(m)

    # Create Wiki pages for each topic cluster
    from app.memory.wiki.store import get_wiki_store
    from app.memory.wiki.models import WikiPage

    store = get_wiki_store()
    await store.initialize()

    pages_created = 0
    for topic, group in topic_groups.items():
        try:
            # Build page content
            title = topic.replace("_", " ").replace("-", " ").title()
            facts = "\n".join(f"- {m['content']}" for m in group)
            evidence = "\n".join(
                f"- Confidence: {m['confidence']:.2f}" for m in group
            )

            content = f"""# {title}

## Summary

Auto-migrated from {len(group)} memories about {topic}.

## Key Facts

{facts}

## Evidence

{evidence}

## Details

*Migrated from memories table.*
"""
            page = WikiPage(
                title=title,
                summary=f"Auto-migrated: {len(group)} memories about {topic}",
                content=content,
                tags=[topic],
                confidence=max(m["confidence"] for m in group),
            )
            await store.create_page(page)
            pages_created += 1

        except Exception as e:
            logger.error(f"Failed to migrate topic '{topic}': {e}")

    logger.info(f"Migration complete: {pages_created} pages created from {len(memories)} memories")
    return {
        "migrated": len(memories),
        "pages_created": pages_created,
        "topics": list(topic_groups.keys()),
        "status": "completed",
    }
