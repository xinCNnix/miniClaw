"""
Knowledge Graph Prompt Constants.

Three core prompts used by KGExtractor:
- MEMORY_CLASSIFY_PROMPT  — judge whether a conversation is worth storing in the KG
- TRIPLE_EXTRACT_PROMPT   — extract (subject, predicate, object) triples from text
- QUERY_ROUTE_PROMPT      — recognise the user's query intent and entities
"""

# ---------------------------------------------------------------------------
# Predefined predicate set — the LLM must only emit these predicates.
# ---------------------------------------------------------------------------
VALID_PREDICATES: list[str] = [
    "WORKS_AT",
    "HAS_ROLE",
    "BELONGS_TO",
    "HAS_PREFERENCE",
    "HAS_HABIT",
    "RESPONSIBLE_FOR",
    "MANAGES",
    "REPORTS_TO",
    "AT_TIME",
    "LOCATED_AT",
    "KNOWN_AS",
    "MEMBER_OF",
    "HAS_SKILL",
    "OWNS",
    "CREATED",
]

# ---------------------------------------------------------------------------
# Predefined intent labels — the LLM must only emit these intents.
# ---------------------------------------------------------------------------
VALID_INTENTS: list[str] = [
    "ASK_PERSON_ROLE",
    "ASK_PERSON_ALL",
    "ASK_PROJECT_OWNER",
    "ASK_PROJECT_ALL",
    "ASK_PREFERENCE",
    "ASK_HABIT",
    "ASK_RELATION_BETWEEN",
    "ASK_WHO_HAS_ROLE",
    "ASK_ORG_MEMBERS",
    "FALLBACK_SEARCH",
]

# ---------------------------------------------------------------------------
# 1. Memory Classify Prompt
# ---------------------------------------------------------------------------

MEMORY_CLASSIFY_PROMPT: str = """\
You are a knowledge-graph gatekeeper. Decide whether the conversation below \
contains information worth persisting in a structured knowledge graph.

**Worth storing** (should_store = true):
- Facts about people (roles, organisations, skills, relationships)
- Facts about projects (ownership, membership, status)
- User preferences and habits (coding style, communication preferences)
- Organisation structure information

**NOT worth storing** (should_store = false):
- Short chitchat, greetings, small talk
- Pure operational commands ("run this", "show me that")
- Transient debugging output
- Questions without new factual information

Return ONLY valid JSON (no markdown fences):
{{"should_store": true/false, "reason": "brief explanation"}}\
"""

# ---------------------------------------------------------------------------
# 2. Triple Extraction Prompt
# ---------------------------------------------------------------------------

_TRIPLE_PREDICATES_BLOCK = "\n".join(f"- {p}" for p in VALID_PREDICATES)

TRIPLE_EXTRACT_PROMPT: str = f"""\
You are a knowledge-graph triple extractor. Read the conversation and extract \
subject-predicate-object triples that represent factual knowledge.

**Rules**:
1. The `predicate` field MUST be one of the following (use exactly):
{_TRIPLE_PREDICATES_BLOCK}
2. Each triple must include:
   - subject: entity name (e.g. "张三")
   - subject_type: one of Person, Org, Project, Client, Event, Preference, Time, Other
   - predicate: from the list above
   - object: entity or value
   - object_type: one of Person, Org, Project, Client, Event, Preference, Time, Other
   - qualifiers: optional dict of additional context (e.g. {{"since": "2024"}})
   - confidence: float 0.0–1.0

3. Only extract facts you are confident about. Skip opinions, guesses, or vague \
statements.
4. If no meaningful triples exist, return an empty array.

Return ONLY a valid JSON array (no markdown fences):
[
  {{{{
    "subject": "...",
    "subject_type": "Person",
    "predicate": "WORKS_AT",
    "object": "...",
    "object_type": "Org",
    "qualifiers": {{}},
    "confidence": 0.9
  }}}}
]\
"""

# ---------------------------------------------------------------------------
# 3. Query Route Prompt
# ---------------------------------------------------------------------------

_INTENTS_BLOCK = "\n".join(f"- {i}" for i in VALID_INTENTS)

QUERY_ROUTE_PROMPT: str = f"""\
You are a knowledge-graph query router. Analyse the user's question and decide \
how the system should look up the answer.

**Available intents**:
{_INTENTS_BLOCK}

**Rules**:
1. The `intent` field MUST be one of the intents listed above.
2. `entities` is a dict mapping entity role to entity name (e.g. \
{{"person": "张三", "org": "阿里"}}).
3. `use_kg` should be true when the question can be answered from structured \
facts. Set false only when it is a general-knowledge question or ambiguous \
search (intent = "FALLBACK_SEARCH").

Return ONLY valid JSON (no markdown fences):
{{"intent": "ASK_PERSON_ROLE", "entities": {{"person": "王总"}}, "use_kg": true}}\
"""
