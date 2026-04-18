"""
Unified LLM retry utility module.

Provides retry logic with exponential backoff and jitter for all LLM calls.
Handles retryable errors such as rate limits (429), service unavailable (503),
bad gateway (502), timeouts, connection errors, and overloaded responses.

Usage:
    from backend.app.core.llm_retry import retry_llm_call, LLMRetryConfig

    # Simple usage with defaults
    result = await retry_llm_call(
        coro_factory=lambda: llm.ainvoke(prompt),
        context="thought_generator",
    )

    # Custom config with retry callback
    config = LLMRetryConfig(max_retries=5, base_delay=3.0)
    result = await retry_llm_call(
        coro_factory=lambda: llm.ainvoke(prompt),
        config=config,
        on_retry=handle_retry_event,
        context="research_agent",
    )
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass
class LLMRetryConfig:
    """Configuration for LLM retry behavior.

    Attributes:
        max_retries: Maximum number of retry attempts (not counting the initial call).
        base_delay: Base delay in seconds before the first retry.
        max_delay: Maximum delay cap in seconds.
        jitter_range: Random jitter range as a fraction (+/- this fraction of the delay).
    """

    max_retries: int = 3
    base_delay: float = 2.0
    max_delay: float = 30.0
    jitter_range: float = 0.3


# Patterns for detecting retryable errors, mapped to their error codes.
# Each group contains lowercase pattern strings that indicate the same error category.
_RETRYABLE_PATTERNS: list[tuple[list[str], str]] = [
    (["429", "rate_limit", "rate limit"], "429"),
    (["503", "service_unavailable", "service unavailable"], "503"),
    (["502", "bad_gateway", "bad gateway"], "502"),
    (["timeout", "timed out", "timeouterror"], "TIMEOUT"),
    (["connection", "connectionerror", "connect_error"], "CONNECTION"),
    (["overloaded", "overload", "capacity"], "OVERLOADED"),
]


def is_retryable_error(exc: Exception) -> tuple[bool, str]:
    """Determine whether an exception is retryable and classify it.

    Checks the exception's string representation and type name against known
    retryable error patterns (rate limits, service unavailable, timeouts, etc.).

    Args:
        exc: The exception to inspect.

    Returns:
        A tuple of (is_retryable, error_code). If the error is not retryable,
        error_code will be an empty string.
    """
    error_text = f"{type(exc).__name__}: {str(exc)}".lower()

    for patterns, error_code in _RETRYABLE_PATTERNS:
        for pattern in patterns:
            if pattern in error_text:
                return True, error_code

    return False, ""


def _build_retry_event(
    attempt: int,
    max_retries: int,
    delay: float,
    error_code: str,
    error_message: str,
    context: str,
) -> dict[str, Any]:
    """Build a standardized retry event dict.

    Args:
        attempt: The attempt number that just failed (0-based).
        max_retries: Maximum configured retries.
        delay: The delay in seconds before the next attempt.
        error_code: The classified error code (e.g. "429", "TIMEOUT").
        error_message: The original error message string.
        context: Caller-provided context label for logging.

    Returns:
        A dictionary describing the retry event.
    """
    return {
        "type": "llm_retry",
        "attempt": attempt + 1,
        "max_retries": max_retries,
        "delay": round(delay, 2),
        "error_code": error_code,
        "error_message": error_message,
        "context": context,
    }


def _build_error_event(
    error_code: str,
    error_message: str,
    context: str,
) -> dict[str, Any]:
    """Build a standardized error-exhausted event dict.

    Args:
        error_code: The classified error code.
        error_message: The original error message string.
        context: Caller-provided context label for logging.

    Returns:
        A dictionary describing the exhausted-retries error event.
    """
    return {
        "type": "llm_error",
        "error_code": error_code,
        "error_message": error_message,
        "exhausted": True,
        "context": context,
    }


def _compute_delay(attempt: int, config: LLMRetryConfig) -> float:
    """Compute the backoff delay for a given attempt number.

    Uses exponential backoff capped at max_delay, with randomized jitter
    to avoid thundering-herd effects.

    Args:
        attempt: The 0-based attempt number (the retry number, not the total call count).
        config: The retry configuration.

    Returns:
        Delay in seconds (always positive).
    """
    exponential_delay = min(
        config.base_delay * (2 ** attempt),
        config.max_delay,
    )
    jitter = random.uniform(-config.jitter_range, config.jitter_range)
    delay = exponential_delay * (1 + jitter)
    # Ensure delay is never negative or zero
    return max(delay, 0.1)


async def retry_llm_call(
    coro_factory: Callable[[], Awaitable[Any]],
    config: LLMRetryConfig | None = None,
    on_retry: Callable[[dict], Awaitable[None]] | None = None,
    context: str = "",
) -> Any:
    """Execute an LLM call with automatic retry on retryable errors.

    Wraps a coroutine factory (so each attempt creates a fresh coroutine) and
    retries on transient errors using exponential backoff with jitter.

    Args:
        coro_factory: A zero-argument callable that returns a new awaitable
            for each attempt. This pattern ensures the coroutine is not consumed
            by a failed attempt.
        config: Retry configuration. Uses LLMRetryConfig defaults when None.
        on_retry: Optional async callback invoked on each retry and on final
            failure. Receives a dict with event details.
        context: A human-readable label for logging (e.g. "thought_generator",
            "research_agent") to identify which part of the system is retrying.

    Returns:
        The result of the successful coroutine invocation.

    Raises:
        Exception: The last exception encountered if all retries are exhausted,
            or any non-retryable exception immediately.
    """
    if config is None:
        config = LLMRetryConfig()

    last_exception: Exception | None = None

    for attempt in range(config.max_retries + 1):
        try:
            coro = coro_factory()
            return await coro
        except Exception as exc:
            last_exception = exc
            is_retryable, error_code = is_retryable_error(exc)

            if not is_retryable:
                # Non-retryable error -- propagate immediately.
                logger.error(
                    "[LLM_RETRY] context=%s attempt=%d/%d error=non_retryable error_message=%s",
                    context,
                    attempt + 1,
                    config.max_retries + 1,
                    str(exc),
                )
                raise

            # Check if we have retries remaining.
            if attempt >= config.max_retries:
                logger.error(
                    "[LLM_RETRY] context=%s attempt=%d/%d error_code=%s "
                    "retries_exhausted error_message=%s",
                    context,
                    attempt + 1,
                    config.max_retries + 1,
                    error_code,
                    str(exc),
                )
                if on_retry is not None:
                    error_event = _build_error_event(
                        error_code=error_code,
                        error_message=str(exc),
                        context=context,
                    )
                    await on_retry(error_event)
                raise

            # Compute delay and schedule retry.
            delay = _compute_delay(attempt, config)

            logger.warning(
                "[LLM_RETRY] context=%s attempt=%d/%d error_code=%s delay=%.1fs error_message=%s",
                context,
                attempt + 1,
                config.max_retries + 1,
                error_code,
                delay,
                str(exc),
            )

            if on_retry is not None:
                retry_event = _build_retry_event(
                    attempt=attempt,
                    max_retries=config.max_retries,
                    delay=delay,
                    error_code=error_code,
                    error_message=str(exc),
                    context=context,
                )
                await on_retry(retry_event)

            await asyncio.sleep(delay)

    # This should be unreachable, but just in case, re-raise the last exception.
    if last_exception is not None:
        raise last_exception

    raise RuntimeError("retry_llm_call exited loop without result or exception")
