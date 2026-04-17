"""Meta Policy 集成辅助 — 统一的元策略决策获取与记录入口。

避免在各集成点 (agent / ToT / PERV / StreamCoordinator) 重复
元策略初始化、嵌入编码、部署阶段判断等逻辑。
与 tca_helpers.py 对称设计。
"""

import logging
from typing import Optional

import torch

logger = logging.getLogger(__name__)


def get_meta_policy_decision(
    query: str,
    ctx: str = "",
    cap_map: Optional[object] = None,
) -> Optional[dict]:
    """获取元策略工具/技能推荐决策。

    处理 feature flag 检查、部署阶段判断、嵌入编码、模型推理、
    注入文本生成全流程。

    Args:
        query: 用户查询文本
        ctx: 上下文文本 (可选)
        cap_map: CapabilityMap 实例 (可选，默认自动创建)

    Returns:
        dict 包含:
            - injection_text: 注入到 prompt 的引导文本
            - action_type: 建议的动作类型 (call_tool/call_skill/think/finish)
            - tool: 推荐的工具名称 (仅 call_tool)
            - skill: 推荐的技能名称 (仅 call_skill)
            - confidence: 决策置信度
            - strategy_type: 策略来源 (baseline/nn_prediction/continuous)
            - stage: 当前部署阶段
        或 None (元策略未启用/未到注入阶段/模型不可用)
    """
    from app.config import get_settings

    settings = get_settings()
    if not getattr(settings, "enable_meta_policy", False):
        return None

    try:
        from app.memory.auto_learning.reflection.strategy_scheduler import get_strategy_scheduler
        from app.memory.auto_learning.nn import get_pattern_nn
        from app.core.meta_policy.capability_map import CapabilityMap
        from app.core.meta_policy.injection import PolicyInjector
        from app.core.meta_policy.types import ActionType

        scheduler = get_strategy_scheduler()
        nn_model = get_pattern_nn()

        # baseline 阶段不注入
        if scheduler.current_stage == "baseline":
            return None

        # 获取 capability_map
        if cap_map is None:
            cap_map = CapabilityMap.from_core_tools()

        tool_index_map = cap_map.get_active_tool_slots()  # {slot_index: tool_name}
        skill_index_map = cap_map.get_active_skill_slots()  # {slot_index: skill_name}

        # 编码查询为 state_vec
        state_vec = None
        try:
            from app.memory.auto_learning.utils import get_embedder
            embedder = get_embedder()
            state_vec = torch.tensor(
                embedder.encode(query), dtype=torch.float32
            )
        except Exception:
            pass

        if state_vec is None or nn_model is None:
            return None

        # 通过 scheduler 获取策略建议 (含渐进比例控制)
        meta_advice = scheduler.get_meta_policy_advice(
            nn_model, state_vec, None, tool_index_map, skill_index_map
        )

        if not meta_advice:
            return None

        # --- 根据 action_id 反推 ActionType ---
        strategy_type = meta_advice.get("strategy_type", "baseline")
        action_id = meta_advice.get("action_id", 0)
        tool_suggestion = meta_advice.get("tool_suggestion")
        skill_suggestion = meta_advice.get("skill_suggestion")
        confidence = meta_advice.get("confidence", 0.0)
        stage = meta_advice.get("stage", scheduler.current_stage)

        # 判断 action_type
        if tool_suggestion:
            action_type = ActionType.CALL_TOOL
        elif skill_suggestion:
            action_type = ActionType.CALL_SKILL
        elif strategy_type == "baseline" or action_id == 0:
            action_type = ActionType.FINISH
        else:
            action_type = ActionType.THINK

        # --- 通过 PolicyInjector 生成渐进注入文本 ---
        injector = PolicyInjector()
        # 将 stage 映射到注入强度
        strength = _stage_to_strength(stage)
        injection_text = injector.build_injection_text(
            action_type=action_type,
            tool=tool_suggestion,
            skill=skill_suggestion,
            confidence=confidence,
            strength=strength,
            stage=stage,
        )

        if not injection_text:
            return None

        logger.debug(
            "[MetaPolicy] Decision: type=%s, tool=%s, skill=%s, "
            "confidence=%.2f, stage=%s, strategy=%s",
            action_type.value, tool_suggestion, skill_suggestion,
            confidence, stage, strategy_type,
        )

        return {
            "injection_text": injection_text,
            "action_type": action_type.value,
            "tool": tool_suggestion,
            "skill": skill_suggestion,
            "confidence": confidence,
            "strategy_type": strategy_type,
            "stage": stage,
            "action_id": action_id,
        }

    except Exception as e:
        logger.debug("[MetaPolicy] get_meta_policy_decision failed: %s", e)
        return None


def record_meta_policy_episode(
    query: str,
    tool_calls: list,
    plan_steps: int = 0,
    task_completed: bool = True,
    reward: float = 0.0,
) -> None:
    """从执行结果中记录元策略训练数据。

    在后执行学习环节 (post-learning) 中调用。
    记录 strategy_type 的表现，用于 StrategyScheduler 的
    渐进阶段推进和回滚判断。

    Args:
        query: 用户查询文本
        tool_calls: 工具调用列表 [{"name": ...}, ...]
        plan_steps: 计划步数
        task_completed: 任务是否成功完成
        reward: 执行奖励 (来自 reflection evaluator)
    """
    from app.config import get_settings

    settings = get_settings()
    if not getattr(settings, "enable_meta_policy", False):
        return

    try:
        from app.memory.auto_learning.reflection.strategy_scheduler import get_strategy_scheduler

        scheduler = get_strategy_scheduler()

        # 使用最后一次决策的 strategy_type
        # 如果没有明确记录，根据工具调用推断
        strategy_type = getattr(scheduler, "_last_strategy_type", "baseline")

        # 更新 episode 计数
        total_episodes = (
            len(scheduler.baseline_rewards)
            + len(scheduler.nn_prediction_rewards)
            + len(scheduler.continuous_rewards)
        )
        scheduler.update_episode_count(total_episodes + 1)

        # 报告性能
        success = task_completed and reward > 0.3
        scheduler.report_performance(
            strategy_type=strategy_type,
            reward=reward if reward > 0 else (0.5 if task_completed else 0.1),
            success=success,
        )

        logger.debug(
            "[MetaPolicy] Recorded episode: strategy=%s, reward=%.3f, success=%s, "
            "total_episodes=%d, stage=%s",
            strategy_type, reward, success, total_episodes + 1, scheduler.current_stage,
        )

    except Exception as e:
        logger.debug("[MetaPolicy] record_meta_policy_episode failed: %s", e)


def _stage_to_strength(stage: str) -> str:
    """将 StrategyScheduler 阶段映射为 PolicyInjector 注入强度。

    Args:
        stage: 阶段名称 (baseline/conservative/nn_dominant/transition/personalized)

    Returns:
        注入强度 (hint/suggest/guide)
    """
    mapping = {
        "baseline": "hint",       # 不应该到这里，但保险起见
        "conservative": "hint",
        "nn_dominant": "suggest",
        "transition": "guide",
        "personalized": "guide",
    }
    return mapping.get(stage, "hint")
