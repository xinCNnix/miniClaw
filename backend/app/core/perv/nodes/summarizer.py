"""Summarizer 节点 - 压缩观察结果用于中风险任务

仅在 route_decision.risk == "medium" 时激活:
- 高风险任务: 直接传原始数据给 Verifier（不压缩）
- 低风险任务: 跳过 Verifier（不需要摘要）
- 中风险任务: 压缩后传 Verifier（减少 token）

错误时回退到原始观察，确保不丢失数据。
"""

import logging
import time
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_SUMMARIZER_PROMPT = """You are a data summarizer. Compress the following tool execution observations into a structured summary.

Rules:
1. Keep all factual data, numbers, and key findings
2. Remove verbose output, logs, and intermediate steps
3. Structure by tool name and key results
4. Preserve error messages if any
5. Output as numbered observations, one per tool call

Observations to summarize:
{observations}"""


async def summarizer_node(state: dict) -> dict:
    """压缩 Executor 的观察结果，减少后续 Verifier/Finalizer 的 token 消耗。

    仅在 route_decision.risk == "medium" 时使用。
    高风险任务直接传原始数据，低风险任务不走 Verifier。

    Args:
        state: 当前 PlannerState。

    Returns:
        包含 summarized_observations 的状态更新。
    """
    route_decision = state.get("route_decision")
    observations = state.get("observations", [])
    pevr_log = state.get("_pevr_log")

    # 非中风险：透传
    if not route_decision or route_decision.get("risk") != "medium":
        logger.debug(
            "Summarizer skipped: risk=%s",
            route_decision.get("risk") if route_decision else "none",
        )
        return {"summarized_observations": None}

    # 空观察：直接返回
    if not observations:
        logger.debug("Summarizer: no observations to summarize")
        return {"summarized_observations": []}

    start_time = time.monotonic()

    try:
        from app.config import get_settings
        settings = get_settings()

        if not getattr(settings, "perv_summarizer_enabled", True):
            logger.debug("Summarizer disabled by config")
            return {"summarized_observations": None}

        max_tokens = getattr(settings, "perv_summarizer_max_tokens", 500)

        # 格式化观察结果
        obs_text_parts = []
        for i, obs in enumerate(observations):
            tool = obs.get("tool", "unknown")
            status = obs.get("status", "unknown")
            result = obs.get("result", "")
            # 截断过长的结果
            result_str = str(result)
            if len(result_str) > 500:
                result_str = result_str[:500] + "...[truncated]"
            obs_text_parts.append(
                f"[{i+1}] Tool: {tool} | Status: {status}\nResult: {result_str}"
            )

        obs_text = "\n\n".join(obs_text_parts)

        # 调用 LLM 摘要
        from app.core.llm import create_llm
        from langchain_core.messages import HumanMessage, SystemMessage

        llm = create_llm(get_settings().llm_provider)
        bound_llm = llm.bind(max_tokens=max_tokens, temperature=0.0)

        messages = [
            SystemMessage(content="You are a data summarizer. Output concise numbered observations."),
            HumanMessage(content=_SUMMARIZER_PROMPT.format(observations=obs_text)),
        ]

        response = await bound_llm.ainvoke(messages)
        summary_text = response.content if hasattr(response, "content") else str(response)

        # 分割为摘要列表
        summaries = [
            line.strip()
            for line in summary_text.strip().split("\n")
            if line.strip()
        ]

        elapsed_ms = (time.monotonic() - start_time) * 1000
        logger.info(
            "Summarizer: %d observations -> %d summaries (%.1fms)",
            len(observations), len(summaries), elapsed_ms,
        )

        # 记录到 PEVRLogger（如果方法存在）
        if pevr_log and hasattr(pevr_log, "log_custom_phase"):
            try:
                pevr_log.log_custom_phase(
                    phase="summarization",
                    duration_ms=elapsed_ms,
                    details={
                        "input_count": len(observations),
                        "output_count": len(summaries),
                    },
                )
            except Exception:
                pass  # 日志失败不影响主流程

        return {"summarized_observations": summaries}

    except Exception as e:
        elapsed_ms = (time.monotonic() - start_time) * 1000
        logger.error("Summarizer failed (%.1fms): %s", elapsed_ms, e, exc_info=True)
        # 错误时回退到原始观察
        return {"summarized_observations": None}
