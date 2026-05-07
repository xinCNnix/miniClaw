"""Distill node — extracts provisional skill from trajectory via LLM."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from app.core.dream.models import SkillCard
from app.core.online_distill.config import get_distill_config
from app.core.online_distill.models import DistillState, VerifyResult
from app.core.online_distill.prompts.distill import build_distiller_prompt

logger = logging.getLogger(__name__)


def _get_llm(model_name: str):
    """获取蒸馏专用的 LLM 实例。

    复用 main 角色的 base_url/api_key，但覆盖 model 为蒸馏专用模型名称。
    通过 get_role_llm_config 获取原始配置（而非 LLM 实例），
    以便构造自定义参数的 ChatOpenAI 实例。

    Args:
        model_name: 蒸馏目标模型名称

    Returns:
        ChatOpenAI: 配置了蒸馏模型参数的 LLM 实例
    """
    from langchain_openai import ChatOpenAI
    from app.core.model_roles import get_role_llm_config

    # 获取 main 角色的原始 LLM 配置（base_url/api_key）
    base_config = get_role_llm_config("main")
    logger.info(
        f"蒸馏 LLM 初始化: base_url={base_config.base_url}, model={model_name}"
    )
    return ChatOpenAI(
        base_url=base_config.base_url,
        api_key=base_config.api_key,
        model=model_name,
        temperature=0.1,
        streaming=False,
    )


def _parse_skill_json(content: str) -> Optional[Dict]:
    """Parse LLM distillation output to JSON dict."""
    content = content.strip()
    if not content or content.lower() == "null":
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                return None
        return None


def _steps_to_json(steps: list) -> str:
    """Serialize steps to JSON string."""
    if not steps:
        return "[]"
    return json.dumps([asdict(s) if hasattr(s, "__dataclass_fields__") else s for s in steps])


def _tool_calls_to_json(tool_calls: list) -> str:
    """Serialize tool calls to JSON string."""
    if not tool_calls:
        return "[]"
    return json.dumps([asdict(tc) if hasattr(tc, "__dataclass_fields__") else tc for tc in tool_calls])


def _verify_to_json(verify: VerifyResult) -> str:
    """Serialize VerifyResult to JSON string."""
    if verify is None:
        return "{}"
    return json.dumps({
        "success": verify.success,
        "score": verify.score,
        "error_tags": verify.error_tags,
        "should_distill": verify.should_distill,
        "evidence": verify.evidence,
    })


async def distill_node(state: DistillState) -> DistillState:
    """Distill a provisional skill from trajectory via LLM.

    Uses Distiller Prompt with confidence cap of 0.6.
    """
    traj = state.get("trajectory")
    verify = state.get("verify_result")

    if not traj or not verify or not verify.should_distill:
        state["distilled_skill"] = None
        return state

    distill_config = get_distill_config()

    prompt = build_distiller_prompt(
        user_query=traj.user_query,
        final_answer=traj.final_answer,
        task_type=traj.execution_mode,
        steps_json=_steps_to_json(traj.steps),
        tool_logs_json=_tool_calls_to_json(traj.tool_calls),
        verifier_json=_verify_to_json(verify),
        mode="online",
    )

    try:
        llm = _get_llm(distill_config.distill_model)
        response = await llm.ainvoke(prompt)
    except Exception as e:
        logger.warning("[OnlineDistill] LLM call failed: %s", e)
        state["distilled_skill"] = None
        return state

    skill_data = _parse_skill_json(response.content)
    if skill_data is None:
        state["distilled_skill"] = None
        return state

    # Enforce online mode constraints
    skill_data["status"] = "provisional"
    raw_conf = skill_data.get("confidence", 0.3)
    skill_data["confidence"] = min(float(raw_conf), distill_config.max_confidence)
    skill_data.setdefault("source_traj_ids", []).append(traj.traj_id)

    # Ensure required lists
    for key in ("steps", "verification", "anti_patterns", "tags", "examples"):
        skill_data.setdefault(key, [])
    skill_data.setdefault("regression_tests", [])
    skill_data.setdefault("supporting_cases", 0)

    try:
        skill = SkillCard(**skill_data)
    except (TypeError, ValueError) as e:
        logger.warning("[OnlineDistill] Invalid skill data from LLM: %s", e)
        state["distilled_skill"] = None
        return state

    state["distilled_skill"] = skill
    return state
