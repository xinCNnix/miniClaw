"""
TaskGraph 数据模型 — 双层架构所有 Pydantic 模型和 TypedDict 定义。

包含:
- TaskStatus 枚举
- TaskBudget / ToolPlanItem / BeamConfig / TaskNode / TaskGraph — 任务图核心
- DoDCheck / CheckResult / VerifierVerdict / PatchRecord — 验证与修补
- ArtifactType / Artifact — 产出物
- MicroCandidate / ReplanResult — MicroToT
- SkillRunResult / BudgetCheck — 执行结果
- TaskGraphState — LangGraph 状态 TypedDict
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field


# ============================================================
# 枚举
# ============================================================


class TaskStatus(str, Enum):
    """任务状态枚举，用于状态机流转"""
    TODO = "TODO"
    READY = "READY"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    ABORTED = "ABORTED"


class ArtifactType(str, Enum):
    """产出物类型"""
    FILE = "FILE"
    CODE_SNIPPET = "CODE"
    DATASET = "DATASET"
    IMAGE = "IMAGE"
    REPORT = "REPORT"
    CACHE = "CACHE"


# ============================================================
# 任务图核心模型
# ============================================================


class TaskBudget(BaseModel):
    """单个任务或全局预算约束"""
    max_tokens: int = 10000
    max_cost_usd: float = 0.5
    max_wallclock_seconds: float = 300
    tokens_used: int = 0
    cost_used: float = 0.0
    wallclock_seconds_used: float = 0.0


class ToolPlanItem(BaseModel):
    """工具计划中的一个步骤"""
    tool_name: str
    args_template: Dict[str, Any] = {}
    fallback: Optional[str] = None
    estimated_cost: float = 0.0


class BeamConfig(BaseModel):
    """Beam search 参数，由 BeamSearchRouter 根据 thinking_mode 填充"""
    beam_width: int = 3
    max_depth: int = 3
    timeout_seconds: float = 240
    max_tool_steps_per_node: int = 5
    branching_factor: int = 3


class TaskNode(BaseModel):
    """TaskGraph 中的一个任务节点"""
    id: str
    title: str
    description: str
    dependencies: List[str] = []
    status: TaskStatus = TaskStatus.TODO
    tool_plan: List[ToolPlanItem] = []
    priority: int = 50
    budget: TaskBudget = TaskBudget()

    # 执行模式
    execution_mode: str = "direct"  # "direct" | "beam_search" | "research"
    beam_config: Optional[BeamConfig] = None
    task_type: str = "generic"  # "research" | "decision" | "coding" | "writing" | "generic"

    # DoD + Verifier
    dod: List[DoDCheck] = []  # type: ignore[name-defined]
    verifier_result: Optional[VerifierVerdict] = None  # type: ignore[name-defined]
    patch_history: List[PatchRecord] = []  # type: ignore[name-defined]
    attempt_count: int = 0
    max_attempts: int = 3

    # 产出物
    artifacts_produced: List[str] = []

    # 执行结果
    tool_results: List[Dict[str, Any]] = []
    error: Optional[str] = None
    metadata: Dict[str, Any] = {}


class TaskGraph(BaseModel):
    """任务有向无环图 (DAG) — TaskGraph 宏观层核心数据结构"""
    nodes: Dict[str, TaskNode] = {}
    root_task_ids: List[str] = []

    def add_task(self, task: TaskNode) -> None:
        """添加任务节点到图中"""
        self.nodes[task.id] = task
        if not task.dependencies:
            if task.id not in self.root_task_ids:
                self.root_task_ids.append(task.id)

    def remove_task(self, task_id: str) -> None:
        """移除任务节点"""
        self.nodes.pop(task_id, None)
        if task_id in self.root_task_ids:
            self.root_task_ids.remove(task_id)

    def refresh_ready(self) -> List[str]:
        """刷新 READY 状态：依赖全部 DONE 的 TODO 任务变为 READY，依赖有 ABORTED 的级联中止"""
        ready_ids = []
        for task in self.nodes.values():
            if task.status != TaskStatus.TODO:
                continue
            if not task.dependencies:
                task.status = TaskStatus.READY
                ready_ids.append(task.id)
                continue
            # 检查是否有 ABORTED/FAILED 依赖 → 级联中止
            has_blocked_dep = any(
                self.nodes.get(dep_id) is not None
                and self.nodes[dep_id].status in (TaskStatus.ABORTED, TaskStatus.FAILED)
                for dep_id in task.dependencies
            )
            if has_blocked_dep:
                task.status = TaskStatus.ABORTED
                task.error = f"依赖任务中止/失败"
                continue
            all_deps_done = all(
                self.nodes.get(dep_id, None) is not None
                and self.nodes[dep_id].status == TaskStatus.DONE
                for dep_id in task.dependencies
            )
            if all_deps_done:
                task.status = TaskStatus.READY
                ready_ids.append(task.id)
        return ready_ids

    def get_ready_tasks(self) -> List[TaskNode]:
        """获取所有 READY 状态的任务"""
        self.refresh_ready()
        return [t for t in self.nodes.values() if t.status == TaskStatus.READY]

    def mark_done(self, task_id: str) -> None:
        """标记任务完成"""
        if task_id in self.nodes:
            self.nodes[task_id].status = TaskStatus.DONE

    def mark_failed(self, task_id: str, error: str, retryable: bool = True) -> None:
        """标记任务失败"""
        if task_id in self.nodes:
            task = self.nodes[task_id]
            task.error = error
            task.status = TaskStatus.FAILED if retryable else TaskStatus.ABORTED

    def apply_patch(self, task_id: str, patch: PatchRecord) -> None:  # type: ignore[name-defined]
        """记录修补历史"""
        if task_id in self.nodes:
            self.nodes[task_id].patch_history.append(patch)

    def replan_subgraph(self, task_id: str, new_tasks: List[TaskNode]) -> None:
        """替换某个任务为一组新任务"""
        old_task = self.nodes.pop(task_id, None)
        for t in new_tasks:
            self.add_task(t)

    def is_done(self) -> bool:
        """所有任务是否都已完成、中止或失败"""
        return all(
            t.status in (TaskStatus.DONE, TaskStatus.ABORTED, TaskStatus.FAILED)
            for t in self.nodes.values()
        )

    def topological_order(self) -> List[str]:
        """返回拓扑排序的任务 ID 列表"""
        visited = set()
        order = []

        def _visit(tid: str) -> None:
            if tid in visited:
                return
            visited.add(tid)
            task = self.nodes.get(tid)
            if task:
                for dep in task.dependencies:
                    _visit(dep)
                order.append(tid)

        for tid in self.nodes:
            _visit(tid)
        return order

    def get_dependents(self, task_id: str) -> List[str]:
        """获取依赖于指定任务的所有任务 ID"""
        return [
            tid for tid, task in self.nodes.items()
            if task_id in task.dependencies
        ]

    def progress_summary(self) -> Dict[str, Any]:
        """返回进度摘要"""
        total = len(self.nodes)
        done = sum(1 for t in self.nodes.values() if t.status == TaskStatus.DONE)
        return {
            "total": total,
            "done": done,
            "running": sum(1 for t in self.nodes.values() if t.status == TaskStatus.RUNNING),
            "failed": sum(1 for t in self.nodes.values() if t.status == TaskStatus.FAILED),
            "aborted": sum(1 for t in self.nodes.values() if t.status == TaskStatus.ABORTED),
            "ready": sum(1 for t in self.nodes.values() if t.status == TaskStatus.READY),
            "todo": sum(1 for t in self.nodes.values() if t.status == TaskStatus.TODO),
            "percent": round(done / total * 100, 1) if total > 0 else 0.0,
        }


# ============================================================
# DoD + Verifier 模型
# ============================================================


class DoDCheck(BaseModel):
    """完成标准检查项"""
    check_type: str  # NON_EMPTY | TOOL_SUCCESS | FILE_EXISTS | OUTPUT_FORMAT | MIN_LENGTH | SOURCE_COUNT | ARTIFACT_EXISTS | CUSTOM
    severity: str    # HARD | SOFT
    description: str
    params: Dict[str, Any] = {}


class CheckResult(BaseModel):
    """单个检查结果"""
    check_type: str
    passed: bool
    evidence: str
    severity: str


class VerifierVerdict(BaseModel):
    """验证裁决结果"""
    passed: bool
    confidence: float
    failed_reasons: List[str]
    patch_suggestions: List[str]
    check_results: List[CheckResult]
    verification_layer: str  # RULE | CODE | LLM


class PatchRecord(BaseModel):
    """修补记录"""
    attempt: int
    patch_type: str       # RETRY_ARGS | FALLBACK_TOOL | REPLAN
    suggestions_applied: List[str]
    previous_error: str
    timestamp: float


# ============================================================
# Artifact 模型
# ============================================================


class Artifact(BaseModel):
    """任务产出物"""
    id: str
    name: str
    artifact_type: ArtifactType
    path: Optional[str] = None
    content_ref: Optional[str] = None
    checksum: str = ""
    size_bytes: int = 0
    mime_type: str = ""
    encoding: str = "utf-8"
    created_by_task: str
    version: int = 1
    created_at: float
    metadata: Dict[str, Any] = {}
    verified: bool = False
    verification_notes: str = ""


# ============================================================
# MicroToT 模型
# ============================================================


class MicroCandidate(BaseModel):
    """MicroToT 候选方案"""
    tool_plan: List[ToolPlanItem]
    description: str
    variant_type: str  # ARG_VARIANT | TOOL_VARIANT | COMBINED
    expected_score: float = 0.0


class ReplanResult(BaseModel):
    """MicroToT 重规划结果"""
    new_tool_plan: List[ToolPlanItem]
    patch_description: str
    confidence: float


# ============================================================
# 执行结果模型
# ============================================================


class SkillRunResult(BaseModel):
    """Skill 执行结果"""
    success: bool
    should_fallback: bool = False
    artifacts: List[Artifact] = []
    tool_results: List[Dict[str, Any]] = []
    error: Optional[str] = None


class BudgetCheck(BaseModel):
    """预算检查结果"""
    task_exceeded: bool
    global_exceeded: bool
    should_abort: bool


# ============================================================
# LangGraph 状态
# ============================================================


class TaskGraphState(TypedDict, total=False):
    """TaskGraph LangGraph 图状态 — 所有节点共享的可变状态"""
    # 输入
    user_query: str
    session_context: dict
    messages: list
    tools: list
    llm: Any
    llm_with_tools: Any
    system_prompt: str
    session_id: str
    run_id: str

    # TaskGraph 核心
    task_graph: TaskGraph
    scheduler: Any  # TaskScheduler 实例，不可序列化
    artifact_store: Any  # ArtifactStore 实例
    checkpoint: Any  # GraphCheckpoint 实例
    budget_enforcer: Any  # BudgetEnforcer 实例
    event_buffer: Any  # TaskGraphEventBuffer 实例

    # 执行控制
    current_task_ids: List[str]
    thinking_mode: str

    # 分类
    task_mode: str
    task_type: str
    domain_profile: Any  # DomainProfile

    # Skill-first
    skill_result: Optional[SkillRunResult]
    skill_tool_plan: Optional[List[Dict]]
    skill_name: Optional[str]

    # Trace
    trajectory: Any  # TaskGraphTrajectory 实例

    # Research 支持
    evidence_store: dict
    coverage_map: dict
    contradictions: list
    raw_sources: list

    # Enrichment
    retrieved_patterns: list
    semantic_history: str
    tca_injection_text: str
    meta_policy_injection_text: str

    # 流式输出
    reasoning_trace: list

    # 最终输出
    final_answer: str

    # 取消控制
    cancel_event: Any
