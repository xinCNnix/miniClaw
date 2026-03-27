"""Pattern Extractor implementation using LLM."""

import asyncio
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)


# Default prompt template for pattern extraction
DEFAULT_PATTERN_PROMPT = ChatPromptTemplate.from_template("""
你是一个模式提炼专家。请从以下执行记录中，提炼出**一条通用、可复用的模式**。

模式格式：问题 + 根因 + 最佳修复（一句话，简洁明确）

情境: {situation}
执行结果: {outcome}
修复动作: {fix}

只输出一行模式描述，不要解释：
""")


class PatternExtractor:
    """Extract patterns from task execution using LLM.

    This class uses LangChain with an LLM to extract reusable patterns
    from task execution records. It supports both async and sync methods,
    with timeout control and fallback strategies.

    Attributes:
        llm: The LLM instance for pattern extraction
        chain: The LangChain chain (Prompt | LLM | StrOutputParser)
        timeout: Timeout in seconds for LLM calls
    """

    def __init__(
        self,
        llm: BaseChatModel | None = None,
        prompt: ChatPromptTemplate = DEFAULT_PATTERN_PROMPT,
        timeout: int = 30,
    ) -> None:
        """Initialize PatternExtractor.

        Args:
            llm: Optional LLM instance. If None, creates default LLM
            prompt: Optional prompt template for pattern extraction
            timeout: Timeout in seconds for LLM calls (default: 30)

        Examples:
            >>> extractor = PatternExtractor()
            >>> pattern = await extractor.extract(
            ...     situation="API timeout error",
            ...     outcome="Failed after 30s",
            ...     fix="Increased timeout to 60s"
            ... )
        """
        self.llm = llm or self._get_default_llm()
        self.prompt = prompt
        self.timeout = timeout

        # Build the chain: Prompt | LLM | StrOutputParser
        self.chain = self.prompt | self.llm | StrOutputParser()

        logger.info(
            f"PatternExtractor initialized with LLM: {type(self.llm).__name__}, timeout: {timeout}s"
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
                max_tokens=500,
            )

    async def extract(
        self,
        situation: str,
        outcome: str,
        fix: str,
        timeout: int | None = None,
    ) -> str:
        """Extract pattern from execution record (async version).

        Args:
            situation: Task context/situation description
            outcome: Execution result (success/failure details)
            fix: Action taken to fix the issue
            timeout: Optional timeout override in seconds

        Returns:
            Extracted pattern string

        Raises:
            asyncio.TimeoutError: If LLM call times out
            Exception: If LLM call fails (with fallback)

        Examples:
            >>> extractor = PatternExtractor()
            >>> pattern = await extractor.extract(
            ...     situation="Database connection failed",
            ...     outcome="Connection timeout after 10s",
            ...     fix="Increased connection timeout to 30s"
            ... )
            >>> print(pattern)
            'Database connection timeout: Increase timeout from 10s to 30s'
        """
        timeout = timeout or self.timeout

        try:
            logger.debug(f"Extracting pattern from situation: {situation[:50]}...")

            # Run with timeout
            pattern = await asyncio.wait_for(
                self.chain.ainvoke(
                    {
                        "situation": situation,
                        "outcome": outcome,
                        "fix": fix,
                    }
                ),
                timeout=timeout,
            )

            # Clean up the result
            pattern = pattern.strip()
            logger.info(f"Successfully extracted pattern: {pattern[:100]}...")

            return pattern

        except asyncio.TimeoutError:
            logger.error(f"Pattern extraction timed out after {timeout}s")
            # Return fallback pattern
            return self._get_fallback_pattern(situation, outcome, fix)

        except Exception as e:
            logger.error(f"Pattern extraction failed: {e}", exc_info=True)
            # Return fallback pattern
            return self._get_fallback_pattern(situation, outcome, fix)

    def extract_sync(
        self,
        situation: str,
        outcome: str,
        fix: str,
        timeout: int | None = None,
    ) -> str:
        """Extract pattern from execution record (sync version).

        Args:
            situation: Task context/situation description
            outcome: Execution result (success/failure details)
            fix: Action taken to fix the issue
            timeout: Optional timeout override in seconds

        Returns:
            Extracted pattern string

        Raises:
            TimeoutError: If LLM call times out
            Exception: If LLM call fails (with fallback)

        Examples:
            >>> extractor = PatternExtractor()
            >>> pattern = extractor.extract_sync(
            ...     situation="Database connection failed",
            ...     outcome="Connection timeout after 10s",
            ...     fix="Increased connection timeout to 30s"
            ... )
            >>> print(pattern)
            'Database connection timeout: Increase timeout from 10s to 30s'
        """
        timeout = timeout or self.timeout

        try:
            logger.debug(f"Extracting pattern (sync) from situation: {situation[:50]}...")

            # Run with timeout
            pattern = self.chain.invoke(
                {
                    "situation": situation,
                    "outcome": outcome,
                    "fix": fix,
                }
            )

            # Clean up the result
            pattern = pattern.strip()
            logger.info(f"Successfully extracted pattern (sync): {pattern[:100]}...")

            return pattern

        except TimeoutError:
            logger.error(f"Pattern extraction (sync) timed out after {timeout}s")
            # Return fallback pattern
            return self._get_fallback_pattern(situation, outcome, fix)

        except Exception as e:
            logger.error(f"Pattern extraction (sync) failed: {e}", exc_info=True)
            # Return fallback pattern
            return self._get_fallback_pattern(situation, outcome, fix)

    def _get_fallback_pattern(
        self,
        situation: str,
        outcome: str,
        fix: str,
    ) -> str:
        """Generate fallback pattern when LLM fails.

        Args:
            situation: Task context/situation description
            outcome: Execution result
            fix: Action taken

        Returns:
            Simple fallback pattern string
        """
        # Create a simple pattern from the input
        fallback = f"Pattern: {situation[:100]} -> {fix[:100]}"

        logger.warning(f"Using fallback pattern: {fallback[:100]}...")

        return fallback


# Convenience function for quick pattern extraction
async def extract_pattern(
    situation: str,
    outcome: str,
    fix: str,
    llm: BaseChatModel | None = None,
    timeout: int = 30,
) -> str:
    """Quick function to extract pattern (convenience wrapper).

    Args:
        situation: Task context/situation description
        outcome: Execution result
        fix: Action taken
        llm: Optional LLM instance
        timeout: Timeout in seconds

    Returns:
        Extracted pattern string

    Examples:
        >>> pattern = await extract_pattern(
        ...     situation="API error",
        ...     outcome="500 Internal Server Error",
        ...     fix="Added retry logic with exponential backoff"
        ... )
    """
    extractor = PatternExtractor(llm=llm, timeout=timeout)
    return await extractor.extract(situation, outcome, fix)
