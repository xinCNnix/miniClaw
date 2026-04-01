"""
Mathematical Logic Proof Profile.

Profile for formal mathematical reasoning including proofs, derivations,
and theorem verification. Emphasizes rigor, correctness, and proper
application of inference rules.
"""

from .base import DomainProfile

MATH_PROOF_PROFILE = DomainProfile(
    task="math_proof",
    goal=(
        "Construct a rigorous, logically sound mathematical proof or "
        "derivation with correct application of definitions, theorems, "
        "and inference rules"
    ),
    must_check=[
        "definition_alignment",
        "quantifier_scope_and_binding",
        "rule_of_inference_soundness",
        "assumption_tracking",
        "theorem_condition_verification",
        "circular_reasoning_detection",
        "counterexample_attempt_or_model_check",
    ],
    preferred_methods=[
        "definition_expansion",
        "standard_theorem_application",
        "arbitrary_element_derivation",
        "witness_construction",
        "bidirectional_proof",
        "proof_by_contradiction",
        "structural_induction",
        "syntactic_vs_semantic_parallel_search",
    ],
    fatal_flaws=[
        "quantifier_inversion_or_scope_error",
        "using_theorem_without_checking_conditions",
        "silent_strengthening_of_assumptions",
        "circular_reasoning",
        "non_constructive_step_where_construction_required",
        "handwaving_gap_without_patchable_lemma",
    ],
    scoring_dimensions={
        "correctness": (
            "Logical validity of each proof step and absence of "
            "formal errors"
        ),
        "goal_progress": (
            "Measurable advancement toward the proof objective"
        ),
        "rigor": (
            "Strict adherence to formal reasoning standards with "
            "no unjustified leaps"
        ),
        "feasibility": (
            "Likelihood that the current proof strategy can reach "
            "the target conclusion"
        ),
        "risk_control": (
            "Assessment of whether the proof path introduces "
            "unnecessary assumptions or dependencies"
        ),
        "clarity": (
            "Readability and precise mathematical notation usage"
        ),
        "dependency_safety": (
            "Whether lemmas and theorems used are properly "
            "verified and not circularly dependent"
        ),
        "generality_preserved": (
            "Whether the proof maintains generality without "
            "unwarranted specialization"
        ),
    },
    weights={
        "correctness": 0.25,
        "goal_progress": 0.20,
        "rigor": 0.20,
        "feasibility": 0.10,
        "risk_control": 0.10,
        "clarity": 0.05,
        "dependency_safety": 0.05,
        "generality_preserved": 0.05,
    },
    stop_condition_signals={
        "proof_complete": [
            "QED_reached",
            "all_cases_exhausted",
            "contradiction_derived_in_contradiction_proof",
        ],
        "redundancy": [
            "revisiting_already_proven_intermediate_result",
            "applying_same_technique_with_no_new_progress",
        ],
        "dead_end": [
            "contradiction_derived_in_direct_proof",
            "assumption_too_strong_to_be_useful",
            "no_applicable_theorem_found_after_exhaustive_search",
        ],
    },
    confidence_calibration_rules=[
        {
            "condition": "unverified_theorem_application",
            "action": "reduce_confidence",
            "adjustment": "cap at 0.5 until conditions verified",
        },
        {
            "condition": "circular_dependency_detected",
            "action": "invalidate",
            "adjustment": "set confidence to 0.0",
        },
        {
            "condition": "all_conditions_verified",
            "action": "increase_confidence",
            "adjustment": "boost by 0.15 per verified condition",
        },
    ],
    output_requirements=[
        "numbered_proof_steps",
        "explicit_justification_per_step",
        "clear_statement_of_assumptions",
        "QED_or_equivalent_conclusion",
    ],
    style_constraints=[
        "use_standard_mathematical_notation",
        "label_each_step_with_justification",
        "separate_assumptions_from_derivations",
    ],
    generator_instruction=(
        "You are a specialized mathematical reasoning engine. Rules:\n"
        "\n"
        "1. PROOF STATE: Maintain explicit state at every step:\n"
        "   [Known]: Verified facts and lemmas\n"
        "   [Goal]: Current target to prove\n"
        "   [Plan]: Active proof strategy\n"
        "\n"
        "2. OUTPUT FORMAT per expansion:\n"
        "   [Proof State] -> [Candidate Thoughts](>=3) -> [Self-Check] -> [Request Evaluation]\n"
        "\n"
        "3. STRATEGY PRIORITY (try in order):\n"
        "   - definition_expansion: Expand and normalize definitions first\n"
        "   - standard_theorem: Apply known theorems (check ALL conditions)\n"
        "   - arbitrary_element: Derive properties via arbitrary element\n"
        "   - witness_construction: Construct explicit witness for existential claims\n"
        "   - bidirectional_proof: Prove both directions for equivalence claims\n"
        "   - contradiction: Use negation of Goal to derive contradiction when negation is structured\n"
        "   - structural_induction: Induction on well-founded structures\n"
        "   - syntactic_vs_semantic: Parallel search in both proof systems\n"
        "\n"
        "4. PROHIBITED:\n"
        "   - Fabricating theorems or lemmas\n"
        '   - Using "obviously", "clearly", "trivially" without justification\n'
        "   - Proof by analogy or example\n"
        "   - Probabilistic language for strict derivation\n"
        "   - Using any theorem without verifying its preconditions\n"
        "\n"
        "5. ALWAYS state whether you are doing syntactic proof or semantic proof."
    ),
    evaluator_instruction=(
        "Additional evaluation rules for mathematical proofs:\n"
        "\n"
        "1. COUNTEREXAMPLE CHECK: For every universal claim (forall x P(x)), attempt to\n"
        "   find a counterexample. If counterexample found -> fatal_flaw.\n"
        "\n"
        "2. QUANTIFIER SCOPE: Verify all quantifier bindings are explicit.\n"
        "   Missing scope -> penalty on rigor dimension.\n"
        "\n"
        "3. SCORE THRESHOLDS:\n"
        "   - total <= 3.0 -> auto-mark status as \"pruned\" (branch unsalvageable)\n"
        "   - total >= 8.0 -> mark status as \"excellent\"\n"
        "\n"
        "4. PROOF STYLE: Penalize \"obviously\", \"clearly\", handwaving gaps.\n"
        "   Reward explicit justification per step.\n"
        "\n"
        "5. FATAL FLAW HANDLING: If any fatal flaw detected, evaluation_score\n"
        "   must be capped at 3.0 regardless of individual dimension scores."
    ),
    termination_instruction=(
        "Proof completion rules:\n"
        "- Stop when QED reached or all subgoals discharged\n"
        "- Stop when counterexample successfully constructed\n"
        "- Do NOT stop on partial proofs without explicit gap analysis\n"
        "- Final answer must include: numbered steps, explicit justification\n"
        "  per step, statement of assumptions, QED conclusion"
    ),
    preferred_output_schema={
        "type": "object",
        "required": ["result_type", "formal_statement", "proof"],
        "properties": {
            "result_type": {
                "type": "string",
                "enum": ["proof", "counterexample", "undetermined"],
            },
            "formal_statement": {"type": "string"},
            "proof": {"type": "array", "items": {"type": "string"}},
            "dependencies": {"type": "array", "items": {"type": "string"}},
            "notes": {"type": "array", "items": {"type": "string"}},
            "key_lemmas": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Key lemmas used in the proof",
            },
            "dependency_chain": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "from": {"type": "string"},
                        "to": {"type": "string"},
                        "via": {"type": "string"},
                    },
                },
                "description": (
                    "Logical dependency relationships between proof steps"
                ),
            },
            "unprovability_reason": {
                "type": "string",
                "description": (
                    "If undetermined, explain why: missing condition / "
                    "proposition false / need additional assumptions"
                ),
            },
        },
    },
)
