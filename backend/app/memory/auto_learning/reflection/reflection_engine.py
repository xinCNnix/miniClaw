"""Reflection engine for analyzing agent execution results."""

import asyncio
import logging
import os

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from app.config import get_settings
from app.memory.auto_learning.reflection.models import ReflectionResult

logger = logging.getLogger(__name__)


# Default prompt template for reflection analysis
REFLECTION_PROMPT = ChatPromptTemplate.from_template("""
请分析以下Agent执行结果，提供结构化反思。

**用户查询:**
{user_query}

**Agent输出:**
{agent_output}

**工具调用记录:**
{tool_calls}

**执行时长:**
{execution_time:.2f}秒

请返回JSON格式（不要其他内容）：
{{
    "completed": true/false,
    "task": "任务描述（简洁）",
    "failure_type": "tool_error|planning_error|information_gap|quality_low|unknown|none",
    "root_cause": "根本原因分析（如果失败）",
    "problems": ["问题1", "问题2"],
    "suggestions": ["建议1", "建议2"],
    "reusable_pattern": "可复用策略（如果有，格式：情境→行动→结果）",
    "confidence": 0.8,
    "quality_score": 7.5
}}

**注意：**
1. failure_type 必须是以下之一：
   - tool_error: 工具调用失败
   - planning_error: 规划错误
   - information_gap: 信息不足
   - quality_low: 质量不佳
   - unknown: 未知原因
   - none: 无失败

2. reusable_pattern 格式：在[情境]时，采取[行动]，实现[结果]
   示例：在需要读取多个文件时，先使用glob工具批量查找文件路径，再逐个读取

3. quality_score 范围：0.0-10.0
   - 9.0-10.0: 完美执行
   - 7.0-8.9: 良好执行，有小问题
   - 5.0-6.9: 基本满足，有明显问题
   - 3.0-4.9: 执行失败，但有部分正确
   - 0.0-2.9: 完全失败

4. 评分应综合"工具执行结果"和"文字回答质量"：
   - 工具成功完成用户请求的核心目标（如生图、计算）是基本分
   - 文字解释是否准确、完整、有误导性，决定最终分
   - 工具成功但文字有误：不应超过 7.0
   - 工具失败但文字正确指出了问题：不低于 5.0
   - 两者都好：7.0-10.0

5. 只返回JSON，不要其他内容

JSON:
""")


