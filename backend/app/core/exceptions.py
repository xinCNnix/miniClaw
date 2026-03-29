"""
MiniClaw Exception Hierarchy

Provides a structured exception system for better error handling,
debugging, and user feedback.
"""

import builtins
from typing import Any, Dict, Optional


class MiniClawError(Exception):
    """
    Base exception for all miniClaw errors.

    All custom exceptions should inherit from this class.
    Provides consistent error structure with context and original error tracking.
    """

    def __init__(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        super().__init__(message)
        self.context = context or {}
        self.original_error = original_error
        self.message = message

    def __str__(self) -> str:
        """String representation includes context if available."""
        base = self.message
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            return f"{base} (Context: {context_str})"
        return base

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for API responses."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "context": self.context,
        }


class AgentError(MiniClawError):
    """
    Agent execution errors.

    Raised when the Agent encounters issues during:
    - Task execution
    - Tool selection
    - State management
    - Planning failures
    """

    def __init__(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        super().__init__(message, context, original_error)
        self.error_type = "agent_error"


class ToolExecutionError(AgentError):
    """
    Tool execution errors.

    Raised when a tool fails to execute properly.
    """

    def __init__(
        self,
        tool_name: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        full_message = f"Tool '{tool_name}' failed: {message}"
        super().__init__(full_message, context, original_error)
        self.tool_name = tool_name
        self.error_type = "tool_execution_error"


class ToolNotFoundError(ToolExecutionError):
    """
    Raised when a requested tool is not available.
    """

    def __init__(
        self,
        tool_name: str,
        available_tools: Optional[list[str]] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        message = f"Tool '{tool_name}' not found"
        if available_tools:
            message += f". Available tools: {', '.join(available_tools)}"
        super().__init__(tool_name, message, context)
        self.error_type = "tool_not_found"


class ToolInputError(ToolExecutionError):
    """
    Raised when tool input validation fails.
    """

    def __init__(
        self,
        tool_name: str,
        input_errors: Dict[str, str],
        context: Optional[Dict[str, Any]] = None
    ):
        message = f"Tool '{tool_name}' input validation failed: {input_errors}"
        super().__init__(tool_name, message, {**(context or {}), "input_errors": input_errors})
        self.error_type = "tool_input_error"


class MemoryError(MiniClawError):
    """
    Memory system errors.

    Raised when there are issues with:
    - Memory storage/retrieval
    - Vector database operations
    - Session management
    - Knowledge base operations
    """

    def __init__(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        super().__init__(message, context, original_error)
        self.error_type = "memory_error"


class VectorStoreError(MemoryError):
    """
    Vector database errors.

    Raised when vector operations fail.
    """

    def __init__(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        super().__init__(message, context, original_error)
        self.error_type = "vector_store_error"


class SessionError(MemoryError):
    """
    Session management errors.

    Raised when session operations fail.
    """

    def __init__(
        self,
        message: str,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        full_message = f"Session error: {message}"
        if session_id:
            full_message += f" (Session ID: {session_id})"
        super().__init__(full_message, context, original_error)
        self.session_id = session_id
        self.error_type = "session_error"


class NetworkError(MiniClawError):
    """
    Network-related errors.

    Raised when network operations fail.
    """

    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        status_code: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        full_message = f"Network error: {message}"
        if url:
            full_message += f" (URL: {url})"
        if status_code:
            full_message += f" (Status: {status_code})"
        super().__init__(full_message, context, original_error)
        self.url = url
        self.status_code = status_code
        self.error_type = "network_error"


class ConfigurationError(MiniClawError):
    """
    Configuration errors.

    Raised when:
    - Invalid configuration values
    - Missing required configuration
    - Configuration file parsing errors
    """

    def __init__(
        self,
        message: str,
        config_key: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        full_message = f"Configuration error: {message}"
        if config_key:
            full_message += f" (Key: {config_key})"
        super().__init__(full_message, context, original_error)
        self.config_key = config_key
        self.error_type = "configuration_error"


class ValidationError(MiniClawError):
    """
    Input validation errors.

    Raised when user input or API request validation fails.
    """

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Optional[Any] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        full_message = f"Validation error: {message}"
        if field:
            full_message += f" (Field: {field})"
        if value is not None:
            full_message += f" (Value: {str(value)[:50]})"
        super().__init__(full_message, context)
        self.field = field
        self.value = value
        self.error_type = "validation_error"


class AuthenticationError(MiniClawError):
    """
    Authentication errors.

    Raised when authentication fails.
    """

    def __init__(
        self,
        message: str = "Authentication failed",
        context: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        super().__init__(message, context, original_error)
        self.error_type = "authentication_error"


class AuthorizationError(MiniClawError):
    """
    Authorization errors.

    Raised when user lacks permission for an action.
    """

    def __init__(
        self,
        message: str,
        required_permission: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        full_message = f"Authorization error: {message}"
        if required_permission:
            full_message += f" (Required: {required_permission})"
        super().__init__(full_message, context, original_error)
        self.required_permission = required_permission
        self.error_type = "authorization_error"


class ResourceNotFoundError(MiniClawError):
    """
    Resource not found errors.

    Raised when a requested resource doesn't exist.
    """

    def __init__(
        self,
        resource_type: str,
        resource_id: str,
        context: Optional[Dict[str, Any]] = None
    ):
        message = f"{resource_type} not found: {resource_id}"
        super().__init__(message, context)
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.error_type = "resource_not_found"


class RateLimitError(MiniClawError):
    """
    Rate limiting errors.

    Raised when rate limits are exceeded.
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        full_message = f"{message}"
        if retry_after:
            full_message += f" (Retry after: {retry_after}s)"
        super().__init__(full_message, context)
        self.retry_after = retry_after
        self.error_type = "rate_limit_error"


class TimeoutError(MiniClawError):
    """
    Timeout errors.

    Raised when operations take too long.
    """

    def __init__(
        self,
        message: str,
        timeout_seconds: Optional[float] = None,
        context: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        full_message = f"Timeout error: {message}"
        if timeout_seconds:
            full_message += f" (Timeout: {timeout_seconds}s)"
        super().__init__(full_message, context, original_error)
        self.timeout_seconds = timeout_seconds
        self.error_type = "timeout_error"


class ToTError(MiniClawError):
    """
    Tree of Thoughts (ToT) specific errors.

    Raised when ToT reasoning fails.
    """

    def __init__(
        self,
        message: str,
        tot_stage: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        full_message = f"ToT error: {message}"
        if tot_stage:
            full_message += f" (Stage: {tot_stage})"
        super().__init__(full_message, context, original_error)
        self.tot_stage = tot_stage
        self.error_type = "tot_error"


class LLMError(MiniClawError):
    """
    LLM-related errors.

    Raised when LLM operations fail.
    """

    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        full_message = f"LLM error: {message}"
        if provider:
            full_message += f" (Provider: {provider})"
        if model:
            full_message += f" (Model: {model})"
        super().__init__(full_message, context, original_error)
        self.provider = provider
        self.model = model
        self.error_type = "llm_error"


class SkillError(MiniClawError):
    """
    Skill-related errors.

    Raised when skill operations fail.
    """

    def __init__(
        self,
        message: str,
        skill_name: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        full_message = f"Skill error: {message}"
        if skill_name:
            full_message += f" (Skill: {skill_name})"
        super().__init__(full_message, context, original_error)
        self.skill_name = skill_name
        self.error_type = "skill_error"


# Convenience functions for common error scenarios

def wrap_tool_execution(
    tool_name: str,
    func,
    *args,
    **kwargs
):
    """
    Wrapper for tool execution that converts exceptions to ToolExecutionError.

    Usage:
        result = wrap_tool_execution("read_file", read_file, path="test.txt")
    """
    try:
        return func(*args, **kwargs)
    except MiniClawError:
        raise  # Re-raise our custom errors
    except Exception as e:
        raise ToolExecutionError(
            tool_name=tool_name,
            message=str(e),
            original_error=e
        ) from e


def handle_error_with_logging(
    error: Exception,
    logger,
    context: Optional[Dict[str, Any]] = None
) -> MiniClawError:
    """
    Convert generic exceptions to specific MiniClawError types with logging.

    Usage:
        try:
            risky_operation()
        except Exception as e:
            raise handle_error_with_logging(e, logger, {"operation": " risky_operation"})
    """
    if isinstance(error, MiniClawError):
        # Already a MiniClawError, just log and re-raise
        logger.error(f"{error.__class__.__name__}: {error}", extra=context)
        return error

    # Convert to appropriate MiniClawError type based on error type
    error_type = type(error).__name__

    if isinstance(error, builtins.TimeoutError) or "timeout" in error_type.lower():
        new_error = TimeoutError(
            message=str(error),
            original_error=error
        )
    elif "connection" in error_type.lower() or "network" in error_type.lower():
        new_error = NetworkError(
            message=str(error),
            original_error=error
        )
    elif "validation" in error_type.lower() or "invalid" in str(error).lower():
        new_error = ValidationError(
            message=str(error)
        )
    elif "authentication" in error_type.lower() or "unauthorized" in error_type.lower():
        new_error = AuthenticationError(
            message=str(error),
            original_error=error
        )
    elif "forbidden" in error_type.lower() or "permission" in error_type.lower():
        new_error = AuthorizationError(
            message=str(error),
            original_error=error
        )
    elif "not found" in str(error).lower():
        new_error = ResourceNotFoundError(
            resource_type="Resource",
            resource_id=str(error)
        )
    else:
        # Default to generic AgentError
        new_error = AgentError(
            message=str(error),
            context=context,
            original_error=error
        )

    logger.error(f"Converted {error_type} to {new_error.__class__.__name__}", extra=context)
    return new_error
