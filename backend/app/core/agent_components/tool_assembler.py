"""
Tool Call Assembler

从 LLM 流式响应中组装完整的工具调用。

Author: Task 3.1 Implementation
Created: 2026-03-22
"""

import json
import logging
from typing import Any

from app.core.exceptions import ToolExecutionError

logger = logging.getLogger(__name__)


class ToolCallAssembler:
    """
    从 LLM chunks 组装完整的工具调用。

    处理 LangChain 的流式响应，将增量 tool_call_chunks
    组装成完整的 tool_calls 对象。

    Attributes:
        _calls: 存储每个工具调用的增量数据
        _content_parts: 存储所有文本内容
    """

    def __init__(self) -> None:
        """初始化组装器"""
        self._calls: dict[int, dict] = {}
        self._content_parts: list[str] = []
        # 🔧 Track tool calls using auto-incrementing index
        # This handles cases where tool_calls list has only one element per chunk
        self._next_call_index: int = 0
        self._pending_ids: dict[int, str] = {}  # Map position to actual call ID

    def add_chunk(self, chunk: Any) -> None:
        """
        添加流式 chunk 并更新内部状态。

        Args:
            chunk: LangChain 的流式响应 chunk

        Raises:
            ToolExecutionError: 如果工具调用组装失败
        """
        try:
            # 处理文本内容
            if hasattr(chunk, 'content') and chunk.content:
                content_str = str(chunk.content)
                self._content_parts.append(content_str)
                logger.debug(f"[ASSEMBLER] Added content chunk: {len(content_str)} chars")

            # 处理工具调用片段
            if hasattr(chunk, 'tool_calls') and chunk.tool_calls:
                # 🔧 Fix: Use auto-incrementing index for new tool calls
                # This handles the case where each chunk has only one tool_call element
                for position, tc in enumerate(chunk.tool_calls):
                    tc_id = tc.get('id')
                    tc_name = tc.get('name')
                    tc_args = tc.get('args')

                    # Determine if this is a new tool call or continuation
                    has_id = bool(tc_id)
                    has_name = bool(tc_name)

                    if has_id or has_name:
                        # This is the start of a new tool call
                        idx = self._next_call_index
                        self._next_call_index += 1

                        # Check if this ID was seen before (in case id appears in later chunks)
                        if tc_id and tc_id in self._pending_ids:
                            # Reuse the existing index
                            idx = self._pending_ids[tc_id]
                        else:
                            # Create new entry
                            self._calls[idx] = {
                                'id': tc_id or '',
                                'name': tc_name or '',
                                'args': '{}',
                                'index': idx
                            }
                            if tc_id:
                                self._pending_ids[idx] = tc_id
                        logger.debug(f"[ASSEMBLER] Created/renewed tool call: {tc_name} at index {idx}")
                    else:
                        # This is a continuation (has args but no id/name)
                        # Find the most recently created tool call
                        if not self._calls:
                            logger.warning(f"[ASSEMBLER] Skipping args chunk with no existing tool calls")
                            continue

                        # Use the last created index
                        idx = self._next_call_index - 1
                        logger.debug(f"[ASSEMBLER] Continuation chunk, using index {idx}")

                    # Now update the tool call at idx
                    if idx not in self._calls:
                        logger.warning(f"[ASSEMBLER] Index {idx} not found, skipping")
                        continue

                    # Update fields
                    if tc_id:
                        self._calls[idx]['id'] = tc_id
                        self._pending_ids[idx] = tc_id
                    if tc_name:
                        self._calls[idx]['name'] = tc_name

                    # 合并 args
                    if tc_args:
                        existing = self._calls[idx].get('args', '{}')
                        try:
                            # 🔧 Fix: Convert args to string if it's a dict
                            new_args = tc_args
                            if isinstance(new_args, dict):
                                new_args = json.dumps(new_args, ensure_ascii=False)

                            merged = self._merge_args(existing, new_args)
                            self._calls[idx]['args'] = merged
                            logger.debug(f"[ASSEMBLER] Merged args for {self._calls[idx].get('name')}: {len(merged)} chars")
                        except Exception as e:
                            logger.error(f"[ASSEMBLER] Failed to merge args for {self._calls[idx].get('name')}: {e}")
                            raise ToolExecutionError(
                                tool_name=self._calls[idx].get('name', 'unknown'),
                                message=f"Failed to merge tool arguments: {e}",
                                original_error=e
                            ) from e

        except ToolExecutionError:
            raise
        except Exception as e:
            logger.error(f"[ASSEMBLER] Unexpected error processing chunk: {e}", exc_info=True)
            raise ToolExecutionError(
                tool_name="assembler",
                message=f"Failed to process chunk: {e}",
                original_error=e
            ) from e

    def get_completed_calls(self) -> list[dict]:
        """
        获取已完成的工具调用。

        Returns:
            完整的工具调用列表（args已解析为字典）
        """
        # 将args字符串解析为字典，确保前端可以正确处理
        completed = []
        for call in self._calls.values():
            parsed_call = dict(call)
            # 将args字符串解析为字典
            if 'args' in parsed_call:
                try:
                    parsed_call['args'] = json.loads(parsed_call['args'])
                except json.JSONDecodeError:
                    # 如果解析失败，保持为字符串或设为空字典
                    logger.warning(f"[ASSEMBLER] Failed to parse args as JSON for {parsed_call.get('name')}: {parsed_call['args']}")
                    parsed_call['args'] = {}
            completed.append(parsed_call)
        return completed

    def get_all_content(self) -> str:
        """
        获取所有累积的文本内容。

        Returns:
            合并后的完整文本
        """
        return ''.join(self._content_parts)

    def has_pending_calls(self) -> bool:
        """
        检查是否有待处理的工具调用。

        Returns:
            是否有工具调用
        """
        return len(self._calls) > 0

    def reset(self) -> None:
        """重置状态（用于新轮次）"""
        self._calls.clear()
        self._content_parts.clear()
        self._next_call_index = 0
        self._pending_ids.clear()
        logger.debug("[ASSEMBLER] Reset state for new round")

    def get_cleaned_calls(self) -> list[dict]:
        """
        获取清理后的工具调用（移除 'index' 字段，解析args为字典）

        LangChain AIMessage 不接受 'index' 字段，需要清理。
        同时确保 args 是字典而不是字符串。

        Returns:
            清理后的工具调用列表
        """
        cleaned = []
        for tc in self._calls.values():
            # 移除 'index' 字段
            cleaned_tc = {k: v for k, v in tc.items() if k != 'index'}
            # 将args字符串解析为字典
            if 'args' in cleaned_tc:
                try:
                    cleaned_tc['args'] = json.loads(cleaned_tc['args'])
                except json.JSONDecodeError:
                    # 如果解析失败，设为空字典
                    logger.warning(f"[ASSEMBLER] Failed to parse args as JSON for {cleaned_tc.get('name')}: {cleaned_tc['args']}")
                    cleaned_tc['args'] = {}
            cleaned.append(cleaned_tc)
        return cleaned

    def _merge_args(self, existing: str, new: str) -> str:
        """
        智能合并 JSON args 字符串。

        处理 LLM 流式响应中的增量 JSON 片段：
        1. 尝试将现有字符串和新片段作为独立 JSON 解析
        2. 如果都是完整 JSON 对象，合并它们
        3. 如果新片段是增量（不完整），直接拼接
        4. 处理空字符串和空对象的情况

        Args:
            existing: 现有的 args 字符串
            new: 新的 args 片段

        Returns:
            合并后的完整 args

        Raises:
            ValueError: 如果 JSON 解析失败或合并逻辑错误
        """
        # 处理空字符串情况
        if not existing or existing == '{}':
            return new if new else '{}'
        if not new or new == '{}':
            return existing

        # 尝试将两边都解析为 JSON
        try:
            existing_dict = json.loads(existing)
            new_dict = json.loads(new)

            # 都是有效的 JSON 对象，合并它们
            if isinstance(existing_dict, dict) and isinstance(new_dict, dict):
                merged = {**existing_dict, **new_dict}
                result = json.dumps(merged, ensure_ascii=False)
                logger.debug(f"[ASSEMBLER] Merged two JSON objects: {len(existing)} + {len(new)} -> {len(result)} chars")
                return result

            # 如果不是对象，直接拼接
            logger.debug("[ASSEMBLER] One or both args are not objects, concatenating")
            return existing + new

        except json.JSONDecodeError as e:
            # 至少有一边是不完整的 JSON，这是流式响应的正常情况
            # 直接拼接字符串
            logger.debug(f"[ASSEMBLER] JSON decode error (expected in streaming), concatenating: {e}")
            result = existing + new

            # 验证拼接后的结果是否可能是有效的 JSON
            # 这只是一个启发式检查，不保证完全正确
            open_braces = result.count('{')
            close_braces = result.count('}')
            if open_braces < close_braces:
                logger.warning(f"[ASSEMBLER] Suspicious JSON: more closing braces than opening ({open_braces} < {close_braces})")

            return result

        except Exception as e:
            logger.error(f"[ASSEMBLER] Unexpected error merging args: {e}", exc_info=True)
            raise ValueError(f"Failed to merge args: {e}") from e
