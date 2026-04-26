"""
PEVR Orchestrator - builds graph, runs it, yields SSE events.

Provides the high-level ``PlannerOrchestrator`` class that:
  1. Compiles the PEVR LangGraph on first use.
  2. Feeds the user request into the graph.
  3. Streams SSE-compatible event dicts for real-time progress.
  4. Falls back gracefully on unexpected errors.

The orchestrator does **not** use LangGraph's StreamWriter (unavailable in
langgraph 0.0.20).  Instead, SSE events are derived from the
``reasoning_trace`` field and per-node state updates.
"""

import asyncio
import logging
import threading
import time
from typing import AsyncIterator, Dict, Any, List, Optional

from app.core.perv.graph import build_planner_graph
from app.core.execution_trace.perv_trace import PEVRTrace as PEVRLogger, get_pevr_logger

logger = logging.getLogger(__name__)
_stderr_lock = threading.Lock()


class PlannerOrchestrator:
    """Orchestrates the PEVR closed-loop execution.

    Yields SSE-compatible event dicts for real-time streaming to the
    frontend.  On catastrophic PEVR failure the caller can fall back to
    direct ``AgentManager`` execution.

    Args:
        agent_manager: Optional reference to the application's
            ``AgentManager`` (reserved for future fallback support).
        max_retries: Maximum replan loops before force-finalizing.
        max_llm_calls: Soft cap on total LLM calls across all nodes
            (used by nodes to decide early termination).
        session_id: Optional session ID for log correlation.
    """

    def __init__(
        self,
        agent_manager=None,
        max_retries: int = 3,
        max_llm_calls: int = 15,
        session_id: str = "",
    ):
        self.agent_manager = agent_manager
        self.max_retries = max_retries
        self.max_llm_calls = max_llm_calls
        self.session_id = session_id
        self._graph = None
        self._pevr_log: Optional[PEVRLogger] = None

        # Collected state for post-execution learning
        self._final_observations: List[Dict] = []
        self._final_plan: List[Dict] = []
        self._final_answer: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process_request(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        force_mode: Optional[str] = None,
        cancel_event: Optional["asyncio.Event"] = None,
        run_id: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Main entry point.  Yields SSE event dicts.

        Constructs the initial PEVR state from the conversation, runs the
        compiled graph, and translates node outputs into SSE events.

        If PERV Router is enabled, performs routing decision first:
        - direct_answer: yields perv_direct_answer signal for chat.py fallback
        - plan_execute/plan_execute_verify: injects route_decision into state

        Args:
            messages: Conversation messages (last entry is the current
                user message).
            system_prompt: The agent system prompt forwarded to nodes.

        Yields:
            SSE event dictionaries with keys ``type`` and optional
            payload fields.
        """
        self._wd_tracker = None

        if not self._graph:
            try:
                self._graph = build_planner_graph()
            except OSError:
                # Windows uvicorn reload subprocess may have invalid stderr.
                # graph.compile() can trigger internal writes to stderr that fail.
                # Retry after patching stderr to a safe sink.
                import io as _io
                import sys as _sys
                with _stderr_lock:
                    _prev = _sys.stderr
                    _sys.stderr = _io.StringIO()
                    try:
                        self._graph = build_planner_graph()
                    finally:
                        _sys.stderr = _prev

        task = messages[-1]["content"] if messages else ""

        # Reset collected state for this request
        self._final_observations = []
        self._final_plan = []
        self._final_answer = None

        # Initialize lifecycle logger
        self._pevr_log = get_pevr_logger(task=task, session_id=self.session_id)

        # ── PERV Router 决策 ──
        route_decision = None
        route_start = time.monotonic()
        try:
            if force_mode:
                # 外部强制指定模式，跳过路由判断
                from app.core.perv.state import RouteDecision
                route_decision = RouteDecision(
                    mode=force_mode,
                    risk="medium",
                    reason=f"forced_by_caller:{force_mode}",
                    max_steps=6,
                    allow_tools=True,
                    source="force",
                )
            else:
                from app.config import get_settings
                settings = get_settings()
                if getattr(settings, "perv_router_enabled", True):
                    from app.core.perv.router import route
                    route_decision = await route(task)
        except Exception as e:
            logger.warning("Router failed, using safe default: %s", e)
            route_decision = None

        route_duration_ms = (time.monotonic() - route_start) * 1000

        # 记录路由决策
        if self._pevr_log and route_decision:
            self._pevr_log.log_routing(route_decision, duration_ms=route_duration_ms)

        # 发送路由决策事件
        if route_decision:
            yield {
                "type": "perv_router_decision",
                "decision": route_decision,
                "duration_ms": route_duration_ms,
            }

        # 如果是 direct_answer，返回信号让 chat.py 用普通 Agent
        # 注意：需要在 with pevr_log 块内 return，确保 __exit__ 触发 _auto_save_trace
        # 旧代码在 with 之前 return，导致 direct_answer 时不保存 trace
        # if route_decision and route_decision.get("mode") == "direct_answer":
        #     logger.info(
        #         "Router selected direct_answer: reason=%s",
        #         route_decision.get("reason"),
        #     )
        #     yield {"type": "perv_direct_answer"}
        #     yield {"type": "done"}
        #     return

        # ── Pre-hook enrichment (Phase 2) ──
        enrichment = await self._prepare_enrichment(task)

        initial_state: Dict[str, Any] = {
            "task": task,
            "messages": messages,
            "system_prompt": system_prompt,
            "session_context": {
                "semantic_history": enrichment.get("semantic_history", ""),
            },
            "plan": [],
            "observations": [],
            "verifier_report": None,
            "retry_count": 0,
            "max_retries": self.max_retries,
            "consecutive_failures": 0,
            "step_cursor": 0,
            "step_outputs": {},
            "route_decision": route_decision,
            "summarized_observations": None,
            "final_answer": None,
            "reasoning_trace": [],
            "enrichment": enrichment,
            "learning_metrics": {},
            "skill_policy_report": None,
            "_pevr_log": self._pevr_log,
        }

        with self._pevr_log:
            self._pevr_log.log_config({
                "max_retries": self.max_retries,
                "max_llm_calls": self.max_llm_calls,
            })

            # direct_answer 分支：在 with 块内处理，确保 __exit__ 触发 _auto_save_trace
            if route_decision and route_decision.get("mode") == "direct_answer":
                logger.info(
                    "Router selected direct_answer: reason=%s",
                    route_decision.get("reason"),
                )
                yield {"type": "perv_direct_answer"}
                yield {"type": "done"}
                return

            try:
                yield {"type": "pevr_start"}

                start = time.time()
                async for event in self._run_graph(
                    initial_state,
                    cancel_event=cancel_event,
                    run_id=run_id,
                ):
                    yield event
                graph_duration = time.time() - start

                logger.info(
                    "[PEVR Orchestrator] Graph completed in %.1fs",
                    graph_duration,
                )

                # === PERV 反思与补正 ===
                if self._final_answer:
                    try:
                        from app.config import get_settings as _reflect_gs
                        _reflect_settings = _reflect_gs()
                        if getattr(_reflect_settings, "enable_agent_reflection", False):
                            from app.core.reflection.helpers import evaluate_and_correct

                            tool_calls = self._extract_tool_calls_from_observations(
                                self._final_observations or []
                            )
                            action = await evaluate_and_correct(
                                user_query=task,
                                agent_output=self._final_answer,
                                tool_calls=tool_calls,
                                execution_time=graph_duration,
                                execution_mode="perv",
                            )
                            if action.should_correct and action.correction:
                                yield {
                                    "type": "self_correction",
                                    "quality_score": action.quality_score,
                                    "correction": action.correction,
                                }
                    except Exception as e:
                        logger.debug("[Reflection] PERV reflection failed: %s", e)

                yield {"type": "done"}

                # Trigger post-execution learning (fire-and-forget)
                import asyncio
                try:
                    from app.config import get_settings as _gs
                    if getattr(_gs(), "perv_enable_post_learning", False) and self._final_answer:
                        asyncio.create_task(
                            self._post_execution_learning(
                                task=task,
                                final_answer=self._final_answer,
                                observations=self._final_observations,
                                plan=self._final_plan,
                                execution_metrics={"total_duration": graph_duration},
                            )
                        )
                except Exception as _le:
                    logger.debug("[PEVR] Post-learning trigger failed: %s", _le)

            except Exception as exc:
                logger.error(
                    "[PEVR Orchestrator] Fatal error: %s (%.1fs)",
                    exc,
                    time.time() - start if 'start' in dir() else 0,
                    exc_info=True,
                )
                if self._pevr_log:
                    self._pevr_log.log_error("orchestrator", exc)
                yield {"type": "error", "error": str(exc)}
                yield {"type": "done"}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _prepare_enrichment(self, task: str) -> Dict[str, Any]:
        """Gather enrichment data from learning subsystems before planning.

        Retrieves relevant patterns, strategy guidance, and semantic history
        to inject into the planner prompt.  Each feature is guarded by its
        own try/except so that a failure in any single subsystem does not
        block the PERV pipeline.

        Args:
            task: The user's original task text.

        Returns:
            A dict with optional keys ``retrieved_patterns``,
            ``strategy_prompt``, and ``semantic_history``.
        """
        enrichment: Dict[str, Any] = {}

        try:
            from app.config import get_settings
            settings = get_settings()
        except Exception as e:
            logger.warning("[PERV Enrichment] Could not load settings: %s", e)
            return enrichment

        # --- a) Pattern Retrieval ---
        if getattr(settings, "perv_enable_pattern_retrieval", False):
            try:
                import asyncio
                from app.memory.auto_learning.memory import get_pattern_memory
                memory = get_pattern_memory()
                patterns = await asyncio.to_thread(
                    lambda: memory.get_top_patterns(query=task, top_k=3)
                )
                enrichment["retrieved_patterns"] = [
                    {
                        "description": p.get("description", ""),
                        "situation": p.get("situation", ""),
                        "outcome": p.get("outcome", ""),
                        "fix_action": p.get("fix_action", ""),
                    }
                    for p in patterns
                ]
                if self._pevr_log:
                    self._pevr_log.log_custom("pattern_retrieval", count=len(patterns))
            except Exception as e:
                logger.warning("[PERV Enrichment] Pattern retrieval failed: %s", e)

        # --- b) Strategy Injection ---
        if getattr(settings, "perv_enable_strategy_injection", False):
            try:
                import asyncio
                from app.memory.auto_learning.reflection.strategy_scheduler import get_strategy_scheduler
                from app.memory.auto_learning.utils import get_embedder
                from app.memory.auto_learning.nn import get_pattern_nn
                scheduler = get_strategy_scheduler()
                nn_model = get_pattern_nn()
                embedder = get_embedder()
                state_vec = await asyncio.to_thread(lambda: embedder.encode(task))
                strategy_prompt = await asyncio.to_thread(
                    lambda: scheduler.get_strategy(nn_model, state_vec, None, None)
                )
                enrichment["strategy_prompt"] = strategy_prompt or ""
                if self._pevr_log:
                    self._pevr_log.log_custom(
                        "strategy_injection", prompt=strategy_prompt[:100]
                    )
            except Exception as e:
                logger.warning("[PERV Enrichment] Strategy injection failed: %s", e)

        # --- c) Semantic History (unified KG + vector) ---
        if getattr(settings, "perv_enable_semantic_history", False):
            try:
                from app.memory.retriever_factory import get_memory_retriever
                retriever = get_memory_retriever()
                memory_result = await retriever.retrieve(task)
                if memory_result.merged_context:
                    enrichment["semantic_history"] = memory_result.merged_context
                    if self._pevr_log:
                        self._pevr_log.log_custom(
                            "semantic_history", kg_source=memory_result.kg_source,
                        )
            except Exception as e:
                logger.warning("[PERV Enrichment] Semantic history search failed: %s", e)

        # --- d) Meta Policy Injection ---
        if getattr(settings, "enable_meta_policy", False):
            try:
                from app.core.meta_policy.meta_policy_helpers import get_meta_policy_decision
                from app.core.meta_policy.capability_map import CapabilityMap

                cap_map_mp = CapabilityMap.from_core_tools()
                meta_decision = get_meta_policy_decision(task, cap_map=cap_map_mp)
                if meta_decision and meta_decision.get("injection_text"):
                    enrichment["meta_policy_advice"] = meta_decision
                    if self._pevr_log:
                        self._pevr_log.log_custom(
                            "meta_policy_injection",
                            action_type=meta_decision.get("action_type"),
                            confidence=meta_decision.get("confidence"),
                            strategy_type=meta_decision.get("strategy_type"),
                        )
            except Exception as e:
                logger.warning("[PERV Enrichment] Meta policy injection failed: %s", e)

        # --- e) TCA (Task Complexity Analyzer) Injection ---
        if getattr(settings, "enable_tca", False):
            try:
                import asyncio
                from app.core.meta_policy.tca_helpers import get_tca_decision
                from app.core.meta_policy.capability_map import CapabilityMap

                cap_map = CapabilityMap.from_core_tools()
                tca_decision = await asyncio.to_thread(
                    lambda: get_tca_decision(task, cap_map=cap_map)
                )
                if tca_decision and tca_decision.injection_text:
                    enrichment["tca_decision"] = tca_decision.model_dump()
                    # 简单任务 → 标记可跳过 planner
                    if not tca_decision.should_decompose and tca_decision.confidence > 0.7:
                        enrichment["tca_skip_planner"] = True
                    if self._pevr_log:
                        self._pevr_log.log_custom(
                            "tca_injection",
                            decompose=tca_decision.should_decompose,
                            complexity=tca_decision.complexity,
                            subtasks=tca_decision.suggested_subtask_count,
                        )
            except Exception as e:
                logger.debug("[PERV Enrichment] TCA injection failed: %s", e)

        return enrichment

    async def _run_graph(
        self, initial_state: Dict[str, Any],
        cancel_event: Optional["asyncio.Event"] = None,
        run_id: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Run the compiled graph and yield SSE events.

        Uses ``astream()`` without ``stream_mode`` for compatibility with
        langgraph 0.0.20.  Each yielded chunk is a ``{node_name: state}``
        dict.  Falls back to ``ainvoke()`` if streaming is unsupported.
        """
        pevr_log = initial_state.get("_pevr_log")

        try:
            # Primary path: streaming via astream()
            async for chunk in self._graph.astream(initial_state):
                if not isinstance(chunk, dict):
                    continue
                for node_name, state_update in chunk.items():
                    if node_name == "__end__":
                        continue

                    # === Watchdog 取消检查 ===
                    if cancel_event and cancel_event.is_set():
                        logger.info(f"[Watchdog] PERV run 在节点 '{node_name}' 被取消")
                        yield {
                            "type": "cancelled",
                            "reason": "cancelled_by_user",
                            "node": node_name,
                        }
                        return

                    logger.debug(
                        "[PEVR Orchestrator] Node '%s' completed, keys=%s",
                        node_name,
                        list(state_update.keys()) if isinstance(state_update, dict) else "?",
                    )
                    async for event in self._process_node_output(
                        node_name, state_update, pevr_log
                    ):
                        yield event

                    # === Watchdog 心跳 + 进度 ===
                    if run_id:
                        from app.core.watchdog import get_registry, ProgressTracker
                        _wd_reg = get_registry()
                        _wd_reg.heartbeat(run_id)
                        if self._wd_tracker is None:
                            self._wd_tracker = ProgressTracker()
                        self._wd_tracker.record_action({
                            "type": "node",
                            "name": node_name,
                        })
                        self._wd_tracker.record_state({
                            "node": node_name,
                            "keys": list(state_update.keys()) if isinstance(state_update, dict) else [],
                        })
                        _wd_reg.update_progress(run_id, self._wd_tracker.snapshot())
                        if self._wd_tracker.is_state_stuck():
                            logger.warning(f"[Watchdog] PERV 状态卡死，节点 '{node_name}'")
                            yield {"type": "cancelled", "reason": "state_stuck", "node": node_name}
                            return
                        if self._wd_tracker.is_action_repeating():
                            logger.warning(f"[Watchdog] PERV 动作重复，节点 '{node_name}'")
                            yield {"type": "cancelled", "reason": "action_repeating", "node": node_name}
                            return
        except TypeError as te:
            # Fallback for older langgraph that may not support astream
            logger.warning(
                "[PEVR Orchestrator] astream unavailable (%s), falling back to ainvoke",
                te,
            )
            result = await self._graph.ainvoke(initial_state)
            async for event in self._process_result(result, pevr_log):
                yield event

    async def _process_node_output(
        self,
        node_name: str,
        state_update: Dict[str, Any],
        pevr_log: Optional[PEVRLogger] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Convert a single node's state update to SSE events.

        Args:
            node_name: The graph node that produced this update.
            state_update: The partial state returned by the node.
            pevr_log: Optional PEVRLogger for lifecycle tracking.

        Yields:
            SSE event dictionaries.
        """
        if node_name == "planner":
            plan = state_update.get("plan", [])
            self._final_plan = plan
            yield {"type": "pevr_planning", "plan": plan}
            yield {"type": "thinking_start"}

        elif node_name == "executor":
            observations = state_update.get("observations", [])

            # Emit layer-start event if DAG parallel layers are available
            execution_layers = state_update.get("execution_layers")
            if execution_layers:
                yield {
                    "type": "pevr_layer_start",
                    "layers": execution_layers,
                    "total_steps": len(observations),
                }

            # Emit per-step completion events for parallel progress tracking
            for obs in observations:
                yield {
                    "type": "pevr_step_complete",
                    "step_id": obs.get("step_id", "?"),
                    "status": obs.get("status", "unknown"),
                    "tool": obs.get("tool", ""),
                }

            # Collect generated_images from all observations
            all_gen_images = []
            for obs in observations:
                gi = obs.get("generated_images")
                if gi:
                    all_gen_images.extend(gi)

            exec_complete_event = {
                "type": "pevr_execution_complete",
                "steps_completed": len(observations),
                "parallel": len(observations) > 1,
            }
            if all_gen_images:
                exec_complete_event["generated_images"] = all_gen_images
            yield exec_complete_event

            # Collect observations for post-execution learning
            self._final_observations.extend(observations)

        elif node_name == "summarizer":
            summaries = state_update.get("summarized_observations")
            yield {
                "type": "perv_summarized",
                "summary_count": len(summaries) if summaries else 0,
            }

        elif node_name == "skill_policy":
            report = state_update.get("skill_policy_report")
            if report and report.get("policy_applied"):
                yield {
                    "type": "perv_skill_policy",
                    "matched": len(report.get("matched_skills", [])),
                    "compiled": len(report.get("compiled_plan") or []),
                }

        elif node_name == "verifier":
            report = state_update.get("verifier_report")
            if report:
                yield {"type": "pevr_verification", "report": report}

        elif node_name == "replanner":
            plan = state_update.get("plan", [])
            retry_count = state_update.get("retry_count", 0)
            yield {"type": "pevr_replan", "retry_count": retry_count}

        if node_name == "finalize":
            logger.info(
                "[PEVR Orchestrator] Finalize state_update type=%s value=%s",
                type(state_update).__name__,
                str(state_update)[:500] if isinstance(state_update, (dict, str)) else state_update,
            )
            logger.info(
                "[PEVR Orchestrator] Finalize node output keys=%s, has_final_answer=%s",
                list(state_update.keys()) if isinstance(state_update, dict) else "?",
                "final_answer" in state_update if isinstance(state_update, dict) else False,
            )
            final_answer = state_update.get("final_answer")
            if final_answer:
                # [IMAGE_UNIFY] Append images from ALL loops, not just current
                all_images = []
                for obs in self._final_observations:
                    gi = obs.get("generated_images")
                    if gi:
                        all_images.extend(gi)
                # Also include images already appended by finalizer (current loop)
                # Dedup by media_id
                seen = set()
                unique = []
                for img in all_images:
                    mid = img.get("media_id")
                    if mid and mid not in seen:
                        seen.add(mid)
                        unique.append(img)
                if unique:
                    from app.core.streaming.image_embedder import build_image_markdown
                    # Avoid double-appending if finalizer already added some
                    if not any(img.get("api_url", "") in final_answer for img in unique):
                        final_answer += build_image_markdown(unique)
                self._final_answer = final_answer
                yield {"type": "content_delta", "content": final_answer}
            else:
                logger.warning(
                    "[PEVR Orchestrator] Finalize node has no final_answer! state_update=%s",
                    str(state_update)[:500] if isinstance(state_update, dict) else state_update,
                )

    # ------------------------------------------------------------------
    # Post-execution learning (Phase 3)
    # ------------------------------------------------------------------

    def _extract_tool_calls_from_observations(
        self, observations: list
    ) -> list[dict]:
        """Convert PERV observations to tool_calls format for PatternLearner.

        PatternLearner expects: [{name, success, ...}]
        PERV observations have: {step_id, tool, status, result, ...}

        Args:
            observations: List of observation dicts from executor node.

        Returns:
            List of tool call dicts compatible with PatternLearner.
        """
        tool_calls = []
        for obs in observations:
            if not isinstance(obs, dict):
                continue
            tool_calls.append({
                "name": obs.get("tool", "unknown"),
                "success": obs.get("status") == "success",
                "result": str(obs.get("result", ""))[:500],
                "step_id": obs.get("step_id", ""),
                "error": None if obs.get("status") == "success" else str(obs.get("result", ""))[:200],
            })
        return tool_calls

    async def _post_execution_learning(
        self,
        task: str,
        final_answer: str,
        observations: list,
        plan: list,
        execution_metrics: dict,
    ) -> None:
        """Post-execution learning: reflection + reward + pattern extraction + RL training.

        Runs as a fire-and-forget asyncio task after the PERV graph completes.
        Never raises -- all errors are caught and logged.

        Args:
            task: The original user task/query.
            final_answer: The final answer produced by the PERV pipeline.
            observations: Collected observations from executor nodes.
            plan: The execution plan used.
            execution_metrics: Dict with metrics like total_duration.
        """
        from app.config import get_settings
        settings = get_settings()

        if not getattr(settings, "perv_enable_post_learning", False):
            return

        try:
            # Build tool_calls format (compatible with PatternLearner)
            tool_calls = self._extract_tool_calls_from_observations(observations)

            # Run full PatternLearner learning cycle
            from app.memory.auto_learning.reflection.learner import get_pattern_learner
            learner = get_pattern_learner()
            learning_result = await learner.learn_from_execution(
                session_id=self.session_id or "perv_unknown",
                user_query=task,
                agent_output=final_answer,
                tool_calls=tool_calls,
                execution_time=execution_metrics.get("total_duration", 0),
            )

            # Log learning metrics to PEVRLogger
            if learning_result and self._pevr_log:
                result_data = {}
                if hasattr(learning_result, "pattern_extracted"):
                    result_data["pattern_extracted"] = learning_result.pattern_extracted
                if hasattr(learning_result, "pattern_id"):
                    result_data["pattern_id"] = learning_result.pattern_id
                if hasattr(learning_result, "reward") and learning_result.reward is not None:
                    result_data["reward"] = getattr(learning_result.reward, "total_reward", None)
                if hasattr(learning_result, "training_triggered"):
                    result_data["training_triggered"] = learning_result.training_triggered

                self._pevr_log.log_custom("learning_result", data=result_data)

            logger.info(
                "[PEVR] Post-execution learning completed: pattern=%s",
                bool(learning_result),
            )

        except Exception as e:
            logger.warning("[PEVR] Post-execution learning failed: %s", e)

        # TCA 数据记录
        if getattr(settings, "enable_tca", False):
            try:
                from app.core.meta_policy.tca_helpers import record_tca_episode
                record_tca_episode(
                    query=task,
                    tool_calls=tool_calls,
                    plan_steps=len(plan) if isinstance(plan, list) else 0,
                    task_completed=True,
                )
            except Exception as e:
                logger.debug("[PEVR] TCA recording failed: %s", e)

        # Meta Policy 数据记录
        if getattr(settings, "enable_meta_policy", False):
            try:
                from app.core.meta_policy.meta_policy_helpers import record_meta_policy_episode
                record_meta_policy_episode(
                    query=task,
                    tool_calls=tool_calls,
                    plan_steps=len(plan) if isinstance(plan, list) else 0,
                    task_completed=True,
                )
            except Exception as e:
                logger.debug("[PEVR] MetaPolicy recording failed: %s", e)

    async def _process_result(
        self,
        result: Dict[str, Any],
        pevr_log: Optional[PEVRLogger] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Process the full result from a non-streaming ``ainvoke`` call.

        Emits a simplified event sequence covering the major lifecycle
        milestones.

        Args:
            result: The final state after graph execution.
            pevr_log: Optional PEVRLogger for lifecycle tracking.

        Yields:
            SSE event dictionaries.
        """
        plan = result.get("plan", [])
        if plan:
            yield {"type": "pevr_planning", "plan": plan}

        report = result.get("verifier_report")
        if report:
            yield {"type": "pevr_verification", "report": report}

        final = result.get("final_answer")
        if final:
            yield {"type": "content_delta", "content": final}


# ── 单例工厂 ─────────────────────────────────────────────────

_orchestrator_instance: Optional[PlannerOrchestrator] = None
_orchestrator_agent_id: Optional[int] = None


def get_orchestrator(
    agent_manager=None,
    session_id: str = "",
    max_retries: int = 3,
    max_llm_calls: int = 15,
) -> PlannerOrchestrator:
    """获取或复用 PlannerOrchestrator 单例。

    按 agent_manager id 判断是否需要重建实例。
    复用时仅重置 session_id 和收集状态。

    Args:
        agent_manager: Agent 管理器实例。
        session_id: 当前会话 ID。
        max_retries: 最大重试次数。
        max_llm_calls: 最大 LLM 调用次数。

    Returns:
        PlannerOrchestrator 实例。
    """
    global _orchestrator_instance, _orchestrator_agent_id
    if _orchestrator_instance is None or _orchestrator_agent_id != id(agent_manager):
        _orchestrator_instance = PlannerOrchestrator(
            agent_manager=agent_manager,
            max_retries=max_retries,
            max_llm_calls=max_llm_calls,
            session_id=session_id,
        )
        _orchestrator_agent_id = id(agent_manager)
    else:
        _orchestrator_instance.session_id = session_id
        _orchestrator_instance._final_observations = []
        _orchestrator_instance._final_plan = []
        _orchestrator_instance._final_answer = None
    return _orchestrator_instance
