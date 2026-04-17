"""
Research Data Models for Tree of Thoughts Framework.

Defines Pydantic models for evidence collection, coverage mapping,
and contradiction detection during deep research tasks.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Optional


class EvidenceItem(BaseModel):
    """A single piece of evidence extracted from a source document.

    Attributes:
        source_id: Unique identifier for the source (e.g., arxiv ID, URL hash).
        source_type: Type of source (arxiv, blog, github, docs, benchmark, etc.).
        title: Title or heading of the source document.
        url: URL or locator for the source.
        quote: Original text fragment extracted from the source.
        claim: The claim or assertion distilled from the quote.
        numbers: Structured metrics, values, or baselines extracted from the evidence.
        reliability: Reliability score of the source (0.0 - 1.0).
        relevance: Relevance score to the current research query (0.0 - 1.0).
    """

    source_id: str = Field(description="Unique identifier for the source")
    source_type: str = Field(
        description="Type of source: arxiv, blog, github, docs, benchmark, etc."
    )
    title: str = Field(description="Title or heading of the source document")
    url: str = Field(default="", description="URL or locator for the source")
    quote: str = Field(description="Original text fragment extracted from the source")
    claim: str = Field(
        description="The claim or assertion distilled from the quote"
    )
    numbers: List[Dict] = Field(
        default_factory=list,
        description="Structured metrics, values, or baselines extracted from the evidence",
    )
    reliability: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Reliability score of the source (0.0 - 1.0)",
    )
    relevance: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Relevance score to the current research query (0.0 - 1.0)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "source_id": "arxiv_2301_01234",
                "source_type": "arxiv",
                "title": "Attention Is All You Need",
                "url": "https://arxiv.org/abs/1706.03762",
                "quote": "The Transformer achieves 28.4 BLEU on WMT 2014 English-to-German.",
                "claim": "Transformer architecture achieves state-of-the-art 28.4 BLEU on WMT'14 En-De.",
                "numbers": [
                    {"metric": "BLEU", "value": 28.4, "dataset": "WMT 2014 En-De"}
                ],
                "reliability": 0.95,
                "relevance": 0.85,
            }
        }
    )


class CoverageTopic(BaseModel):
    """Coverage status for a single research sub-topic.

    Attributes:
        topic: Name of the sub-topic.
        covered: Whether the topic has been adequately covered.
        sources_count: Number of sources contributing evidence for this topic.
        claims_count: Number of distinct claims extracted for this topic.
        numbers_count: Number of quantitative data points for this topic.
        missing_evidence_types: Types of evidence still needed.
        notes: Free-form notes about coverage quality or gaps.
    """

    topic: str = Field(description="Name of the sub-topic")
    covered: bool = Field(default=False, description="Whether the topic is adequately covered")
    sources_count: int = Field(default=0, description="Number of sources contributing evidence")
    claims_count: int = Field(default=0, description="Number of distinct claims extracted")
    numbers_count: int = Field(default=0, description="Number of quantitative data points")
    missing_evidence_types: List[str] = Field(
        default_factory=list,
        description="Types of evidence still needed (e.g., benchmark, benchmark_comparison)",
    )
    notes: str = Field(default="", description="Free-form notes about coverage quality or gaps")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "topic": "Transformer architecture performance",
                "covered": True,
                "sources_count": 3,
                "claims_count": 5,
                "numbers_count": 4,
                "missing_evidence_types": [],
                "notes": "Well covered with benchmarks from multiple sources.",
            }
        }
    )


class CoverageMap(BaseModel):
    """Overall coverage map for a research query.

    Tracks which sub-topics have been covered, identifies critical gaps,
    and provides a coverage score and recommended next actions.

    Attributes:
        query: The original research query.
        topics: List of sub-topics with their coverage status.
        critical_missing_topics: Topics that are completely missing evidence.
        critical_missing_evidence_types: Evidence types that are critically needed.
        coverage_score: Overall coverage score (0.0 - 1.0).
        recommended_next_actions: Suggested actions to improve coverage.
    """

    query: str = Field(description="The original research query")
    topics: List[CoverageTopic] = Field(
        default_factory=list,
        description="List of sub-topics with their coverage status",
    )
    critical_missing_topics: List[str] = Field(
        default_factory=list,
        description="Topics that are completely missing evidence",
    )
    critical_missing_evidence_types: List[str] = Field(
        default_factory=list,
        description="Evidence types that are critically needed across topics",
    )
    coverage_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Overall coverage score (0.0 - 1.0)",
    )
    recommended_next_actions: List[Dict] = Field(
        default_factory=list,
        description="Suggested actions to improve coverage",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "What are the latest advances in LLM reasoning?",
                "topics": [
                    {
                        "topic": "Chain-of-Thought prompting",
                        "covered": True,
                        "sources_count": 4,
                        "claims_count": 6,
                        "numbers_count": 3,
                        "missing_evidence_types": [],
                        "notes": "Well covered.",
                    }
                ],
                "critical_missing_topics": ["Tree of Thoughts benchmarks"],
                "critical_missing_evidence_types": ["benchmark_comparison"],
                "coverage_score": 0.65,
                "recommended_next_actions": [
                    {
                        "action": "search",
                        "query": "Tree of Thoughts benchmark results 2024",
                        "reason": "No evidence found for ToT benchmarks.",
                    }
                ],
            }
        }
    )


class Contradiction(BaseModel):
    """A contradiction or conflict between two pieces of evidence.

    Records conflicting claims from different sources, with analysis
    of possible explanations and a verification plan.

    Attributes:
        issue: Short description of the contradiction.
        type: Category of contradiction (metric_conflict, claim_conflict,
              definition_conflict, missing_context).
        side_a: First side of the contradiction (claim, source_ids, quote).
        side_b: Second side of the contradiction (claim, source_ids, quote).
        possible_explanations: Potential reasons for the discrepancy.
        verification_plan: Plan for resolving the contradiction.
        severity: Severity score (0.0 - 1.0), higher means more critical.
    """

    issue: str = Field(description="Short description of the contradiction")
    type: str = Field(
        description=(
            "Category of contradiction: "
            "metric_conflict, claim_conflict, definition_conflict, missing_context"
        ),
    )
    side_a: Dict = Field(
        description="First side: {claim, source_ids, quote}",
    )
    side_b: Dict = Field(
        description="Second side: {claim, source_ids, quote}",
    )
    possible_explanations: List[str] = Field(
        default_factory=list,
        description="Potential reasons for the discrepancy",
    )
    verification_plan: Dict = Field(
        default_factory=dict,
        description="Plan for resolving: {what_to_check, suggested_queries}",
    )
    severity: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Severity score (0.0 - 1.0), higher means more critical",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "issue": "Conflicting BLEU scores for the same model",
                "type": "metric_conflict",
                "side_a": {
                    "claim": "Model X achieves 28.4 BLEU on WMT'14 En-De.",
                    "source_ids": ["arxiv_2301_01234"],
                    "quote": "BLEU score of 28.4 on WMT 2014.",
                },
                "side_b": {
                    "claim": "Model X achieves 27.8 BLEU on WMT'14 En-De.",
                    "source_ids": ["blog_example_com"],
                    "quote": "We measured 27.8 BLEU on the same dataset.",
                },
                "possible_explanations": [
                    "Different tokenization schemes",
                    "Different test set splits",
                    "Blog may be reporting case-sensitive BLEU.",
                ],
                "verification_plan": {
                    "what_to_check": "Tokenization and case sensitivity settings",
                    "suggested_queries": [
                        "Model X BLEU score tokenization sensitivity",
                        "WMT 2014 En-De standard evaluation protocol",
                    ],
                },
                "severity": 0.6,
            }
        }
    )
