"""
Post-Execution Re-Evaluator Node

Re-evaluates thoughts after execution based on actual results.
Only triggered when best_score >= quality_threshold (8.0) to prevent
premature termination caused by "high proposal score, poor actual result".

Flow: execute_thoughts → [conditional: best_score >= 8.0] → re_evaluate → extractor
"""

import logging
import json
import time
from typing import Any, Dict, List, Optional
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.tot.state import ToTState, Thought

logger = logging.getLogger(__name__)

# Same threshold as termination_checker.py
QUALITY_THRESHOLD = 8.0

# Blending weights: pre-execution vs post-execution
PRE_WEIGHT = 0.3
POST_WEIGHT = 0.7

# Post-execution criteria weights
POST_CRITERIA_WEIGHTS = {
    "result_quality": 0.4,
    "query_satisfaction": 0.4,
    "output_completeness": 0.2,
}


def _summarize_tool_results(thought: Thought) -> str:
    """Build a concise summary of tool results for the LLM prompt.

    No raw content — only metadata + preview.
    """
    if not thought.tool_results:
        return "  (no tool results)"

    lines = []
    image_parts = []
    for i, result in enumerate(thought.tool_results):
        tool_name = result.get("name", result.get("tool", f"tool_{i}"))
        status = result.get("status", "unknown")
        content = result.get("content", result.get("result", ""))
        content_str = str(content) if content else ""

        # Detect images
        img_count = 0
        img_names: list[str] = []
        if isinstance(content, dict):
            images = content.get("images", content.get("generated_images", []))
            if isinstance(images, list):
                for img in images:
                    img_count += 1
                    if isinstance(img, dict):
                        img_names.append(img.get("path", img.get("name", f"img_{img_count}")))
                    elif isinstance(img, str):
                        img_names.append(img)

        line = f"  - Tool: {tool_name} | Status: {status}"
        if img_count > 0:
            line += f" | Type: text+images ({len(content_str)} chars)"
            line += f" | Images: {img_count} {img_names[:5]}"
        elif content_str:
            line += f" | Type: text ({len(content_str)} chars)"
            line += f" | Preview: {content_str[:200]}"
        elif status == "error":
            err = result.get("error", "")
            line += f" | Error: {str(err)[:200]}"
        else:
            line += " | (empty output)"

        lines.append(line)

    # deferred images
    deferred = thought.metadata.get("deferred_image_paths", [])
    if deferred:
        lines.append(f"  - Deferred images: {len(deferred)}")

    return "\n".join(lines)


def _build_re_evaluation_prompt(
    thoughts: List[Thought],
    user_query: str,
) -> str:
    """Build prompt for post-execution batch re-evaluation."""
    items = []
    for t in thoughts:
        pre_score = t.evaluation_score or 0.0
        result_summary = _summarize_tool_results(t)
        items.append(
            f"[THOUGHT_{t.id}]\n"
            f"Plan: \"{t.content}\"\n"
            f"Pre-score: {pre_score:.1f}\n"
            f"Results:\n{result_summary}\n"
            f"---"
        )

    thoughts_text = "\n".join(items)

    return f"""Re-evaluate these executed thoughts based on ACTUAL RESULTS, not the proposed plan.

User Query: {user_query}

{thoughts_text}

Score each thought on 3 criteria (0-10):
- result_quality: Are the tool outputs useful, accurate, and substantial?
- query_satisfaction: Do the ACTUAL RESULTS satisfy the user's original need?
- output_completeness: Is the output complete and usable (e.g., images when requested)?

CRITICAL RULES:
1. Judge based on ACTUAL RESULTS, not the proposed plan.
2. A thought that proposed a great plan but produced poor results should score LOW.
3. A thought that proposed a modest plan but produced excellent results should score HIGH.
4. If the user asked for images/charts and none were generated, query_satisfaction should be LOW.

Return a JSON array with EXACTLY {len(thoughts)} elements:
```json
[
  {{"thought_id": "<id>", "result_quality": X, "query_satisfaction": X, "output_completeness": X}},
  ...
]
```

Each thought_id MUST match the [THOUGHT_<id>] header above."""


def _parse_re_eval_scores(content: str, thoughts: List[Thought]) -> Dict[str, Dict]:
    """Parse LLM re-evaluation response into scores map."""
    try:
        text = content.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        results = json.loads(text)
        if not isinstance(results, list):
            results = [results]

        scores_map: Dict[str, Dict] = {}
        for item in results:
            tid = item.get("thought_id", "")
            rq = float(item.get("result_quality", 5.0))
            qs = float(item.get("query_satisfaction", 5.0))
            oc = float(item.get("output_completeness", 5.0))
            post_score = (
                rq * POST_CRITERIA_WEIGHTS["result_quality"]
                + qs * POST_CRITERIA_WEIGHTS["query_satisfaction"]
                + oc * POST_CRITERIA_WEIGHTS["output_completeness"]
            )
            scores_map[tid] = {
                "criteria": {
                    "result_quality": rq,
                    "query_satisfaction": qs,
                    "output_completeness": oc,
                },
                "post_score": post_score,
            }
        return scores_map

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning(f"[PostEval] Score parsing failed: {e}")
        return {}


