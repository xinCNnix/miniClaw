"""
Request Router and ToT Orchestrator

Routes requests to simple agent or ToT agent based on task complexity.
"""

import asyncio
import hashlib
import json
import logging
import re
from typing import List, Dict, Any, AsyncIterator, Literal, Optional

from langchain_core.messages import BaseMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool

from app.core.tot.state import ToTState, Thought
# build_tot_graph imported lazily in _stream_tot_reasoning_inner() to avoid circular import
# (graph_builder → synthesis_node → research.prompts → research.__init__ → research_agent → router)
from app.core.agent import AgentManager

logger = logging.getLogger(__name__)


def _clean_base64_from_text(text: str) -> str:
    """清理 LLM 回答中自行嵌入的 base64 图片数据。"""
    if "data:image/" not in text and not re.search(r'[A-Za-z0-9+/=]{2000,}', text):
        return text
    text = re.sub(
        r'!\[[^\]]*\]\(data:image/[^)]{100,}\)',
        '[图片已在上方显示]',
        text,
    )
    text = re.sub(
        r'(?:[A-Za-z0-9+/]{4}){500,}={0,2}',
        '[base64 数据已移除]',
        text,
    )
    return text


def get_settings_lazy():
    """Lazy import of get_settings to avoid circular imports at module level."""
    from app.config import get_settings
    return get_settings()


class TaskComplexityClassifier:
    """
    Classify incoming tasks by complexity to determine routing.

    Simple tasks go directly to the agent (fast).
    Complex tasks use ToT reasoning (thorough).
    """

    COMPLEXITY_KEYWORDS = {
        "high": [
            "deep research",
            "comprehensive analysis",
            "multi-step",
            "detailed investigation",
            "thorough review",
            "in-depth study"
        ],
        "medium": [
            "analyze",
            "compare",
            "evaluate",
            "explain",
            "investigate",
            "summarize"
        ],
        "low": [
            "simple",
            "quick",
            "basic",
            "brief",
            "what is",
            "how to"
        ]
    }

    RESEARCH_KEYWORDS = [
        # 中文
        "深入研究", "综述", "论文", "调研", "文献综述", "系统性综述",
        "深度分析", "研究报告", "学术论文", "科研", "文献回顾",
        # 英文
        "deep research", "survey", "paper", "literature review",
        "systematic review", "research report", "academic paper",
        "comprehensive study", "in-depth analysis",
    ]

    def __init__(self, config: Dict[str, Any] | None = None):
        """
        Initialize classifier with optional config.

        Args:
            config: Configuration dict with thresholds
        """
        self.config = config or {}
        self.query_length_threshold = self.config.get("query_length_threshold", 200)
        self.multi_question_threshold = self.config.get("multi_question_threshold", 2)

    def classify(
        self,
        query: str,
        session_context: Dict[str, Any] | None = None
    ) -> Literal["simple", "complex"]:
        """
        Classify task complexity.

        Factors:
        1. Query length and complexity
        2. Presence of complexity keywords
        3. Multiple sub-questions
        4. Session context (follow-up vs new task)

        Args:
            query: User query text
            session_context: Optional session context

        Returns:
            "simple" or "complex"
        """
        query_lower = query.lower()
        session_context = session_context or {}

        # Factor 1: Check for high-complexity keywords
        for keyword in self.COMPLEXITY_KEYWORDS["high"]:
            if keyword in query_lower:
                logger.info(f"Classified as COMPLEX due to keyword: {keyword}")
                return "complex"

        # Factor 2: Check query length
        if len(query) > self.query_length_threshold:
            logger.info(f"Classified as COMPLEX due to length: {len(query)}")
            return "complex"

        # Factor 3: Check for multiple sub-questions
        question_count = query.count("?")
        if question_count >= self.multi_question_threshold:
            logger.info(f"Classified as COMPLEX due to {question_count} questions")
            return "complex"

        # Factor 4: Check for complex structures (lists, numbered items)
        lines = query.split("\n")
        if len(lines) > 3:
            # Check if it looks like a structured request
            numbered_lines = sum(1 for line in lines if line.strip().startswith(("1.", "2.", "3.", "-", "*")))
            if numbered_lines >= 2:
                logger.info("Classified as COMPLEX due to structured format")
                return "complex"

        # Default: simple
        logger.info("Classified as SIMPLE")
        return "simple"

    async def classify_route(self, query: str, llm=None) -> tuple:
        """Classify route for ToT orchestrator.

        Strategy: LLM classification first (accurate, bilingual),
        keyword matching as fallback when LLM unavailable or fails.

        Args:
            query: User query text
            llm: Optional LLM instance for classification

        Returns:
            Tuple of (task_mode, task_type, route_details)
        """
        # Try LLM classification first
        if llm:
            try:
                from app.core.tot.profiles.registry import detect_task_type_llm
                task_type, match_details = await detect_task_type_llm(query, llm)
                task_mode = "research" if task_type == "research" else "standard"
                return (task_mode, task_type, match_details)
            except Exception as e:
                logger.warning(f"LLM classification failed, falling back to keywords: {e}")

        # Fallback: keyword-based routing
        from app.core.tot.profiles.registry import detect_task_type

        # 1. Check research keywords
        query_lower = query.lower()
        for kw in self.RESEARCH_KEYWORDS:
            if kw in query_lower:
                return ("research", "research", {
                    "matched_keyword": kw,
                    "rationale": f"Research keyword detected: {kw}",
                    "method": "keyword_fallback",
                })

        # 2. Keyword-based profile detection
        task_type, match_details = detect_task_type(query)
        match_details["method"] = "keyword_fallback"
        return ("standard", task_type, match_details)


