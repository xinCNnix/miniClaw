"""
Verifier node - verifies execution results against task.

Evaluates whether the collected observations adequately answer the original
task.  Applies a configurable strictness level to the pass/fail decision.
"""

import logging
import os
import re
import time
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage

from app.config import get_settings
from app.core.llm import create_llm
from app.core.llm_retry import retry_llm_call
from app.core.perv.json_repair import repair_json_or_none
from app.core.perv.prompts import build_verifier_prompt
from app.core.execution_trace.perv_trace import PEVRTrace as PEVRLogger
from app.core.execution_trace.token_utils import extract_token_usage

logger = logging.getLogger(__name__)


async def verifier_node(state: dict) -> dict:
    """Verify execution results against the original task.

    Calls the LLM with a verification prompt, parses the structured report,
    and applies strictness adjustments before returning the verdict.

    Args:
        state: Current PlannerState dictionary.

    Returns:
        Dictionary with ``verifier_report`` and appended ``reasoning_trace``.
    """
    task: str = state.get("task", "")
    plan = state.get("plan", [])
    observations = state.get("observations", [])
    retry_count: int = state.get("retry_count", 0)
    pevr_log: PEVRLogger | None = state.get("_pevr_log")

    settings = get_settings()
    strictness: str = getattr(settings, "planner_verification_strictness", "normal")

    start = time.time()

    try:
        # --- Build verifier prompt ---
        prompt_text = build_verifier_prompt(
            task=task,
            plan=plan,
            observations=observations,
        )

        logger.debug(
            "[PEVR Verifier] Prompt: %d chars, strictness=%s, plan_steps=%d, observations=%d",
            len(prompt_text),
            strictness,
            len(plan),
            len(observations),
        )

        # --- Call LLM ---
        provider = settings.llm_provider
        llm = create_llm(provider)

        response = await retry_llm_call(
            coro_factory=lambda: llm.ainvoke([HumanMessage(content=prompt_text)]),
            context="pevr_verifier",
        )

        # --- Extract token usage ---
        token_usage = extract_token_usage(response)

        raw_content: str = getattr(response, "content", str(response))
        logger.debug(
            "[PEVR Verifier] LLM response: %d chars preview=%s",
            len(raw_content),
            raw_content[:300],
        )

        _fallback_report: Dict[str, Any] = {
            "verdict": "fail",
            "confidence": 0.0,
            "checks": [],
            "risk_notes": [],
            "passed": False,
            "reason": "Failed to parse verifier response",
            "missing": [],
            "grounded": False,
            "coverage": 0.0,
            "scores": {},
        }
        report: Dict[str, Any] = repair_json_or_none(raw_content) or _fallback_report

        # Ensure required keys exist (support both old and new format)
        report.setdefault("verdict", "fail")
        report.setdefault("confidence", 0.0)
        report.setdefault("checks", [])
        report.setdefault("risk_notes", [])
        report.setdefault("passed", False)
        report.setdefault("reason", "")
        report.setdefault("missing", [])
        report.setdefault("grounded", False)
        report.setdefault("coverage", 0.0)
        report.setdefault("scores", {})

        # Normalize: if new format has verdict but no passed field, derive it
        verdict = report.get("verdict", "")
        if verdict and "passed" not in report:
            report["passed"] = verdict == "pass"
        # If old format has passed but no verdict, derive verdict
        if not verdict and "passed" in report:
            report["verdict"] = "pass" if report["passed"] else "fail"

        # Extract confidence from new format or derive from old scores
        confidence = float(report.get("confidence", 0.0))
        if confidence == 0.0 and report.get("scores"):
            scores = report["scores"]
            if isinstance(scores, dict) and scores:
                confidence = sum(scores.values()) / (len(scores) * 10.0)
                report["confidence"] = confidence

        # --- File-existence sanity check ---
        # When the task implies file generation (images, charts, documents),
        # verify that output files referenced in observations actually exist.
        # This catches cases where the LLM claims success but the file was
        # written to a non-existent or wrong path.
        _file_gen_keywords = [
            "图", "chart", "plot", "image", "graph", "diagram", "png", "svg",
            "pdf", "draw", "画", "generate", "save", "export",
        ]
        task_lower = task.lower()
        needs_file_output = any(kw in task_lower for kw in _file_gen_keywords)

        if needs_file_output and report.get("passed"):
            output_paths: List[str] = []
            _file_ext_pattern = re.compile(r'[\'""]?([\w/\\:.]+\.(?:png|svg|jpg|jpeg|pdf|dot|csv|html|txt))[\'""]?', re.IGNORECASE)
            for obs in observations:
                output = str(obs.get("output", ""))
                for m in _file_ext_pattern.finditer(output):
                    p = m.group(1).replace("\\", "/")
                    # Filter out source/data paths; only keep output-like paths
                    if "/data/skills/" not in p and "/knowledge_base/" not in p:
                        output_paths.append(p)

            missing_files = []
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            for p in output_paths:
                # Try absolute path first, then relative to backend dir
                candidates = [p, os.path.join(backend_dir, p)]
                if not any(os.path.exists(c) for c in candidates):
                    missing_files.append(p)

            if missing_files and output_paths:
                logger.warning(
                    "[PEVR Verifier] File-existence check FAILED: %d/%d output "
                    "files missing: %s — overriding passed=True to False",
                    len(missing_files), len(output_paths),
                    missing_files[:5],
                )
                report["passed"] = False
                report["verdict"] = "fail"
                report.setdefault("missing", [])
                report["missing"].extend(f"Output file not found: {f}" for f in missing_files)
                report["confidence"] = min(float(report.get("confidence", 0.5)), 0.3)

        # --- Apply strictness adjustments ---
        confidence = float(report.get("confidence", 0.0))

        if strictness == "loose":
            report["passed"] = confidence >= 0.5
            report["verdict"] = "pass" if confidence >= 0.5 else "fail"
        elif strictness == "strict":
            # All critical checks must pass
            checks = report.get("checks", [])
            critical_fail = any(
                c.get("status") == "fail"
                for c in checks
                if c.get("name") in ("step_completion", "task_coverage")
            )
            report["passed"] = confidence >= 0.8 and not critical_fail
            report["verdict"] = "pass" if report["passed"] else "fail"
        # "normal" uses the LLM's own judgment as-is

        # Sync verdict and passed fields (bidirectional)
        if report.get("passed"):
            report["verdict"] = "pass"
        elif report.get("verdict") == "pass":
            report["passed"] = True

        duration = time.time() - start
        logger.info(
            "[PEVR Verifier] passed=%s verdict=%s confidence=%.2f grounded=%s "
            "strictness=%s missing=%d (%.1fms)",
            report["passed"],
            report.get("verdict", "?"),
            confidence,
            report.get("grounded", False),
            strictness,
            len(report.get("missing", [])),
            duration * 1000,
        )

        if not report["passed"]:
            logger.info(
                "[PEVR Verifier] Failure reason: %s",
                report.get("reason", "")[:200],
            )
            for item in report.get("missing", []):
                logger.debug("[PEVR Verifier]   missing: %s", item)

        if pevr_log:
            pevr_log.log_verification(
                loop_index=retry_count,
                report=report,
                duration_s=duration,
                token_usage=token_usage,
            )

    except Exception as e:
        duration = time.time() - start
        logger.error(
            "[PEVR Verifier] FAILED after %.1fms: %s",
            duration * 1000,
            e,
            exc_info=True,
        )
        report = {
            "verdict": "fail",
            "confidence": 0.0,
            "checks": [],
            "risk_notes": [],
            "passed": False,
            "reason": f"Verifier exception: {e}",
            "missing": [],
            "grounded": False,
            "coverage": 0.0,
            "scores": {},
        }
        if pevr_log:
            pevr_log.log_verification(
                loop_index=retry_count,
                report=report,
                duration_s=duration,
                error=e,
            )
            pevr_log.log_node_error(
                "verifier",
                e,
                f"plan_steps={len(plan)} obs={len(observations)}",
            )

    return {
        "verifier_report": report,
        "reasoning_trace": [{"phase": "verification", "report": report}],
    }
