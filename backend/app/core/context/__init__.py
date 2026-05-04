"""Context management system exports.

导出上下文管理系统的所有公共模块：
- ContextResult: 上下文准备结果
- ExtractedState: 规则提取的结构化状态
- SessionState: Session 级压缩状态追踪
- TokenEstimator: token 预算估算
- MessageSelector: 消息选择器
- StateExtractor: 规则扫描状态提取器
- CompressionSummarizer: LLM 压缩摘要生成器
- AgentSnapshot: 快照数据模型
- SnapshotManager: 快照持久化管理
- ContextManager: 上下文管理主入口
"""
from app.core.context.models import ContextResult, ExtractedState, SessionState
from app.core.context.token_estimator import TokenEstimator
from app.core.context.message_selector import MessageSelector
from app.core.context.state_extractor import StateExtractor
from app.core.context.compression_summarizer import CompressionSummarizer
from app.core.context.snapshot import AgentSnapshot, SnapshotManager
from app.core.context.manager import ContextManager, get_context_manager

__all__ = [
    "ContextResult", "ExtractedState", "SessionState",
    "TokenEstimator", "MessageSelector",
    "StateExtractor", "CompressionSummarizer",
    "AgentSnapshot", "SnapshotManager",
    "ContextManager", "get_context_manager",
]
