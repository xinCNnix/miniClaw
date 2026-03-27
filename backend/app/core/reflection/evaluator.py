"""
Unified Evaluation Framework

Avoids duplicate LLM calls by providing a single evaluation interface
that distinguishes between LLM micro-evaluations (not persisted) and
Agent macro-evaluations (persisted).

Key Design:
- LLM Micro: Execution-time, implicit, not persisted (should_persist=False)
- Agent Macro: Post-execution, explicit, persisted (should_persist=True)
"""

import hashlib
import json
import logging
import time
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage

from app.core.tot.nodes.thought_evaluator import (
    _build_evaluation_prompt,
    _parse_evaluation_scores,
)
from app.core.tot.nodes.termination_checker import ToTSmartStopping
from app.memory.auto_learning.reflection.models import ReflectionResult

logger = logging.getLogger(__name__)


EvaluationType = Literal[
    "micro_quality",  # LLM层：thought质量评分
    "micro_sufficiency",  # LLM层：信息充分性判断
    "macro_task",  # Agent层：任务完成度评估
    "macro_failure",  # Agent层：失败原因分析
]


class EvaluationResult:
    """
    统一评估结果

    Attributes:
        evaluation_type: 评估类型（micro_* 或 macro_*）
        scores: 评分字典（质量分数、充分性等）
        should_persist: 是否持久化到记忆
        reflection: 完整的反思结果（仅宏观评估）
    """

    def __init__(
        self,
        evaluation_type: str,
        scores: dict[str, float] | None = None,
        should_persist: bool = False,
        reflection: ReflectionResult | None = None,
    ):
        self.evaluation_type = evaluation_type
        self.scores = scores or {}
        self.should_persist = should_persist
        self.reflection = reflection

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "evaluation_type": self.evaluation_type,
            "scores": self.scores,
            "should_persist": self.should_persist,
            "reflection": self.reflection.to_dict() if self.reflection else None,
        }


