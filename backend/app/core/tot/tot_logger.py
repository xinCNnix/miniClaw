"""ToT execution lifecycle logger for tree-structured reasoning."""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolCallRecord:
    """Record of a single tool call within ToT execution."""
    tool_name: str
    args_summary: str
    cached: bool = False
    duration_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None


@dataclass
class ThoughtScore:
    """Score for a single thought in evaluation."""
    thought_id: str
    score: float
    criteria: dict = field(default_factory=dict)
    fatal_flaw: Optional[str] = None


@dataclass
class PromptCompositionRecord:
    """Record of how a prompt was composed for a ToT node."""
    node_role: str = ""  # generator / evaluator / termination
    template_name: str = ""  # _GENERATOR_TEMPLATE etc.
    system_prompt_length: int = 0
    base_prompt_length: int = 0
    appendix_length: int = 0
    appendix_preview: str = ""  # ToT role-specific instructions (without base prompt)
    user_prompt_preview: str = ""  # First 500 chars of user prompt
    domain_methods_injected: list = field(default_factory=list)
    domain_instruction_preview: str = ""  # Domain-specific instruction snippet
    tool_list: str = ""  # Tool names injected into the prompt
    variant: int = 0  # Variant hint index


@dataclass
class IterationRecord:
    """Record of a single ToT iteration (generate -> evaluate -> execute -> terminate)."""
    depth: int
    start_time: float = 0.0
    end_time: float = 0.0

    # Generation phase
    generation_count: int = 0
    generation_variant: str = ""
    generation_prompt_length: int = 0
    generation_duration_ms: float = 0.0

    # Prompt composition tracking
    generation_prompt_composition: Optional[PromptCompositionRecord] = None
    evaluation_prompt_composition: Optional[PromptCompositionRecord] = None
    termination_prompt_preview: str = ""  # Final answer generation prompt snippet

    # Evaluation phase
    scores: list = field(default_factory=list)
    best_path_changed: bool = False
    beam_pruned: int = 0
    evaluation_duration_ms: float = 0.0

    # Execution phase
    tool_calls: list = field(default_factory=list)
    cache_hits: int = 0
    cache_misses: int = 0
    execution_duration_ms: float = 0.0

    # Termination decision
    should_stop: bool = False
    stop_trigger: Optional[str] = None
    termination_details: dict = field(default_factory=dict)


