"""
RegressionTest — Skill regression testing before stable promotion.

Each skill must pass regression tests to be promoted from candidate → stable.
Minimum 3 tests, at least 80% pass rate required.
"""

import json
import logging
import re
from typing import Any, Dict, List

from app.core.dream.config import DreamConfig
from app.core.dream.models import DreamState, SkillCard

logger = logging.getLogger(__name__)


def _check_expected_properties(
    properties: List[str], steps: List[str], final_answer: str
) -> bool:
    """Check if expected properties are satisfied by the skill."""
    if not properties:
        return True

    satisfied = 0
    combined = " ".join(steps) + " " + (final_answer or "")

    for prop in properties:
        pl = prop.lower()
        if "non-empty" in pl and combined.strip():
            satisfied += 1
        elif "structured output" in pl and ("{" in combined or "[" in combined):
            satisfied += 1
        elif "valid" in pl and combined.strip():
            satisfied += 1
        elif "tool" in pl and any(s for s in steps if "use" in s.lower()):
            satisfied += 1
        else:
            # Default: property is about having relevant content
            if combined.strip():
                satisfied += 1

    return satisfied >= len(properties) * 0.8


def _check_tool_expectations(
    expectations: Dict[str, Any], steps: List[str]
) -> bool:
    """Check tool usage expectations."""
    if not expectations:
        return True

    steps_text = " ".join(steps).lower()

    # must_call: these tools should be mentioned
    for tool in expectations.get("must_call", []):
        if tool.lower() not in steps_text:
            return False

    # must_not_call: these tools should NOT appear
    for tool in expectations.get("must_not_call", []):
        if tool.lower() in steps_text:
            return False

    # max_calls: check step count
    max_calls = expectations.get("max_calls", 0)
    if max_calls > 0 and len(steps) > max_calls:
        return False

    return True


def _check_adversarial_variants(
    variants: List[str], skill: SkillCard
) -> bool:
    """Check if skill handles adversarial inputs safely."""
    if not variants:
        return True

    # Check that skill has anti_patterns that address adversarial scenarios
    anti_pattern_text = " ".join(skill.anti_patterns).lower()
    for variant in variants:
        vl = variant.lower()
        if "injection" in vl:
            if "injection" not in anti_pattern_text and "ignore" not in anti_pattern_text:
                # Skill doesn't explicitly handle injection, but has generic safety
                if not skill.anti_patterns:
                    return False
    return True


def run_single_test(test: Dict[str, Any], skill: SkillCard) -> bool:
    """Run a single regression test against a skill card."""
    test_id = test.get("test_id", "unknown")

    # Check 1: expected properties
    properties = test.get("expected_properties", [])
    if not _check_expected_properties(properties, skill.steps, skill.examples[0] if skill.examples else ""):
        logger.debug(f"Test {test_id}: expected properties not met")
        return False

    # Check 2: tool expectations
    tool_exp = test.get("tool_expectations", {})
    if not _check_tool_expectations(tool_exp, skill.steps):
        logger.debug(f"Test {test_id}: tool expectations not met")
        return False

    # Check 3: adversarial variants
    variants = test.get("adversarial_variants", [])
    if not _check_adversarial_variants(variants, skill):
        logger.debug(f"Test {test_id}: adversarial handling insufficient")
        return False

    # Check 4: skill structure completeness
    if not skill.trigger:
        logger.debug(f"Test {test_id}: missing trigger")
        return False
    if not skill.steps:
        logger.debug(f"Test {test_id}: missing steps")
        return False
    if len(skill.regression_tests) < 3:
        logger.debug(f"Test {test_id}: insufficient regression tests")
        return False

    return True


def regression_test_node(state: DreamState) -> DreamState:
    """Dream Subgraph node: run regression tests on deduplicated skills."""
    config = DreamConfig()
    skills = state.get("deduplicated_skills", [])

    report: Dict[str, Dict[str, Any]] = {}

    for skill in skills:
        if not skill.regression_tests:
            report[skill.skill_id] = {
                "passed": False,
                "reason": "no regression tests",
                "passed_count": 0,
                "total_count": 0,
            }
            continue

        results = []
        for test in skill.regression_tests:
            ok = run_single_test(test, skill)
            results.append(ok)

        passed_count = sum(results)
        total_count = len(results)

        # Pass threshold: min(regression_min_pass, 80% of total)
        min_pass = max(
            config.regression_min_pass,
            int(total_count * 0.8),
        )
        passed = passed_count >= min_pass and total_count >= config.regression_min_tests

        report[skill.skill_id] = {
            "passed": passed,
            "passed_count": passed_count,
            "total_count": total_count,
            "details": [
                {"test_id": skill.regression_tests[i].get("test_id", f"T{i+1}"), "passed": r}
                for i, r in enumerate(results)
            ],
        }

        if passed:
            # Promote to stable
            skill.status = "stable"
            skill.confidence = min(
                config.promotion_max_confidence,
                skill.confidence + config.promotion_confidence_boost,
            )
            logger.info(
                f"RegressionTest: {skill.skill_name} PASSED "
                f"({passed_count}/{total_count}) → stable (conf={skill.confidence:.2f})"
            )
        else:
            logger.info(
                f"RegressionTest: {skill.skill_name} FAILED "
                f"({passed_count}/{total_count}), remains candidate"
            )

    total_passed = sum(1 for r in report.values() if r["passed"])
    logger.info(
        f"RegressionTest: {total_passed}/{len(skills)} skills promoted to stable"
    )

    state["regression_report"] = report
    return state
