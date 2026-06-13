"""
TaskGraph 轨迹日志系统 — 结构化 DAG 执行记录。

以 task 为中心记录完整生命周期:
  scheduling -> execution -> verification -> result

支持双输出:
  1. 实时文件日志 (通过现有 logger)
  2. 结构化 JSON (执行完成后持久化)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 基础 Record
# ---------------------------------------------------------------------------


@dataclass
class ToolCallTrace:
    """单次工具调用的轨迹记录。"""

    tool_name: str = ""
    args: Dict[str, Any] = field(default_factory=dict)
    output_preview: str = ""
    success: bool = True
    duration_ms: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "args": self.args,
            "output_preview": self.output_preview[:500] if self.output_preview else "",
            "success": self.success,
            "duration_ms": round(self.duration_ms, 1),
            "error": self.error,
        }


@dataclass
class LLMCallRecord:
    """单次 LLM 调用的轨迹记录。"""

    caller: str = ""
    prompt_preview: str = ""
    response_preview: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    duration_ms: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "caller": self.caller,
            "prompt_preview": self.prompt_preview[:300] if self.prompt_preview else "",
            "response_preview": self.response_preview[:300] if self.response_preview else "",
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "duration_ms": round(self.duration_ms, 1),
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Graph 级别 Record
# ---------------------------------------------------------------------------


@dataclass
class GraphBuiltRecord:
    """TaskGraph DAG 生成记录。"""

    task_count: int = 0
    task_summaries: List[Dict[str, Any]] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    duration_ms: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_count": self.task_count,
            "task_summaries": self.task_summaries,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "duration_ms": round(self.duration_ms, 1),
            "error": self.error,
        }


@dataclass
class SkillRouteRecord:
    """Skill 匹配路由记录。"""

    candidates_scanned: int = 0
    matched_skill: Optional[str] = None
    match_score: float = 0.0
    llm_gate_called: bool = False
    skill_executed: bool = False
    skill_success: bool = False
    skill_steps: int = 0
    skill_errors: List[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidates_scanned": self.candidates_scanned,
            "matched_skill": self.matched_skill,
            "match_score": round(self.match_score, 3),
            "llm_gate_called": self.llm_gate_called,
            "skill_executed": self.skill_executed,
            "skill_success": self.skill_success,
            "skill_steps": self.skill_steps,
            "skill_errors": self.skill_errors[:3],
            "duration_ms": round(self.duration_ms, 1),
        }


# ---------------------------------------------------------------------------
# Task 级别 Record
# ---------------------------------------------------------------------------


@dataclass
class ScheduleRecord:
    """task 调度记录。"""

    score: float = 0.0
    batch_size: int = 0
    scheduled_at_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 3),
            "batch_size": self.batch_size,
            "scheduled_at_ms": round(self.scheduled_at_ms, 1),
        }


@dataclass
class ExecutionRecord:
    """task 执行记录。"""

    mode: str = "direct"
    tool_calls: List[ToolCallTrace] = field(default_factory=list)
    success: bool = False
    duration_ms: float = 0.0
    tokens_used: int = 0
    errors: List[str] = field(default_factory=list)
    wallclock_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "success": self.success,
            "duration_ms": round(self.duration_ms, 1),
            "tokens_used": self.tokens_used,
            "errors": self.errors[:3],
            "wallclock_seconds": round(self.wallclock_seconds, 3),
        }


@dataclass
class VerificationRecord:
    """task 验证记录。"""

    rule_passed: bool = False
    code_passed: bool = False
    llm_called: bool = False
    llm_passed: bool = False
    confidence: float = 0.0
    failed_reasons: List[str] = field(default_factory=list)
    patch_suggestions: List[str] = field(default_factory=list)
    check_results_count: int = 0
    verification_layer: str = ""
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_passed": self.rule_passed,
            "code_passed": self.code_passed,
            "llm_called": self.llm_called,
            "llm_passed": self.llm_passed,
            "confidence": round(self.confidence, 2),
            "failed_reasons": self.failed_reasons[:5],
            "patch_suggestions": self.patch_suggestions[:3],
            "check_results_count": self.check_results_count,
            "verification_layer": self.verification_layer,
            "duration_ms": round(self.duration_ms, 1),
        }


@dataclass
class PatchTraceRecord:
    """单次 patch 尝试记录。"""

    attempt: int = 0
    patch_type: str = ""
    suggestions_applied: List[str] = field(default_factory=list)
    previous_error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attempt": self.attempt,
            "patch_type": self.patch_type,
            "suggestions_applied": self.suggestions_applied[:3],
            "previous_error": self.previous_error[:200] if self.previous_error else "",
        }


@dataclass
class TaskTrajectoryRecord:
    """单个 task 的完整生命周期轨迹。"""

    task_id: str = ""
    title: str = ""
    execution_mode: str = ""
    schedule: Optional[ScheduleRecord] = None
    execution: Optional[ExecutionRecord] = None
    verification: Optional[VerificationRecord] = None
    patch_history: List[PatchTraceRecord] = field(default_factory=list)
    final_status: str = ""
    attempt_count: int = 0
    micro_tot_replans: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "execution_mode": self.execution_mode,
            "schedule": self.schedule.to_dict() if self.schedule else None,
            "execution": self.execution.to_dict() if self.execution else None,
            "verification": self.verification.to_dict() if self.verification else None,
            "patch_history": [p.to_dict() for p in self.patch_history],
            "final_status": self.final_status,
            "attempt_count": self.attempt_count,
            "micro_tot_replans": self.micro_tot_replans,
        }


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------


@dataclass
class TrajectorySummary:
    """执行汇总统计。"""

    total_tasks: int = 0
    done_count: int = 0
    failed_count: int = 0
    aborted_count: int = 0
    total_tool_calls: int = 0
    total_llm_calls: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_tasks": self.total_tasks,
            "done_count": self.done_count,
            "failed_count": self.failed_count,
            "aborted_count": self.aborted_count,
            "total_tool_calls": self.total_tool_calls,
            "total_llm_calls": self.total_llm_calls,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_duration_ms": round(self.total_duration_ms, 1),
        }


# ---------------------------------------------------------------------------
# 顶层轨迹类
# ---------------------------------------------------------------------------


class TaskGraphTrajectory:
    """TaskGraph 执行轨迹 — 记录 DAG 完整生命周期。

    使用方式:
        trajectory = TaskGraphTrajectory(session_id=..., run_id=...)
        trajectory.set_user_query(query)
        # ... 在各 node 中调用 log_xxx() ...
        trajectory.finish()
        trajectory.save()
    """

    def __init__(self, session_id: str = "", run_id: str = ""):
        self.session_id = session_id
        self.run_id = run_id
        self.user_query: str = ""
        self.start_time: float = 0.0
        self.end_time: Optional[float] = None

        # Graph 级别记录
        self.graph_built: Optional[GraphBuiltRecord] = None
        self.skill_route: Optional[SkillRouteRecord] = None

        # 每个 task 的轨迹
        self.task_records: Dict[str, TaskTrajectoryRecord] = {}

        # 所有 LLM 调用
        self.llm_calls: List[LLMCallRecord] = []

        # 汇总
        self.summary: Optional[TrajectorySummary] = None

    # --- 生命周期 ---

    def start(self) -> None:
        """开始记录。"""
        self.start_time = time.time()

    def finish(self) -> None:
        """结束记录，生成汇总。"""
        self.end_time = time.time()
        self.summary = self._build_summary()

    # --- Graph 级别日志 ---

    def set_user_query(self, query: str) -> None:
        """记录用户查询。"""
        self.user_query = query

    def log_graph_built(
        self,
        task_count: int,
        task_summaries: List[Dict[str, Any]],
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        duration_ms: float = 0.0,
        error: Optional[str] = None,
    ) -> None:
        """记录 TaskGraph DAG 生成完成。"""
        self.graph_built = GraphBuiltRecord(
            task_count=task_count,
            task_summaries=task_summaries,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
            error=error,
        )
        logger.info(
            "[Trajectory] graph_built: %d tasks, %d tokens, %.0fms",
            task_count, total_tokens, duration_ms,
        )

    def log_skill_route(
        self,
        candidates_scanned: int = 0,
        matched_skill: Optional[str] = None,
        match_score: float = 0.0,
        llm_gate_called: bool = False,
    ) -> None:
        """记录 Skill 匹配路由。"""
        self.skill_route = SkillRouteRecord(
            candidates_scanned=candidates_scanned,
            matched_skill=matched_skill,
            match_score=match_score,
            llm_gate_called=llm_gate_called,
        )
        logger.info(
            "[Trajectory] skill_route: scanned=%d matched=%s score=%.2f",
            candidates_scanned, matched_skill, match_score,
        )

    def log_skill_execution(
        self,
        executed: bool = False,
        success: bool = False,
        steps: int = 0,
        errors: Optional[List[str]] = None,
        duration_ms: float = 0.0,
    ) -> None:
        """补充记录 Skill 执行结果。"""
        if self.skill_route is None:
            self.skill_route = SkillRouteRecord()
        self.skill_route.skill_executed = executed
        self.skill_route.skill_success = success
        self.skill_route.skill_steps = steps
        self.skill_route.skill_errors = errors or []
        self.skill_route.duration_ms = duration_ms
        logger.info(
            "[Trajectory] skill_execution: executed=%s success=%s steps=%d",
            executed, success, steps,
        )

    # --- Task 级别日志 ---

    def _ensure_task_record(self, task_id: str, title: str = "", execution_mode: str = "") -> TaskTrajectoryRecord:
        """确保 task_id 对应的记录存在。"""
        if task_id not in self.task_records:
            self.task_records[task_id] = TaskTrajectoryRecord(
                task_id=task_id,
                title=title,
                execution_mode=execution_mode,
            )
        rec = self.task_records[task_id]
        if title:
            rec.title = title
        if execution_mode:
            rec.execution_mode = execution_mode
        return rec

    def log_task_scheduled(
        self,
        task_id: str,
        title: str = "",
        score: float = 0.0,
        batch_size: int = 0,
    ) -> None:
        """记录 task 被调度。"""
        rec = self._ensure_task_record(task_id, title=title)
        rec.schedule = ScheduleRecord(
            score=score,
            batch_size=batch_size,
            scheduled_at_ms=(time.time() - self.start_time) * 1000 if self.start_time else 0,
        )
        logger.info(
            "[Trajectory] task_scheduled: %s (%s) score=%.2f batch=%d",
            task_id, title, score, batch_size,
        )

    def log_task_execution(
        self,
        task_id: str,
        mode: str = "direct",
        tool_calls: Optional[List[ToolCallTrace]] = None,
        success: bool = False,
        duration_ms: float = 0.0,
        tokens_used: int = 0,
        errors: Optional[List[str]] = None,
        wallclock_seconds: float = 0.0,
    ) -> None:
        """记录 task 执行完成。"""
        rec = self._ensure_task_record(task_id)
        rec.execution_mode = mode
        rec.execution = ExecutionRecord(
            mode=mode,
            tool_calls=tool_calls or [],
            success=success,
            duration_ms=duration_ms,
            tokens_used=tokens_used,
            errors=errors or [],
            wallclock_seconds=wallclock_seconds,
        )
        logger.info(
            "[Trajectory] task_executed: %s mode=%s success=%s tools=%d duration=%.0fms",
            task_id, mode, success, len(tool_calls or []), duration_ms,
        )

    def log_task_verification(
        self,
        task_id: str,
        rule_passed: bool = False,
        code_passed: bool = False,
        llm_called: bool = False,
        llm_passed: bool = False,
        confidence: float = 0.0,
        failed_reasons: Optional[List[str]] = None,
        patch_suggestions: Optional[List[str]] = None,
        check_results_count: int = 0,
        verification_layer: str = "",
        duration_ms: float = 0.0,
    ) -> None:
        """记录 task 验证结果。"""
        rec = self._ensure_task_record(task_id)
        rec.verification = VerificationRecord(
            rule_passed=rule_passed,
            code_passed=code_passed,
            llm_called=llm_called,
            llm_passed=llm_passed,
            confidence=confidence,
            failed_reasons=failed_reasons or [],
            patch_suggestions=patch_suggestions or [],
            check_results_count=check_results_count,
            verification_layer=verification_layer,
            duration_ms=duration_ms,
        )
        logger.info(
            "[Trajectory] task_verified: %s passed=%s layer=%s confidence=%.2f",
            task_id, rule_passed and (llm_passed if llm_called else True),
            verification_layer, confidence,
        )

    def log_task_result(
        self,
        task_id: str,
        final_status: str = "",
        attempt_count: int = 0,
        patch_type: str = "",
        patch_suggestions: Optional[List[str]] = None,
        previous_error: str = "",
    ) -> None:
        """记录 task 处理结果 (done/patched/aborted)。"""
        rec = self._ensure_task_record(task_id)
        rec.final_status = final_status
        rec.attempt_count = attempt_count
        if patch_type:
            rec.patch_history.append(PatchTraceRecord(
                attempt=attempt_count,
                patch_type=patch_type,
                suggestions_applied=patch_suggestions or [],
                previous_error=previous_error,
            ))
        logger.info(
            "[Trajectory] task_result: %s -> %s attempt=%d",
            task_id, final_status, attempt_count,
        )

    def log_task_micro_tot(self, task_id: str, replans: int) -> None:
        """记录 MicroToT 触发。"""
        rec = self._ensure_task_record(task_id)
        rec.micro_tot_replans = replans
        logger.info("[Trajectory] task_micro_tot: %s replans=%d", task_id, replans)

    # --- LLM 调用日志 ---

    def log_llm_call(
        self,
        caller: str,
        prompt_preview: str = "",
        response_preview: str = "",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        duration_ms: float = 0.0,
        error: Optional[str] = None,
    ) -> None:
        """记录一次 LLM 调用。"""
        record = LLMCallRecord(
            caller=caller,
            prompt_preview=prompt_preview,
            response_preview=response_preview,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
            error=error,
        )
        self.llm_calls.append(record)
        logger.info(
            "[Trajectory] llm_call: caller=%s tokens=%d duration=%.0fms",
            caller, total_tokens, duration_ms,
        )

    # --- Synthesize 日志 ---

    def log_synthesize(
        self,
        parts_count: int = 0,
        answer_length: int = 0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        duration_ms: float = 0.0,
    ) -> None:
        """记录最终答案组装。"""
        self.log_llm_call(
            caller="synthesize",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            duration_ms=duration_ms,
        )
        logger.info(
            "[Trajectory] synthesize: parts=%d answer_len=%d",
            parts_count, answer_length,
        )

    # --- 汇总 ---

    def _build_summary(self) -> TrajectorySummary:
        """构建执行汇总统计。"""
        done = sum(1 for r in self.task_records.values() if r.final_status == "DONE")
        failed = sum(1 for r in self.task_records.values() if r.final_status == "FAILED")
        aborted = sum(1 for r in self.task_records.values() if r.final_status == "ABORTED")

        total_tool_calls = 0
        for rec in self.task_records.values():
            if rec.execution:
                total_tool_calls += len(rec.execution.tool_calls)

        total_prompt = sum(llm.prompt_tokens for llm in self.llm_calls)
        total_completion = sum(llm.completion_tokens for llm in self.llm_calls)

        duration = ((self.end_time or time.time()) - self.start_time) * 1000 if self.start_time else 0

        return TrajectorySummary(
            total_tasks=len(self.task_records),
            done_count=done,
            failed_count=failed,
            aborted_count=aborted,
            total_tool_calls=total_tool_calls,
            total_llm_calls=len(self.llm_calls),
            total_prompt_tokens=total_prompt,
            total_completion_tokens=total_completion,
            total_duration_ms=duration,
        )

    # --- 序列化 ---

    def get_summary(self) -> Dict[str, Any]:
        """返回 JSON 可序列化的执行摘要。"""
        return {
            "mode": "taskgraph",
            "session_id": self.session_id,
            "run_id": self.run_id,
            "user_query": self.user_query[:200] if self.user_query else "",
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": (self.end_time or 0) - self.start_time if self.start_time else 0,
            "graph_built": self.graph_built.to_dict() if self.graph_built else None,
            "skill_route": self.skill_route.to_dict() if self.skill_route else None,
            "task_records": {tid: rec.to_dict() for tid, rec in self.task_records.items()},
            "llm_calls": [llm.to_dict() for llm in self.llm_calls],
            "summary": self.summary.to_dict() if self.summary else None,
        }

    def save(self) -> Optional[str]:
        """持久化轨迹到 JSON 文件。"""
        from app.core.execution_trace.writer import save_trace

        data = self.get_summary()
        filepath = save_trace(
            data=data,
            mode="taskgraph",
            task_name=self.user_query[:50] if self.user_query else "unknown",
            session_id=self.session_id,
        )
        if filepath:
            logger.info("[Trajectory] Saved to %s", filepath)
        return filepath
