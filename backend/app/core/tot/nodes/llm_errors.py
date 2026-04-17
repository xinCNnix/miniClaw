"""
LLM error classification and retry utilities for ToT nodes.
"""

import asyncio
import re
import logging
from openai import APIStatusError

logger = logging.getLogger(__name__)

# HTTP status codes that indicate the LLM is unusable — must abort immediately.
FATAL_STATUS_CODES = {400, 401, 402, 403, 404, 500, 502, 503}

# 429 (rate limit) is retryable, not fatal
RETRYABLE_STATUS_CODES = {429}

# User-friendly messages for common error codes
ERROR_MESSAGES = {
    400: "LLM request invalid",
    401: "API key invalid or expired",
    402: "API quota exceeded",
    403: "API access denied",
    404: "LLM model unavailable or deprecated",
    429: "API rate limit reached, retrying...",
    500: "LLM server internal error",
    502: "LLM server unavailable",
    503: "LLM service overloaded",
}


def _extract_status_code(exc: Exception) -> int | None:
    """Extract HTTP status code from an exception."""
    if isinstance(exc, APIStatusError):
        return exc.status_code
    msg = str(exc)
    m = re.search(r"Error code:\s*(\d{3})", msg)
    return int(m.group(1)) if m else None


def is_fatal_llm_error(exc: Exception) -> tuple[bool, int | None]:
    """Check whether an exception indicates a fatal LLM failure.

    Returns (is_fatal, status_code).  When *is_fatal* is True the caller
    should re-raise so the router can surface the error to the frontend.
    """
    code = _extract_status_code(exc)
    if code is None:
        return False, None
    return code in FATAL_STATUS_CODES, code


def is_retryable_error(exc: Exception) -> tuple[bool, int | None]:
    """Check whether an exception is retryable (e.g. 429 rate limit)."""
    code = _extract_status_code(exc)
    if code is None:
        return False, None
    return code in RETRYABLE_STATUS_CODES, code


def fatal_error_message(status_code: int | None, detail: str) -> str:
    """Return a user-friendly error string for a fatal LLM error."""
    prefix = ERROR_MESSAGES.get(status_code, "LLM service error") if status_code else "LLM service error"
    return f"{prefix} (code {status_code}): {detail}"


async def llm_call_with_retry(coro, max_retries: int = 3, base_delay: float = 2.0):
    """Call an async LLM function with retry on 429 rate-limit errors.

    Args:
        coro: Awaitable (the LLM call).
        max_retries: Maximum number of retries for 429 errors.
        base_delay: Base delay in seconds, doubled after each retry.

    Returns:
        The LLM response.

    Raises:
        The original exception if retries are exhausted or a fatal error occurs.
    """
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return await coro
        except Exception as e:
            # Fatal error — propagate immediately
            fatal, _ = is_fatal_llm_error(e)
            if fatal:
                raise

            # Retryable (429) — wait and retry
            retryable, code = is_retryable_error(e)
            if retryable and attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    f"Rate limited (429), retry {attempt + 1}/{max_retries} "
                    f"after {delay:.1f}s..."
                )
                await asyncio.sleep(delay)
                last_exc = e
                continue

            # Not retryable or retries exhausted
            raise
