"""
Knowledge Graph Query Templates.

Parameterized query templates that use the KGStoreInterface methods.
LLM never generates SQL directly — each template maps an intent to a
store-method-based query function.

Templates:
- ASK_PERSON_ROLE   — person's role/position
- ASK_PERSON_ALL    — all relations for a person
- ASK_PROJECT_OWNER — project owner
- ASK_PROJECT_ALL   — all relations for a project
- ASK_PREFERENCE    — person's preferences
- ASK_HABIT         — person's habits
- ASK_RELATION_BETWEEN — relations between two entities
- ASK_WHO_HAS_ROLE  — who has a specific role
- ASK_ORG_MEMBERS   — members of an org
- FALLBACK_SEARCH   — fuzzy search entities
"""

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from app.memory.kg.models import KGRelation
from app.memory.kg.store_interface import KGStoreInterface

logger = logging.getLogger(__name__)


@dataclass
class QueryTemplate:
    """A parameterized KG query template.

    Attributes:
        name: Template name (matches an intent label).
        description: Human-readable description of what this template queries.
        param_names: Ordered list of parameter names the execute function expects.
        execute: Async callable ``(store, params) -> List[KGRelation]``.
    """

    name: str
    description: str
    param_names: List[str] = field(default_factory=list)
    execute: Callable = field(default=None)


# ---------------------------------------------------------------------------
# Template execute implementations
# ---------------------------------------------------------------------------


async def _ask_person_role(
    store: KGStoreInterface,
    params: Dict[str, str],
) -> List[KGRelation]:
    """Query a person's role/position relations."""
    person_name = params.get("person", "")
    if not person_name:
        return []

    entity = await store.find_entity(person_name)
    if entity is None:
        entity = await store.find_entity_by_alias(person_name)
    if entity is None:
        return []

    relations = await store.find_active_relations(
        subject_id=entity.entity_id,
        predicate="HAS_ROLE",
    )
    # Also check WORKS_AT for role context
    works_at = await store.find_active_relations(
        subject_id=entity.entity_id,
        predicate="WORKS_AT",
    )
    return relations + works_at


async def _ask_person_all(
    store: KGStoreInterface,
    params: Dict[str, str],
) -> List[KGRelation]:
    """Query all relations for a person."""
    person_name = params.get("person", "")
    if not person_name:
        return []

    entity = await store.find_entity(person_name)
    if entity is None:
        entity = await store.find_entity_by_alias(person_name)
    if entity is None:
        return []

    # Relations where person is the subject
    as_subject = await store.find_active_relations(subject_id=entity.entity_id)
    # Relations where person is the object
    as_object = await store.find_active_relations(object_id=entity.entity_id)
    return as_subject + as_object


async def _ask_project_owner(
    store: KGStoreInterface,
    params: Dict[str, str],
) -> List[KGRelation]:
    """Query the owner/leader of a project."""
    project_name = params.get("project", "")
    if not project_name:
        return []

    entity = await store.find_entity(project_name)
    if entity is None:
        entity = await store.find_entity_by_alias(project_name)
    if entity is None:
        return []

    # RESPONSIBLE_FOR points from person to project, so project is the object
    responsible = await store.find_active_relations(
        predicate="RESPONSIBLE_FOR",
        object_id=entity.entity_id,
    )
    # Also check MANAGES
    manages = await store.find_active_relations(
        predicate="MANAGES",
        object_id=entity.entity_id,
    )
    return responsible + manages


async def _ask_project_all(
    store: KGStoreInterface,
    params: Dict[str, str],
) -> List[KGRelation]:
    """Query all relations for a project."""
    project_name = params.get("project", "")
    if not project_name:
        return []

    entity = await store.find_entity(project_name)
    if entity is None:
        entity = await store.find_entity_by_alias(project_name)
    if entity is None:
        return []

    as_subject = await store.find_active_relations(subject_id=entity.entity_id)
    as_object = await store.find_active_relations(object_id=entity.entity_id)
    return as_subject + as_object


async def _ask_preference(
    store: KGStoreInterface,
    params: Dict[str, str],
) -> List[KGRelation]:
    """Query a person's preferences."""
    person_name = params.get("person", "")
    if not person_name:
        return []

    entity = await store.find_entity(person_name)
    if entity is None:
        entity = await store.find_entity_by_alias(person_name)
    if entity is None:
        return []

    return await store.find_active_relations(
        subject_id=entity.entity_id,
        predicate="HAS_PREFERENCE",
    )


async def _ask_habit(
    store: KGStoreInterface,
    params: Dict[str, str],
) -> List[KGRelation]:
    """Query a person's habits."""
    person_name = params.get("person", "")
    if not person_name:
        return []

    entity = await store.find_entity(person_name)
    if entity is None:
        entity = await store.find_entity_by_alias(person_name)
    if entity is None:
        return []

    return await store.find_active_relations(
        subject_id=entity.entity_id,
        predicate="HAS_HABIT",
    )


async def _ask_relation_between(
    store: KGStoreInterface,
    params: Dict[str, str],
) -> List[KGRelation]:
    """Query relations between two entities."""
    entity_a_name = params.get("entity_a", "")
    entity_b_name = params.get("entity_b", "")
    if not entity_a_name or not entity_b_name:
        return []

    entity_a = await store.find_entity(entity_a_name)
    if entity_a is None:
        entity_a = await store.find_entity_by_alias(entity_a_name)
    if entity_a is None:
        return []

    entity_b = await store.find_entity(entity_b_name)
    if entity_b is None:
        entity_b = await store.find_entity_by_alias(entity_b_name)
    if entity_b is None:
        return []

    return await store.get_relations_between(entity_a.entity_id, entity_b.entity_id)