class UnifiedEvaluator:
    """
    统一评估接口 - 避免多重LLM调用

    职责：
    1. LLM微观评估（执行中）：质量评分、充分性判断
    2. Agent宏观评估（执行后）：任务完成度、失败分析

    关键：通过评估类型（evaluation_type）区分层级
    """

    def __init__(self, llm: BaseChatModel, cache_enabled: bool = True):
        """
        初始化统一评估器

        Args:
            llm: 基础LLM模型
            cache_enabled: 是否启用缓存
        """
        self.llm = llm
        self.cache_enabled = cache_enabled
        self._cache: dict[str, dict] = {}

        # 复用现有组件
        self.smart_stopping = ToTSmartStopping()

        logger.info(f"UnifiedEvaluator initialized with cache_enabled={cache_enabled}")

    async def evaluate(
        self,
        evaluation_type: EvaluationType,
        context: dict[str, Any],
    ) -> EvaluationResult:
        """
        统一评估入口

        关键设计：
        1. 根据类型决定是否持久化
        2. 复用现有评估逻辑（避免重复）
        3. 缓存机制（避免重复LLM调用）

        Args:
            evaluation_type: 评估类型
            context: 评估上下文

        Returns:
            EvaluationResult: 评估结果
        """
        # 检查缓存
        if self.cache_enabled:
            cached = self._get_from_cache(evaluation_type, context)
            if cached:
                logger.debug(f"Cache hit for {evaluation_type}")
                return cached

        # 执行评估
        if evaluation_type.startswith("micro_"):
            result = await self._micro_evaluate(evaluation_type, context)
            result.should_persist = False  # LLM层不持久化
        else:
            result = await self._macro_evaluate(evaluation_type, context)
            result.should_persist = True  # Agent层持久化

        # 缓存结果
        if self.cache_enabled:
            self._set_to_cache(evaluation_type, context, result)

        return result

    async def _micro_evaluate(
        self,
        evaluation_type: str,
        context: dict[str, Any],
    ) -> EvaluationResult:
        """
        LLM微观评估

        复用现有评估逻辑：
        - micro_quality → thought_evaluator._build_evaluation_prompt()
        - micro_sufficiency → termination_checker.llm_evaluate_sufficiency()
        """
        if evaluation_type == "micro_quality":
            return await self._evaluate_thought_quality(context)
        elif evaluation_type == "micro_sufficiency":
            return await self._evaluate_sufficiency(context)
        else:
            raise ValueError(f"Unknown micro evaluation type: {evaluation_type}")

    async def _macro_evaluate(
        self,
        evaluation_type: str,
        context: dict[str, Any],
    ) -> EvaluationResult:
        """
        Agent宏观评估

        复用现有评估逻辑：
        - macro_task → reflection_engine.reflect()
        - macro_failure → reflection_engine.reflect() + 失败分析
        """
        if evaluation_type == "macro_task":
            return await self._evaluate_task_completion(context)
        elif evaluation_type == "macro_failure":
            return await self._evaluate_failure(context)
        else:
            raise ValueError(f"Unknown macro evaluation type: {evaluation_type}")

    async def _evaluate_thought_quality(
        self,
        context: dict[str, Any],
    ) -> EvaluationResult:
        """
        评估 thought 质量（LLM微观）

        复用 thought_evaluator 的评估逻辑
        """
        thought = context.get("thought")
        user_query = context.get("user_query")
        all_thoughts = context.get("thoughts", [])

        if not thought or not user_query:
            logger.warning("Missing required context for quality evaluation")
            return EvaluationResult(
                evaluation_type="micro_quality",
                scores={"relevance": 5.0, "feasibility": 5.0, "novelty": 5.0},
            )

        try:
            # 复用现有提示词构建逻辑
            prompt = _build_evaluation_prompt(thought, user_query, all_thoughts)

            # 获取评估
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])

            # 复用现有评分解析逻辑
            scores = _parse_evaluation_scores(response.content)

            logger.debug(f"Thought quality scores: {scores}")

            return EvaluationResult(
                evaluation_type="micro_quality",
                scores=scores,
            )

        except Exception as e:
            logger.error(f"Error evaluating thought quality: {e}")
            return EvaluationResult(
                evaluation_type="micro_quality",
                scores={"relevance": 5.0, "feasibility": 5.0, "novelty": 5.0},
            )

    async def _evaluate_sufficiency(
        self,
        context: dict[str, Any],
    ) -> EvaluationResult:
        """
        评估信息充分性（LLM微观）

        复用 termination_checker 的评估逻辑
        """
        from app.core.tot.state import ToTState, Thought

        user_query = context.get("user_query")
        thoughts_data = context.get("thoughts", [])
        current_depth = context.get("current_depth", 0)

        if not user_query:
            logger.warning("Missing required context for sufficiency evaluation")
            return EvaluationResult(
                evaluation_type="micro_sufficiency",
                scores={"sufficiency": 0.5},
            )

        try:
            # 构建 ToTState（临时，用于调用 llm_evaluate_sufficiency）
            # 注意：这里需要创建一个最小化的 ToTState
            thoughts = []
            for t in thoughts_data:
                if isinstance(t, Thought):
                    thoughts.append(t)
                elif isinstance(t, dict):
                    # 从字典创建 Thought 对象
                    thoughts.append(
                        Thought(
                            id=t.get("id", ""),
                            parent_id=t.get("parent_id"),
                            content=t.get("content", ""),
                            tool_calls=t.get("tool_calls", []),
                            tool_results=t.get("tool_results", []),
                            evaluation_score=t.get("evaluation_score"),
                            criteria_scores=t.get("criteria_scores"),
                            status=t.get("status", "pending"),
                        )
                    )

            # 创建临时 state
            temp_state = {
                "user_query": user_query,
                "thoughts": thoughts,
                "current_depth": current_depth,
                "llm": self.llm,
            }  # 类型: ToTState

            # 复用 ToTSmartStopping 的评估逻辑
            sufficient, _ = await self.smart_stopping.llm_evaluate_sufficiency(temp_state)

            # 转换为评分格式
            sufficiency_score = 0.0 if sufficient else 1.0

            logger.debug(
                f"Sufficiency evaluation: sufficient={sufficient}, score={sufficiency_score}"
            )

            return EvaluationResult(
                evaluation_type="micro_sufficiency",
                scores={"sufficiency": sufficiency_score},
            )

        except Exception as e:
            logger.error(f"Error evaluating sufficiency: {e}")
            return EvaluationResult(
                evaluation_type="micro_sufficiency",
                scores={"sufficiency": 0.5},
            )

    async def _evaluate_task_completion(
        self,
        context: dict[str, Any],
    ) -> EvaluationResult:
        """
        评估任务完成度（Agent宏观）

        调用 reflection_engine 进行完整反思
        """
        # 导入在这里避免循环依赖
        from app.memory.auto_learning.reflection.reflection_engine import (
            ReflectionEngine,
        )

        user_query = context.get("user_query", "")
        agent_output = context.get("agent_output", context.get("agent_response", ""))
        tool_calls = context.get("tool_calls", [])

        if not user_query or not agent_output:
            logger.warning("Missing required context for task evaluation")
            return EvaluationResult(
                evaluation_type="macro_task",
                scores={"quality": 5.0},
                reflection=ReflectionResult(
                    completed=False,
                    problems=["Missing context for evaluation"],
                    confidence=0.0,
                ),
            )

        try:
            # 使用 ReflectionEngine 进行完整反思
            engine = ReflectionEngine(llm=self.llm)
            reflection = await engine.reflect(
                user_query=user_query,
                agent_output=agent_output,
                tool_calls=tool_calls,
            )

            # 提取质量分数
            quality_score = 7.0 if reflection.completed else 4.0

            logger.info(
                f"Task completion evaluation: completed={reflection.completed}, "
                f"quality={quality_score}"
            )

            return EvaluationResult(
                evaluation_type="macro_task",
                scores={"quality": quality_score},
                reflection=reflection,
            )

        except Exception as e:
            logger.error(f"Error evaluating task completion: {e}")
            return EvaluationResult(
                evaluation_type="macro_task",
                scores={"quality": 5.0},
                reflection=ReflectionResult(
                    completed=False,
                    problems=[f"Evaluation error: {str(e)}"],
                    confidence=0.0,
                ),
            )

    async def _evaluate_failure(
        self,
        context: dict[str, Any],
    ) -> EvaluationResult:
        """
        评估失败原因（Agent宏观）

        调用 reflection_engine 进行失败分析
        """
        # 导入在这里避免循环依赖
        from app.memory.auto_learning.reflection.reflection_engine import (
            ReflectionEngine,
        )

        user_query = context.get("user_query", "")
        agent_output = context.get("agent_output", context.get("agent_response", ""))
        tool_calls = context.get("tool_calls", [])
        error_message = context.get("error_message", "")

        if not user_query:
            logger.warning("Missing required context for failure evaluation")
            return EvaluationResult(
                evaluation_type="macro_failure",
                scores={"quality": 3.0},
                reflection=ReflectionResult(
                    completed=False,
                    problems=["Missing context for failure analysis"],
                    confidence=0.0,
                ),
            )

        try:
            # 使用 ReflectionEngine 进行失败分析
            engine = ReflectionEngine(llm=self.llm)

            # 在输出中包含错误信息
            output_with_error = agent_output
            if error_message:
                output_with_error = f"{agent_output}\n\nError: {error_message}"

            reflection = await engine.reflect(
                user_query=user_query,
                agent_output=output_with_error,
                tool_calls=tool_calls,
            )

            # 失败情况下质量分数较低
            quality_score = 3.0

            logger.info(f"Failure evaluation: problems={len(reflection.problems)}")

            return EvaluationResult(
                evaluation_type="macro_failure",
                scores={"quality": quality_score},
                reflection=reflection,
            )

        except Exception as e:
            logger.error(f"Error evaluating failure: {e}")
            return EvaluationResult(
                evaluation_type="macro_failure",
                scores={"quality": 3.0},
                reflection=ReflectionResult(
                    completed=False,
                    problems=[f"Failure analysis error: {str(e)}"],
                    confidence=0.0,
                ),
            )

    def _get_from_cache(
        self,
        evaluation_type: str,
        context: dict[str, Any],
    ) -> EvaluationResult | None:
        """从缓存获取评估结果"""
        key = self._generate_cache_key(evaluation_type, context)

        if key in self._cache:
            entry = self._cache[key]
            if time.time() - entry["timestamp"] < 300:  # 5分钟TTL
                logger.debug(f"Cache hit: {evaluation_type}")
                return entry["result"]
            else:
                del self._cache[key]  # 过期，删除

        return None

    def _set_to_cache(
        self,
        evaluation_type: str,
        context: dict[str, Any],
        result: EvaluationResult,
    ):
        """缓存评估结果"""
        key = self._generate_cache_key(evaluation_type, context)

        # LRU 淘汰（简单实现：超过1000个条目时删除最旧的）
        if len(self._cache) >= 1000:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k]["timestamp"])
            del self._cache[oldest_key]

        self._cache[key] = {
            "result": result,
            "timestamp": time.time(),
        }

        logger.debug(f"Cached: {evaluation_type}")

    @staticmethod
    def _generate_cache_key(evaluation_type: str, context: dict[str, Any]) -> str:
        """生成缓存键"""
        # 处理 Pydantic 模型和其他不可序列化的对象
        serializable_context = {}

        for key, value in context.items():
            # 如果是 Pydantic 模型，使用 model_dump() 或 dict()
            if hasattr(value, "model_dump"):
                # Pydantic v2
                serializable_context[key] = value.model_dump()
            elif hasattr(value, "dict"):
                # Pydantic v1
                serializable_context[key] = value.dict()
            elif isinstance(value, (list, tuple)):
                # 处理列表中的 Pydantic 模型
                serializable_list = []
                for item in value:
                    if hasattr(item, "model_dump"):
                        serializable_list.append(item.model_dump())
                    elif hasattr(item, "dict"):
                        serializable_list.append(item.dict())
                    else:
                        serializable_list.append(item)
                serializable_context[key] = serializable_list
            else:
                serializable_context[key] = value

        # 基于 evaluation_type 和 context 生成哈希
        content = f"{evaluation_type}:{json.dumps(serializable_context, sort_keys=True)}"
        return hashlib.md5(content.encode()).hexdigest()

    def get_cache_stats(self) -> dict[str, Any]:
        """获取缓存统计信息"""
        total = len(self._cache)
        # 简化统计：不区分hit/miss（需要在实际调用中跟踪）
        return {
            "total_entries": total,
            "max_size": 1000,
            "ttl_seconds": 300,
        }

    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        logger.info("Evaluation cache cleared")


# 全局单例
_evaluator: UnifiedEvaluator | None = None


def get_unified_evaluator() -> UnifiedEvaluator:
    """获取统一评估器单例"""
    global _evaluator
    if _evaluator is None:
        from app.config import settings
        from langchain_openai import ChatOpenAI

        # 使用配置的LLM
        llm = ChatOpenAI(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            api_key=settings.openai_api_key,
        )

        _evaluator = UnifiedEvaluator(
            llm=llm,
            cache_enabled=settings.evaluation_cache_enabled,
        )

    return _evaluator


def reset_unified_evaluator():
    """重置统一评估器（主要用于测试）"""
    global _evaluator
    _evaluator = None
