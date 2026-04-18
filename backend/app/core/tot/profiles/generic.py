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
        "Make assumptions explicit. Avoid handwaving.\n"
        "\n"
        "TOOL & SKILL USAGE (mandatory for applicable tasks):\n"
        "1. When the task requires output you cannot produce directly in text "
        "(visualizations, images, diagrams, code execution results, file operations, "
        "web content retrieval), you MUST call the appropriate tool.\n"
        "2. Check the Available Tools and Skills listed above. Match the task need "
        "to the tool/skill capability — do NOT skip tools and describe output in text.\n"
        "3. To activate a Skill: read_file(path=\"data/skills/<skill-name>/SKILL.md\"). "
        "The system auto-executes the skill. Do NOT reimplement skill logic with other tools.\n"
        "4. DO NOT generate inline URLs, base64 data, or pseudo-code to simulate "
        "tool output. If a tool exists for the job, USE IT.\n"
        "5. When no tool/Skill is needed (pure reasoning/analysis), text-only thoughts are fine.\n"
    ),
    # required_tools is set below via required_tools parameter
    required_tools=["read_file"],  # Skill 调用依赖 read_file
    evaluator_instruction="",
    termination_instruction="",
    synthesis_instruction=(
        "You are composing the final answer from completed reasoning steps.\n"
        "\n"
        "RULES:\n"
        "1. The reasoning steps and tool results are ALREADY provided below.\n"
        "2. If tool results contain images (markdown format), include them directly.\n"
        "3. Do NOT write any code or reference any tools.\n"
        "4. Provide a clear, comprehensive answer based on the reasoning process.\n"
        "5. Output in the same language as the user query."
    ),
    preferred_output_schema={},
)
