"""Reflection helpers: evaluate agent output quality and generate corrections.

This module provides the core integration point between the reflection engine
and the three execution modes (Normal Agent, ToT, PERV). When quality_score
falls below the configured threshold, a correction is generated and sent
back via SSE events.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from app.config import get_settings
from app.core.reflection.action import ReflectionAction
from app.memory.auto_learning.reflection.models import ReflectionResult
from app.memory.auto_learning.reflection.reflection_engine import ReflectionEngine

logger = logging.getLogger(__name__)

CORRECTION_PROMPT = ChatPromptTemplate.from_template(
    """你是 Agent 的自我反思系统。Agent 对用户问题的回答质量不足，请生成补正内容。

原始问题：{user_query}
Agent 回答（质量分 {quality_score}/10）：{agent_output}
反思发现的问题：{problems}

请直接生成补正内容（不要重复已有内容，只补充缺失或修正错误的部分）。
格式：直接输出修正后的内容，以"**补充说明：**"开头。"""
)


async def evaluate_and_correct(
    user_query: str,
    agent_output: str,
    tool_calls: list[dict],
    execution_time: float,
    execution_mode: str = "normal",
    llm: BaseChatModel | None = None,
) -> ReflectionAction:
    """Evaluate answer quality; if low quality, generate correction content.

    Args:
        user_query: Original user question
        agent_output: Agent's response text
        tool_calls: Tool call records from execution
        execution_time: Total execution time in seconds
        execution_mode: "tot" | "perv" | "normal"
        llm: Optional LLM override for testing

    Returns:
        ReflectionAction with should_correct, quality_score, correction, reflection
    """
    settings = get_settings()
    threshold = settings.agent_reflection_quality_threshold

    # Step 1: Run reflection evaluation
    engine = ReflectionEngine(llm=llm)
    reflection = await engine.reflect(
        user_query=user_query,
        agent_output=agent_output,
        tool_calls=tool_calls,
        execution_time=execution_time,
    )

    quality_score = reflection.quality_score
    should_correct = quality_score < threshold

    logger.info(
        f"[Reflection] mode={execution_mode}, "
        f"quality={quality_score:.1f}/{threshold}, "
        f"should_correct={should_correct}, "
        f"problems={len(reflection.problems)}"
    )

    # Step 2: Generate correction if quality is below threshold
    correction = None
    if should_correct:
        correction = await _generate_correction(
            user_query=user_query,
            agent_output=agent_output,
            quality_score=quality_score,
            problems=reflection.problems,
            llm=llm or engine.llm,
        )
        if correction:
            logger.info(
                f"[Reflection] Correction generated: {len(correction)} chars"
            )

    return ReflectionAction(
        should_correct=should_correct,
        quality_score=quality_score,
        correction=correction,
        reflection=reflection,
        execution_mode=execution_mode,
    )


async def _generate_correction(
    user_query: str,
    agent_output: str,
    quality_score: float,
    problems: list[str],
    llm: BaseChatModel,
) -> str | None:
    """Generate correction content using LLM.

    Returns:
        Correction text or None on failure.
    """
    try:
        chain = CORRECTION_PROMPT | llm
        response = await chain.ainvoke(
            {
                "user_query": user_query,
                "agent_output": agent_output[:2000],  # Truncate to avoid token limits
                "quality_score": f"{quality_score:.1f}",
                "problems": "; ".join(problems[:5]),  # Limit problems
            }
        )
        content = response.content.strip() if response.content else None
        return content
    except Exception as e:
        logger.warning(f"[Reflection] Correction generation failed: {e}")
        return None
