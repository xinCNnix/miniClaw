"""
Token Usage Extraction Utilities

Shared functions for extracting token usage from LLM responses.
Extracted from perv/pevr_logger.py to eliminate cross-module dependencies.
"""

from datetime import datetime, timezone
from typing import Any, Dict


def _ts() -> str:
    """Return ISO-format UTC timestamp with millisecond precision."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def extract_token_usage(response: Any) -> Dict[str, int]:
    """Extract token usage from an LLM response.

    Compatible with LangChain new and old token statistics formats:
    - usage_metadata (LangChain 0.2+): input_tokens / output_tokens / total_tokens
    - response_metadata.token_usage (legacy): prompt_tokens / completion_tokens / total_tokens

    Args:
        response: LangChain AIMessage or similar object.

    Returns:
        Dict with prompt_tokens, completion_tokens, total_tokens.
    """
    # Prefer usage_metadata (LangChain 0.2+)
    usage = getattr(response, "usage_metadata", None)
    if usage and isinstance(usage, dict):
        return {
            "prompt_tokens": usage.get("input_tokens", 0) or 0,
            "completion_tokens": usage.get("output_tokens", 0) or 0,
            "total_tokens": usage.get("total_tokens", 0) or 0,
        }

    # Fallback to response_metadata.token_usage
    meta = getattr(response, "response_metadata", {})
    if isinstance(meta, dict):
        token_usage = meta.get("token_usage", {})
        if isinstance(token_usage, dict) and token_usage:
            return {
                "prompt_tokens": token_usage.get("prompt_tokens", 0) or 0,
                "completion_tokens": token_usage.get("completion_tokens", 0) or 0,
                "total_tokens": token_usage.get("total_tokens", 0) or 0,
            }

    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
