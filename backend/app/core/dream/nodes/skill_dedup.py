"""
SkillDedup — Embedding-based skill deduplication and merge.

Reuses the project's EmbeddingModelManager for embedding computation.
Merges skills with similarity > 0.9, tags variants at similarity > 0.7.
"""

import json
import logging
import math
from typing import Dict, List, Optional, Tuple

from app.core.dream.config import DreamConfig
from app.core.dream.models import DreamState, SkillCard
from app.core.dream.prompts.consolidator import format_consolidator_prompt

logger = logging.getLogger(__name__)


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def _embed_text(text: str) -> List[float]:
    """Get embedding for text using the project's embedding manager."""
    try:
        from app.core.embedding_manager import get_embedding_manager
        mgr = get_embedding_manager()
        model = mgr.get_model()
        if model is None:
            return []
        result = await model.aget_text_embedding(text)
        return result
    except Exception as e:
        logger.warning(f"Embedding failed: {e}")
        return []


def _skill_to_text(skill: SkillCard) -> str:
    """Convert skill to text for embedding comparison."""
    parts = [skill.problem_pattern, skill.trigger]
    parts.extend(skill.steps[:3])
    return " ".join(p for p in parts if p)


def _merge_skills(primary: SkillCard, secondary: SkillCard) -> SkillCard:
    """Merge two skills, keeping primary as base."""
    merged_tags = list(set(primary.tags + secondary.tags))
    if "variant" not in merged_tags:
        merged_tags.append("merged")

    # Merge steps (deduplicate)
    seen_steps = set(primary.steps)
    merged_steps = list(primary.steps)
    for s in secondary.steps:
        if s not in seen_steps:
            merged_steps.append(s)
            seen_steps.add(s)

    # Merge anti_patterns
    seen_anti = set(primary.anti_patterns)
    merged_anti = list(primary.anti_patterns)
    for a in secondary.anti_patterns:
        if a not in seen_anti:
            merged_anti.append(a)
            seen_anti.add(a)

    # Merge regression_tests (need >= 6 after merge)
    merged_tests = list(primary.regression_tests) + list(secondary.regression_tests)
    # Deduplicate by test_id
    seen_ids = set()
    deduped_tests = []
    for t in merged_tests:
        tid = t.get("test_id", "")
        if tid not in seen_ids:
            deduped_tests.append(t)
            seen_ids.add(tid)

    # Merge source traj IDs
    merged_sources = list(set(primary.source_traj_ids + secondary.source_traj_ids))

    # Confidence in consolidator range
    config = DreamConfig()
    low, high = config.consolidator_confidence_range
    avg_conf = (primary.confidence + secondary.confidence) / 2
    merged_conf = max(low, min(high, avg_conf))

    return SkillCard(
        skill_id=primary.skill_id,
        skill_name=primary.skill_name,
        trigger=f"{primary.trigger} OR {secondary.trigger}",
        problem_pattern=primary.problem_pattern,
        steps=merged_steps,
        verification=primary.verification + secondary.verification,
        anti_patterns=merged_anti,
        examples=primary.examples + secondary.examples,
        tags=merged_tags,
        confidence=merged_conf,
        supporting_cases=primary.supporting_cases + secondary.supporting_cases,
        source_traj_ids=merged_sources,
        status="candidate",
        regression_tests=deduped_tests,
    )


async def skill_dedup_node_async(state: DreamState) -> DreamState:
    """Async version: compute embeddings for dedup."""
    skills = state.get("distilled_skills", [])
    if not skills:
        state["deduplicated_skills"] = []
        return state

    # Compute embeddings for all skills
    embeddings: Dict[str, List[float]] = {}
    for skill in skills:
        text = _skill_to_text(skill)
        emb = await _embed_text(text)
        embeddings[skill.skill_id] = emb

    # Compute pairwise similarities
    n = len(skills)
    sim_matrix: Dict[Tuple[str, str], float] = {}
    for i in range(n):
        for j in range(i + 1, n):
            a = embeddings.get(skills[i].skill_id, [])
            b = embeddings.get(skills[j].skill_id, [])
            sim = _cosine_similarity(a, b) if a and b else 0.0
            sim_matrix[(skills[i].skill_id, skills[j].skill_id)] = sim

    # Group similar skills
    merged_set: set = set()
    skill_map = {s.skill_id: s for s in skills}
    result: List[SkillCard] = []

    for i in range(n):
        si = skills[i]
        if si.skill_id in merged_set:
            continue

        # Check for merges
        merged = si
        for j in range(i + 1, n):
            sj = skills[j]
            if sj.skill_id in merged_set:
                continue

            key = (si.skill_id, sj.skill_id)
            sim = sim_matrix.get(key, 0.0)

            if sim > 0.9:
                merged = _merge_skills(merged, sj)
                merged_set.add(sj.skill_id)
                logger.info(
                    f"SkillDedup: merged {sj.skill_name} into {merged.skill_name} "
                    f"(sim={sim:.3f})"
                )
            elif sim > 0.7:
                if "variant" not in merged.tags:
                    merged.tags.append("variant")

        result.append(merged)

    logger.info(
        f"SkillDedup: {len(skills)} → {len(result)} skills "
        f"({len(merged_set)} merged)"
    )

    state["deduplicated_skills"] = result
    return state


def skill_dedup_node(state: DreamState) -> DreamState:
    """Dream Subgraph node: deduplicate skills using embedding similarity.

    Falls back to text-based similarity when embeddings are unavailable.
    """
    skills = state.get("distilled_skills", [])
    if not skills:
        state["deduplicated_skills"] = []
        return state

    # Text-based fallback similarity
    skill_map = {s.skill_id: s for s in skills}
    n = len(skills)
    merged_set: set = set()
    result: List[SkillCard] = []

    for i in range(n):
        si = skills[i]
        if si.skill_id in merged_set:
            continue

        merged = si
        for j in range(i + 1, n):
            sj = skills[j]
            if sj.skill_id in merged_set:
                continue

            sim = _text_similarity(si, sj)
            if sim > 0.9:
                merged = _merge_skills(merged, sj)
                merged_set.add(sj.skill_id)
                logger.info(
                    f"SkillDedup: merged {sj.skill_name} into {merged.skill_name}"
                )
            elif sim > 0.7:
                if "variant" not in merged.tags:
                    merged.tags.append("variant")

        result.append(merged)

    logger.info(f"SkillDedup: {len(skills)} → {len(result)} skills")
    state["deduplicated_skills"] = result
    return state


def _text_similarity(a: SkillCard, b: SkillCard) -> float:
    """Jaccard-like text similarity for fallback."""
    def _tokenize(text: str) -> set:
        return set(text.lower().split())

    tokens_a = _tokenize(_skill_to_text(a))
    tokens_b = _tokenize(_skill_to_text(b))

    if not tokens_a or not tokens_b:
        return 0.0

    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)
