"""
TaskGraph LangGraph 节点函数。

8 个节点:
- skill_route_node: SkillPolicy 匹配
- execute_skill_node: SkillRunner 执行
- build_task_graph_node: LLM 生成 DAG
- schedule_next_node: Scheduler 选 task
- execute_task_node: 执行 task 工具链
- verify_task_node: 三层验证
- handle_result_node: pass/fail/patch/replan
- synthesize_node: 组装最终答案
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict

from app.core.tot.taskgraph.beam_search_router import BeamSearchRouter
from app.core.tot.taskgraph.budget import BudgetEnforcer
from app.core.tot.taskgraph.checkpoint import GraphCheckpoint
from app.core.tot.taskgraph.event_buffer import TaskGraphEventBuffer
from app.core.tot.taskgraph.executor import TaskExecutor
from app.core.tot.taskgraph.graph_builder import TaskGraphBuilder
from app.core.tot.taskgraph.micro_tot import MicroToT
from app.core.tot.taskgraph.models import (
    TaskGraph,
    TaskNode,
    TaskStatus,
    ToolPlanItem,
    SkillRunResult,
)
from app.core.tot.taskgraph.artifact_store import ArtifactStore
from app.core.tot.taskgraph.patch import apply_patch
from app.core.tot.taskgraph.scheduler import TaskScheduler
from app.core.tot.taskgraph.skill_runner import SkillRunner
from app.core.tot.taskgraph.tot_adapter import ToTStateAdapter
from app.core.tot.taskgraph.subgraph_runner import run_tot_subgraph
from app.core.tot.taskgraph.trajectory import (
    TaskGraphTrajectory,
    ToolCallTrace,
)
from app.core.tot.taskgraph.verifier import TaskVerifier

logger = logging.getLogger(__name__)


def _trajectory(state: Dict) -> TaskGraphTrajectory:
    """获取轨迹对象，不存在时返回空壳（防御性）。"""
    return state.get("trajectory") or TaskGraphTrajectory()

_CN_EN_KEYWORDS: Dict[str, list] = {
    "研究": ["research", "study", "investigate"],
    "报告": ["report", "paper", "writing"],
    "论文": ["paper", "arxiv", "academic", "publication"],
    "检索": ["search", "retrieve", "find", "arxiv", "paper", "academic", "lookup"],
    "搜索": ["search", "find", "lookup", "arxiv"],
    "综述": ["survey", "review", "literature"],
    "调研": ["research", "investigation", "survey"],
    "分析": ["analyze", "analysis"],
    "写": ["write", "writing", "generate"],
    "查找": ["search", "find", "lookup", "arxiv"],
    "查找论文": ["arxiv", "semantic scholar", "paper", "literature"],
    "图表": ["chart", "plot", "diagram", "visualization"],
    "代码": ["code", "python", "debug", "refactor"],
    "修复": ["fix", "debug", "repair"],
    "天气": ["weather", "forecast"],
    "搜索论文": ["arxiv", "semantic scholar", "paper", "literature"],
    "检索论文": ["arxiv", "semantic scholar", "paper", "literature", "search"],
    "研究报告": ["research report", "report writer", "arxiv", "paper"],
    "进展": ["progress", "latest", "recent", "advance"],
    "最新": ["latest", "recent", "new"],
}

# 当查询包含这些关键词组合时，表示明确的文献检索意图，强制提升搜索类 skill 的优先级
_RESEARCH_INTENT_KEYWORDS = {"检索", "搜索", "查找", "论文", "paper", "arxiv", "文献", "papers", "文献检索"}


def _expand_chinese_keywords(query: str) -> str:
    """将中文查询中的关键词扩展为英文，用于 skill 匹配。"""
    extensions: list = []
    for cn_key, en_words in _CN_EN_KEYWORDS.items():
        if cn_key in query:
            extensions.extend(en_words)
    return " ".join(extensions)


def _emit(state: Dict, event_type: str, **kwargs) -> None:
    """向 event_buffer 追加事件"""
    buf = state.get("event_buffer")
    if buf:
        buf.append({"type": event_type, **kwargs})
    trace = state.get("reasoning_trace", [])
    trace.append({"type": event_type, **kwargs})
    state["reasoning_trace"] = trace


async def skill_route_node(state: Dict) -> Dict:
    """Skill-first 路由: 检测 query 是否匹配已知 skill"""
    query = state.get("user_query", "")
    llm = state.get("llm")
    traj = _trajectory(state)
    route_start = time.time()
    logger.info("[TG:skill_route] query=%s", query[:100])
    _emit(state, "tg_reasoning_start", query=query)

    try:
        from app.core.skill_policy.engine import run_skill_policy
        from app.core.skill_policy.types import PolicyInput

        skill_candidates = _scan_skill_candidates(state)

        # 预筛无候选或最高分过低，直接跳过 LLM 调用
        if not skill_candidates or skill_candidates[0].get("score", 0) < 0.05:
            state["skill_result"] = None
            _emit(state, "tg_skill_miss")
            traj.log_skill_route(candidates_scanned=len(skill_candidates))
            logger.info("[TG:skill_route] result=skill_miss (no candidates or low score)")
            return state

        best_skill = None
        best_score = 0.0
        best_output = None
        llm_gate_called = False

        for candidate in skill_candidates:
            scan_score = candidate.get("score", 0.0)
            policy_input = PolicyInput(
                user_query=query,
                current_step={"id": "tg_route", "intent": query},
                available_tools=_get_tool_names(state).split(", "),
                candidate_skills=[candidate],
                skill_content=candidate.get("content", ""),
                skill_name=candidate["name"],
                skill_type=candidate.get("type", "instruction"),
                history={},
            )
            llm_gate_called = True
            gate_start = time.time()
            output = await run_skill_policy(policy_input, llm)
            gate_ms = (time.time() - gate_start) * 1000
            # 记录 skill gate LLM 调用
            traj.log_llm_call(
                caller="skill_gate",
                prompt_preview=f"skill={candidate['name']} query={query[:100]}",
                response_preview=str(output.get("action", ""))[:200],
                duration_ms=gate_ms,
            )
            if output.get("action") == "EXECUTE_TOOL_PLAN" and output.get("tool_plan"):
                # 使用 PolicyOutput 中的 MATCH 分数（6 维评分），比 SCAN 关键词重叠更准确
                selected = output.get("selected_skill") or {}
                match_score = selected.get("score", scan_score)
                effective_score = max(match_score, scan_score)
                logger.info(
                    "[TG:skill_route] candidate=%s scan=%.3f match=%.3f effective=%.3f plan_steps=%d",
                    candidate["name"], scan_score, match_score, effective_score,
                    len(output.get("tool_plan", [])),
                )
                if effective_score > best_score:
                    best_score = effective_score
                    best_skill = candidate
                    best_output = output

        if best_output and best_skill:
            state["skill_result"] = SkillRunResult(
                success=True,
                should_fallback=False,
                tool_results=[],
                error=None,
            )
            state["skill_tool_plan"] = best_output["tool_plan"]
            state["skill_name"] = best_skill["name"]
            _emit(state, "tg_skill_matched", skill=best_skill["name"], score=best_score)
            traj.log_skill_route(
                candidates_scanned=len(skill_candidates),
                matched_skill=best_skill["name"],
                match_score=best_score,
                llm_gate_called=llm_gate_called,
            )
            logger.info("[TG:skill_route] MATCHED skill=%s score=%.2f", best_skill["name"], best_score)
        else:
            state["skill_result"] = None
            _emit(state, "tg_skill_miss")
            traj.log_skill_route(
                candidates_scanned=len(skill_candidates),
                llm_gate_called=llm_gate_called,
            )
            logger.info("[TG:skill_route] result=skill_miss (no skill matched)")
    except Exception as e:
        logger.warning("[TG:skill_route] Skill matching failed: %s", e)
        state["skill_result"] = None
        traj.log_skill_route(candidates_scanned=0)

    return state


async def execute_skill_node(state: Dict) -> Dict:
    """执行匹配到的 skill 的 tool_plan"""
    query = state.get("user_query", "")
    traj = _trajectory(state)
    exec_start = time.time()
    logger.info("[TG:execute_skill] query=%s", query[:100])

    skill_result = state.get("skill_result")
    tool_plan = state.get("skill_tool_plan", [])
    tools = state.get("tools", {})

    if not skill_result or not skill_result.success or not tool_plan:
        state["skill_result"] = SkillRunResult(
            success=False,
            should_fallback=True,
            error="No skill matched or no tool_plan",
        )
        traj.log_skill_execution(executed=False)
        logger.info("[TG:execute_skill] skill_result=None, will fallback to build_task_graph")
        return state

    tool_results = []
    errors = []
    tools_dict = _tools_to_dict(tools)

    # 检测工具输出是否为 usage/error/无效文本而非有效数据
    _ERROR_PATTERNS = [
        "usage:", "Usage:", "USAGE:",
        "error: the following arguments are required",
        "Error: Failed to fetch",
        "HTTP 429", "HTTP 403", "rate limit",
        "No results found", "没有找到",
    ]
    # 检测工具输出是否为代码/文档/配置文件（read_file fallback 产生的垃圾）
    _CODE_PATTERNS = [
        ("from ", "import "),       # Python import
        ("class ", "def "),         # Python class/def
        ("def run(", "def main("),  # Python entry point
        ("# ", "## "),              # Markdown headers (SKILL.md 内容)
        ("---\nname:", "---\ndescription:"),  # SKILL.md frontmatter
        ("{\"type\": \"", "\"args\": {"),  # tool_plan JSON 被当作输出
    ]

    def _is_error_output(text: str) -> bool:
        """检测工具输出是否为错误/usage/代码/文档而非有效数据"""
        if not text or len(text) < 20:
            return True
        for pat in _ERROR_PATTERNS:
            if pat in text:
                return True
        # 检测代码/文档模式
        for p1, p2 in _CODE_PATTERNS:
            if p1 in text and p2 in text:
                return True
        return False

    for step in tool_plan:
        tool_name = step.get("tool", "")
        tool_args = step.get("args", {})
        tool = tools_dict.get(tool_name)
        if tool is None:
            errors.append(f"工具不存在: {tool_name}")
            continue
        step_start = time.time()
        try:
            output = await tool.ainvoke(tool_args)
            step_ms = (time.time() - step_start) * 1000
            output_str = str(output)
            if _is_error_output(output_str):
                logger.warning(
                    "[TG:execute_skill] Step produced error/usage output (tool=%s, len=%d): %s",
                    tool_name, len(output_str), output_str[:200],
                )
                tool_results.append({"tool": tool_name, "output": "", "success": False, "error": output_str[:500]})
                errors.append(f"工具 {tool_name} 输出无效: {output_str[:100]}")
            else:
                tool_results.append({"tool": tool_name, "output": output_str, "success": True})
        except Exception as e:
            step_ms = (time.time() - step_start) * 1000
            errors.append(str(e))
            tool_results.append({"tool": tool_name, "output": "", "success": False, "error": str(e)})

    success = len(errors) == 0 and len(tool_results) > 0
    state["skill_result"] = SkillRunResult(
        success=success,
        should_fallback=not success,
        tool_results=tool_results,
        error="; ".join(errors) if errors else None,
    )
    exec_ms = (time.time() - exec_start) * 1000
    traj.log_skill_execution(
        executed=True,
        success=success,
        steps=len(tool_results),
        errors=errors,
        duration_ms=exec_ms,
    )
    _emit(state, "tg_skill_executed", success=success, steps=len(tool_results))
    logger.info("[TG:execute_skill] success=%s steps=%d errors=%s",
                success, len(tool_results), errors[:2] if errors else [])
    return state


async def build_task_graph_node(state: Dict) -> Dict:
    """一次 LLM 调用生成 TaskGraph"""
    llm = state.get("llm")
    query = state.get("user_query", "")
    traj = _trajectory(state)
    context = str(state.get("session_context", {}))

    # 截断上下文，避免超过 LLM API 请求大小限制
    # 只保留最近 3000 字符的会话上下文
    _MAX_CONTEXT_CHARS = 3000
    if len(context) > _MAX_CONTEXT_CHARS:
        context = "...[truncated] " + context[-_MAX_CONTEXT_CHARS:]
        logger.info("[TG:build_task_graph] Context truncated to %d chars", _MAX_CONTEXT_CHARS)

    # 截断 enrichment 文本 — 图构建不需要完整历史
    _MAX_ENRICHMENT_CHARS = 500

    logger.info("[TG:build_task_graph] Building graph for query=%s context_len=%d", query[:100], len(context))

    # 构建 skill_hints: 将已扫描的 skill 候选信息传递给图构建器，
    # 以便 LLM 在 tool_plan 中优先使用 terminal 调用 skill 脚本
    skill_hints = _build_skill_hints(state)

    builder = TaskGraphBuilder(llm=llm)
    build_start = time.time()
    build_error = None
    try:
        graph = await builder.build(
            query=query,
            context=context,
            domain=state.get("domain_profile"),
            tool_list=_get_tool_names(state),
            skill_hints=skill_hints,
            enrichment_texts={},  # 不传 enrichment，避免请求过大
        )
    except Exception as e:
        build_error = str(e)
        logger.error("[TG:build_task_graph] LLM graph build failed: %s", e, exc_info=True)
        graph = TaskGraph()

    build_ms = (time.time() - build_start) * 1000
    state["task_graph"] = graph
    task_summary = [{"id": t.id, "title": t.title, "deps": t.dependencies} for t in graph.nodes.values()]

    # 记录 LLM 调用（graph_builder 内部调用 LLM）
    traj.log_llm_call(
        caller="graph_builder",
        prompt_preview=f"query={query[:100]} tool_list={_get_tool_names(state)[:100]}",
        response_preview=f"{len(graph.nodes)} tasks generated",
        duration_ms=build_ms,
        error=build_error,
    )
    traj.log_graph_built(
        task_count=len(graph.nodes),
        task_summaries=task_summary,
        duration_ms=build_ms,
        error=build_error,
    )

    _emit(state, "tg_graph_built", tasks=task_summary)
    logger.info(
        "[TG:build_task_graph] Graph built: %d tasks — %s",
        len(graph.nodes),
        task_summary,
    )
    return state


async def schedule_next_node(state: Dict) -> Dict:
    """Scheduler 选择下一个（批）task"""
    graph: TaskGraph = state.get("task_graph", TaskGraph())
    traj = _trajectory(state)

    if graph.is_done():
        progress = graph.progress_summary()
        _emit(state, "tg_graph_done", progress=progress)
        state["current_task_ids"] = []
        logger.info("[TG:schedule_next] Graph done: %s", progress)
        return state

    scheduler: TaskScheduler = state.get("scheduler") or TaskScheduler()
    state["scheduler"] = scheduler

    batch = scheduler.pick_ready_batch(graph, max_parallel=4)
    state["current_task_ids"] = [t.id for t in batch]

    if not batch:
        logger.info("[TG:schedule_next] No ready tasks, graph has %d nodes: %s",
                     len(graph.nodes), graph.progress_summary())
        state["current_task_ids"] = []
        return state

    for t in batch:
        t.status = TaskStatus.RUNNING
        _emit(state, "tg_task_running", task_id=t.id, title=t.title)
        traj.log_task_scheduled(
            task_id=t.id,
            title=t.title,
            batch_size=len(batch),
        )

    logger.info(
        "[TG:schedule_next] Scheduled %d tasks: %s",
        len(batch),
        [{"id": t.id, "title": t.title, "mode": t.execution_mode} for t in batch],
    )
    return state


async def execute_task_node(state: Dict) -> Dict:
    """执行当前 batch 的 task（支持 direct/beam_search/research 三种模式）"""
    graph: TaskGraph = state.get("task_graph", TaskGraph())
    task_ids = state.get("current_task_ids", [])
    tools = state.get("tools", {})
    thinking_mode = state.get("thinking_mode", "heuristic")
    traj = _trajectory(state)

    logger.info("[TG:execute_task] Executing %d tasks: %s", len(task_ids), task_ids)

    executor = TaskExecutor(tools=_tools_to_dict(tools), trajectory=traj)
    beam_router = BeamSearchRouter()

    for task_id in task_ids:
        task = graph.nodes.get(task_id)
        if task is None:
            logger.warning("[TG:execute_task] Task %s not found in graph", task_id)
            continue

        # 使用 BeamSearchRouter 决定执行模式
        mode = beam_router.route(task, thinking_mode)
        logger.info("[TG:execute_task] task=%s mode=%s (routed from %s)",
                     task_id, mode, task.execution_mode)

        task_start = time.time()
        if mode == "direct":
            result = await executor.execute_direct(task)
        elif mode in ("beam_search", "research"):
            result = await _run_tot_subgraph(
                state, task, mode=mode, thinking_mode=thinking_mode,
            )
        else:
            result = await executor.execute_direct(task)
        task_ms = (time.time() - task_start) * 1000

        task.tool_results = result.get("tool_results", [])
        task.error = "; ".join(result.get("errors", [])) if not result.get("success") else None

        # 记录工具调用轨迹
        tool_traces = []
        for tr in result.get("tool_results", []):
            tool_traces.append(ToolCallTrace(
                tool_name=tr.get("tool", ""),
                args={},
                output_preview=tr.get("output", "")[:500],
                success=tr.get("success", False),
                error=tr.get("error"),
            ))

        traj.log_task_execution(
            task_id=task_id,
            mode=mode,
            tool_calls=tool_traces,
            success=result.get("success", False),
            duration_ms=task_ms,
            tokens_used=result.get("tokens_used", 0),
            errors=result.get("errors", []),
            wallclock_seconds=result.get("wallclock_seconds", 0),
        )

        budget_enforcer: BudgetEnforcer = state.get("budget_enforcer")
        if budget_enforcer:
            budget_enforcer.check_and_record(task, result)

        logger.info(
            "[TG:execute_task] task=%s success=%s results=%d errors=%s",
            task_id, result.get("success"), len(task.tool_results),
            result.get("errors", [])[:2] if result.get("errors") else [],
        )

    return state


async def verify_task_node(state: Dict) -> Dict:
    """验证执行结果（三层: Rule → Code → LLM）"""
    graph: TaskGraph = state.get("task_graph", TaskGraph())
    task_ids = state.get("current_task_ids", [])
    traj = _trajectory(state)

    store = state.get("artifact_store") or ArtifactStore()
    state["artifact_store"] = store
    verifier = TaskVerifier()
    llm = state.get("llm")

    logger.info("[TG:verify_task] Verifying %d tasks", len(task_ids))

    for task_id in task_ids:
        task = graph.nodes.get(task_id)
        if task is None:
            continue

        verify_start = time.time()

        # Layer 1 + Layer 2: Rule → Code
        verdict = verifier.verify(task, store)

        # 判断 Rule+Code 是否通过
        rule_code_passed = verdict.passed
        llm_called = False
        llm_passed = False

        # Layer 3: LLM judge（仅在 Rule+Code 通过时调用）
        if verdict.passed and llm:
            from app.core.tot.taskgraph.llm_verifier import LLMVerifier
            llm_verifier = LLMVerifier(llm=llm, trajectory=traj)
            llm_verdict = await llm_verifier.verify(task, verdict.check_results)
            llm_called = True
            if llm_verdict:
                verdict = llm_verdict
                llm_passed = verdict.passed

        verify_ms = (time.time() - verify_start) * 1000

        task.verifier_result = verdict

        traj.log_task_verification(
            task_id=task_id,
            rule_passed=rule_code_passed,
            code_passed=rule_code_passed,
            llm_called=llm_called,
            llm_passed=llm_passed,
            confidence=verdict.confidence,
            failed_reasons=verdict.failed_reasons,
            patch_suggestions=verdict.patch_suggestions,
            check_results_count=len(verdict.check_results),
            verification_layer=verdict.verification_layer,
            duration_ms=verify_ms,
        )

        if verdict.passed:
            _emit(state, "tg_task_verified", task_id=task_id, confidence=verdict.confidence)
            logger.info("[TG:verify_task] task=%s PASSED confidence=%.2f", task_id, verdict.confidence)
        else:
            _emit(state, "tg_task_verify_fail", task_id=task_id, reasons=verdict.failed_reasons)
            logger.warning(
                "[TG:verify_task] task=%s FAILED reasons=%s",
                task_id, verdict.failed_reasons,
            )

    return state


async def handle_result_node(state: Dict) -> Dict:
    """处理验证结果: pass → done, fail → patch/replan"""
    graph: TaskGraph = state.get("task_graph", TaskGraph())
    task_ids = state.get("current_task_ids", [])
    traj = _trajectory(state)

    logger.info("[TG:handle_result] Handling %d tasks", len(task_ids))

    for task_id in task_ids:
        task = graph.nodes.get(task_id)
        if task is None:
            continue

        if task.verifier_result and task.verifier_result.passed:
            graph.mark_done(task_id)
            _emit(state, "tg_task_done", task_id=task_id)
            traj.log_task_result(task_id=task_id, final_status="DONE")
            logger.info("[TG:handle_result] task=%s → DONE", task_id)
        else:
            task.attempt_count += 1
            micro_tot_replans = task.metadata.get("micro_tot_replans", 0)
            max_micro_tot = task.metadata.get("max_micro_tot", 2)

            if task.attempt_count >= task.max_attempts:
                if micro_tot_replans < max_micro_tot and MicroToT().should_trigger(task):
                    result = MicroToT().replan_rule(task)
                    task.tool_plan = result.new_tool_plan
                    task.status = TaskStatus.READY
                    task.verifier_result = None
                    task.attempt_count = 0
                    task.metadata["micro_tot_replans"] = micro_tot_replans + 1
                    _emit(state, "tg_micro_tot_start", task_id=task_id)
                    traj.log_task_micro_tot(task_id=task_id, replans=micro_tot_replans + 1)
                    logger.info("[TG:handle_result] task=%s → MicroToT replan (replan=%d/%d)",
                                task_id, micro_tot_replans + 1, max_micro_tot)
                else:
                    graph.mark_failed(task_id, task.error or "超过最大重试", retryable=False)
                    _emit(state, "tg_task_aborted", task_id=task_id)
                    traj.log_task_result(
                        task_id=task_id,
                        final_status="ABORTED",
                        attempt_count=task.attempt_count,
                        previous_error=task.error or "",
                    )
                    logger.warning("[TG:handle_result] task=%s → ABORTED: %s (attempts=%d, micro_tot=%d)",
                                   task_id, task.error, task.attempt_count, micro_tot_replans)
            else:
                if task.verifier_result:
                    apply_patch(task, task.verifier_result, task.attempt_count - 1)
                _emit(state, "tg_task_patched", task_id=task_id, attempt=task.attempt_count)
                traj.log_task_result(
                    task_id=task_id,
                    final_status="PATCHED",
                    attempt_count=task.attempt_count,
                    patch_type=task.patch_history[-1].patch_type if task.patch_history else "unknown",
                    patch_suggestions=task.verifier_result.patch_suggestions if task.verifier_result else [],
                    previous_error=task.error or "",
                )
                task.status = TaskStatus.READY
                logger.info("[TG:handle_result] task=%s → PATCHED (attempt=%d)", task_id, task.attempt_count)

    checkpoint: GraphCheckpoint = state.get("checkpoint")
    if checkpoint:
        session_id = state.get("session_id", "unknown")
        run_id = state.get("run_id", "unknown")
        checkpoint.save(session_id, run_id, graph, {})

    return state


async def synthesize_node(state: Dict) -> Dict:
    """组装最终答案（多步骤时 LLM 打磨）"""
    graph: TaskGraph = state.get("task_graph", TaskGraph())
    traj = _trajectory(state)

    # 处理 skill-first 快速路径
    skill_result = state.get("skill_result")
    if skill_result and skill_result.success and skill_result.tool_results:
        parts = [
            tr["output"] for tr in skill_result.tool_results
            if tr.get("success") and tr.get("output")
        ]
    else:
        parts = []
        for task_id in graph.topological_order():
            task = graph.nodes.get(task_id)
            if task and task.status == TaskStatus.DONE:
                for tr in task.tool_results:
                    if tr.get("success") and tr.get("output"):
                        parts.append(tr["output"])

    raw_text = "\n\n".join(parts) if parts else ""

    if not raw_text:
        # 所有任务均未产出有效结果 — 诚实报告失败
        progress = graph.progress_summary()
        aborted = progress.get("aborted", 0)
        failed = progress.get("failed", 0)
        total = progress.get("total", 0)

        failure_report = (
            f"⚠️ TaskGraph 执行管线未能完成此任务。\n\n"
            f"**执行摘要**: 共 {total} 个任务，{aborted} 个中止，{failed} 个失败，"
            f"无任务成功完成。\n\n"
            f"可能原因：工具调用参数错误、外部 API 不可用、或验证标准过严。\n"
            f"建议：简化查询或重试。"
        )
        state["final_answer"] = failure_report
        buf = state.get("event_buffer")
        if buf:
            buf.mark_completed(failure_report)
        _emit(state, "tg_reasoning_complete", answer_length=len(failure_report))
        traj.log_synthesize(parts_count=len(parts), answer_length=len(failure_report))
        logger.warning(
            "[TG:synthesize] All tasks failed/aborted: %d total, %d aborted, %d failed",
            total, aborted, failed,
        )
        return state

    # LLM 打磨 — 始终调用，清理原始工具输出中的推理噪音
    llm = state.get("llm")
    final_answer = raw_text
    synth_start = time.time()
    synth_prompt_tokens = 0
    synth_completion_tokens = 0

    # 收集未完成任务的上下文信息
    aborted_tasks = [
        t for t in graph.nodes.values()
        if t.status in (TaskStatus.ABORTED, TaskStatus.FAILED)
    ]
    abort_context = ""
    if aborted_tasks:
        abort_context = (
            f"\n\n**注意**: 以下任务未能完成（已中止/失败）: "
            + "、".join(f"「{t.title}」" for t in aborted_tasks)
            + "。请基于已完成的任务结果尽力回答。"
        )

    if llm:
        # 区分 skill-first 快速路径和多任务图路径
        is_skill_path = bool(skill_result and skill_result.success and skill_result.tool_results)
        skill_name = state.get("skill_name", "")
        user_query = state.get("user_query", "")

        if is_skill_path:
            prompt = (
                f"用户的问题: {user_query}\n\n"
                f"以下是工具执行返回的原始数据（来自技能 {skill_name}）。\n"
                "你的任务是：基于这些数据直接回答用户的问题。\n\n"
                "严格要求:\n"
                "1. 提取数据中的关键信息（如论文标题、作者、摘要、引用数等），以结构化方式呈现\n"
                "2. 如果数据是搜索结果，按相关性整理并呈现\n"
                "3. 如果数据是分析结果，总结关键发现\n"
                "4. 绝对不要评论工具执行过程（如脚本是否成功、参数是否正确）\n"
                "5. 绝对不要分析数据是否为'执行失败'——数据就是数据，直接使用\n"
                "6. 直接输出最终答案，不要加前缀说明或过程分析\n\n"
                f"原始数据:\n{'---\n'.join(parts)}"
            )
        else:
            prompt = (
                "你是一个专业助手。以下是一个多步骤任务各步骤的执行结果。\n"
                "请将这些结果整合为一个连贯、完整的最终回答。\n"
                "保留所有关键信息和数据，去除重复，确保逻辑流畅。\n"
                "直接输出整合后的回答，不要加前缀说明。\n"
                f"{abort_context}\n\n"
                f"各步骤结果:\n{'---\n'.join(parts)}"
            )
        try:
            response = await llm.ainvoke([{"role": "user", "content": prompt}])
            final_answer = response.content if hasattr(response, "content") else str(response)
            # 提取 token 用量
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                synth_prompt_tokens = response.usage_metadata.get("prompt_tokens", 0)
                synth_completion_tokens = response.usage_metadata.get("completion_tokens", 0)
            elif hasattr(response, "response_metadata"):
                usage = response.response_metadata.get("token_usage", {})
                synth_prompt_tokens = usage.get("prompt_tokens", 0)
                synth_completion_tokens = usage.get("completion_tokens", 0)
        except Exception as e:
            logger.warning("[TG:synthesize] LLM polish failed: %s, using raw join", e)
            final_answer = raw_text

    synth_ms = (time.time() - synth_start) * 1000
    traj.log_synthesize(
        parts_count=len(parts),
        answer_length=len(final_answer),
        prompt_tokens=synth_prompt_tokens,
        completion_tokens=synth_completion_tokens,
        duration_ms=synth_ms,
    )

    buf = state.get("event_buffer")
    if buf:
        buf.mark_completed(final_answer)

    _emit(state, "tg_reasoning_complete", answer_length=len(final_answer))
    state["final_answer"] = final_answer

    logger.info(
        "[TG:synthesize] Answer assembled: len=%d, parts=%d, graph_progress=%s",
        len(final_answer),
        len(parts),
        graph.progress_summary(),
    )
    return state


async def _run_tot_subgraph(
    state: Dict, task: TaskNode, mode: str, thinking_mode: str,
) -> Dict[str, Any]:
    """运行 ToT 子图（beam_search 或 research）"""
    beam_router = BeamSearchRouter()
    beam_config = beam_router.get_beam_config(thinking_mode)

    adapter = ToTStateAdapter(
        tg_state=state, task=task, mode=mode, beam_config=beam_config,
    )
    tot_state = adapter.build_tot_state()

    try:
        tot_result = await run_tot_subgraph(
            tot_state,
            task_mode="research" if mode == "research" else "standard",
            beam_width=beam_config.beam_width,
            max_depth=beam_config.max_depth,
        )
        # 合并子图 reasoning_trace 到主事件流
        sub_trace = tot_result.get("reasoning_trace", [])
        if sub_trace:
            main_trace = state.get("reasoning_trace", [])
            main_trace.extend(sub_trace)
            state["reasoning_trace"] = main_trace

        return adapter.extract_results(tot_result)
    except Exception as e:
        logger.error("[TG:subgraph] ToT subgraph failed for task=%s: %s", task.id, e, exc_info=True)
        return {
            "success": False,
            "tool_results": [],
            "errors": [f"子图执行失败: {e}"],
            "wallclock_seconds": 0,
        }


def _scan_skill_candidates(state: Dict) -> list:
    """扫描 data/skills/ 下的 SKILL.md 文件，返回候选 skill 列表。

    轻量级预筛: 基于 query 与 skill name/content 的关键词重叠度评分。
    只返回 top-3 候选，避免对过多 skill 调用 LLM。
    当检测到文献检索意图时，强制提升搜索类 skill 的优先级。
    """
    import os
    import glob as glob_mod

    candidates = []
    skills_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "data", "skills")
    query_raw = state.get("user_query", "")
    query = query_raw.lower()
    query_words = set(query.split())
    # 扩展中文关键词到英文，增加 skill 匹配率
    cn_expansion = _expand_chinese_keywords(query)
    if cn_expansion:
        query_words.update(cn_expansion.split())

    # 检测文献检索意图：查询中是否包含搜索/论文相关关键词
    has_research_intent = any(kw in query for kw in _RESEARCH_INTENT_KEYWORDS)

    if not os.path.isdir(skills_dir):
        return candidates

    # 搜索类 skill 名称模式（当检测到研究意图时，这些 skill 会被强制加分）
    _SEARCH_SKILL_PATTERNS = {"arxiv-search", "baidu-search", "web-search", "google-search"}

    for skill_md in glob_mod.glob(os.path.join(skills_dir, "*", "SKILL.md")):
        try:
            with open(skill_md, "r", encoding="utf-8") as f:
                content = f.read()
            skill_name = os.path.basename(os.path.dirname(skill_md))

            # 关键词重叠度评分
            name_words = set(skill_name.replace("-", " ").replace("_", " ").lower().split())
            content_lower = content[:2000].lower()
            content_words = set(content_lower.split())

            overlap = len(query_words & (name_words | content_words))
            score = min(overlap / max(len(query_words), 1), 1.0) if query_words else 0.1

            # 文献检索意图加分：搜索类 skill 在有研究意图时获得大幅加分
            if has_research_intent and skill_name in _SEARCH_SKILL_PATTERNS:
                score = max(score, 0.5) + 0.3  # 保证搜索 skill 至少 0.8 分

            candidates.append({
                "name": skill_name,
                "content": content,
                "score": score,
                "type": "instruction",
            })
        except Exception:
            continue

    candidates.sort(key=lambda c: c["score"], reverse=True)
    logger.info("[TG:skill_scan] query=%s has_research_intent=%s candidates=%s",
                query_raw[:60], has_research_intent,
                [(c["name"], round(c["score"], 3)) for c in candidates[:5]])
    return candidates[:3]


# ------------------------------------------------------------------
# 辅助函数
# ------------------------------------------------------------------


def _get_tool_names(state: Dict) -> str:
    """获取可用工具名称列表"""
    tools = state.get("tools", [])
    if isinstance(tools, list):
        return ", ".join(getattr(t, "name", str(t)) for t in tools)
    if isinstance(tools, dict):
        return ", ".join(tools.keys())
    return ""


def _tools_to_dict(tools: Any) -> Dict[str, Any]:
    """将工具列表/字典统一为 dict"""
    if isinstance(tools, dict):
        return tools
    if isinstance(tools, list):
        return {getattr(t, "name", str(i)): t for i, t in enumerate(tools)}
    return {}


def _build_skill_hints(state: Dict) -> str:
    """构建 skill 提示文本，供 TaskGraphBuilder LLM 参考。

    扫描 data/skills/ 下的 SKILL.md，提取 name、description 和 scripts，
    让图构建器在规划 tool_plan 时使用正确的 terminal 命令调用 skill 脚本。
    """
    import os
    import glob as glob_mod

    skills_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "data", "skills")
    if not os.path.isdir(skills_dir):
        return ""

    hints = []
    for skill_md in glob_mod.glob(os.path.join(skills_dir, "*", "SKILL.md")):
        try:
            with open(skill_md, "r", encoding="utf-8") as f:
                content = f.read(1000)
            skill_name = os.path.basename(os.path.dirname(skill_md))
            skill_dir = os.path.dirname(skill_md)

            # 提取 description
            desc = ""
            if "description:" in content:
                import re
                m = re.search(r'description:\s*["\']?(.+?)["\']?\n', content)
                if m:
                    desc = m.group(1).strip('"').strip("'")

            # 检查是否有 scripts 目录
            scripts_dir = os.path.join(skill_dir, "scripts")
            script_cmds = []
            if os.path.isdir(scripts_dir):
                for script_file in sorted(os.listdir(scripts_dir)):
                    if script_file.endswith(".py") and not script_file.endswith(".bak"):
                        script_cmds.append(
                            f"    terminal: python data/skills/{skill_name}/scripts/{script_file} --query \"<搜索词>\" --max-results 10"
                        )

            if script_cmds:
                hints.append(f"- {skill_name}: {desc}\n" + "\n".join(script_cmds))
            else:
                hints.append(f"- {skill_name}: {desc}")
        except Exception:
            continue

    return "\n".join(hints) if hints else ""
