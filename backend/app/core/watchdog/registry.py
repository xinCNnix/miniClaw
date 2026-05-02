"""Watchdog 运行注册表。

在内存中追踪所有活跃和已完成的 Agent 运行。
替代 spec 中基于 Redis 的 run:{run_id}:* 键结构。
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import time
import uuid
from enum import StrEnum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"
    CANCELLED = "cancelled"
    CANCEL_REQUESTED = "cancel_requested"
    KILLED = "killed"


@dataclasses.dataclass
class RunInfo:
    """单个 Agent 运行的状态追踪。"""

    run_id: str
    session_id: str
    status: RunStatus = RunStatus.RUNNING
    cancel_event: asyncio.Event = dataclasses.field(default_factory=asyncio.Event)
    last_heartbeat: float = dataclasses.field(default_factory=time.time)
    started_at: float = dataclasses.field(default_factory=time.time)
    finished_at: Optional[float] = None
    progress: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    killed_reason: Optional[str] = None
    result: Optional[Any] = None

    @property
    def elapsed(self) -> float:
        end = self.finished_at or time.time()
        return end - self.started_at

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            RunStatus.FINISHED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.KILLED,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "status": self.status,
            "last_heartbeat": self.last_heartbeat,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed": round(self.elapsed, 1),
            "progress": self.progress,
            "error": self.error,
            "killed_reason": self.killed_reason,
        }


class RunRegistry:
    """Agent 运行的内存注册表。"""

    def __init__(self):
        self._runs: Dict[str, RunInfo] = {}

    def register(
        self,
        run_id: Optional[str] = None,
        session_id: str = "default",
    ) -> RunInfo:
        run_id = run_id or str(uuid.uuid4())
        if run_id in self._runs:
            raise ValueError(f"Run {run_id} already registered")
        info = RunInfo(run_id=run_id, session_id=session_id)
        self._runs[run_id] = info
        logger.info(f"[Watchdog] 注册 run {run_id} (session={session_id})")
        return info

    def get(self, run_id: str) -> Optional[RunInfo]:
        return self._runs.get(run_id)

    def update_status(self, run_id: str, status: RunStatus) -> None:
        info = self._runs.get(run_id)
        if info is None:
            return
        info.status = status
        if info.is_terminal:
            info.finished_at = time.time()
            info.cancel_event.set()

    def heartbeat(self, run_id: str) -> None:
        info = self._runs.get(run_id)
        if info is not None:
            info.last_heartbeat = time.time()

    def update_progress(self, run_id: str, snapshot: Dict[str, Any]) -> None:
        info = self._runs.get(run_id)
        if info is not None:
            info.progress = snapshot

    def request_cancel(self, run_id: str) -> None:
        info = self._runs.get(run_id)
        if info is None:
            return
        info.status = RunStatus.CANCEL_REQUESTED
        info.cancel_event.set()
        logger.info(f"[Watchdog] 用户请求取消 run {run_id}")

    def kill(self, run_id: str, reason: str) -> None:
        info = self._runs.get(run_id)
        if info is None:
            return
        info.status = RunStatus.KILLED
        info.killed_reason = reason
        info.finished_at = time.time()
        info.cancel_event.set()
        logger.warning(f"[Watchdog] 终止 run {run_id}，原因：{reason}")

    def set_error(self, run_id: str, error: str) -> None:
        info = self._runs.get(run_id)
        if info is None:
            return
        info.error = error
        info.status = RunStatus.FAILED
        info.finished_at = time.time()

    def set_result(self, run_id: str, result: Any) -> None:
        info = self._runs.get(run_id)
        if info is None:
            return
        info.result = result
        info.status = RunStatus.FINISHED
        info.finished_at = time.time()

    def unregister(self, run_id: str) -> None:
        self._runs.pop(run_id, None)

    def list_active(self) -> List[RunInfo]:
        return [info for info in self._runs.values() if not info.is_terminal]

    def list_all(self) -> List[RunInfo]:
        return list(self._runs.values())

    def cleanup_old(self, max_age: int = 3600) -> int:
        """清理已结束超过 max_age 秒的 run，返回清理数量。"""
        now = time.time()
        to_remove = [
            rid for rid, info in self._runs.items()
            if info.is_terminal and info.finished_at and (now - info.finished_at) > max_age
        ]
        for rid in to_remove:
            del self._runs[rid]
        if to_remove:
            logger.info(f"[Watchdog] 清理了 {len(to_remove)} 个过期 run")
        return len(to_remove)


# 单例
_registry: Optional[RunRegistry] = None


def get_registry() -> RunRegistry:
    global _registry
    if _registry is None:
        _registry = RunRegistry()
    return _registry
