"""Evidence registry — extensible source confidence table.

Skills register their source_type and confidence here.
New sources only need to append a row — no engine code changes required.
"""

from pydantic import BaseModel
from typing import Optional


class MemoryEvidence(BaseModel):
    """Extensible structured evidence reference.

    Does not hard-code source types or fields. Any skill/tool can produce
    evidence by filling source_type + ref_id + meta.
    """

    # --- Required ---
    source_type: str = ""       # e.g. "conversation", "arxiv-search", "baidu-search"
    ref_id: str = ""            # event_id / URL / file_path / trace_id
    summary: str = ""           # human-readable summary
    ts: str = ""                # evidence timestamp

    # --- Confidence ---
    confidence: float = 1.0     # set by producer

    # --- Extension (arbitrary key-value) ---
    meta: dict = {}

    # --- State ---
    orphaned: bool = False      # source has been deleted/expired


# Source confidence registry — hot-updateable, no code change for new skills
SOURCE_CONFIDENCE: dict[str, float] = {
    "conversation": 0.9,
    "arxiv-search": 0.8,
    "conference-paper": 0.85,
    "agent-papers": 0.7,
    "baidu-search": 0.6,
    "deep_source_extractor": 0.75,
    "knowledge_base": 0.8,
    "tool_execution": 0.7,
    # New skills: just append a line below
}


def get_source_confidence(source_type: str) -> float:
    """Return the base confidence for a source type.

    Unknown sources default to 0.5.
    """
    return SOURCE_CONFIDENCE.get(source_type, 0.5)
