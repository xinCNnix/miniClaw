"""ToT execution lifecycle logger for tree-structured reasoning."""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.perv.pevr_logger import extract_token_usage, _ts

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
class EvidenceExtractionRecord:
    """Record of evidence extracted from a single source."""
    source_id: str
    source_type: str
    claim_count: int
    number_count: int
    reliability: float
    duration_ms: float


@dataclass
class CoverageUpdateRecord:
    """Record of a coverage map update during research."""
    coverage_score: float
    topics_covered: int
    topics_total: int
    critical_missing: List[str]


@dataclass
class ContradictionRecord:
    """Record of contradiction detection results."""
    conflict_count: int
    max_severity: float
    types_found: List[str]


@dataclass
class CitationChaseRecord:
    """Record of citation chasing activity."""
    targets_count: int
    fetched_count: int
    budget_remaining: int


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

    # Phase 9: Beam search tracking
    active_beam_count: int = 0
    beam_width_used: int = 0
    backtrack_events: list = field(default_factory=list)  # [{"reason": ..., "beam_idx": ...}]
    local_loop_steps: int = 0

    # Execution phase
    tool_calls: list = field(default_factory=list)
    cache_hits: int = 0
    cache_misses: int = 0
    execution_duration_ms: float = 0.0

    # Termination decision
    should_stop: bool = False
    stop_trigger: Optional[str] = None
    termination_details: dict = field(default_factory=dict)

    # Research phase tracking
    evidence_extraction: Optional[List[EvidenceExtractionRecord]] = None
    coverage_update: Optional[CoverageUpdateRecord] = None
    contradiction_detection: Optional[ContradictionRecord] = None
    citation_chase: Optional[CitationChaseRecord] = None
    token_used_this_iteration: Optional[int] = None
    research_round: Optional[int] = None

    # ISO UTC timestamps (millisecond precision)
    start_ts: str = ""
    end_ts: str = ""

    # Per-phase token tracking
    generation_tokens: Dict[str, int] = field(default_factory=dict)
    evaluation_tokens: Dict[str, int] = field(default_factory=dict)
    execution_tokens: Dict[str, int] = field(default_factory=dict)
    termination_tokens: Dict[str, int] = field(default_factory=dict)


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

        # Token aggregate counters
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.total_llm_calls: int = 0
        self._custom_events: List[Dict[str, Any]] = []
        self._start_ts: str = ""
        self._end_ts: str = ""

    def __enter__(self) -> "ToTExecutionLogger":
        self._start_ts = _ts()
        logger.info(f"[ToT] [{self._start_ts}] Start session: {self.task_name} (profile={self.profile})")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        self._end_ts = _ts()
        duration = (self.end_time - self.start_time) * 1000
        if exc_type:
            logger.error(f"[ToT] [{self._end_ts}] Session failed: {exc_val} ({duration:.0f}ms)")
        else:
            logger.info(
                f"[ToT] [{self._end_ts}] Session complete: {len(self.iterations)} iterations, "
                f"{duration:.0f}ms, {self.total_tool_calls} tool calls"
            )
        self._auto_save_trace()

    # --- Auto iteration lifecycle ---

    def _finalize_iteration(self):
        """Finalize current iteration and add to iterations list."""
        if self._current_iteration is not None:
            self._current_iteration.end_time = time.time()
            self._current_iteration.end_ts = _ts()
            self.iterations.append(self._current_iteration)
            self._current_iteration = None

    def _ensure_iteration(self, depth: int):
        """Ensure an active iteration exists for the given depth, finalizing previous if needed."""
        if self._current_iteration is None or self._current_iteration.depth != depth:
            self._finalize_iteration()
            self._current_iteration = IterationRecord(depth=depth, start_time=time.time(), start_ts=_ts())

    # --- Phase logging (auto-manages iteration lifecycle) ---

    def log_generation(self, depth: int, count: int, variant: str,
                       prompt_length: int, duration: float,
                       token_usage: Optional[Dict[str, int]] = None):
        """Log the thought generation phase. Auto-starts a new iteration."""
        self._ensure_iteration(depth)
        self._current_iteration.generation_count = count
        self._current_iteration.generation_variant = variant
        self._current_iteration.generation_prompt_length = prompt_length
        self._current_iteration.generation_duration_ms = duration * 1000
        if token_usage:
            self._current_iteration.generation_tokens = token_usage
            self.total_prompt_tokens += token_usage.get("prompt_tokens", 0)
            self.total_completion_tokens += token_usage.get("completion_tokens", 0)
            self.total_llm_calls += 1
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
                       best_path_changed: bool, beam_pruned: int,
                       token_usage: Optional[Dict[str, int]] = None):
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
        if token_usage:
            self._current_iteration.evaluation_tokens = token_usage
            self.total_prompt_tokens += token_usage.get("prompt_tokens", 0)
            self.total_completion_tokens += token_usage.get("completion_tokens", 0)
            self.total_llm_calls += 1
        logger.info(
            f"[ToT] Evaluated {len(scores)} thoughts at depth {depth}, "
            f"best_path_changed={best_path_changed}, pruned={beam_pruned}"
        )

    def log_execution(self, depth: int, tool_calls: list[dict],
                      cache_hits: int, cache_misses: int, duration: float,
                      token_usage: Optional[Dict[str, int]] = None):
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
        if token_usage:
            self._current_iteration.execution_tokens = token_usage
            self.total_prompt_tokens += token_usage.get("prompt_tokens", 0)
            self.total_completion_tokens += token_usage.get("completion_tokens", 0)
            self.total_llm_calls += 1

        self.total_tool_calls += len(tool_calls)
        self.total_cache_hits += cache_hits
        self.total_cache_misses += cache_misses
        logger.info(
            f"[ToT] Executed {len(tool_calls)} tools at depth {depth} "
            f"(cache: {cache_hits}H/{cache_misses}M, {duration * 1000:.0f}ms)"
        )

    def log_termination_check(self, depth: int, should_stop: bool,
                               trigger: Optional[str], details: dict,
                               token_usage: Optional[Dict[str, int]] = None):
        """Log the termination check. Auto-finalizes the iteration."""
        self._ensure_iteration(depth)
        self._current_iteration.should_stop = should_stop
        self._current_iteration.stop_trigger = trigger
        self._current_iteration.termination_details = details
        if token_usage:
            self._current_iteration.termination_tokens = token_usage
            self.total_prompt_tokens += token_usage.get("prompt_tokens", 0)
            self.total_completion_tokens += token_usage.get("completion_tokens", 0)
            self.total_llm_calls += 1
        # Termination is the last phase -> finalize this iteration
        self._finalize_iteration()
        logger.debug(
            f"[ToT] Termination check at depth {depth}: "
            f"stop={should_stop}, trigger={trigger}"
        )

    # --- Custom event logging (mirrors PERV pattern) ---

    def log_custom(self, event_type: str, data: Any = None, **kwargs):
        """Log a custom event (mirrors PERV's log_custom pattern).

        Args:
            event_type: Event type string (e.g. "pattern_retrieval", "learning_result").
            data: Optional data payload.
            **kwargs: Additional key-value pairs merged into the event.
        """
        event: Dict[str, Any] = {"type": event_type, "ts": _ts()}
        if data is not None:
            event["data"] = data
        event.update(kwargs)
        self._custom_events.append(event)

    # --- Auto-save trace ---

    def _auto_save_trace(self):
        """Auto-save trace to logs/tot_traces/ on context manager exit."""
        try:
            trace_dir = Path("logs") / "tot_traces"
            trace_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            sid = self.session_id[:8] if self.session_id else "no-session"
            self.save_trace(str(trace_dir / f"tot_{ts}_{sid}.json"))
        except Exception as e:
            logger.debug("[ToT] Auto-save trace failed: %s", e)

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

    def log_evidence_extraction(
        self,
        depth: int,
        source_id: str,
        claim_count: int,
        number_count: int,
        reliability: float,
        duration_ms: float,
        source_type: str = "unknown",
    ):
        """Log evidence extraction from a single source.

        Args:
            depth: Current reasoning depth.
            source_id: Identifier of the source being extracted.
            claim_count: Number of claims extracted from the source.
            number_count: Number of quantitative data points extracted.
            reliability: Reliability score of the source (0.0 - 1.0).
            duration_ms: Time spent on extraction in milliseconds.
            source_type: Type of the source (e.g. "web", "paper", "database").
        """
        self._ensure_iteration(depth)
        record = EvidenceExtractionRecord(
            source_id=source_id,
            source_type=source_type,
            claim_count=claim_count,
            number_count=number_count,
            reliability=reliability,
            duration_ms=duration_ms,
        )
        if self._current_iteration.evidence_extraction is None:
            self._current_iteration.evidence_extraction = []
        self._current_iteration.evidence_extraction.append(record)
        logger.info(
            f"[ToT] Evidence extraction from {source_id} ({source_type}): "
            f"{claim_count} claims, {number_count} numbers, "
            f"reliability={reliability:.2f}, {duration_ms:.0f}ms"
        )

    def log_coverage_update(
        self,
        depth: int,
        coverage_score: float,
        topics_covered: int,
        topics_total: int,
        critical_missing: List[str],
    ):
        """Log coverage map update.

        Args:
            depth: Current reasoning depth.
            coverage_score: Overall coverage score (0.0 - 1.0).
            topics_covered: Number of topics covered so far.
            topics_total: Total number of topics to cover.
            critical_missing: List of critical topics still missing.
        """
        self._ensure_iteration(depth)
        self._current_iteration.coverage_update = CoverageUpdateRecord(
            coverage_score=coverage_score,
            topics_covered=topics_covered,
            topics_total=topics_total,
            critical_missing=critical_missing,
        )
        logger.info(
            f"[ToT] Coverage update: {coverage_score:.2f} "
            f"({topics_covered}/{topics_total} topics, "
            f"{len(critical_missing)} critical missing)"
        )

    def log_contradiction_detection(
        self,
        depth: int,
        conflict_count: int,
        max_severity: float,
        types_found: List[str],
    ):
        """Log contradiction detection results.

        Args:
            depth: Current reasoning depth.
            conflict_count: Number of conflicts/contradictions found.
            max_severity: Maximum severity score among detected conflicts (0.0 - 1.0).
            types_found: List of contradiction type labels found.
        """
        self._ensure_iteration(depth)
        self._current_iteration.contradiction_detection = ContradictionRecord(
            conflict_count=conflict_count,
            max_severity=max_severity,
            types_found=types_found,
        )
        logger.info(
            f"[ToT] Contradiction detection: {conflict_count} conflicts, "
            f"max_severity={max_severity:.2f}, types={types_found}"
        )

    def log_citation_chasing(
        self,
        depth: int,
        targets_count: int,
        fetched_count: int,
        budget_remaining: int,
    ):
        """Log citation chasing activity.

        Args:
            depth: Current reasoning depth.
            targets_count: Number of citation targets identified.
            fetched_count: Number of targets successfully fetched.
            budget_remaining: Remaining citation chase budget.
        """
        self._ensure_iteration(depth)
        self._current_iteration.citation_chase = CitationChaseRecord(
            targets_count=targets_count,
            fetched_count=fetched_count,
            budget_remaining=budget_remaining,
        )
        logger.info(
            f"[ToT] Citation chasing: {fetched_count}/{targets_count} fetched, "
            f"budget_remaining={budget_remaining}"
        )

    # --- Phase 9: Beam search logging ---

    def log_beam_selection(
        self,
        depth: int,
        active_beams: List[List[str]],
        beam_scores: List[float],
        beam_width: int,
        pruned_count: int = 0,
        backtrack_events: Optional[List[Dict[str, Any]]] = None,
    ):
        """Log beam selection results after pruning.

        Args:
            depth: Current reasoning depth.
            active_beams: List of active beam paths (each a list of thought IDs).
            beam_scores: Scores corresponding to each active beam.
            beam_width: Configured beam width (B).
            pruned_count: Number of candidates pruned this round.
            backtrack_events: List of backtrack/regeneration events, e.g.
                [{"reason": "low_score", "beam_idx": 2}, ...]
        """
        self._ensure_iteration(depth)
        self._current_iteration.active_beam_count = len(active_beams)
        self._current_iteration.beam_width_used = beam_width
        if backtrack_events:
            self._current_iteration.backtrack_events.extend(backtrack_events)
            self.total_backtracks += len(backtrack_events)

        logger.info(
            f"[ToT] Beam selection at depth {depth}: "
            f"{len(active_beams)}/{beam_width} beams active, "
            f"scores={[round(s, 2) for s in beam_scores]}, "
            f"pruned={pruned_count}"
        )
        if backtrack_events:
            for evt in backtrack_events:
                logger.info(
                    f"[ToT] Backtrack: reason={evt.get('reason')}, "
                    f"beam_idx={evt.get('beam_idx')}"
                )

    def log_local_loop_step(
        self,
        depth: int,
        thought_id: str,
        step_index: int,
        tool_name: str,
        success: bool,
        duration_ms: float,
    ):
        """Log a single step within a multi-step local tool execution loop.

        Args:
            depth: Current reasoning depth.
            thought_id: ID of the thought being executed.
            step_index: Step index within the tool plan (0-based).
            tool_name: Name of the tool executed.
            success: Whether the step succeeded.
            duration_ms: Duration of this step in milliseconds.
        """
        self._ensure_iteration(depth)
        self._current_iteration.local_loop_steps += 1
        status = "ok" if success else "fail"
        logger.debug(
            f"[ToT] Local loop step at depth {depth}, thought {thought_id}: "
            f"step {step_index} ({tool_name}) {status} {duration_ms:.0f}ms"
        )

    # --- Existing research mode logging ---

    def log_draft_update(self, depth: int, sections_count: int, citations_count: int):
        """Log writer draft update.

        Args:
            depth: Current reasoning depth.
            sections_count: Number of sections in the current draft.
            citations_count: Number of citations in the current draft.
        """
        self._ensure_iteration(depth)
        logger.info(
            f"[ToT] Draft update at depth {depth}: "
            f"{sections_count} sections, {citations_count} citations"
        )

    def log_token_usage(self, depth: int, tokens: int, research_round: int):
        """Log token usage for the current iteration.

        Args:
            depth: Current reasoning depth.
            tokens: Number of tokens used in this iteration.
            research_round: The research round number within the iteration.
        """
        self._ensure_iteration(depth)
        self._current_iteration.token_used_this_iteration = tokens
        self._current_iteration.research_round = research_round
        logger.debug(
            f"[ToT] Token usage at depth {depth}, round {research_round}: {tokens} tokens"
        )

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

        # Classify custom events
        enrichment_types = {"pattern_retrieval", "strategy_injection", "semantic_history"}
        learning_types = {"learning_result", "memory_extraction"}
        enrichment_events = [e for e in self._custom_events if e.get("type") in enrichment_types]
        learning_events = [e for e in self._custom_events if e.get("type") in learning_types]

        return {
            "mode": "tot",
            "start_ts": self._start_ts,
            "end_ts": self._end_ts,
            "profile": self.profile,
            "task_name": self.task_name,
            "session_id": self.session_id,
            "config": self.config,
            "profile_selection": self.profile_selection,
            "iterations": [
                {
                    "depth": it.depth,
                    "start_ts": it.start_ts,
                    "end_ts": it.end_ts,
                    "generation": {
                        "count": it.generation_count,
                        "variant": it.generation_variant,
                        "prompt_length": it.generation_prompt_length,
                        "duration_ms": round(it.generation_duration_ms, 1),
                        "prompt_composition": _serialize_prompt_composition(it.generation_prompt_composition),
                        "tokens": it.generation_tokens,
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
                        "tokens": it.evaluation_tokens,
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
                        "tokens": it.execution_tokens,
                    },
                    "termination": {
                        "should_stop": it.should_stop,
                        "trigger": it.stop_trigger,
                        "details": it.termination_details,
                        "prompt_preview": it.termination_prompt_preview,
                        "tokens": it.termination_tokens,
                    },
                    # Phase 9: beam search tracking
                    "beam": {
                        "active_beam_count": it.active_beam_count,
                        "beam_width_used": it.beam_width_used,
                        "backtrack_events": it.backtrack_events,
                        "local_loop_steps": it.local_loop_steps,
                    } if it.active_beam_count > 0 else None,
                    "research": _serialize_research(it),
                    "duration_ms": round(
                        (it.end_time - it.start_time) * 1000 if it.end_time else 0, 1
                    ),
                }
                for it in self.iterations
            ],
            "enrichment_events": enrichment_events,
            "learning_events": learning_events,
            "final_answer": self.final_answer,
            "best_path": self.best_path,
            "summary": {
                "total_iterations": len(self.iterations),
                "total_duration_ms": round(total_duration, 1),
                "total_prompt_tokens": self.total_prompt_tokens,
                "total_completion_tokens": self.total_completion_tokens,
                "total_llm_calls": self.total_llm_calls,
                "total_tool_calls": self.total_tool_calls,
                "cache_hit_rate": (
                    self.total_cache_hits / cache_total if cache_total > 0 else 0.0
                ),
                "avg_score": self._compute_avg_score(),
                "backtrack_count": self.total_backtracks,
                "total_evidence_items": self._compute_total_evidence_items(),
                "avg_evidence_reliability": self._compute_avg_reliability(),
                "final_coverage_score": self._compute_final_coverage(),
                "total_contradictions": self._compute_total_contradictions(),
                "citation_chase_rounds": self._compute_citation_chase_rounds(),
                "total_tokens_used": self._compute_total_tokens(),
                # Phase 9: beam search aggregate
                "total_beam_backtracks": self.total_backtracks,
                "total_local_loop_steps": sum(it.local_loop_steps for it in self.iterations),
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

    def _compute_total_evidence_items(self) -> int:
        """Compute total evidence items extracted across all iterations."""
        total = 0
        for it in self.iterations:
            if it.evidence_extraction is not None:
                for rec in it.evidence_extraction:
                    total += rec.claim_count + rec.number_count
        return total

    def _compute_avg_reliability(self) -> float:
        """Compute average reliability of extracted evidence sources."""
        reliabilities: List[float] = []
        for it in self.iterations:
            if it.evidence_extraction is not None:
                for rec in it.evidence_extraction:
                    reliabilities.append(rec.reliability)
        return round(sum(reliabilities) / len(reliabilities), 2) if reliabilities else 0.0

    def _compute_final_coverage(self) -> Optional[float]:
        """Get the final coverage score from the last iteration that has one."""
        for it in reversed(self.iterations):
            if it.coverage_update is not None:
                return round(it.coverage_update.coverage_score, 2)
        return None

    def _compute_total_contradictions(self) -> int:
        """Compute total contradictions detected across all iterations."""
        total = 0
        for it in self.iterations:
            if it.contradiction_detection is not None:
                total += it.contradiction_detection.conflict_count
        return total

    def _compute_citation_chase_rounds(self) -> int:
        """Count the number of iterations that performed citation chasing."""
        return sum(
            1 for it in self.iterations if it.citation_chase is not None
        )

    def _compute_total_tokens(self) -> int:
        """Compute total tokens used across all iterations."""
        total = 0
        for it in self.iterations:
            if it.token_used_this_iteration is not None:
                total += it.token_used_this_iteration
        return total


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


def _serialize_research(it: IterationRecord) -> Optional[Dict[str, Any]]:
    """Serialize research-related fields from an IterationRecord.

    Returns None if no research data is present on the iteration.
    """
    has_research = (
        it.evidence_extraction is not None
        or it.coverage_update is not None
        or it.contradiction_detection is not None
        or it.citation_chase is not None
        or it.token_used_this_iteration is not None
        or it.research_round is not None
    )
    if not has_research:
        return None

    result: Dict[str, Any] = {}

    if it.evidence_extraction is not None:
        result["evidence_extraction"] = [
            {
                "source_id": rec.source_id,
                "source_type": rec.source_type,
                "claim_count": rec.claim_count,
                "number_count": rec.number_count,
                "reliability": rec.reliability,
                "duration_ms": round(rec.duration_ms, 1),
            }
            for rec in it.evidence_extraction
        ]

    if it.coverage_update is not None:
        result["coverage_update"] = {
            "coverage_score": it.coverage_update.coverage_score,
            "topics_covered": it.coverage_update.topics_covered,
            "topics_total": it.coverage_update.topics_total,
            "critical_missing": it.coverage_update.critical_missing,
        }

    if it.contradiction_detection is not None:
        result["contradiction_detection"] = {
            "conflict_count": it.contradiction_detection.conflict_count,
            "max_severity": it.contradiction_detection.max_severity,
            "types_found": it.contradiction_detection.types_found,
        }

    if it.citation_chase is not None:
        result["citation_chase"] = {
            "targets_count": it.citation_chase.targets_count,
            "fetched_count": it.citation_chase.fetched_count,
            "budget_remaining": it.citation_chase.budget_remaining,
        }

    if it.token_used_this_iteration is not None:
        result["tokens_used"] = it.token_used_this_iteration

    if it.research_round is not None:
        result["research_round"] = it.research_round

    return result
