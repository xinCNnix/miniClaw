"""
智能停止功能 - 简化版

这个模块实现智能工具停止机制：
1. 简单的基本检查（简单问候、硬编码上限）
2. 每隔 N 轮让 LLM 评估是否应该停止
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class SmartToolStopping:
    """
    智能工具停止机制（简化版）

    功能：
    1. 检测简单问候（不应该调用工具）
    2. LLM 评估信息充分性（每隔几轮）
    3. 硬编码上限防止死循环
    """

    def __init__(
        self,
        evaluation_interval: int = 5,
        hard_limit: int = 60,
        enable: bool = True
    ):
        """
        初始化智能停止机制

        Args:
            evaluation_interval: 每隔几轮让 LLM 评估一次
            hard_limit: 硬编码上限，防止死循环
            enable: 是否启用
        """
        self.evaluation_interval = evaluation_interval
        self.hard_limit = hard_limit
        self.enable = enable

    def should_stop_before_execution(
        self,
        round_count: int,
        tool_name: str,
        tool_args: Dict,
        user_message: str
    ) -> tuple[bool, str]:
        """
        在工具执行前检查是否应该停止

        Returns:
            (should_stop, reason)
        """
        if not self.enable:
            return False, ""

        # 检查 1: 简单问候不应该调用工具
        if self._is_simple_greeting(user_message):
            if round_count == 0 and tool_name:
                return True, "简单问候不需要工具调用"

        return False, ""

    async def should_stop_after_execution(
        self,
        round_count: int,
        user_message: str,
        conversation_messages: List,
        llm
    ) -> tuple[bool, str]:
        """
        在工具执行后检查是否应该停止

        Args:
            round_count: 当前轮数
            user_message: 用户原始消息
            conversation_messages: 对话历史（包含工具调用结果）
            llm: LLM 实例（用于评估）

        Returns:
            (should_stop, reason)
        """
        if not self.enable:
            return False, ""

        # 检查 1: 硬编码上限
        if round_count >= self.hard_limit:
            return True, f"已达到硬编码上限 {self.hard_limit} 轮"

        # 检查 2: 每隔 N 轮让 LLM 评估
        if round_count > 0 and round_count % self.evaluation_interval == 0:
            logger.info(f"[SMART_STOP] 第 {round_count} 轮，让 LLM 评估信息充分性")
            should_stop = await self._llm_evaluate_sufficiency(
                user_message,
                conversation_messages,
                llm
            )
            if should_stop:
                return True, f"LLM 评估认为已有足够信息回答用户问题"

        return False, ""

    def _is_simple_greeting(self, message: str) -> bool:
        """检测是否为简单问候（整个消息只是问候语，不是包含问候语）"""
        import re
        message_lower = message.lower().strip()

        # 先检查是否包含请求关键词（有请求就不是简单问候）
        request_keywords = [
            "请", "帮我", "搜索", "检索", "查找", "分析", "写", "生成", "能不能", "可不可以",
            "please", "help", "search", "find", "analyze", "write", "generate", "can you",
            "arxiv", "论文", "资料", "最新", "recent", "paper", "?", "？"
        ]

        has_request = any(keyword in message_lower for keyword in request_keywords)
        if has_request:
            return False

        # 检查消息长度（超过 15 个字符肯定不是简单问候）
        clean_message = re.sub(r'[^\w\u4e00-\u9fff]', '', message_lower)
        if len(clean_message) > 15:
            return False

        # 简单问候列表（完整匹配）
        simple_greetings = [
            "你好", "hi", "hello", "嗨", "早上好", "下午好", "晚上好",
            "在吗", "在不在", "你是谁", "what's up", "sup", "hey"
        ]

        # 检查消息是否就是简单的问候语（去除空格和标点后完全匹配）
        for greeting in simple_greetings:
            if clean_message == greeting.lower():
                return True

        return False

    async def _llm_evaluate_sufficiency(
        self,
        user_message: str,
        conversation_messages: List,
        llm
    ) -> bool:
        """
        让 LLM 评估当前信息是否充分

        Args:
            user_message: 用户原始消息
            conversation_messages: 对话历史
            llm: LLM 实例

        Returns:
            True if LLM 认为信息充分，False otherwise
        """
        # 构建评估提示
        evaluation_prompt = f"""你是一个智能助手。请评估当前情况：

用户问题：{user_message}

到目前为止，助手已经执行了多轮工具调用。请评估：

1. 当前的工具调用结果是否已经包含足够的信息来回答用户问题？
2. 继续调用工具是否可能获得更有价值的信息？

如果已经获得足够信息，回答 "YES"。
如果还需要更多信息，回答 "NO"。

只回答 YES 或 NO，不要其他内容。"""

        try:
            from langchain_core.messages import HumanMessage

            response = await llm.ainvoke([HumanMessage(content=evaluation_prompt)])
            response_text = response.content.lower().strip() if hasattr(response, 'content') else str(response).lower().strip()

            logger.info(f"[SMART_STOP] LLM 评估结果: {response_text}")

            # 检查是否包含 "yes"
            if "yes" in response_text:
                logger.info("[SMART_STOP] LLM 认为信息已充分，建议停止")
                return True
            else:
                logger.debug("[SMART_STOP] LLM 认为还需要更多信息")
                return False

        except Exception as e:
            logger.error(f"[SMART_STOP] LLM 评估失败: {e}")
            # 评估失败时不停止，继续执行
            return False


# 便捷函数
def should_stop_before_execution(
    settings,
    round_count: int,
    tool_name: str,
    tool_args: Dict,
    user_message: str
) -> tuple[bool, str]:
    """
    工具执行前检查是否应该停止
    """
    if not settings.enable_smart_stopping:
        return False, ""

    stopper = SmartToolStopping(
        evaluation_interval=settings.sufficiency_evaluation_interval,
        hard_limit=settings.max_tool_rounds,
        enable=True
    )

    return stopper.should_stop_before_execution(
        round_count, tool_name, tool_args, user_message
    )


async def should_stop_after_execution(
    settings,
    round_count: int,
    user_message: str,
    conversation_messages: List,
    llm
) -> tuple[bool, str]:
    """
    工具执行后检查是否应该停止
    """
    if not settings.enable_smart_stopping:
        return False, ""

    stopper = SmartToolStopping(
        evaluation_interval=settings.sufficiency_evaluation_interval,
        hard_limit=settings.max_tool_rounds,
        enable=True
    )

    return await stopper.should_stop_after_execution(
        round_count, user_message, conversation_messages, llm
    )


# 向后兼容的旧函数（保留以便其他地方调用）
def should_stop_tool_calling(
    settings,
    round_count: int,
    tool_name: str,
    tool_args: Dict,
    user_message: str,
    current_round_time: float
) -> tuple[bool, str]:
    """
    向后兼容：包装函数，调用 before_execution 版本
    """
    return should_stop_before_execution(
        settings, round_count, tool_name, tool_args, user_message
    )