async def _ask_who_has_role(
    store: KGStoreInterface,
    params: Dict[str, str],
) -> List[KGRelation]:
    """Query who has a specific role."""
    role = params.get("role", "")
    if not role:
        return []

    # Search for entities with the role name; the role may be an entity
    role_entities = await store.search_entities(role)
    if role_entities:
        # Try to find HAS_ROLE relations pointing to this entity
        for re in role_entities:
            relations = await store.find_active_relations(
                predicate="HAS_ROLE",
                object_id=re.entity_id,
            )
            if relations:
                return relations

    # Fallback: search all HAS_ROLE relations and filter by object_name
    all_role_relations = await store.find_active_relations(predicate="HAS_ROLE")
    role_lower = role.lower()
    return [
        r for r in all_role_relations
        if role_lower in r.object_name.lower()
    ]


async def _ask_org_members(
    store: KGStoreInterface,
    params: Dict[str, str],
) -> List[KGRelation]:
    """Query members of an organisation."""
    org_name = params.get("org", "")
    if not org_name:
        return []

    entity = await store.find_entity(org_name)
    if entity is None:
        entity = await store.find_entity_by_alias(org_name)
    if entity is None:
        return []

    # MEMBER_OF points from person to org, so org is the object
    member_of = await store.find_active_relations(
        predicate="MEMBER_OF",
        object_id=entity.entity_id,
    )
    # Also check BELONGS_TO
    belongs_to = await store.find_active_relations(
        predicate="BELONGS_TO",
        object_id=entity.entity_id,
    )
    # And WORKS_AT
    works_at = await store.find_active_relations(
        predicate="WORKS_AT",
        object_id=entity.entity_id,
    )
    return member_of + belongs_to + works_at


async def _fallback_search(
    store: KGStoreInterface,
    params: Dict[str, str],
) -> List[KGRelation]:
    """Fuzzy search entities and return their relations."""
    query = params.get("query", "")
    if not query:
        return []

    entities = await store.search_entities(query)
    if not entities:
        return []

    all_relations: List[KGRelation] = []
    for entity in entities[:5]:  # Limit to top 5 entities
        as_subject = await store.find_active_relations(subject_id=entity.entity_id)
        as_object = await store.find_active_relations(object_id=entity.entity_id)
        all_relations.extend(as_subject)
        all_relations.extend(as_object)

    return all_relations


# ---------------------------------------------------------------------------
# Template Registry
# ---------------------------------------------------------------------------

_TEMPLATE_MAP: Dict[str, QueryTemplate] = {
    "ASK_PERSON_ROLE": QueryTemplate(
        name="ASK_PERSON_ROLE",
        description="Query a person's role/position",
        param_names=["person"],
        execute=_ask_person_role,
    ),
    "ASK_PERSON_ALL": QueryTemplate(
        name="ASK_PERSON_ALL",
        description="Query all relations for a person",
        param_names=["person"],
        execute=_ask_person_all,
    ),
    "ASK_PROJECT_OWNER": QueryTemplate(
        name="ASK_PROJECT_OWNER",
        description="Query the owner/leader of a project",
        param_names=["project"],
        execute=_ask_project_owner,
    ),
    "ASK_PROJECT_ALL": QueryTemplate(
        name="ASK_PROJECT_ALL",
        description="Query all relations for a project",
        param_names=["project"],
        execute=_ask_project_all,
    ),
    "ASK_PREFERENCE": QueryTemplate(
        name="ASK_PREFERENCE",
        description="Query a person's preferences",
        param_names=["person"],
        execute=_ask_preference,
    ),
    "ASK_HABIT": QueryTemplate(
        name="ASK_HABIT",
        description="Query a person's habits",
        param_names=["person"],
        execute=_ask_habit,
    ),
    "ASK_RELATION_BETWEEN": QueryTemplate(
        name="ASK_RELATION_BETWEEN",
        description="Query relations between two entities",
        param_names=["entity_a", "entity_b"],
        execute=_ask_relation_between,
    ),
    "ASK_WHO_HAS_ROLE": QueryTemplate(
        name="ASK_WHO_HAS_ROLE",
        description="Query who has a specific role",
        param_names=["role"],
        execute=_ask_who_has_role,
    ),
    "ASK_ORG_MEMBERS": QueryTemplate(
        name="ASK_ORG_MEMBERS",
        description="Query members of an organisation",
        param_names=["org"],
        execute=_ask_org_members,
    ),
    "FALLBACK_SEARCH": QueryTemplate(
        name="FALLBACK_SEARCH",
        description="Fuzzy search entities and return their relations",
        param_names=["query"],
        execute=_fallback_search,
    ),
}


def get_template(intent: str) -> Optional[QueryTemplate]:
    """Look up a query template by intent label.

    Args:
        intent: One of the VALID_INTENTS labels (e.g. ``"ASK_PERSON_ROLE"``).

    Returns:
        The matching ``QueryTemplate``, or ``None`` if the intent is unknown.
    """
    return _TEMPLATE_MAP.get(intent)
