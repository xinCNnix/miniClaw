"""
Trajectory File Writer

Handles saving trajectory data to JSON files with truncation and size control.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _truncate(text: str, max_length: int) -> str:
    """Truncate text to max_length, appending indicator if truncated."""
    if max_length <= 0 or not text:
        return text or ""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "...[truncated]"


def save_trajectory(
    data: dict[str, Any],
    task_name: str,
    session_id: str = "",
) -> str | None:
    """
    Save trajectory data to a JSON file.

    Reads config for output directory, truncation lengths, and size limits.

    Args:
        data: Trajectory data dict (steps, summary, etc.)
        task_name: Task name for filename generation
        session_id: Session ID for filename generation

    Returns:
        Saved file path, or None on failure
    """
    try:
        from app.config import get_settings
        settings = get_settings()

        log_dir = getattr(settings, "trajectory_log_dir", "logs/trajectories")
        thought_max = getattr(settings, "trajectory_thought_max_length", 500)
        result_max = getattr(settings, "trajectory_result_max_length", 1000)
        max_size = getattr(settings, "max_trajectory_size", 10000)

        # Create output directory
        traj_dir = Path(log_dir)
        traj_dir.mkdir(parents=True, exist_ok=True)

        # Truncate step fields
        for step in data.get("steps", []):
            step["thought"] = _truncate(step.get("thought", ""), thought_max)
            step["result"] = _truncate(step.get("result", ""), result_max)

        # Serialize
        json_str = json.dumps(data, ensure_ascii=False, indent=2)

        # Size check
        if max_size > 0 and len(json_str) > max_size:
            logger.warning(
                f"Trajectory too large ({len(json_str)} > {max_size}), truncating result fields"
            )
            # Re-serialize with shorter truncation
            for step in data.get("steps", []):
                step["result"] = _truncate(step.get("result", ""), min(result_max, 200))
            json_str = json.dumps(data, ensure_ascii=False, indent=2)

        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_task = task_name.replace("/", "_").replace("\\", "_")[:50]
        safe_session = session_id[:12] if session_id else "default"
        filename = f"trajectory_{safe_session}_{safe_task}_{timestamp}.json"
        filepath = traj_dir / filename

        # Write
        filepath.write_text(json_str, encoding="utf-8")
        logger.info(f"Trajectory saved: {filepath} ({len(json_str)} bytes)")
        return str(filepath)

    except Exception as e:
        logger.error(f"Failed to save trajectory: {e}")
        return None
