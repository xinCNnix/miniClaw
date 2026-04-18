"""
智能停止功能 - 紧急修复

这个模块实现智能工具停止机制，防止无限制的工具调用循环
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class SmartToolStopping:
    """
    智能工具停止机制

    功能：
    1. 检测冗余工具调用（同样的工具重复调用）
    2. 评估信息充分性（是否已经有足够信息回答）
    3. 强制停止不必要的工具调用
    """

    # 类变量：在所有实例间共享工具调用历史
    # 存储 (tool_name, signature) 元组，signature 基于关键参数生成
    _shared_tool_history: List[tuple] = []

    def __init__(
        self,
        redundancy_window: int = 3,
        sufficiency_interval: int = 2,
        enable: bool = True
    ):
        """
        初始化智能停止机制

        Args:
            redundancy_window: 检测冗余的窗口大小
            sufficiency_interval: 评估充分性的间隔
            enable: 是否启用
        """
        self.redundancy_window = redundancy_window
        self.sufficiency_interval = sufficiency_interval
        self.enable = enable

    @property
    def tool_history(self) -> List[tuple]:
        """获取工具调用历史（使用类变量）"""
        return SmartToolStopping._shared_tool_history

    def reset_history(self):
        """重置工具调用历史（在开始新对话时调用）"""
        SmartToolStopping._shared_tool_history.clear()
        logger.debug("[SMART_STOP] 工具调用历史已重置")

    @staticmethod
    def _make_signature(tool_name: str, tool_args: Dict) -> str:
        """根据工具名和关键参数生成调用签名，用于区分不同的调用"""
        if not tool_args:
            return tool_name

        # read_file: 用 file_path 区分不同文件读取
        if tool_name == "read_file":
            return f"read_file:{tool_args.get('file_path', tool_args.get('path', ''))}"

        # terminal: 用 command 区分不同命令
        if tool_name == "terminal":
            return f"terminal:{tool_args.get('command', '')}"

        # python_repl: 用 code/query 区分不同代码
        if tool_name == "python_repl":
            code = tool_args.get('code', tool_args.get('query', ''))
            return f"python_repl:{code[:100]}"

        # search_kb: 用 query 区分不同搜索
        if tool_name == "search_kb":
            return f"search_kb:{tool_args.get('query', '')}"

        # write_file: 用 file_path 区分
        if tool_name == "write_file":
            return f"write_file:{tool_args.get('file_path', tool_args.get('path', ''))}"

        # 其他工具：使用工具名
        return tool_name

    def should_stop_tool_calling(
        self,
        round_count: int,
        tool_name: str,
        tool_args: Dict,
        user_message: str,
        current_round_time: float
    ) -> tuple[bool, str]:
        """
        判断是否应该停止工具调用

        Returns:
            (should_stop, reason)
        """
        if not self.enable:
            return False, ""

        # 检查 1: 简单问候不应该调用工具
        if self._is_simple_greeting(user_message):
            if round_count == 0 and tool_name:
                return True, "简单问候不需要工具调用"

        # 检查 2: 检测冗余工具调用
        if self._is_redundant_tool_call(tool_name, tool_args):
            return True, f"工具 {tool_name} 重复调用（最近 {self.redundancy_window} 轮内已使用）"

        # 检查 3: 评估信息充分性
        if round_count >= self.sufficiency_interval:
            logger.debug(f"[SMART_STOP] 检查信息充分性：round_count={round_count}, interval={self.sufficiency_interval}, tool={tool_name}")
            if self._has_sufficient_info(round_count, tool_name):
                return True, f"已执行 {round_count} 轮，信息已充分，应该生成回答"

        # 检查 4: 避免无限探索
        if round_count >= 15:
            return True, f"已达到 {round_count} 轮工具调用，避免过度探索"

        return False, ""

    def _is_simple_greeting(self, message: str) -> bool:
        """检测是否为简单问候"""
        message_lower = message.lower().strip()

        # 简单问候关键词
        greetings = [
            "你好", "hi", "hello", "嗨", "早上好", "下午好", "晚上好",
            "在吗", "在不在", "你是谁", "what's up", "sup"
        ]

        # 检查是否包含问候语
        has_greeting = any(greeting in message_lower for greeting in greetings)

        # 如果没有问候语，肯定不是简单问候
        if not has_greeting:
            return False

        # ✅ 修复：检查是否包含请求关键词（如果有，则不是简单问候）
        request_keywords = [
            "请", "帮我", "搜索", "检索", "查找", "分析", "写", "生成",
            "please", "help", "search", "find", "analyze", "write", "generate",
            "arxiv", "论文", "资料", "最新", "recent", "paper"
        ]

        has_request = any(keyword in message_lower for keyword in request_keywords)

        # 如果有请求关键词，不是简单问候
        if has_request:
            logger.debug(f"[SMART_STOP] 消息包含请求关键词，不是简单问候: {message_lower[:50]}")
            return False

        # ✅ 修复：检查消息长度（简单问候应该很短）
        # 去除空格和标点后的纯文本
        import re
        clean_message = re.sub(r'[^\w\u4e00-\u9fff]', '', message_lower)

        # 如果消息很长（>20个字符），不是简单问候
        if len(clean_message) > 20:
            logger.debug(f"[SMART_STOP] 消息过长({len(clean_message)}字符)，不是简单问候")
            return False

        # 通过所有检查，确认为简单问候
        logger.debug(f"[SMART_STOP] 检测到简单问候: {message_lower[:30]}")
        return True

    def _is_redundant_tool_call(self, tool_name: str, tool_args: Dict) -> bool:
        """检测冗余工具调用（基于工具名+关键参数签名，而非仅工具名）"""
        signature = self._make_signature(tool_name, tool_args)

        # 添加签名到历史
        self.tool_history.append((tool_name, signature))

        # 检查窗口内是否有相同的签名重复（同工具+同参数 = 真正冗余）
        recent = self.tool_history[-self.redundancy_window:]
        signature_count = sum(1 for _, sig in recent if sig == signature)

        # 同一个签名在窗口内使用超过 2 次 → 真正的冗余
        if signature_count > 2:
            logger.warning(f"[SMART_STOP] 检测到冗余工具调用: {tool_name} (signature={signature})")
            return True

        # 额外检查：同一工具名（不同参数）连续超过 5 次 → 可能陷入了工具循环
        name_count = sum(1 for name, _ in recent if name == tool_name)
        extended_window = self.tool_history[-(self.redundancy_window * 2):]
        extended_name_count = sum(1 for name, _ in extended_window if name == tool_name)

        if extended_name_count > 5:
            logger.warning(f"[SMART_STOP] 工具 {tool_name} 连续调用 {extended_name_count} 次（不同参数），可能陷入循环")
            return True

        return False

    def _has_sufficient_info(self, round_count: int, current_tool: str) -> bool:
        """评估是否已有足够信息"""
        # 如果已经执行了 10 轮以上的工具调用
        if round_count >= 10:
            # 如果当前还在"探索类"工具（terminal, read_file）
            exploring_tools = ["terminal", "read_file", "search_kb"]
            if current_tool in exploring_tools:
                logger.warning(f"[SMART_STOP] 过度探索：第 {round_count} 轮仍在使用探索类工具")
                return True

        # ✅ 新增：如果已经执行了超过配置的间隔轮数，且仍在探索
        # 避免无限探索，但允许合理的多轮工具调用
        if round_count >= self.sufficiency_interval * 2:  # 至少是配置间隔的 2 倍
            exploring_tools = ["terminal", "read_file", "search_kb"]
            if current_tool in exploring_tools:
                logger.warning(f"[SMART_STOP] 已探索 {round_count} 轮，仍在使用探索类工具 {current_tool}")
                return True

        return False


# 便捷函数
def should_stop_tool_calling(
    settings,
    round_count: int,
    tool_name: str,
    tool_args: Dict,
    user_message: str,
    current_round_time: float
) -> tuple[bool, str]:
    """
    包装函数，便于在 agent.py 中调用
    """
    if not settings.enable_smart_stopping:
        return False, ""

    stopper = SmartToolStopping(
        redundancy_window=settings.redundancy_detection_window,
        sufficiency_interval=settings.sufficiency_evaluation_interval,
        enable=True
    )

    return stopper.should_stop_tool_calling(
        round_count, tool_name, tool_args, user_message, current_round_time
    )


# ── Backward-compatible aliases ──────────────────────────────────────

# should_stop_before_execution was renamed to should_stop_tool_calling
should_stop_before_execution = should_stop_tool_calling


async def should_stop_after_execution(
    settings,
    round_count: int,
    tool_name: str,
    tool_args: Dict,
    user_message: str,
    current_round_time: float,
    execution_result: Any = None,
) -> tuple[bool, str]:
    """Async version of should_stop for post-execution checks.

    Currently delegates to the sync version. Reserved for future
    post-execution heuristics (e.g., result quality analysis).
    """
    return should_stop_tool_calling(
        settings, round_count, tool_name, tool_args,
        user_message, current_round_time,
    )
