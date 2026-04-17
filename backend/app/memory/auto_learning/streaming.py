"""流式处理模块 - Pattern Learning 事件流"""

import logging
from collections.abc import AsyncIterator
from typing import Any

from app.memory.auto_learning.nodes import PatternState

logger = logging.getLogger(__name__)


class PatternLearningEventStreamer:
    """
    Pattern Learning 事件流处理器。

    将 LangGraph 节点输出转换为 SSE 流式事件。

    事件类型：
    - patterns_retrieved: 检索到的模式
    - agent_thinking: Agent 思考过程
    - tool_call: 工具调用
    - pattern_extracted: 提取的新模式
    - final_answer: 最终答案
    - error: 错误信息
    """

    @staticmethod
    async def stream_node_events(
        node_name: str,
        state: PatternState
    ) -> AsyncIterator[dict[str, Any]]:
        """
        将节点执行转换为流式事件。

        Args:
            node_name: 节点名称
            state: 当前图状态

        Yields:
            事件字典
        """
        logger.debug(f"Streaming events for node: {node_name}")

        if node_name == "retrieve_patterns":
            # 发送检索到的模式
            yield {
                "type": "patterns_retrieved",
                "patterns": state.get("retrieved_patterns", []),
                "count": len(state.get("retrieved_patterns", [])),
            }

        elif node_name == "agent":
            # 发送 Agent 思考事件
            yield {
                "type": "agent_thinking",
                "message": "Agent is processing...",
            }

            # 如果有工具调用，发送工具调用事件
            messages = state.get("messages", [])
            if messages:
                last_message = messages[-1]
                if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                    tool_calls_data = []
                    for tc in last_message.tool_calls:
                        tool_calls_data.append({
                            "id": tc.get("id", ""),
                            "name": tc.get("name", "unknown"),
                            "args": tc.get("args", {}),
                        })

                    yield {
                        "type": "tool_call",
                        "tool_calls": tool_calls_data,
                        "count": len(tool_calls_data),
                    }

        elif node_name == "extract_pattern":
            # 发送提取的模式
            extracted_pattern = state.get("extracted_pattern")
            if extracted_pattern:
                yield {
                    "type": "pattern_extracted",
                    "pattern": extracted_pattern,
                }
            else:
                yield {
                    "type": "pattern_extracted",
                    "pattern": None,
                    "message": "No pattern extracted",
                }

    @staticmethod
    def create_final_answer_event(final_answer: str) -> dict[str, Any]:
        """创建最终答案事件"""
        return {
            "type": "final_answer",
            "answer": final_answer,
        }

    @staticmethod
    def create_error_event(error: str) -> dict[str, Any]:
        """创建错误事件"""
        return {
            "type": "error",
            "error": error,
        }

    @staticmethod
    def create_start_event() -> dict[str, Any]:
        """创建开始事件"""
        return {
            "type": "start",
            "message": "Starting pattern learning execution",
        }

    @staticmethod
    def create_done_event() -> dict[str, Any]:
        """创建完成事件"""
        return {
            "type": "done",
            "message": "Execution completed",
        }


async def stream_pattern_events(
    node_name: str,
    state: PatternState
) -> AsyncIterator[dict[str, Any]]:
    """
    流式输出 Pattern Learning 事件（便捷包装器）。

    Args:
        node_name: 节点名称
        state: 当前图状态

    Yields:
        事件字典
    """
    streamer = PatternLearningEventStreamer()
    async for event in streamer.stream_node_events(node_name, state):
        yield event
