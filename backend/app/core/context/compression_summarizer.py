"""CompressionSummarizer — 接收 ExtractedState，调用 LLM 生成结构化状态头，LLM 失败时降级。

工作流程：
1. 将 ExtractedState 中的结构化信息格式化为 prompt
2. 调用 LLM 生成综合状态摘要
3. 如果 LLM 不可用，降级为模板拼装的摘要

输出格式：
- role: "system"（系统角色，不会与 assistant 回复混淆）
- content: 包含 [上下文状态摘要] 标记的结构化文本
- metadata: 包含压缩来源、时间戳、原始消息数等信息
"""
from __future__ import annotations

import logging
import textwrap
from datetime import datetime

from app.core.context.models import ExtractedState

logger = logging.getLogger(__name__)

# LLM prompt 模板：将结构化信息格式化为 LLM 可理解的 prompt
_LLM_PROMPT_TEMPLATE = textwrap.dedent("""\
你是一个上下文压缩助手。以下是之前对话中提取的结构化信息，请综合整理为状态摘要。

## 提取的任务列表
- 已完成: {tasks_completed}
- 进行中: {tasks_in_progress}
- 待完成: {tasks_pending}

## 文件变更记录
{file_changes}

## 工具执行摘要
{tool_narrations}

## 已识别的决策
{decisions}

## 遇到的问题及解决方案
{errors}

## 用户偏好和约束
{user_preferences}

## 用户意图线索
{user_intent_clues}

请按以下格式输出状态摘要：

[上下文状态摘要]
## 目标
{{综合任务列表和意图线索，描述用户的最终目标}}

## 已完成
{{tasks_completed 的详细描述}}

## 关键决策
- {{决策}}: {{理由}}

## 已修改文件
- {{path}}: {{修改内容简述}}

## 遇到的问题及解决方案
- {{问题}}: {{解决方案}}

## 待完成
{{tasks_pending 的描述}}

## 用户约束
{{用户偏好列表}}""")

# 降级模板：LLM 不可用时用模板拼装摘要
_FALLBACK_TEMPLATE = textwrap.dedent("""\
[上下文状态摘要]
## 目标
{intent}

## 已完成
{completed}

## 关键决策
{decisions}

## 已修改文件
{files}

## 遇到的问题及解决方案
{errors}

## 待完成
{pending}

## 用户约束
{preferences}""")


class CompressionSummarizer:
    """接收 StateExtractor 输出 + 需压缩的消息，调用 LLM 生成结构化状态头。

    优先使用 LLM 生成高质量摘要。LLM 不可用时自动降级为模板拼装，
    保证系统在任何情况下都能返回有效的状态摘要。
    """

    async def summarize(
        self,
        state: ExtractedState,
        messages: list[dict],
        llm_config: object,
        llm: object | None = None,
    ) -> dict:
        """生成结构化状态头消息。

        Args:
            state: StateExtractor 提取的结构化状态。
            messages: 原始消息列表（用于统计和降级）。
            llm_config: LLM 配置对象。
            llm: 可选的 LLM 实例（用于测试注入）。如不提供则从配置创建。

        Returns:
            system 角色的状态头消息 dict，包含 role、content、metadata。
        """
        try:
            # 获取 LLM 实例（测试时可注入）
            if llm is None:
                from app.core.llm import create_llm_from_config
                llm = create_llm_from_config(llm_config)

            # 构建 prompt 并调用 LLM
            prompt = self._build_prompt(state)
            from langchain_core.messages import HumanMessage
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            content = response.content

            # 检查 LLM 返回是否有效
            if not content or not content.strip():
                raise ValueError("LLM returned empty response")

            return {
                "role": "system",
                "content": content,
                "metadata": {
                    "type": "compression_summary",
                    "compressed_at": datetime.now().isoformat(),
                    "original_message_count": len(messages),
                    "state_source": "extracted_and_llm",
                },
            }

        except Exception as e:
            # LLM 调用失败，降级为模板摘要
            logger.warning(f"CompressionSummarizer: LLM 调用失败，降级为模板摘要: {e}")
            return self._build_fallback(state, len(messages))

    def _build_prompt(self, state: ExtractedState) -> str:
        """构建 LLM prompt。

        将 ExtractedState 中的各字段格式化为 LLM 可理解的文本，
        包含任务列表、文件变更、工具叙述、决策、错误、用户偏好等。

        Args:
            state: 提取的结构化状态。

        Returns:
            格式化后的 prompt 字符串。
        """
        return _LLM_PROMPT_TEMPLATE.format(
            tasks_completed="; ".join(state.tasks_completed) or "无",
            tasks_in_progress="; ".join(state.tasks_in_progress) or "无",
            tasks_pending="; ".join(state.tasks_pending) or "无",
            file_changes="\n".join(
                f"- {fc.path} ({fc.action}): {fc.key_findings}" for fc in state.file_changes
            ) or "无文件变更",
            tool_narrations="\n".join(f"- {n}" for n in state.tool_narrations) or "无",
            decisions="\n".join(
                f"- {d.decision}: {d.rationale}" for d in state.decisions
            ) or "无",
            errors="\n".join(
                f"- {e.problem}: {e.solution}" for e in state.errors
            ) or "无",
            user_preferences="\n".join(f"- {p}" for p in state.user_preferences) or "无",
            user_intent_clues="\n".join(f"- {c}" for c in state.user_intent_clues) or "无",
        )

    def _build_fallback(self, state: ExtractedState, message_count: int) -> dict:
        """LLM 不可用时，用模板拼装降级摘要。

        直接将 ExtractedState 的各字段填入模板，不依赖 LLM。
        保证在 LLM 完全不可用的情况下仍能输出有效的状态摘要。

        Args:
            state: 提取的结构化状态。
            message_count: 原始消息数量。

        Returns:
            system 角色的降级摘要消息 dict。
        """
        content = _FALLBACK_TEMPLATE.format(
            intent="; ".join(state.user_intent_clues) or "无法确定",
            completed="\n".join(f"- {t}" for t in state.tasks_completed) or "无",
            decisions="\n".join(
                f"- {d.decision}: {d.rationale}" for d in state.decisions
            ) or "无",
            files="\n".join(
                f"- {fc.path} ({fc.action}): {fc.key_findings}" for fc in state.file_changes
            ) or "无",
            errors="\n".join(
                f"- {e.problem} → {e.solution}" for e in state.errors
            ) or "无",
            pending="\n".join(f"- {t}" for t in state.tasks_pending) or "无",
            preferences="\n".join(f"- {p}" for p in state.user_preferences) or "无",
        )
        return {
            "role": "system",
            "content": content,
            "metadata": {
                "type": "compression_summary",
                "compressed_at": datetime.now().isoformat(),
                "original_message_count": message_count,
                "state_source": "extraction_only",
            },
        }
