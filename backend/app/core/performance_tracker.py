"""
Performance Tracking Module

This module provides performance monitoring utilities for tracking
operation durations and identifying bottlenecks.
"""

import time
import functools
import logging
import asyncio
from typing import Callable, Any, Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class PerformanceTracker:
    """
    性能追踪器，用于记录关键操作的耗时
    """

    def __init__(self):
        """初始化性能追踪器"""
        self.metrics = {}

    def track_operation(self, operation_name: str):
        """
        装饰器：记录同步操作的耗时

        Args:
            operation_name: 操作名称

        Returns:
            装饰器函数
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                start = time.time()
                try:
                    result = func(*args, **kwargs)
                    duration = time.time() - start
                    self._record_success(operation_name, duration)
                    return result
                except Exception as e:
                    duration = time.time() - start
                    self._record_failure(operation_name, duration, str(e))
                    raise

            return sync_wrapper

        return decorator

    def track_async_operation(self, operation_name: str):
        """
        装饰器：记录异步操作的耗时

        Args:
            operation_name: 操作名称

        Returns:
            装饰器函数
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                start = time.time()
                try:
                    result = await func(*args, **kwargs)
                    duration = time.time() - start
                    self._record_success(operation_name, duration)
                    return result
                except Exception as e:
                    duration = time.time() - start
                    self._record_failure(operation_name, duration, str(e))
                    raise

            return async_wrapper

        return decorator

    def _record_success(self, operation_name: str, duration: float):
        """
        记录成功操作的性能数据

        Args:
            operation_name: 操作名称
            duration: 耗时（秒）
        """
        if operation_name not in self.metrics:
            self.metrics[operation_name] = {
                "count": 0,
                "success_count": 0,
                "total_duration": 0.0,
                "max_duration": 0.0,
                "min_duration": float('inf'),
                "errors": []
            }

        metrics = self.metrics[operation_name]
        metrics["count"] += 1
        metrics["success_count"] += 1
        metrics["total_duration"] += duration
        metrics["max_duration"] = max(metrics["max_duration"], duration)
        metrics["min_duration"] = min(metrics["min_duration"], duration)

        # 计算平均耗时
        avg_duration = metrics["total_duration"] / metrics["success_count"]

        # 根据耗时记录日志
        if duration > 1.0:  # 超过1秒记录警告
            logger.warning(
                f"[PERF] {operation_name} completed in {duration:.2f}s "
                f"(avg: {avg_duration:.2f}s, max: {metrics['max_duration']:.2f}s)"
            )
        elif duration > 0.5:  # 超过0.5秒记录信息
            logger.info(
                f"[PERF] {operation_name} completed in {duration:.2f}s "
                f"(avg: {avg_duration:.2f}s)"
            )
        else:  # 快速操作记录debug
            logger.debug(
                f"[PERF] {operation_name} completed in {duration:.2f}s"
            )

    def _record_failure(self, operation_name: str, duration: float, error: str):
        """
        记录失败操作的性能数据

        Args:
            operation_name: 操作名称
            duration: 耗时（秒）
            error: 错误信息
        """
        if operation_name not in self.metrics:
            self.metrics[operation_name] = {
                "count": 0,
                "success_count": 0,
                "total_duration": 0.0,
                "max_duration": 0.0,
                "min_duration": float('inf'),
                "errors": []
            }

        metrics = self.metrics[operation_name]
        metrics["count"] += 1
        metrics["total_duration"] += duration
        metrics["errors"].append({
            "error": error,
            "duration": duration,
            "timestamp": time.time()
        })

        logger.error(
            f"[PERF] {operation_name} failed after {duration:.2f}s: {error}"
        )

    def get_metrics(self, operation_name: Optional[str] = None) -> dict:
        """
        获取性能指标

        Args:
            operation_name: 操作名称，如果为None则返回所有指标

        Returns:
            性能指标字典
        """
        if operation_name:
            return self.metrics.get(operation_name, {})

        return self.metrics

    def get_summary(self) -> dict:
        """
        获取性能摘要

        Returns:
            包含关键统计的摘要字典
        """
        summary = {}

        for op_name, metrics in self.metrics.items():
            if metrics["success_count"] > 0:
                avg_duration = metrics["total_duration"] / metrics["success_count"]
                success_rate = (metrics["success_count"] / metrics["count"]) * 100
            else:
                avg_duration = 0
                success_rate = 0

            summary[op_name] = {
                "count": metrics["count"],
                "success_count": metrics["success_count"],
                "avg_duration": avg_duration,
                "max_duration": metrics["max_duration"],
                "min_duration": metrics["min_duration"] if metrics["min_duration"] != float('inf') else 0,
                "success_rate": success_rate,
                "error_count": len(metrics["errors"])
            }

        return summary


# 全局性能追踪器实例
_global_tracker: Optional[PerformanceTracker] = None


def get_performance_tracker() -> PerformanceTracker:
    """
    获取全局性能追踪器实例

    Returns:
        PerformanceTracker 实例
    """
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = PerformanceTracker()
    return _global_tracker


@contextmanager
def track_performance(operation_name: str):
    """
    上下文管理器：追踪操作耗时

    Usage:
        with track_performance("database_query"):
            result = db.query(...)
        # 自动记录耗时

    Args:
        operation_name: 操作名称
    """
    tracker = get_performance_tracker()
    start = time.time()
    error = None

    try:
        yield
    except Exception as e:
        error = str(e)
        raise
    finally:
        duration = time.time() - start
        if error:
            tracker._record_failure(operation_name, duration, error)
        else:
            tracker._record_success(operation_name, duration)


# 便捷装饰器
def track_sync(operation_name: str):
    """同步操作性能追踪装饰器"""
    return get_performance_tracker().track_operation(operation_name)


def track_async(operation_name: str):
    """异步操作性能追踪装饰器"""
    return get_performance_tracker().track_async_operation(operation_name)
