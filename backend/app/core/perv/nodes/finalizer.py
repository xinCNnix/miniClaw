"""
Finalizer node - synthesizes final answer from execution results.

Produces the user-facing answer by asking the LLM to synthesize the
collected observations into a coherent response.
"""

import logging
import time

from langchain_core.messages import HumanMessage

from app.config import get_settings
from app.core.llm import create_llm
from app.core.llm_retry import retry_llm_call
from app.core.perv.prompts import build_finalizer_prompt, extract_system_style
from app.core.perv.pevr_logger import PEVRLogger, extract_token_usage

logger = logging.getLogger(__name__)


async def finalizer_node(state: dict) -> dict:
    """Synthesize the final answer from execution results.

    Calls the LLM with a finalizer prompt that includes all observations,
    then returns the response as the final answer.

    Args:
        state: Current PlannerState dictionary.

    Returns:
        Dictionary with ``final_answer``.
    """
    task: str = state.get("task", "")
    observations = state.get("observations", [])
    retry_count: int = state.get("retry_count", 0)
    system_prompt: str = state.get("system_prompt", "")
    pevr_log: PEVRLogger | None = state.get("_pevr_log")

    start = time.time()

    try:
        # --- Build finalizer prompt ---
        prompt_text = build_finalizer_prompt(
            system_prompt=system_prompt,
            task=task,
            observations=observations,
        )

        logger.debug(
            "[PEVR Finalizer] Prompt: %d chars, obs=%d",
            len(prompt_text),
            len(observations),
        )

        # --- Call LLM ---
        settings = get_settings()
        provider = settings.llm_provider
        llm = create_llm(provider)

        response = await retry_llm_call(
            coro_factory=lambda: llm.ainvoke([HumanMessage(content=prompt_text)]),
            context="pevr_finalizer",
        )

        # --- Extract token usage ---
        token_usage = extract_token_usage(response)

        content: str = getattr(response, "content", str(response))
        duration = time.time() - start

        logger.info(
            "[PEVR Finalizer] Produced answer: %d chars (%.1fms)",
            len(content),
            duration * 1000,
        )
        logger.debug(
            "[PEVR Finalizer] Answer preview: %s",
            content[:300],
        )

        if pevr_log:
            pevr_log.log_finalization(
                answer=content,
                duration_s=duration,
                token_usage=token_usage,
            )

    except Exception as e:
        duration = time.time() - start
        logger.error(
            "[PEVR Finalizer] FAILED after %.1fms: %s",
            duration * 1000,
            e,
            exc_info=True,
        )
        content = f"Error generating final answer: {e}"
        if pevr_log:
            pevr_log.log_finalization(
                answer="",
                duration_s=duration,
                error=e,
            )
            pevr_log.log_node_error(
                "finalizer",
                e,
                f"obs={len(observations)}",
            )

    # [IMAGE_UNIFY] Image appending moved to orchestrator (handles all loops)
    return {"final_answer": content}
