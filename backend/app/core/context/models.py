"""Data models for the context management system.

包含上下文压缩重设计所需的所有数据模型：
- FileChange: 文件变更记录
- Decision: 决策及理由
- ErrorRecord: 错误及解决方案
- ExtractedState: 规则提取的结构化状态
- SessionState: Session 级压缩状态追踪
- ContextResult: 上下文准备结果
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# 有效的 action 集合，用于 ContextResult 验证
_VALID_ACTIONS = {"normal", "compressed", "checkpoint"}


@dataclass
class FileChange:
    """记录文件变更信息。

    Attributes:
        path: 文件路径
        action: 操作类型 ("read", "write", "create")
        key_findings: 从文件内容中提取的关键发现（函数名、类名等）
    """

    path: str
    action: str  # "read", "write", "create"
    key_findings: str = ""


@dataclass
class Decision:
    """记录决策及理由。

    Attributes:
        decision: 决策内容
        rationale: 决策理由
    """

    decision: str
    rationale: str


@dataclass
class ErrorRecord:
    """记录错误及解决方案。

    Attributes:
        problem: 错误描述
        solution: 解决方案
        resolved: 是否已解决
    """

    problem: str
    solution: str
    resolved: bool = False


@dataclass
class ExtractedState:
    """规则提取的结构化状态。

    由 StateExtractor 从消息流中提取，包含任务列表、文件变更、
    工具执行叙述、决策、错误、用户偏好和意图线索。

    Attributes:
        tasks_completed: 已完成的任务列表
        tasks_in_progress: 进行中的任务列表
        tasks_pending: 待完成的任务列表
        file_changes: 文件变更记录列表
        tool_narrations: 工具执行的一句话叙述列表
        decisions: 已识别的决策列表
        errors: 遇到的错误记录列表
        user_preferences: 用户偏好和约束列表
        user_intent_clues: 用户意图线索列表
    """

    tasks_completed: list[str] = field(default_factory=list)
    tasks_in_progress: list[str] = field(default_factory=list)
    tasks_pending: list[str] = field(default_factory=list)
    file_changes: list[FileChange] = field(default_factory=list)
    tool_narrations: list[str] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    errors: list[ErrorRecord] = field(default_factory=list)
    user_preferences: list[str] = field(default_factory=list)
    user_intent_clues: list[str] = field(default_factory=list)


@dataclass
class SessionState:
    """Session 级压缩状态追踪。

    每个 session 独立追踪压缩次数和上次状态，
    确保 60% 压缩只触发一次。

    Attributes:
        compression_count: 当前 session 的压缩次数（0 或 1）
        last_state: 上次提取的 ExtractedState（用于增量更新）
        last_ratio: 上次计算的 token 占用比例
    """

    compression_count: int = 0
    last_state: ExtractedState | None = None
    last_ratio: float = 0.0


@dataclass
class ContextResult:
    """上下文准备结果。

    由 ContextManager.prepare_context() 返回，包含处理后的消息列表
    和相关元数据。

    Attributes:
        messages: 处理后的消息列表（可能包含状态头）
        action: 执行的动作类型
        checkpoint_id: checkpoint 时的快照 ID
        compression_count: 当前 session 的压缩次数
        budget_used_ratio: token 预算使用比例
        state_header: 压缩时的 ExtractedState（未压缩时为 None）
    """

    messages: list[dict]
    action: Literal["normal", "compressed", "checkpoint"]
    checkpoint_id: str | None = None
    compression_count: int = 0
    budget_used_ratio: float = 0.0
    state_header: ExtractedState | None = None

    def __post_init__(self):
        """验证 action 必须在有效集合内。"""
        if self.action not in _VALID_ACTIONS:
            raise ValueError(f"Invalid action: {self.action!r}. Must be one of {_VALID_ACTIONS}")
