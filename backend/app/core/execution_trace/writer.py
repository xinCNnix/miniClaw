"""
Unified Trace File Writer

Handles saving execution trace data to JSON files with truncation
and size control. Supports all three modes: normal, perv, tot.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _truncate(text: str, max_length: int) -> str:
    """Truncate text to max_length, appending indicator if truncated."""
    if max_length <= 0 or not text:
        return text or ""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "...[truncated]"


def save_trace(
    data: dict[str, Any],
    mode: str,
    task_name: str,
    session_id: str = "",
) -> Optional[str]:
    """Save execution trace data to a JSON file.

    Args:
        data: Trace data dict (must be JSON-serializable).
        mode: Execution mode ("normal", "perv", "tot").
        task_name: Task name for filename generation.
        session_id: Session ID for filename generation.

    Returns:
        Saved file path, or None on failure.
    """
    try:
        from app.config import get_settings
        settings = get_settings()

        # Determine output directory based on mode
        base_dir = getattr(settings, "log_dir", "logs")
        trace_dir = Path(base_dir) / "traces" / mode
        trace_dir.mkdir(parents=True, exist_ok=True)

        # Truncation settings
        thought_max = getattr(settings, "trajectory_thought_max_length", 500)
        result_max = getattr(settings, "trajectory_result_max_length", 1000)
        max_size = getattr(settings, "max_trajectory_size", 10000)

        # Truncate step fields if present
        for step in data.get("steps", []):
            step["thought"] = _truncate(step.get("thought", ""), thought_max)
            step["result"] = _truncate(step.get("result", ""), result_max)

        # Serialize
        json_str = json.dumps(data, ensure_ascii=False, indent=2, default=str)

        # Size check
        if max_size > 0 and len(json_str) > max_size:
            logger.warning(
                f"Trace too large ({len(json_str)} > {max_size}), truncating result fields"
            )
            for step in data.get("steps", []):
                step["result"] = _truncate(step.get("result", ""), min(result_max, 200))
            json_str = json.dumps(data, ensure_ascii=False, indent=2, default=str)

        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_task = task_name.replace("/", "_").replace("\\", "_")[:50]
        safe_session = session_id[:12] if session_id else "default"
        filename = f"{mode}_{safe_session}_{safe_task}_{timestamp}.json"
        filepath = trace_dir / filename

        # Write
        filepath.write_text(json_str, encoding="utf-8")
        logger.info(f"Trace saved: {filepath} ({len(json_str)} bytes)")
        return str(filepath)

    except Exception as e:
        logger.error(f"Failed to save trace: {e}")
        return None
