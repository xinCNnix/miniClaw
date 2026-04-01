"""
Research Report Writing Profile.

Profile for research report and literature survey tasks. Emphasizes
evidence quality, source diversity, structural coherence, and
depth of analysis.
"""

from .base import DomainProfile

RESEARCH_WRITING_PROFILE = DomainProfile(
    task="research_writing",
    goal=(
        "Produce a well-structured research report with rigorous "
        "evidence, diverse sources, and comprehensive analysis"
    ),
    must_check=[
        "citation_accuracy",
        "source_credibility",
        "claim_evidence_alignment",
        "methodology_transparency",
    ],
    preferred_methods=[
        "systematic_literature_review",
        "comparative_analysis",
        "evidence_synthesis",
        "cross_reference_validation",
    ],
    fatal_flaws=[
        "unsupported_generic_claim",
        "missing_citation",
        "factual_error",
        "logical_inconsistency",
        "plagiarism_risk",
    ],
    scoring_dimensions={
        "evidence_quality": (
            "Reliability, relevance, and recency of cited evidence"
        ),
        "structural_coherence": (
            "Logical flow and organization of the report"
        ),
        "depth_of_analysis": (
            "Thoroughness of examination beyond surface-level summary"
        ),
        "source_diversity": (
            "Variety and independence of referenced sources"
        ),
        "clarity": (
            "Readability and precision of scientific writing"
        ),
        "completeness": (
            "Coverage of all relevant aspects of the research topic"
        ),
    },
    weights={
        "evidence_quality": 0.25,
        "structural_coherence": 0.20,
        "depth_of_analysis": 0.20,
        "source_diversity": 0.15,
        "clarity": 0.10,
        "completeness": 0.10,
    },
    stop_condition_signals={
        "sufficient_coverage": [
            "all_required_sections_addressed",
            "key_sources_cited",
        ],
        "diminishing_returns": [
            "additional_sources_add_minimal_new_information",
            "analysis_depth_plateau",
        ],
        "quality_threshold": [
            "evidence_quality_score_above_target",
            "structural_coherence_verified",
        ],
    },
    confidence_calibration_rules=[
        {
            "condition": "single_source_claim",
            "action": "reduce_confidence",
            "adjustment": "flag for additional corroboration",
        },
        {
            "condition": "peer_reviewed_sources_only",
            "action": "increase_confidence",
            "adjustment": "boost by 0.1 per verified peer-reviewed source",
        },
        {
            "condition": "conflicting_evidence_unaddressed",
            "action": "reduce_confidence",
            "adjustment": "cap at 0.6 until conflict resolved",
        },
    ],
    output_requirements=[
        "clear_problem_statement",
        "explicit_contributions",
        "methods_section_with_reproducible_details",
        "evaluation_plan_or_results_summary",
        "limitations_section",
    ],
    style_constraints=[
        "use_academic_tone",
        "proper_citation_format",
        "structured_sections_with_headings",
    ],
    generator_instruction=(
        "You are a Tree-of-Thought research writing agent. Rules:\n"
        "\n"
        "1. SEARCH PROCEDURE (6 steps):\n"
        "   generate -> evaluate -> prune -> expand -> re-evaluate -> final check\n"
        "\n"
        "2. OUTPUT: Structured JSON only. No prose outside JSON.\n"
        "\n"
        "3. EVIDENCE RULES:\n"
        "   - Every major claim needs supporting evidence (paper name/author/method/benchmark)\n"
        "   - Prefer concrete mechanisms over marketing statements\n"
        "   - Explicitly list uncertainties and open questions\n"
        '   - No generic filler ("in recent years", "as we all know")\n'
        "\n"
        "4. BRANCH STRUCTURE:\n"
        "   Depth 0: Generate N route proposals, each with:\n"
        "     route_id, thesis_statement, structure_outline(5-10 sections),\n"
        "     key_topics(8-15), novelty_angle, risks, recommended_sources\n"
        "   Depth 1: Expand selected routes into full outlines\n"
        "   Depth 2: Write sections with claims/citations\n"
        "   Depth 3: Final consistency check across all sections\n"
        "\n"
        "5. MANDATORY TOPICS to cover in report:\n"
        "   - Comparison table when multiple methods exist\n"
        "   - Explicit uncertainties and open questions\n"
        "   - Evaluation methodology or benchmark plan"
    ),
    evaluator_instruction=(
        "Additional evaluation rules for research writing:\n"
        "\n"
        "1. PENALTY RULES:\n"
        "   - Generic/vague outline -> -3 from structural_coherence\n"
        "   - Shallow buzzwords without mechanisms -> -3 from depth_of_analysis\n"
        "   - No evaluation/benchmark section -> -2 from completeness\n"
        "   - No open questions or limitations -> -2 from evidence_quality\n"
        "\n"
        "2. CITATION CHECK: Verify claims have supporting references.\n"
        "   Unsupported strong claim -> flag as fatal_flaw.\n"
        "\n"
        "3. ANTI-HALLUCINATION: Flag any statement that reads like\n"
        '   marketing copy ("revolutionary", "game-changing") without\n'
        "   concrete mechanism description.\n"
        "\n"
        "Depth-dependent evaluation focus:\n"
        "- Depth 0 (Route selection): Evaluate thesis clarity, novelty_angle, structure feasibility,\n"
        "  topic coverage breadth. Heavily penalize generic/similar routes.\n"
        "- Depth 1-2 (Outline/Section): Evaluate evidence_density, technical_correctness,\n"
        "  coherence_with_thesis, hallucination_risk. Penalize filler and unsupported claims.\n"
        "- Depth 3 (Final check): Evaluate cross-section consistency, completeness of mandatory\n"
        "  sections (problem statement, contributions, methods, evaluation, limitations),\n"
        "  citation accuracy."
    ),
    termination_instruction=(
        "Research report completion rules:\n"
        "- Stop when all required sections addressed and key sources cited\n"
        "- Stop when additional sources add minimal new information\n"
        "- Final answer must include: structured sections with headings,\n"
        "  evidence-based claims with citations, explicit uncertainties,\n"
        "  comparison table when applicable, limitations section"
    ),
    preferred_output_schema={
        "type": "object",
        "required": ["title", "sections"],
        "properties": {
            "title": {"type": "string"},
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["section_id", "title", "content"],
                    "properties": {
                        "section_id": {"type": "string"},
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "claims": {"type": "array"},
                        "open_questions": {"type": "array"},
                    },
                },
            },
            "references": {"type": "array"},
        },
    },
)
