"""
Error Tracker

追踪和分类错误。

Author: Task 3.1 Implementation
"""

import logging
from datetime import datetime
from typing import Any

from app.core.exceptions import ToolExecutionError, ValidationError

logger = logging.getLogger(__name__)


class ErrorTracker:
    """
    错误追踪器

    职责：
    - 记录所有错误
    - 分类错误类型
    - 提供错误统计
    - 生成错误报告
    """

    def __init__(self) -> None:
        """初始化追踪器"""
        self._errors: list[dict] = []
        logger.info("[ERROR_TRACKER] Initialized ErrorTracker")

    def track_error(
        self,
        error: Exception,
        context: dict[str, Any]
    ) -> None:
        """
        记录错误

        Args:
            error: 异常对象
            context: 错误上下文
        """
        error_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": type(error).__name__,
            "message": str(error),
            "context": context,
            "category": self._categorize_error(error)
        }

        self._errors.append(error_entry)
        logger.error(
            f"[ERROR_TRACKER] Error recorded: {error_entry['type']} - {error_entry['message']}",
            extra={"context": context}
        )

    def get_errors(self) -> list[dict]:
        """
        获取所有错误

        Returns:
            错误列表
        """
        return list(self._errors)

    def has_errors(self) -> bool:
        """
        检查是否有错误

        Returns:
            是否有错误
        """
        return len(self._errors) > 0

    def get_error_count(self) -> int:
        """
        获取错误数量

        Returns:
            错误数量
        """
        return len(self._errors)

    def get_errors_by_category(
        self,
        category: str
    ) -> list[dict]:
        """
        按类别获取错误

        Args:
            category: 错误类别

        Returns:
            该类别的错误列表
        """
        return [
            error for error in self._errors
            if error.get("category") == category
        ]

    def get_error_summary(self) -> dict[str, Any]:
        """
        获取错误摘要

        Returns:
            错误统计摘要
        """
        summary: dict[str, Any] = {
            "total": len(self._errors),
            "by_category": {},
            "by_type": {},
        }

        for error in self._errors:
            # 按类别统计
            category = error.get("category", "unknown")
            summary["by_category"][category] = summary["by_category"].get(category, 0) + 1

            # 按类型统计
            error_type = error.get("type", "Unknown")
            summary["by_type"][error_type] = summary["by_type"].get(error_type, 0) + 1

        return summary

    def clear(self) -> None:
        """清空错误记录"""
        self._errors.clear()
        logger.info("[ERROR_TRACKER] Cleared all errors")

    def _categorize_error(self, error: Exception) -> str:
        """
        分类错误

        Args:
            error: 异常对象

        Returns:
            错误类别
        """
        if isinstance(error, ToolExecutionError):
            return "tool_execution"
        elif isinstance(error, ValidationError):
            return "validation"
        elif isinstance(error, ConnectionError | TimeoutError):
            return "network"
        elif isinstance(error, PermissionError):
            return "permission"
        elif isinstance(error, ValueError):
            return "value_error"
        else:
            return "unknown"

    def get_recovery_suggestions(self) -> list[str]:
        """
        获取恢复建议

        Returns:
            建议列表
        """
        suggestions: list[str] = []

        if not self._errors:
            return suggestions

        # 基于错误类别提供建议
        categories = {error.get("category") for error in self._errors}

        if "tool_execution" in categories:
            suggestions.append("检查工具配置和参数")
            suggestions.append("验证工具是否可用")

        if "network" in categories:
            suggestions.append("检查网络连接")
            suggestions.append("增加超时时间")

        if "permission" in categories:
            suggestions.append("检查文件权限")
            suggestions.append("验证访问凭证")

        return suggestions
