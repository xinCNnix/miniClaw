"""
Dream API — Manual trigger for Dream offline batch self-replay.
"""

import logging
from fastapi import APIRouter, HTTPException

from app.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dream"])


@router.post("/trigger")
async def trigger_dream():
    """Manually trigger a Dream session.

    Requires `enable_dream=True` in config. Runs the full 9-node Dream
    pipeline and returns a summary of results.
    """
    settings = get_settings()
    if not getattr(settings, "enable_dream", False):
        raise HTTPException(
            status_code=403,
            detail="Dream module is disabled. Set ENABLE_DREAM=true to enable.",
        )

    try:
        from app.core.dream import run_dream

        result = await run_dream(
            mode="manual",
            max_samples=settings.dream_max_samples,
            executor_mode=settings.dream_executor_mode,
        )

        return {
            "status": "completed",
            "sampled": len(result.get("sampled_trajectories", [])),
            "skills_distilled": len(result.get("distilled_skills", [])),
            "skills_written": len(result.get("written_skill_ids", [])),
            "errors": len(result.get("write_errors", [])),
            "dream_request_id": result.get("dream_request_id"),
        }
    except Exception as e:
        logger.error("[Dream] Trigger failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Dream session failed: {e}")
