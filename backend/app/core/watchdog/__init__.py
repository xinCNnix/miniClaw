"""Watchdog 进程监控模块。

监控正在运行的 Agent 执行，检测卡死/循环的 run，
支持用户主动取消。
"""

from app.core.watchdog.registry import RunRegistry, RunInfo, RunStatus, get_registry
from app.core.watchdog.tracker import ProgressTracker
from app.core.watchdog.service import WatchdogService, get_watchdog_service

__all__ = [
    "RunRegistry",
    "RunInfo",
    "RunStatus",
    "get_registry",
    "ProgressTracker",
    "WatchdogService",
    "get_watchdog_service",
]
