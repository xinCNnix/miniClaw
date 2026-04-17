"""
Coding and Debugging Profile.

Profile for software debugging and bug-fixing tasks. Emphasizes root
cause identification, fix correctness, side effect analysis, and
test coverage.
"""

from .base import DomainProfile

CODING_DEBUG_PROFILE = DomainProfile(
    task="coding_debug",
    goal=(
        "Identify the root cause of a bug and produce a correct fix "
        "without introducing regressions or new issues"
    ),
    must_check=[
        "error_message_analysis",
        "stack_trace_reading",
        "variable_state_tracking",
        "boundary_conditions",
    ],
    preferred_methods=[
        "reproduce_the_bug",
        "binary_search_for_root_cause",
        "hypothesis_driven_debugging",
        "regression_test_creation",
    ],
    fatal_flaws=[
        "symptom_fixing_without_root_cause",
        "introducing_new_bugs",
        "ignoring_edge_cases",
        "breaking_existing_tests",
    ],
    scoring_dimensions={
        "root_cause_identification": (
            "Accuracy and depth of root cause diagnosis"
        ),
        "fix_correctness": (
            "Whether the proposed fix actually resolves the bug"
        ),
        "side_effect_analysis": (
            "Assessment of unintended consequences of the fix"
        ),
        "test_coverage": (
            "Quality and completeness of tests for the fix"
        ),
        "code_quality": (
            "Readability, maintainability, and adherence to standards"
        ),
        "documentation": (
            "Clarity of comments and explanation of the fix"
        ),
    },
    weights={
        "root_cause_identification": 0.30,
        "fix_correctness": 0.25,
        "side_effect_analysis": 0.15,
        "test_coverage": 0.15,
        "code_quality": 0.10,
        "documentation": 0.05,
    },
    stop_condition_signals={
        "bug_confirmed_fixed": [
            "reproduction_case_passes",
            "all_existing_tests_pass",
            "edge_cases_verified",
        ],
        "dead_end": [
            "fix_introduces_new_failures",
            "root_cause_is_external_dependency",
        ],
        "sufficient_analysis": [
            "all_code_paths_examined",
            "related_components_checked",
        ],
    },
    confidence_calibration_rules=[
        {
            "condition": "fix_not_tested_against_reproduction",
            "action": "reduce_confidence",
            "adjustment": "cap at 0.4 until reproduction test passes",
        },
        {
            "condition": "existing_tests_pass_after_fix",
            "action": "increase_confidence",
            "adjustment": "boost by 0.15",
        },
        {
            "condition": "side_effects_detected",
            "action": "reduce_confidence",
            "adjustment": "cap at 0.5 until side effects addressed",
        },
    ],
    output_requirements=[
        "root_cause_explanation",
        "fix_diff_or_patch",
        "test_cases_for_fix",
        "regression_check_results",
    ],
    style_constraints=[
        "show_minimal_diff",
        "explain_why_not_what",
        "include_reproduction_steps",
    ],
    generator_instruction=(
        "You are a systematic debugging agent. Rules:\n"
        "\n"
        "1. DEBUGGING WORKFLOW (per branch):\n"
        "   reproduce -> analyze error -> hypothesize root cause -> test hypothesis -> fix -> verify\n"
        "\n"
        "2. OUTPUT FORMAT per expansion:\n"
        "   [Repro Case] -> [Error Analysis] -> [Hypothesis](>=2) -> [Fix Plan] -> [Test Strategy]\n"
        "\n"
        "3. REQUIRED TOOLS:\n"
        "   - terminal: Run reproduction cases and test fixes\n"
        "   - read_file: Examine source code and stack traces\n"
        "   - write_file: Apply patches (minimal diff preferred)\n"
        "\n"
        "4. PROHIBITED:\n"
        "   - Fixing symptoms without identifying root cause\n"
        "   - Rewriting large code sections when a small patch suffices\n"
        "   - Making changes that break API contracts\n"
        "   - Ignoring exception traces or logs\n"
        "   - Applying speculative fixes without validation\n"
        "\n"
        "5. EACH HYPOTHESIS must include:\n"
        "   - Specific root cause explanation\n"
        "   - Evidence from code/logs supporting it\n"
        "   - Minimal fix approach\n"
        "   - Test case to verify the fix\n"
        "\n"
        "6. TOOL & SKILL USAGE (mandatory for applicable tasks):\n"
        "   - When the task can benefit from existing Skills (e.g., code search, "
        "dependency analysis, testing frameworks), check the Available Skills list "
        "and activate via read_file(path=\"data/skills/<skill-name>/SKILL.md\").\n"
        "   - DO NOT reimplement skill logic with terminal/python_repl when a "
        "relevant Skill already exists.\n"
        "   - Use python_repl/terminal for tasks specific to the current debugging "
        "context (reproducing bugs, running tests, applying patches) — not to "
        "replace Skill capabilities.\n"
        "   - read_file is mandatory: for examining source code AND for activating "
        "Skills.\n"
        "   - When debugging pure logic errors (no tool output needed), text-only "
        "reasoning is fine."
    ),
    evaluator_instruction=(
        "Additional evaluation rules for debugging:\n"
        "\n"
        "1. ROOT CAUSE VERIFICATION: Score <= 3 if branch tries to fix\n"
        "   symptoms without identifying root cause (fatal flaw).\n"
        "\n"
        "2. EVIDENCE REQUIRED: Hypotheses without evidence from code,\n"
        "   logs, or test results -> penalty on rigor dimension.\n"
        "\n"
        "3. DIFF MINIMALITY: Prefer small targeted patches over rewrites.\n"
        "   Large diffs get penalty on feasibility dimension.\n"
        "\n"
        "4. SECURITY CHECK: Flag any fix that introduces security risks\n"
        "   as fatal_flaw."
    ),
    termination_instruction=(
        "Debugging completion rules:\n"
        "- Stop when reproduction case passes after fix\n"
        "- Stop when all existing tests pass after fix\n"
        "- Do NOT stop when fix introduces new failures\n"
        "- Final answer must include: root cause explanation, fix diff,\n"
        "  test cases, regression check results"
    ),
    synthesis_instruction=(
        "You are composing the final debugging report from completed analysis steps.\n"
        "\n"
        "RULES:\n"
        "1. The reasoning steps and tool results are ALREADY provided below.\n"
        "2. Tool results contain terminal output, file contents, and execution logs.\n"
        "3. Do NOT write any new code to execute. Do NOT reference any tools.\n"
        "4. Organize into: Root Cause → Fix (minimal diff) → Verification.\n"
        "5. Quote relevant evidence from tool results.\n"
        "6. Output in the same language as the user query."
    ),
    preferred_output_schema={
        "type": "object",
        "required": ["root_cause", "fix"],
        "properties": {
            "root_cause": {"type": "string"},
            "fix": {"type": "array", "items": {"type": "string"}},
            "patch_snippet": {"type": "string"},
            "tests": {"type": "array", "items": {"type": "string"}},
            "risk_notes": {"type": "array", "items": {"type": "string"}},
        },
    },
    required_tools=["terminal", "read_file", "write_file", "python_repl", "fetch_url", "search_kb"],
)
