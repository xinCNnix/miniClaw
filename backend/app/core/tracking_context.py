"""
Request Tracking Context Module

This module provides request tracking functionality to correlate all logs
associated with a single request/session.
"""

import uuid
import contextvars
import logging
from typing import Optional

# 请求 ID 上下文变量
REQUEST_ID_CTX: contextvars.ContextVar[str] = contextvars.ContextVar('request_id', default=None)
SESSION_ID_CTX: contextvars.ContextVar[str] = contextvars.ContextVar('session_id', default=None)


def generate_request_id() -> str:
    """
    生成一个新的请求 ID

    Returns:
        8字符的唯一请求ID
    """
    return str(uuid.uuid4())[:8]


def get_request_id() -> str:
    """
    获取当前请求 ID

    如果当前上下文没有请求 ID，会自动生成一个新的。

    Returns:
        当前请求 ID（8字符字符串）
    """
    rid = REQUEST_ID_CTX.get()
    if rid is None:
        rid = generate_request_id()
        REQUEST_ID_CTX.set(rid)
    return rid


def set_request_id(request_id: str) -> None:
    """
    设置当前请求 ID

    Args:
        request_id: 请求 ID（8字符字符串）
    """
    REQUEST_ID_CTX.set(request_id)


def get_session_id() -> Optional[str]:
    """
    获取当前会话 ID

    Returns:
        会话 ID，如果未设置则返回 None
    """
    return SESSION_ID_CTX.get()


def set_session_id(session_id: str) -> None:
    """
    设置当前会话 ID

    Args:
        session_id: 会话 ID
    """
    SESSION_ID_CTX.set(session_id)


class RequestTrackingContext:
    """
    请求追踪上下文管理器

    用于自动管理请求 ID 的生命周期。

    Usage:
        with RequestTrackingContext(session_id="user_123"):
            # 在这个上下文中，所有日志都会包含相同的请求 ID
            logger.info("Processing request")
            # 所有日志会自动包含 [RID:abc12345]
    """

    def __init__(self, session_id: Optional[str] = None, request_id: Optional[str] = None):
        """
        初始化请求追踪上下文

        Args:
            session_id: 可选的会话 ID
            request_id: 可选的请求 ID（如果不提供，会自动生成）
        """
        self.session_id = session_id
        self.request_id = request_id or generate_request_id()
        self.token = None

    def __enter__(self):
        """进入上下文，设置请求 ID"""
        # 设置请求 ID
        set_request_id(self.request_id)

        # 如果有会话 ID，也设置会话 ID
        if self.session_id:
            set_session_id(self.session_id)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文，清理请求 ID"""
        # 重置上下文变量
        REQUEST_ID_CTX.set(None)
        SESSION_ID_CTX.set(None)
        return False


class RequestTrackingAdapter:
    """
    日志适配器，自动添加请求追踪信息

    Usage:
        logger = logging.getLogger(__name__)
        adapter = RequestTrackingAdapter(logger, extra={})
        logger.info("Message")  # 会自动添加请求 ID
    """

    def __init__(self, logger: logging.Logger, extra: dict):
        """
        初始化适配器

        Args:
            logger: 原始 logger
            extra: 额外的上下文信息
        """
        self.logger = logger
        self.extra = extra

    def process(self, msg, kwargs):
        """
        处理日志消息，添加请求追踪信息

        Args:
            msg: 日志消息
            kwargs: 日志关键字参数

        Returns:
            处理后的 (msg, kwargs)
        """
        # 获取当前请求 ID
        request_id = get_request_id()
        session_id = get_session_id()

        # 添加到 extra 中
        new_extra = self.extra.copy()
        if request_id:
            new_extra['request_id'] = request_id
        if session_id:
            new_extra['session_id'] = session_id

        # 合并 kwargs 中的 extra
        if 'extra' in kwargs:
            kwargs['extra'].update(new_extra)
        else:
            kwargs['extra'] = new_extra

        return msg, kwargs

    # 代理所有日志方法
    def debug(self, msg, *args, **kwargs):
        msg, kwargs = self.process(msg, kwargs)
        self.logger.debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        msg, kwargs = self.process(msg, kwargs)
        self.logger.info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        msg, kwargs = self.process(msg, kwargs)
        self.logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        msg, kwargs = self.process(msg, kwargs)
        self.logger.error(msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        msg, kwargs = self.process(msg, kwargs)
        self.logger.critical(msg, *args, **kwargs)

    def exception(self, msg, *args, **kwargs):
        msg, kwargs = self.process(msg, kwargs)
        self.logger.exception(msg, *args, **kwargs)


def get_tracking_logger(name: str) -> logging.Logger:
    """
    获取带有请求追踪功能的 logger

    Args:
        name: logger 名称

    Returns:
        包装后的 logger，自动包含请求追踪信息
    """
    import logging

    # 使用 LoggerAdapter 来添加请求追踪信息
    original_logger = logging.getLogger(name)

    class TrackingLoggerAdapter(logging.LoggerAdapter):
        def process(self, msg, kwargs):
            request_id = get_request_id()
            session_id = get_session_id()

            extra = kwargs.get('extra', {})
            if request_id:
                extra['request_id'] = request_id
            if session_id:
                extra['session_id'] = session_id

            kwargs['extra'] = extra
            return msg, kwargs

    return TrackingLoggerAdapter(original_logger, {})