class ToTOrchestrator:
    """
    Main orchestrator for Tree of Thoughts reasoning.

    Routes requests to simple agent or ToT agent based on complexity,
    and manages ToT execution with streaming.
    """

    def __init__(self, agent_manager: AgentManager, max_depth: int = 3, branching_factor: int = 3):
        """
        Initialize ToT Orchestrator.

        Args:
            agent_manager: Existing AgentManager instance
            max_depth: Maximum reasoning depth
            branching_factor: Branching factor for thought generation
        """
        self.agent_manager = agent_manager
        self.classifier = TaskComplexityClassifier()
        self.graph = None  # Lazy-loaded
        self.max_depth = max_depth
        self.branching_factor = branching_factor

    async def process_request(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        enable_tot: bool = False,
        max_depth: int = 3,
        cancel_event: Optional["asyncio.Event"] = None,
        run_id: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Route request to simple agent or ToT agent.

        Args:
            messages: User messages (list of {role, content} dicts)
            system_prompt: System prompt
            enable_tot: Force enable ToT regardless of complexity
            max_depth: Maximum reasoning depth for ToT

        Yields:
            SSE event dicts (same format as existing agent)
        """
        user_query = messages[-1]["content"] if messages else ""
        # Extract conversation history (everything except the last message)
        chat_history = messages[:-1] if len(messages) > 1 else []
        session_context = {"chat_history": chat_history}

        # Classify task complexity
        if enable_tot:
            complexity = "complex"
        else:
            complexity = self.classifier.classify(user_query, session_context)

        logger.info(f"Routing {complexity} task")

        # Route based on complexity
        if complexity == "simple":
            # Use simple agent (existing fast path)
            async for event in self._stream_simple_agent(messages, system_prompt):
                yield event
        else:
            # Use ToT agent
            async for event in self._stream_tot_reasoning(
                user_query,
                messages,
                system_prompt,
                max_depth,
                cancel_event=cancel_event,
                run_id=run_id,
            ):
                yield event

    async def _stream_simple_agent(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream using existing simple agent."""
        async for event in self.agent_manager.astream(messages, system_prompt):
            yield event

    async def _stream_tot_reasoning(
        self,
        query: str,
        messages: List[Dict[str, str]],
        system_prompt: str,
        max_depth: int,
        cancel_event: Optional["asyncio.Event"] = None,
        run_id: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Execute ToT reasoning with streaming."""
        # Extract chat history (all messages except the last)
        chat_history_dicts = messages[:-1] if len(messages) > 1 else []

        # Initialize ToT lifecycle logger
        from app.core.execution_trace.tot_trace import ToTTrace as ToTExecutionLogger
        tot_log = ToTExecutionLogger(
            task_name=query[:100],
            session_id="no-session",
            profile=None,
        )
        tot_log.config = {
            "max_depth": max_depth,
            "branching_factor": self.branching_factor,
        }

        with tot_log:
            async for event in self._stream_tot_reasoning_inner(
                query, messages, chat_history_dicts, system_prompt, max_depth, tot_log,
                cancel_event=cancel_event,
                run_id=run_id,
            ):
                yield event

    async def _stream_tot_reasoning_inner(
        self,
        query: str,
        messages: List[Dict[str, str]],
        chat_history_dicts: List[Dict[str, str]],
        system_prompt: str,
        max_depth: int,
        tot_log,
        cancel_event: Optional["asyncio.Event"] = None,
        run_id: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Inner ToT reasoning with logging. Called by _stream_tot_reasoning."""
        self._wd_tracker = None
        # --- Route classification (LLM first, keywords fallback) ---
        task_mode, task_type, route_details = await self.classifier.classify_route(
            query, llm=self.agent_manager.llm
        )
        logger.info(
            f"Route decision: task_mode={task_mode}, task_type={task_type}, "
            f"route_details={route_details}"
        )

        # --- Profile injection ---
        domain_profile = None
        if task_mode == "standard":
            from app.core.tot.profiles.registry import get_profile
            profile = get_profile(task_type)
            domain_profile = profile.model_dump()

        # === Pre-state enrichment (pattern retrieval + semantic history + policy) ===
        _settings = get_settings_lazy()
        tot_enrichment: Dict[str, Any] = {}

        # a) Pattern Retrieval
        try:
            if getattr(_settings, "perv_enable_pattern_retrieval", False):
                from app.memory.auto_learning.memory import get_pattern_memory
                memory = get_pattern_memory()
                patterns = await asyncio.to_thread(
                    lambda: memory.get_top_patterns(query=query, top_k=3)
                )
                tot_enrichment["retrieved_patterns"] = [
                    {
                        "description": p.get("description", ""),
                        "situation": p.get("situation", ""),
                        "outcome": p.get("outcome", ""),
                        "fix_action": p.get("fix_action", ""),
                    }
                    for p in patterns
                ]
                if tot_log:
                    tot_log.log_custom("pattern_retrieval", count=len(patterns))
        except Exception as e:
            logger.debug(f"[ToT Enrichment] Pattern retrieval failed: {e}")

        # b) Semantic History (unified KG + vector)
        try:
            if getattr(_settings, "perv_enable_semantic_history", False):
                from app.memory.retriever_factory import get_memory_retriever
                retriever = get_memory_retriever()
                memory_result = await retriever.retrieve(query)
                if memory_result.merged_context:
                    tot_enrichment["semantic_history"] = memory_result.merged_context
                    if tot_log:
                        tot_log.log_custom(
                            "semantic_history", kg_source=memory_result.kg_source,
                        )
        except Exception as e:
            logger.debug(f"[ToT Enrichment] Semantic history search failed: {e}")

        # c) TCA enrichment
        tca_decision = None
        try:
            if getattr(_settings, "enable_tca", False):
                from app.core.meta_policy.tca_helpers import get_tca_decision
                from app.core.meta_policy.capability_map import CapabilityMap

                cap_map = CapabilityMap.from_core_tools()
                tca_decision = get_tca_decision(query, cap_map=cap_map)
                if tca_decision and tca_decision.get("injection_text"):
                    logger.info(
                        f"[TCA] ToT injection: should_decompose={tca_decision.get('should_decompose')}, "
                        f"complexity={tca_decision.get('complexity')}"
                    )
        except Exception as e:
            logger.debug(f"[TCA] ToT enrichment injection failed: {e}")

        # d) Meta Policy enrichment
        meta_policy_decision = None
        try:
            if getattr(_settings, "enable_meta_policy", False):
                from app.core.meta_policy.meta_policy_helpers import get_meta_policy_decision
                from app.core.meta_policy.capability_map import CapabilityMap

                cap_map_mp = CapabilityMap.from_core_tools()
                meta_policy_decision = get_meta_policy_decision(query, cap_map=cap_map_mp)
                if meta_policy_decision and meta_policy_decision.get("injection_text"):
                    logger.info(
                        f"[MetaPolicy] ToT injection: action_type={meta_policy_decision.get('action_type')}, "
                        f"tool={meta_policy_decision.get('tool')}, skill={meta_policy_decision.get('skill')}"
                    )
        except Exception as e:
            logger.debug(f"[MetaPolicy] ToT enrichment injection failed: {e}")

        # Update tot_log with route info
        tot_log.config["task_mode"] = task_mode
        tot_log.config["task_type"] = task_type
        tot_log.config["route_details"] = route_details

        # Convert chat history dicts to LangChain BaseMessage objects
        from langchain_core.messages import HumanMessage, AIMessage
        chat_history: List[BaseMessage] = []
        for msg in chat_history_dicts:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                chat_history.append(HumanMessage(content=content))
            elif role == "assistant":
                chat_history.append(AIMessage(content=content))

        # Initialize ToT state
        initial_state: ToTState = {
            "user_query": query,
            "session_context": {"chat_history": chat_history_dicts},
            "messages": chat_history,
            "thoughts": [],
            "current_depth": 0,
            "max_depth": max_depth,
            "branching_factor": self.branching_factor,  # Use orchestrator's branching factor
            "best_path": [],
            "best_score": 0.0,
            "tools": self.agent_manager.tools,
            "llm": self.agent_manager.llm,  # Use base LLM for thought generation
            "llm_with_tools": self.agent_manager.llm_with_tools,  # LLM with tools for actual tool calling
            "system_prompt": system_prompt,
            "research_sources": None,
            "research_stage": None,
            # Task classification (set by router)
            "task_mode": task_mode,
            "task_type": task_type,
            "domain_profile": domain_profile,
            "tot_logger": tot_log,
            "session_id": None,
            # Research fields
            "evidence_store": [],
            "coverage_map": None,
            "contradictions": [],
            "draft": None,
            "raw_sources": [],
            "research_round": 0,
            "citation_chase_rounds": 0,
            "citation_chase_max": 2,
            "token_used": 0,
            "token_budget": 50000,
            "prev_coverage_score": 0.0,
            "writer_min_delta": 0.15,
            # Results
            "final_answer": None,
            "reasoning_trace": [],
            "fallback_to_simple": False,
            # TCA injection (may be None)
            "tca_injection_text": (tca_decision or {}).get("injection_text", ""),
            # Meta Policy injection (may be None)
            "meta_policy_injection_text": (meta_policy_decision or {}).get("injection_text", ""),
            # --- Global Beam Search (Phase 6) ---
            "active_beams": [],
            "beam_scores": [],
            "beam_width": self.branching_factor,  # Global Beam: B = k
            "backtrack_count": 0,
            "regenerate_count": 0,
            "beam_switch_count": 0,
            "backtrack_score_threshold": 5.5,
            "needs_regeneration": [],
            "deferred_image_paths": [],
            "max_tool_steps_per_node": 5,
            "max_time_per_node": 30.0,
            # Enrichment data from pattern retrieval + semantic history
            "retrieved_patterns": tot_enrichment.get("retrieved_patterns", []),
            "semantic_history": tot_enrichment.get("semantic_history", ""),
        }

        # Build LangGraph if not exists (lazy import to avoid circular deps)
        if not self.graph:
            from app.core.tot.graph_builder import build_tot_graph
            self.graph = build_tot_graph()

        try:
            # Stream reasoning start
            from app.core.tot.streaming import ToTEventStreamer
            streamer = ToTEventStreamer()

            yield streamer.create_reasoning_start_event(max_depth, task_mode=task_mode, task_type=task_type)

            # Fix 5: 节点名称 → 状态消息映射
            _node_status_map = {
                "thought_generator": "正在生成候选思路...",
                "thought_evaluator": "正在评估思路质量...",
                "thought_executor": "正在执行工具调用...",
                "termination_checker": "正在检查推理进度...",
                "synthesis": "正在合成最终答案...",
            }
            _sent_nodes: set[str] = set()
            _last_heartbeat = asyncio.get_event_loop().time()

            # Execute graph with streaming (no checkpointer, so no config needed)
            # Add timeout protection
            async with asyncio.timeout(36000):  # 36000 seconds timeout (10 hours)
                # Use astream() to get intermediate states for progress updates
                # LangGraph's astream() yields dicts like {node_name: state}
                final_state = None
                # 旧代码：每次遍历全量 reasoning_trace，导致前端收到重复事件
                # 新代码：维护 streamed_trace_count，只发送新增的 trace 事件
                streamed_trace_count = 0
                last_tree_hash = ""
                async for graph_output in self.graph.astream(initial_state):
                    # Heartbeat: 如果距上次输出超过 15s，发送心跳保持 SSE 连接
                    now = asyncio.get_event_loop().time()
                    if now - _last_heartbeat > 15:
                        _last_heartbeat = now
                        yield {"type": "heartbeat", "message": "ToT reasoning in progress..."}

                    # === Watchdog 取消检查 ===
                    if cancel_event and cancel_event.is_set():
                        logger.info(f"[Watchdog] ToT run 在节点 '{node_name}' 被取消")
                        yield {
                            "type": "cancelled",
                            "reason": "cancelled_by_user",
                            "node": node_name,
                        }
                        return

                    # graph_output is a dict {node_name: state_dict}
                    if isinstance(graph_output, dict):
                        # Get the state from the dict
                        # If it's {node_name: state}, extract the state
                        # If it's already the state, use it directly
                        if len(graph_output) == 1:
                            # Likely {node_name: state} format
                            node_name = list(graph_output.keys())[0]
                            state = graph_output[node_name]
                        else:
                            # Likely the state itself
                            state = graph_output
                    else:
                        state = graph_output

                    final_state = state

                    # 跳过 state 为 None 的情况（节点内部报错可能返回 None）
                    if state is None:
                        logger.warning("[ToT Stream] Skipping None state from node %s", node_name if isinstance(graph_output, dict) and len(graph_output) == 1 else "?")
                        continue

                    # Fix 5: 根据完成的节点发送状态消息（每个节点只发一次）
                    if isinstance(graph_output, dict) and len(graph_output) == 1:
                        if node_name not in _sent_nodes and node_name in _node_status_map:
                            _sent_nodes.add(node_name)
                            yield {
                                "type": "tot_status",
                                "status_message": _node_status_map[node_name],
                                "node": node_name,
                            }

                        # === 微观评估触发（Phase 3.1）===
                        if node_name == "thought_evaluator":
                            try:
                                from app.config import get_settings
                                _s = get_settings()
                                if getattr(_s, "enable_agent_reflection", False):
                                    from app.core.reflection.trigger import get_reflection_trigger
                                    _trigger = get_reflection_trigger()
                                    current_depth = state.get("current_depth", 0)
                                    if _trigger.should_trigger_micro_evaluation(current_depth):
                                        logger.info(
                                            f"[reflection] Micro evaluation triggered at depth={current_depth}"
                                        )
                            except Exception as e:
                                logger.debug(f"[reflection] Micro eval trigger check failed: {e}")

                    # === Watchdog 心跳 + 进度 ===
                    if run_id and node_name:
                        from app.core.watchdog import get_registry, ProgressTracker
                        _wd_reg = get_registry()
                        _wd_reg.heartbeat(run_id)
                        if self._wd_tracker is None:
                            self._wd_tracker = ProgressTracker()
                        self._wd_tracker.record_action({
                            "type": "node",
                            "name": node_name,
                        })
                        state_fingerprint = {
                            "node": node_name,
                            "depth": state.get("current_depth") if isinstance(state, dict) else None,
                        }
                        if isinstance(state, dict) and "thoughts" in state:
                            state_fingerprint["thought_count"] = len(state["thoughts"])
                        self._wd_tracker.record_state(state_fingerprint)
                        _wd_reg.update_progress(run_id, self._wd_tracker.snapshot())
                        if self._wd_tracker.is_state_stuck():
                            logger.warning(f"[Watchdog] ToT 状态卡死，节点 '{node_name}'")
                            yield {"type": "cancelled", "reason": "state_stuck", "node": node_name}
                            return
                        if self._wd_tracker.is_action_repeating():
                            logger.warning(f"[Watchdog] ToT 动作重复，节点 '{node_name}'")
                            yield {"type": "cancelled", "reason": "action_repeating", "node": node_name}
                            return

                    # 增量发送新增的 trace 事件
                    trace = state.get("reasoning_trace", [])
                    new_trace = trace[streamed_trace_count:]
                    if new_trace:
                        for trace_event in new_trace:
                            sse_event = ToTEventStreamer._convert_trace_to_sse(trace_event, state)
                            if sse_event:
                                yield sse_event
                        streamed_trace_count = len(trace)

                    # Also send periodic tree updates (hash-based dedup)
                    if "thoughts" in state and len(state["thoughts"]) > 0:
                        try:
                            all_thoughts = state["thoughts"]
                            # Only hash last 100 thoughts to prevent MemoryError
                            hash_source = all_thoughts[-100:] if len(all_thoughts) > 100 else all_thoughts
                            thoughts_data = [
                                {"id": t.id, "content": t.content, "score": t.evaluation_score,
                                 "status": t.status, "tool_calls": t.tool_calls}
                                for t in hash_source
                            ]
                            # best_path 已经是 List[str]（thought ID），无需再取 .id
                            best_path_ids = list(state.get("best_path", []))
                        except AttributeError as ae:
                            logger.error(
                                "[ToT Stream] Attribute error building tree data: %s | "
                                "thoughts types=%s | best_path types=%s",
                                ae,
                                [type(t).__name__ for t in state.get("thoughts", [])[:5]],
                                [type(t).__name__ for t in state.get("best_path", [])[:5]],
                                exc_info=True,
                            )
                            continue

                        tree_hash = hashlib.md5(
                            json.dumps({
                                "thoughts": thoughts_data,
                                "best_path": best_path_ids,
                            }, sort_keys=True, default=str).encode()
                        ).hexdigest()

                        if tree_hash != last_tree_hash:
                            tree_update = streamer.create_tree_update_event(state["thoughts"])
                            yield tree_update
                            last_tree_hash = tree_hash

            # After graph completes, check if we have a final answer
            final_answer = final_state.get("final_answer", "") if final_state else ""
            # Filter out placeholder set by termination_checker (synthesis_node should replace it)
            if final_answer == "__TERMINATE__":
                final_answer = ""

            # === 反思触发检查 + 实际补正（Phase 3.2 集成）===
            tot_correction = None
            tot_correction_score = None
            try:
                from app.config import get_settings
                _settings = get_settings()
                if getattr(_settings, "enable_agent_reflection", False):
                    from app.core.reflection.helpers import evaluate_and_correct

                    # 从 ToT 状态提取工具调用记录
                    tool_calls = []
                    for thought in (final_state.get("thoughts", []) if final_state else []):
                        if hasattr(thought, "tool_calls") and thought.tool_calls:
                            for tc in thought.tool_calls:
                                tool_calls.append({
                                    "name": tc.get("name", "unknown") if isinstance(tc, dict) else "unknown",
                                    "success": tc.get("status") != "error" if isinstance(tc, dict) and tc.get("status") else True,
                                    "duration": 0.0,
                                })

                    action = await asyncio.wait_for(
                        evaluate_and_correct(
                            user_query=query,
                            agent_output=final_answer or "",
                            tool_calls=tool_calls,
                            execution_time=0.0,
                            execution_mode="tot",
                        ),
                        timeout=60.0,
                    )
                    tot_correction_score = action.quality_score
                    logger.info(
                        f"[reflection] ToT reflection: quality={action.quality_score:.1f}, "
                        f"should_correct={action.should_correct}"
                    )
                    if action.should_correct and action.correction:
                        tot_correction = action.correction
            except asyncio.TimeoutError:
                logger.warning("[reflection] ToT reflection timed out (60s), skipping")
            except Exception as e:
                logger.warning(f"[reflection] ToT reflection failed: {e}")

            if final_state and final_answer:
                logger.info(f"✓ Found final_answer in final_state, yielding content_delta")

                # 如果有补正内容，追加到 final_answer
                if tot_correction:
                    final_answer += f"\n\n**自我修正：**\n{tot_correction}"

                # Clean LLM-embedded base64 data before yielding
                final_answer = _clean_base64_from_text(final_answer)

                yield {
                    "type": "content_delta",
                    "content": final_answer
                }

                # 发送补正事件（供前端特殊显示）
                if tot_correction:
                    yield {
                        "type": "self_correction",
                        "quality_score": tot_correction_score,
                        "correction": tot_correction,
                    }

                # Send completion event
                complete_event = streamer.create_reasoning_complete_event(
                    final_answer,
                    final_state.get("best_path", []),
                    len(final_state.get("thoughts", []))
                )
                yield complete_event
            else:
                logger.warning(f"✗ No final_answer in final_state. Keys: {list(final_state.keys()) if final_state else 'None'}")
                # Fallback: generate simple answer
                # BUG FIX: user_query 应为 query（函数参数名）
                # fallback_answer = f"I've analyzed your query about: {user_query}\n\nBased on my Tree of Thoughts reasoning, I explored {len(final_state.get('thoughts', [])) if final_state else 0} thoughts. The best path scored {final_state.get('best_score', 0) if final_state else 0:.2f}."
                fallback_answer = f"I've analyzed your query about: {query}\n\nBased on my Tree of Thoughts reasoning, I explored {len(final_state.get('thoughts', [])) if final_state else 0} thoughts. The best path scored {final_state.get('best_score', 0) if final_state else 0:.2f}."
                yield {
                    "type": "content_delta",
                    "content": fallback_answer
                }

        except asyncio.TimeoutError:
            logger.error("ToT execution timed out after 36000 seconds")
            yield {
                "type": "error",
                "error": "ToT execution timed out"
            }
        except Exception as e:
            logger.error(f"ToT reasoning error: {e}", exc_info=True)
            yield {
                "type": "error",
                "error": f"Reasoning error: {str(e)}"
            }

        # Final done event（必须先发送，后续 TCA/Meta recording 可能卡住）
        yield {"type": "done"}

        # === Async pattern learning (fire-and-forget, after done) ===
        try:
            _tot_tool_calls = []
            for _thought in (final_state.get("thoughts", []) if final_state else []):
                if hasattr(_thought, "tool_calls") and _thought.tool_calls:
                    for _tc in _thought.tool_calls:
                        _tot_tool_calls.append({
                            "name": _tc.get("name", "unknown") if isinstance(_tc, dict) else "unknown"
                        })
            _tot_output = final_answer if final_answer else ""
            if _tot_output:
                from app.core.reflection.helpers import post_execution_learning
                asyncio.create_task(
                    post_execution_learning(
                        user_query=query,
                        agent_output=_tot_output,
                        tool_calls=_tot_tool_calls,
                        execution_time=0.0,
                        execution_mode="tot",
                    )
                )
        except Exception as _le:
            logger.debug("[Learning] ToT post-learning trigger failed: %s", _le)

        # === Online Distill (fire-and-forget, after done) ===
        try:
            if _tot_output:
                from app.core.online_distill import online_distill_skill
                asyncio.create_task(
                    online_distill_skill(
                        user_query=query,
                        agent_output=_tot_output,
                        tool_calls=_tot_tool_calls,
                        execution_time=0.0,
                        execution_mode="tot",
                    )
                )
        except Exception as _le:
            logger.debug("[OnlineDistill] ToT trigger failed: %s", _le)

        # === TCA post-execution data recording（done 之后，不阻塞前端）===
        try:
            _s = get_settings_lazy()
            if getattr(_s, "enable_tca", False):
                from app.core.meta_policy.tca_helpers import record_tca_episode

                # Extract tool calls from thoughts
                tca_tool_calls = []
                for thought in (final_state.get("thoughts", []) if final_state else []):
                    if hasattr(thought, "tool_calls") and thought.tool_calls:
                        for tc in thought.tool_calls:
                            tca_tool_calls.append({"name": tc.get("name", "unknown") if isinstance(tc, dict) else "unknown"})

                record_tca_episode(
                    query=query,
                    tool_calls=tca_tool_calls,
                    plan_steps=len(final_state.get("thoughts", [])) if final_state else 0,
                    task_completed=bool(final_state and final_state.get("final_answer")),
                )
        except Exception as e:
            logger.debug(f"[TCA] ToT post-execution recording failed: {e}")

        # === Meta Policy post-execution data recording ===
        try:
            _s = get_settings_lazy()
            if getattr(_s, "enable_meta_policy", False):
                from app.core.meta_policy.meta_policy_helpers import record_meta_policy_episode

                mp_tool_calls = []
                for thought in (final_state.get("thoughts", []) if final_state else []):
                    if hasattr(thought, "tool_calls") and thought.tool_calls:
                        for tc in thought.tool_calls:
                            mp_tool_calls.append({"name": tc.get("name", "unknown") if isinstance(tc, dict) else "unknown"})

                record_meta_policy_episode(
                    query=query,
                    tool_calls=mp_tool_calls,
                    plan_steps=len(final_state.get("thoughts", [])) if final_state else 0,
                    task_completed=bool(final_state and final_state.get("final_answer")),
                )
        except Exception as e:
            logger.debug(f"[MetaPolicy] ToT post-execution recording failed: {e}")
