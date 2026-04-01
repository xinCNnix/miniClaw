"""
Generic Reasoning Profile.

Default profile for general-purpose reasoning tasks. Provides balanced
scoring across six dimensions covering correctness, relevance,
feasibility, completeness, clarity, and efficiency.
"""

from .base import DomainProfile

GENERIC_PROFILE = DomainProfile(
    task="generic_reasoning",
    goal="Produce a well-reasoned, correct, and clearly communicated answer",
    must_check=[
        "logical_consistency",
        "evidence_support",
        "assumption_validity",
    ],
    preferred_methods=[
        "chain_of_thought",
        "evidence_based_reasoning",
        "systematic_decomposition",
    ],
    fatal_flaws=[
        "circular_reasoning",
        "unsupported_claim",
        "logical_contradiction",
        "missing_critical_step",
    ],
    scoring_dimensions={
        "correctness": "Factual accuracy and logical soundness of the reasoning",
        "relevance": "Direct pertinence to the user query",
        "feasibility": "Practical executability of the proposed solution",
        "completeness": "Coverage of all aspects of the query",
        "clarity": "Clear and unambiguous communication",
        "efficiency": "Achieving the goal with minimal unnecessary steps",
    },
    weights={
        "correctness": 0.25,
        "relevance": 0.20,
        "feasibility": 0.20,
        "completeness": 0.15,
        "clarity": 0.10,
        "efficiency": 0.10,
    },
    stop_condition_signals={
        "redundancy": [
            "repeating previously established points",
            "no new information added",
        ],
        "convergence": [
            "multiple paths agree on conclusion",
            "score plateau across branches",
        ],
        "sufficiency": [
            "all query aspects addressed",
            "evidence adequately supports conclusion",
        ],
    },
    confidence_calibration_rules=[
        {
            "condition": "single_source_claim",
            "action": "reduce_confidence",
            "adjustment": "cap at 0.7 without corroboration",
        },
        {
            "condition": "high_agreement_across_branches",
            "action": "increase_confidence",
            "adjustment": "boost by 0.1 per agreeing branch",
        },
    ],
    output_requirements=[
        "structured_output",
        "explicit_reasoning_steps",
        "evidence_based_claims",
    ],
    style_constraints=[
        "use_structured_formatting",
        "explicit_reasoning_steps",
        "cite_evidence_for_claims",
    ],
    generator_instruction=(
        "Follow systematic reasoning: decompose into subtasks, generate "
        "multiple candidates, evaluate tradeoffs, propose verification steps. "
        "Make assumptions explicit. Avoid handwaving."
    ),
    evaluator_instruction="",
    termination_instruction="",
    preferred_output_schema={},
)
