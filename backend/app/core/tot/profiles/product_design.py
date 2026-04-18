"""
Product Design and PRD Profile.

Profile for product design, PRD creation, and requirements analysis
tasks. Emphasizes user value, feasibility, market fit, and completeness.
"""

from .base import DomainProfile

PRODUCT_DESIGN_PROFILE = DomainProfile(
    task="product_design",
    goal=(
        "Produce a comprehensive product design document or PRD that "
        "is user-centered, technically feasible, and market-appropriate"
    ),
    must_check=[
        "user_persona_definition",
        "success_metrics",
        "edge_case_handling",
        "dependency_identification",
    ],
    preferred_methods=[
        "user_story_mapping",
        "jobs_to_be_done_framework",
        "competitive_analysis",
        "feasibility_prototyping",
    ],
    fatal_flaws=[
        "undefined_target_user",
        "no_success_metrics",
        "technical_infeasibility",
        "scope_creep",
        "ignoring_constraints",
    ],
    scoring_dimensions={
        "user_value": (
            "Degree to which the design addresses real user needs"
        ),
        "feasibility": (
            "Technical and resource viability of the proposed design"
        ),
        "market_fit": (
            "Alignment with market demands and competitive landscape"
        ),
        "clarity": (
            "Unambiguous specification with clear acceptance criteria"
        ),
        "completeness": (
            "Coverage of all necessary PRD sections and edge cases"
        ),
        "innovation": (
            "Novelty and differentiation from existing solutions"
        ),
    },
    weights={
        "user_value": 0.25,
        "feasibility": 0.20,
        "market_fit": 0.15,
        "clarity": 0.15,
        "completeness": 0.15,
        "innovation": 0.10,
    },
    stop_condition_signals={
        "specification_complete": [
            "all_user_stories_defined",
            "acceptance_criteria_specified",
            "technical_constraints_documented",
        ],
        "adequate_depth": [
            "edge_cases_covered",
            "dependencies_identified",
            "success_metrics_defined",
        ],
        "diminishing_returns": [
            "additional_detail_does_not_change_decision",
            "stakeholder_concerns_addressed",
        ],
    },
    confidence_calibration_rules=[
        {
            "condition": "no_user_validation",
            "action": "reduce_confidence",
            "adjustment": "cap at 0.6 until user feedback incorporated",
        },
        {
            "condition": "technical_feasibility_confirmed",
            "action": "increase_confidence",
            "adjustment": "boost by 0.1",
        },
        {
            "condition": "scope_exceeds_constraints",
            "action": "reduce_confidence",
            "adjustment": "flag for scope review",
        },
    ],
    output_requirements=[
        "target_user_personas",
        "user_stories_with_acceptance_criteria",
        "technical_feasibility_assessment",
        "success_metrics_and_kpis",
        "milestone_timeline",
    ],
    style_constraints=[
        "use_structured_prd_format",
        "include_priority_labels",
        "separate_must_have_from_nice_to_have",
    ],
    generator_instruction=(
        "You are a product design and PRD agent. Rules:\n"
        "\n"
        "1. DESIGN THINKING WORKFLOW:\n"
        "   define problem -> identify users -> generate solution options -> evaluate tradeoffs -> define MVP -> plan rollout\n"
        "\n"
        "2. OUTPUT FORMAT per expansion:\n"
        "   [Problem Statement] -> [Solution Options](>=2) -> [Tradeoff Analysis] -> [MVP Scope] -> [Success Metrics]\n"
        "\n"
        "3. REQUIRED ANALYSIS:\n"
        "   - User personas with specific scenarios\n"
        "   - Impact vs effort matrix for feature prioritization\n"
        "   - Explicit scope boundary (must-have vs nice-to-have)\n"
        "   - Success metrics with tracking plan\n"
        "   - Risk identification and mitigation\n"
        "\n"
        "4. PROHIBITED:\n"
        "   - Feature lists without rationale\n"
        "   - Vision statements without actionable specifications\n"
        "   - Ignoring cost/resource constraints\n"
        "   - Over-scoped plans without MVP boundary\n"
        "   - Contradictory requirements (flag immediately)\n"
        "\n"
        "5. EACH SOLUTION OPTION must include:\n"
        "   - Target user segment and scenario\n"
        "   - Key features with priority\n"
        "   - Technical feasibility assessment\n"
        "   - Cost/effort estimate\n"
        "   - Risks and mitigations\n"
        "\n"
        "6. TOOL & SKILL USAGE (mandatory for applicable tasks):\n"
        "   - When the task requires visual output (architecture diagrams, flowcharts, "
        "charts, wireframes), you MUST call the appropriate tool — do NOT describe "
        "them in text.\n"
        "   - Check the Skills list above for relevant capabilities (diagrams, charts, etc.).\n"
        "   - To activate: read_file(path=\"data/skills/<skill-name>/SKILL.md\"). "
        "Do NOT reimplement skill logic with python_repl/terminal.\n"
        "   - When the task is pure analysis (no visual/output needed), text-only is fine.\n"
    ),
    required_tools=["read_file"],  # Skill 调用依赖 read_file
    evaluator_instruction=(
        "Additional evaluation rules for product design:\n"
        "\n"
        "1. USER VALIDATION: Score <= 6 if no target user defined.\n"
        "   Score <= 4 if no user scenarios or personas.\n"
        "\n"
        "2. METRICS CHECK: No success metrics -> -3 from completeness.\n"
        "   Metrics without tracking plan -> -2 from feasibility.\n"
        "\n"
        "3. SCOPE CHECK: Flag scope creep or over-scoped plans.\n"
        "   No MVP boundary -> penalty on risk_control dimension.\n"
        "\n"
        "4. TRADEOFF ANALYSIS: Every solution option must include\n"
        "   tradeoffs. Options without tradeoffs -> -2 from rigor."
    ),
    termination_instruction=(
        "PRD completion rules:\n"
        "- Stop when all user stories defined and acceptance criteria specified\n"
        "- Stop when technical constraints documented and scope finalized\n"
        "- Do NOT stop when key sections missing (problem, users, metrics, MVP)\n"
        "- Final answer must include: problem statement, personas, functional\n"
        "  requirements, non-functional requirements, MVP scope, success\n"
        "  metrics, rollout plan"
    ),
    synthesis_instruction=(
        "You are composing the final product design document from completed analysis.\n"
        "\n"
        "RULES:\n"
        "1. The reasoning steps and tool results are ALREADY provided below.\n"
        "2. Do NOT reference any tools or write code.\n"
        "3. Organize into structured sections: Overview, Requirements, User Stories, MVP Scope, Risks.\n"
        "4. Preserve key metrics and data from tool results.\n"
        "5. Output in the same language as the user query."
    ),
    preferred_output_schema={
        "type": "object",
        "required": ["problem_statement", "mvp_scope", "success_metrics"],
        "properties": {
            "problem_statement": {"type": "string"},
            "personas": {"type": "array"},
            "functional_requirements": {"type": "array"},
            "non_functional_requirements": {"type": "array"},
            "mvp_scope": {"type": "object"},
            "success_metrics": {"type": "array"},
            "rollout_plan": {"type": "array"},
        },
    },
)