class ToTExecutionLogger:
    """ToT execution lifecycle logger.

    Captures the full tree-shaped exploration process of a ToT reasoning session,
    including iteration-level tracking of generate/evaluate/execute/terminate phases.

    Auto-manages iteration lifecycle: log_generation auto-starts an iteration,
    log_termination_check auto-finalizes it.
    """

    def __init__(self, task_name: str, session_id: str, profile: Optional[str] = None):
        self.task_name = task_name
        self.session_id = session_id
        self.profile = profile
        self.start_time = time.time()
        self.end_time: Optional[float] = None

        self.iterations: list[IterationRecord] = []
        self._current_iteration: Optional[IterationRecord] = None

        # Aggregated stats
        self.total_tool_calls = 0
        self.total_cache_hits = 0
        self.total_cache_misses = 0
        self.total_backtracks = 0

        # Result
        self.final_answer: Optional[str] = None
        self.best_path: list[str] = []

        # Config snapshot (set by router)
        self.config: dict[str, Any] = {}

        # Profile selection details
        self.profile_selection: dict[str, Any] = {}  # keyword matches, scores, rationale

    def __enter__(self) -> "ToTExecutionLogger":
        logger.info(f"[ToT] Start session: {self.task_name} (profile={self.profile})")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        duration = (self.end_time - self.start_time) * 1000
        if exc_type:
            logger.error(f"[ToT] Session failed: {exc_val} ({duration:.0f}ms)")
        else:
            logger.info(
                f"[ToT] Session complete: {len(self.iterations)} iterations, "
                f"{duration:.0f}ms, {self.total_tool_calls} tool calls"
            )

    # --- Auto iteration lifecycle ---

    def _finalize_iteration(self):
        """Finalize current iteration and add to iterations list."""
        if self._current_iteration is not None:
            self._current_iteration.end_time = time.time()
            self.iterations.append(self._current_iteration)
            self._current_iteration = None

    def _ensure_iteration(self, depth: int):
        """Ensure an active iteration exists for the given depth, finalizing previous if needed."""
        if self._current_iteration is None or self._current_iteration.depth != depth:
            self._finalize_iteration()
            self._current_iteration = IterationRecord(depth=depth, start_time=time.time())

    # --- Phase logging (auto-manages iteration lifecycle) ---

    def log_generation(self, depth: int, count: int, variant: str,
                       prompt_length: int, duration: float):
        """Log the thought generation phase. Auto-starts a new iteration."""
        self._ensure_iteration(depth)
        self._current_iteration.generation_count = count
        self._current_iteration.generation_variant = variant
        self._current_iteration.generation_prompt_length = prompt_length
        self._current_iteration.generation_duration_ms = duration * 1000
        logger.info(
            f"[ToT] Generated {count} thoughts at depth {depth} "
            f"(variant={variant}, {duration * 1000:.0f}ms)"
        )

    def log_prompt_composition(self, depth: int, phase: str, composition: PromptCompositionRecord):
        """Log how a prompt was composed for a specific phase.

        Args:
            depth: Current reasoning depth.
            phase: "generation", "evaluation", or "termination".
            composition: Detailed record of the prompt composition.
        """
        self._ensure_iteration(depth)
        if phase == "generation":
            self._current_iteration.generation_prompt_composition = composition
        elif phase == "evaluation":
            self._current_iteration.evaluation_prompt_composition = composition

        logger.info(
            f"[ToT] Prompt composition for {phase} at depth {depth}: "
            f"template={composition.template_name}, "
            f"system_prompt_len={composition.system_prompt_length}, "
            f"base_len={composition.base_prompt_length}, "
            f"appendix_len={composition.appendix_length}, "
            f"domain_methods={composition.domain_methods_injected}, "
            f"tools={composition.tool_list}"
        )
        if composition.domain_instruction_preview:
            logger.info(
                f"[ToT] Domain instruction: {composition.domain_instruction_preview[:300]}"
            )

    def log_evaluation(self, depth: int, scores: list[dict],
                       best_path_changed: bool, beam_pruned: int):
        """Log the thought evaluation phase. Auto-starts iteration if needed."""
        self._ensure_iteration(depth)
        self._current_iteration.scores = [
            ThoughtScore(
                thought_id=s.get("thought_id", ""),
                score=s.get("score", 0.0),
                criteria=s.get("criteria", {}),
                fatal_flaw=s.get("fatal_flaw"),
            )
            for s in scores
        ]
        self._current_iteration.best_path_changed = best_path_changed
        self._current_iteration.beam_pruned = beam_pruned
        logger.info(
            f"[ToT] Evaluated {len(scores)} thoughts at depth {depth}, "
            f"best_path_changed={best_path_changed}, pruned={beam_pruned}"
        )

    def log_execution(self, depth: int, tool_calls: list[dict],
                      cache_hits: int, cache_misses: int, duration: float):
        """Log the tool execution phase. Auto-starts iteration if needed."""
        self._ensure_iteration(depth)
        self._current_iteration.tool_calls = [
            ToolCallRecord(
                tool_name=tc.get("tool_name", ""),
                args_summary=tc.get("args_summary", ""),
                cached=tc.get("cached", False),
                duration_ms=tc.get("duration_ms", 0.0),
                success=tc.get("success", True),
                error=tc.get("error"),
            )
            for tc in tool_calls
        ]
        self._current_iteration.cache_hits = cache_hits
        self._current_iteration.cache_misses = cache_misses
        self._current_iteration.execution_duration_ms = duration * 1000

        self.total_tool_calls += len(tool_calls)
        self.total_cache_hits += cache_hits
        self.total_cache_misses += cache_misses
        logger.info(
            f"[ToT] Executed {len(tool_calls)} tools at depth {depth} "
            f"(cache: {cache_hits}H/{cache_misses}M, {duration * 1000:.0f}ms)"
        )

    def log_termination_check(self, depth: int, should_stop: bool,
                               trigger: Optional[str], details: dict):
        """Log the termination check. Auto-finalizes the iteration."""
        self._ensure_iteration(depth)
        self._current_iteration.should_stop = should_stop
        self._current_iteration.stop_trigger = trigger
        self._current_iteration.termination_details = details
        # Termination is the last phase -> finalize this iteration
        self._finalize_iteration()
        logger.debug(
            f"[ToT] Termination check at depth {depth}: "
            f"stop={should_stop}, trigger={trigger}"
        )

    # --- Backward compat: explicit start/end iteration (now no-ops) ---

    def start_iteration(self, depth: int):
        """Start a new iteration at given depth. Keional: auto-managed now."""
        self._ensure_iteration(depth)

    def end_iteration(self, depth: int, decision: str, reason: str):
        """End current iteration.  Optional: auto-managed now."""
        if self._current_iteration and self._current_iteration.depth == depth:
                self._current_iteration.termination_details["decision"] = decision
                self._current_iteration.termination_details["reason"] = reason
        self._finalize_iteration()

    # --- Tool-level logging ---

    def log_tool_call(self, tool_name: str, args_summary: str, cached: bool,
                      duration: float, success: bool):
        """Log a single tool call."""
        self.total_tool_calls += 1
        if cached:
            self.total_cache_hits += 1
        else:
            self.total_cache_misses += 1
        status = "hit" if cached else "miss"
        if success:
            logger.debug(f"[ToT] Tool {tool_name} ({status}, {duration * 1000:.0f}ms)")
        else:
            logger.warning(f"[ToT] Tool {tool_name} failed ({status}, {duration * 1000:.0f}ms)")

    # --- Research mode logging ---

    def log_research_phase(self, phase: str, details: dict):
        """Log research mode phase transition."""
        logger.info(f"[ToT] Research phase: {phase} - {details}")

    # --- Results ---

    def log_final_answer(self, answer: str, best_path: list[str], total_iterations: int):
        """Log the final answer and best path."""
        if self._current_iteration is not None:
            self._finalize_iteration()
        self.final_answer = answer
        self.best_path = best_path
        logger.info(
            f"[ToT] Final answer: {len(answer)} chars, "
            f"path={' -> '.join(best_path[:5])}, "
            f"iterations={total_iterations}"
        )

    # --- Export ---

    def get_summary(self) -> dict:
        """Get execution summary as dict."""
        if self._current_iteration is not None:
            self._finalize_iteration()

        total_duration = ((self.end_time or time.time()) - self.start_time) * 1000
        cache_total = self.total_cache_hits + self.total_cache_misses

        return {
            "mode": "tot",
            "profile": self.profile,
            "task_name": self.task_name,
            "session_id": self.session_id,
            "config": self.config,
            "profile_selection": self.profile_selection,
            "iterations": [
                {
                    "depth": it.depth,
                    "generation": {
                        "count": it.generation_count,
                        "variant": it.generation_variant,
                        "prompt_length": it.generation_prompt_length,
                        "duration_ms": round(it.generation_duration_ms, 1),
                        "prompt_composition": _serialize_prompt_composition(it.generation_prompt_composition),
                    },
                    "evaluation": {
                        "scores": [
                            {
                                "thought_id": s.thought_id,
                                "score": s.score,
                                "criteria": s.criteria,
                                "fatal_flaw": s.fatal_flaw,
                            }
                            for s in it.scores
                        ],
                        "best_path_changed": it.best_path_changed,
                        "beam_pruned": it.beam_pruned,
                        "prompt_composition": _serialize_prompt_composition(it.evaluation_prompt_composition),
                    },
                    "execution": {
                        "tool_calls": [
                            {
                                "tool_name": tc.tool_name,
                                "args_summary": tc.args_summary,
                                "cached": tc.cached,
                                "duration_ms": round(tc.duration_ms, 1),
                                "success": tc.success,
                                "error": tc.error,
                            }
                            for tc in it.tool_calls
                        ],
                        "cache_hits": it.cache_hits,
                        "cache_misses": it.cache_misses,
                        "duration_ms": round(it.execution_duration_ms, 1),
                    },
                    "termination": {
                        "should_stop": it.should_stop,
                        "trigger": it.stop_trigger,
                        "details": it.termination_details,
                        "prompt_preview": it.termination_prompt_preview,
                    },
                    "duration_ms": round(
                        (it.end_time - it.start_time) * 1000 if it.end_time else 0, 1
                    ),
                }
                for it in self.iterations
            ],
            "final_answer": self.final_answer,
            "best_path": self.best_path,
            "summary": {
                "total_iterations": len(self.iterations),
                "total_duration_ms": round(total_duration, 1),
                "total_tool_calls": self.total_tool_calls,
                "cache_hit_rate": (
                    self.total_cache_hits / cache_total if cache_total > 0 else 0.0
                ),
                "avg_score": self._compute_avg_score(),
                "backtrack_count": self.total_backtracks,
            },
        }

    def save_trace(self, filepath: str):
        """Save full execution trace as JSON."""
        if self._current_iteration is not None:
            self._finalize_iteration()
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.get_summary(), f, indent=2, ensure_ascii=False, default=str)
        logger.info(f"[ToT] Trace saved to {filepath}")

    def _compute_avg_score(self) -> float:
        """Compute average score across all evaluations."""
        all_scores = []
        for it in self.iterations:
            for s in it.scores:
                all_scores.append(s.score)
        return round(sum(all_scores) / len(all_scores), 2) if all_scores else 0.0


def _serialize_prompt_composition(pc: Optional[PromptCompositionRecord]) -> Optional[dict]:
    """Serialize a PromptCompositionRecord to dict for JSON export."""
    if pc is None:
        return None
    return {
        "node_role": pc.node_role,
        "template_name": pc.template_name,
        "system_prompt_length": pc.system_prompt_length,
        "base_prompt_length": pc.base_prompt_length,
        "appendix_length": pc.appendix_length,
        "appendix_preview": pc.appendix_preview,
        "user_prompt_preview": pc.user_prompt_preview,
        "domain_methods_injected": pc.domain_methods_injected,
        "domain_instruction_preview": pc.domain_instruction_preview,
        "tool_list": pc.tool_list,
        "variant": pc.variant,
    }