async def _batch_re_evaluate(
    thoughts: List[Thought],
    state: ToTState,
) -> int:
    """Run LLM re-evaluation on executed thoughts. Returns number of thoughts updated."""
    if not thoughts:
        return 0

    llm = state["llm"]
    user_query = state["user_query"]

    from app.core.tot.prompt_composer import compose_system_prompt
    eval_system = compose_system_prompt(
        base_system_prompt=state.get("system_prompt", ""),
        node_role="evaluator",
        domain_profile=state.get("domain_profile"),
        tools=state.get("tools"),
        prompt_level="analysis",
    )

    prompt = _build_re_evaluation_prompt(thoughts, user_query)

    try:
        response = await llm.ainvoke([
            SystemMessage(content=eval_system),
            HumanMessage(content=prompt),
        ])

        scores_map = _parse_re_eval_scores(response.content, thoughts)

        updated = 0
        for thought in thoughts:
            score_data = scores_map.get(thought.id)
            if not score_data:
                logger.warning(
                    f"[PostEval] No parsed score for {thought.id}, keeping pre-score"
                )
                continue

            post_score = score_data["post_score"]
            pre_score = thought.evaluation_score or 5.0
            blended = pre_score * PRE_WEIGHT + post_score * POST_WEIGHT

            # Save original pre-weighted score for traceability
            if thought.criteria_scores is None:
                thought.criteria_scores = {}
            thought.criteria_scores["pre_execution_weighted"] = pre_score

            # Update fields
            thought.post_execution_score = post_score
            thought.post_execution_criteria = score_data["criteria"]
            thought.evaluation_score = blended

            updated += 1

            logger.info(
                f"[PostEval] {thought.id}: "
                f"pre={pre_score:.2f}, post={post_score:.2f}, "
                f"blended={blended:.2f} "
                f"(rq={score_data['criteria']['result_quality']:.1f}, "
                f"qs={score_data['criteria']['query_satisfaction']:.1f}, "
                f"oc={score_data['criteria']['output_completeness']:.1f})"
            )

        return updated

    except Exception as e:
        logger.error(f"[PostEval] LLM call failed: {e}, keeping pre-execution scores")
        return 0


async def _re_run_beam_selection(state: ToTState) -> None:
    """Re-run beam selection after score updates."""
    from app.core.tot.nodes.thought_evaluator import (
        _update_beam_selection,
        _update_best_path,
    )

    beam_width = state.get("beam_width")
    if beam_width:
        await _update_beam_selection(state)
    else:
        _update_best_path(state)


async def post_execution_evaluator_node(state: ToTState) -> ToTState:
    """Post-execution re-evaluator node.

    Re-evaluates executed thoughts using actual tool results.
    Only processes thoughts with status=="done" that have tool_results
    and have not yet been re-evaluated (post_execution_score is None).
    """
    all_thoughts = state["thoughts"]
    best_score = state.get("best_score", 0.0)

    # Filter: done + has tool_results + not yet re-evaluated
    candidates = [
        t for t in all_thoughts
        if t.status == "done"
        and t.tool_results
        and t.post_execution_score is None
    ]

    if not candidates:
        logger.info(
            f"[PostEval] No re-evaluable thoughts "
            f"(best_score={best_score:.2f}, total_thoughts={len(all_thoughts)})"
        )
        return {}  # No-op: return empty dict to avoid triggering thoughts reducer

    logger.info(
        f"[PostEval] Re-evaluating {len(candidates)} executed thoughts "
        f"(best_score={best_score:.2f})"
    )

    start_time = time.time()

    # Run LLM re-evaluation
    updated_count = await _batch_re_evaluate(candidates, state)

    if updated_count > 0:
        # Re-run beam/best-path selection with updated scores
        await _re_run_beam_selection(state)

        # Log new best score
        new_best = state.get("best_score", 0.0)
        elapsed = time.time() - start_time
        logger.info(
            f"[PostEval] Updated {updated_count}/{len(candidates)} thoughts in {elapsed:.2f}s, "
            f"best_score: {best_score:.2f} → {new_best:.2f}"
        )

        # Write reasoning trace
        state["reasoning_trace"].append({
            "type": "post_execution_re_evaluated",
            "thoughts_updated": updated_count,
            "best_score": new_best,
            "score_before": best_score,
            "details": [
                {
                    "thought_id": t.id,
                    "pre_score": t.criteria_scores.get("pre_execution_weighted", 0.0) if t.criteria_scores else 0.0,
                    "post_score": t.post_execution_score,
                    "blended": t.evaluation_score,
                }
                for t in candidates
                if t.post_execution_score is not None
            ],
        })
    else:
        logger.info("[PostEval] No thoughts were updated (LLM call failed or parse error)")

    # Return partial state — thought fields are modified in-place via Pydantic,
    # so we must NOT include "thoughts" to avoid the add_thoughts reducer doubling them.
    return {
        "best_score": state.get("best_score", 0.0),
        "best_path": state.get("best_path", []),
        "active_beams": state.get("active_beams"),
        "beam_scores": state.get("beam_scores"),
        "reasoning_trace": state["reasoning_trace"],
        "needs_regeneration": state.get("needs_regeneration", []),
    }
