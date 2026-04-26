"""Watchdog 后台服务。

定期扫描活跃的 run，终止以下情况的 run：
- 心跳超时（在阈值时间内无进度信号）
- 用户取消
- 状态卡死（连续相同状态指纹）
- 动作重复（连续相同工具调用）
- 超过最大运行时间
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from app.core.watchdog.registry import RunInfo, RunRegistry, RunStatus

logger = logging.getLogger(__name__)


class WatchdogService:
    """监控并终止卡死 Agent 运行的后台任务。"""

    def __init__(
        self,
        registry: Optional[RunRegistry] = None,
        heartbeat_timeout: int = 60,
        poll_interval: int = 5,
        max_runtime: int = 1800,
        stuck_threshold: int = 4,
        repeat_threshold: int = 3,
    ):
        self._registry = registry or RunRegistry()
        self._heartbeat_timeout = heartbeat_timeout
        self._poll_interval = poll_interval
        self._max_runtime = max_runtime
        self._stuck_threshold = stuck_threshold
        self._repeat_threshold = repeat_threshold
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def scan(self) -> None:
        """执行一次扫描周期，检查所有活跃 run 并清理旧记录。"""
        now = time.time()
        for info in self._registry.list_active():
            self._check_run(info, now)
        self._registry.cleanup_old()

    def _check_run(self, info: RunInfo, now: float) -> None:
        if info.is_terminal:
            return
        if info.status == RunStatus.QUEUED:
            return

        if info.elapsed > self._max_runtime:
            self._registry.kill(info.run_id, "max_runtime_exceeded")
            return

        if now - info.last_heartbeat > self._heartbeat_timeout:
            self._registry.kill(info.run_id, "heartbeat_timeout")
            return

        if info.status == RunStatus.CANCEL_REQUESTED:
            self._registry.kill(info.run_id, "user_cancel")
            return

        if info.progress:
            if info.progress.get("state_stuck"):
                self._registry.kill(info.run_id, "progress_state_stuck")
                return
            if info.progress.get("action_repeating"):
                self._registry.kill(info.run_id, "progress_action_repeating")
                return

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_periodically())
        logger.info(
            f"[Watchdog] 服务已启动 "
            f"(心跳超时={self._heartbeat_timeout}s, "
            f"扫描间隔={self._poll_interval}s, "
            f"最大运行时间={self._max_runtime}s)"
        )

    async def _run_periodically(self) -> None:
        while self._running:
            try:
                self.scan()
            except Exception as e:
                logger.error(f"[Watchdog] 扫描错误: {e}")
            await asyncio.sleep(self._poll_interval)

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("[Watchdog] 服务已停止")

    @property
    def is_running(self) -> bool:
        return self._running


# 单例
_service: Optional[WatchdogService] = None


def get_watchdog_service() -> WatchdogService:
    """获取或创建单例 WatchdogService。"""
    global _service
    if _service is None:
        from app.config import get_settings
        settings = get_settings()
        _service = WatchdogService(
            heartbeat_timeout=settings.watchdog_heartbeat_timeout,
            poll_interval=settings.watchdog_poll_interval,
            max_runtime=settings.watchdog_max_runtime,
            stuck_threshold=settings.watchdog_stuck_threshold,
            repeat_threshold=settings.watchdog_repeat_threshold,
        )
    return _service