class ReflectionEngine:
    """LLM-driven reflection engine for analyzing agent execution.

    This class uses LangChain with an LLM to analyze agent execution results
    and generate reflective insights. It supports async methods with retry logic.

    Attributes:
        llm: The LLM instance for reflection analysis
        prompt: The prompt template for reflection
        timeout: Timeout in seconds for LLM calls
        max_retries: Maximum number of retries
    """

    def __init__(
        self,
        llm: BaseChatModel | None = None,
        prompt: ChatPromptTemplate = REFLECTION_PROMPT,
        timeout: int = 30,
        max_retries: int = 3,
    ) -> None:
        """Initialize ReflectionEngine.

        Args:
            llm: Optional LLM instance. If None, creates default LLM
            prompt: Optional prompt template for reflection
            timeout: Timeout in seconds for LLM calls (default: 30)
            max_retries: Maximum number of retries (default: 3)

        Examples:
            >>> engine = ReflectionEngine()
            >>> result = await engine.reflect(
            ...     user_query="What is the weather?",
            ...     agent_output="The weather is sunny.",
            ...     tool_calls=[],
            ...     execution_time=1.5
            ... )
        """
        self.llm = llm or self._get_default_llm()
        self.prompt = prompt
        self.timeout = timeout
        self.max_retries = max_retries

        # Build the chain with JSON output parser
        self.parser = JsonOutputParser()
        self.chain = self.prompt | self.llm | self.parser

        logger.info(
            f"ReflectionEngine initialized with LLM: {type(self.llm).__name__}, "
            f"timeout: {timeout}s, max_retries: {max_retries}"
        )

    def _get_default_llm(self) -> BaseChatModel:
        """Get default LLM instance.

        Returns:
            Configured ChatOpenAI instance

        Note:
            This method attempts to import from miniclaw's LLM module.
            If unavailable, falls back to creating a simple ChatOpenAI instance.
        """
        try:
            # Try to import from miniclaw
            from app.core.llm import get_default_llm as miniclaw_get_llm

            return miniclaw_get_llm()
        except ImportError:
            # Fallback: create a simple ChatOpenAI instance
            logger.warning(
                "miniclaw LLM module not available, using default ChatOpenAI. "
                "Set OPENAI_API_KEY environment variable for production use."
            )
            settings = get_settings()

            # Try to get API key from settings or environment
            api_key = getattr(settings, "openai_api_key", None)
            base_url = getattr(settings, "openai_base_url", None)
            model = getattr(settings, "openai_model", "gpt-4o-mini")

            return ChatOpenAI(
                api_key=api_key,
                base_url=base_url,
                model=model,
                temperature=0.1,
                max_tokens=1000,
            )

    async def reflect(
        self,
        user_query: str,
        agent_output: str,
        tool_calls: list[dict],
        execution_time: float,
    ) -> ReflectionResult:
        """Analyze execution and generate reflection.

        This method uses the LLM to analyze the agent execution and
        generate structured reflection with problems and suggestions.

        Args:
            user_query: Original user query
            agent_output: Agent's output response
            tool_calls: List of tool call records
            execution_time: Execution time in seconds

        Returns:
            ReflectionResult with analysis results

        Raises:
            asyncio.TimeoutError: If LLM call times out after all retries
            ValidationError: If LLM output is not valid ReflectionResult

        Examples:
            >>> engine = ReflectionEngine()
            >>> result = await engine.reflect(
            ...     user_query="What is the weather?",
            ...     agent_output="The weather is sunny.",
            ...     tool_calls=[],
            ...     execution_time=1.5
            ... )
            >>> print(result.completed)
            True
        """
        # Format tool calls for display
        tool_calls_str = self._format_tool_calls(tool_calls)

        # Retry logic with exponential backoff
        for attempt in range(self.max_retries):
            try:
                logger.debug(
                    f"Reflection attempt {attempt + 1}/{self.max_retries} "
                    f"for query: {user_query[:50]}..."
                )

                # Run with timeout
                result_dict = await asyncio.wait_for(
                    self.chain.ainvoke(
                        {
                            "user_query": user_query,
                            "agent_output": agent_output,
                            "tool_calls": tool_calls_str,
                            "execution_time": execution_time,
                        }
                    ),
                    timeout=self.timeout,
                )

                # Validate and create ReflectionResult
                reflection = ReflectionResult(**result_dict)

                logger.info(
                    f"Reflection completed: completed={reflection.completed}, "
                    f"confidence={reflection.confidence:.2f}, "
                    f"problems={len(reflection.problems)}, "
                    f"suggestions={len(reflection.suggestions)}"
                )

                return reflection

            except asyncio.TimeoutError:
                logger.warning(
                    f"Reflection timed out (attempt {attempt + 1}/{self.max_retries})"
                )
                if attempt == self.max_retries - 1:
                    # All retries exhausted, return fallback
                    logger.error("Reflection timed out after all retries")
                    return self._get_fallback_reflection(
                        user_query, agent_output, tool_calls
                    )
                # Exponential backoff before retry
                await asyncio.sleep(2**attempt)

            except ValidationError as e:
                logger.error(f"Invalid reflection output: {e}")
                if attempt >= 1:
                    return self._get_fallback_reflection(
                        user_query, agent_output, tool_calls
                    )
                # Allow 1 retry for validation errors

            except Exception as e:
                logger.error(
                    f"Reflection failed (attempt {attempt + 1}/{self.max_retries}): {e}",
                    exc_info=True,
                )
                if attempt == self.max_retries - 1:
                    # All retries exhausted, return fallback
                    return self._get_fallback_reflection(
                        user_query, agent_output, tool_calls
                    )
                # Exponential backoff before retry
                await asyncio.sleep(2**attempt)

        # Should never reach here, but return fallback just in case
        return self._get_fallback_reflection(user_query, agent_output, tool_calls)

    def _format_tool_calls(self, tool_calls: list[dict]) -> str:
        """Format tool calls for display in prompt.

        Args:
            tool_calls: List of tool call records

        Returns:
            Formatted string representation
        """
        if not tool_calls:
            return "无工具调用"

        formatted = []
        for i, tc in enumerate(tool_calls, 1):
            name = tc.get("name", "unknown")
            success = tc.get("success", True)
            duration = tc.get("duration", 0.0)
            status = "成功" if success else "失败"
            line = f"{i}. {name} - {status} ({duration:.2f}s)"

            gen_images = tc.get("generated_images", [])
            if gen_images:
                filenames = [img["name"] if isinstance(img, dict) else os.path.basename(img) for img in gen_images[:3]]
                line += f" | 生成图片: {len(gen_images)}张 ({', '.join(filenames)})"

            formatted.append(line)

        return "\n".join(formatted)

    def _get_fallback_reflection(
        self,
        user_query: str,
        agent_output: str,
        tool_calls: list[dict],
    ) -> ReflectionResult:
        """Generate fallback reflection when LLM fails.

        Args:
            user_query: Original user query
            agent_output: Agent's output response
            tool_calls: List of tool call records

        Returns:
            Basic ReflectionResult with heuristic analysis
        """
        # Heuristic analysis
        completed = len(agent_output) > 50  # Simple heuristic

        # Check for tool errors
        failed_tools = [tc for tc in tool_calls if not tc.get("success", True)]

        problems = []
        failure_type = "none"
        root_cause = ""

        if failed_tools:
            problems.append(f"{len(failed_tools)} 个工具调用失败")
            failure_type = "tool_error"
            root_cause = "工具调用失败，可能是参数错误或权限问题"

        suggestions = []
        if failed_tools:
            suggestions.append("检查工具调用参数和错误处理")

        # Determine quality score based on completion and errors
        quality_score = 7.0 if completed else 4.0
        if failed_tools:
            quality_score -= 2.0

        return ReflectionResult(
            completed=completed,
            task=user_query[:100],  # Truncate task description
            failure_type=failure_type,
            root_cause=root_cause,
            problems=problems,
            suggestions=suggestions,
            confidence=0.5,  # Low confidence for fallback
            reasoning="Fallback reflection due to LLM failure",
            quality_score=quality_score,
            should_persist=False,  # Don't persist fallback reflections
            evaluation_type="macro_task",
        )


__all__ = ["ReflectionEngine", "REFLECTION_PROMPT"]
