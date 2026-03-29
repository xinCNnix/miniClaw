"""
LangChain Callback Handler for Agent Execution Trajectory

This module provides a LangChain BaseCallbackHandler implementation
that captures Agent execution events and logs them via AgentExecutionLogger.
"""

import logging
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.agents import AgentAction, AgentFinish
from langchain_core.messages import BaseMessage

if TYPE_CHECKING:
    from app.logging_config import AgentExecutionLogger

logger = logging.getLogger(__name__)


class TrajectoryCallbackHandler(BaseCallbackHandler):
    """
    LangChain callback handler for capturing Agent execution trajectory.

    This handler intercepts LangChain events during Agent execution and
    records them using AgentExecutionLogger for complete trajectory tracking.

    Captured events:
    - on_llm_start/end: LLM calls (for thought extraction)
    - on_agent_action: Agent tool calls (action + input)
    - on_tool_start/end: Tool execution (result + success)
    - on_agent_finish: Agent completion

    Args:
        execution_logger: AgentExecutionLogger instance for recording events
        enable_thought_capture: Whether to capture LLM output as thought
        enable_action_capture: Whether to capture agent actions
        enable_result_capture: Whether to capture tool results

    Example:
        ```python
        with AgentExecutionLogger("task_name") as exec_logger:
            handler = TrajectoryCallbackHandler(exec_logger)
            response = await agent.ainvoke(
                messages,
                config={"callbacks": [handler]}
            )
        ```
    """

    def __init__(
        self,
        execution_logger: "AgentExecutionLogger",
        enable_thought_capture: bool = True,
        enable_action_capture: bool = True,
        enable_result_capture: bool = True,
    ):
        """Initialize the trajectory callback handler."""
        super().__init__()
        self.execution_logger = execution_logger
        self.enable_thought_capture = enable_thought_capture
        self.enable_action_capture = enable_action_capture
        self.enable_result_capture = enable_result_capture

        # State tracking
        self._current_thought: Optional[str] = None
        self._current_action: Optional[str] = None
        self._current_input: Optional[Dict] = None
        self._step_start_time: Optional[float] = None
        self._step_number: int = 0

        logger.debug(
            f"TrajectoryCallbackHandler initialized: "
            f"thought={enable_thought_capture}, action={enable_action_capture}, "
            f"result={enable_result_capture}"
        )

    def on_llm_start(
        self,
        prompts: List[str],
        **kwargs: Any,
    ) -> None:
        """Called when LLM starts processing."""
        logger.debug(f"LLM start - prompts count: {len(prompts)}")

    def on_llm_end(
        self,
        response: LLMResult,
        **kwargs: Any,
    ) -> Any:
        """
        Called when LLM finishes processing.

        Extracts the LLM output as the agent's "thought" process.
        """
        if not self.enable_thought_capture:
            return

        try:
            # Extract content from LLM response
            generations = response.generations
            if generations and len(generations) > 0:
                generation = generations[0]
                if generation and len(generation) > 0:
                    message = generation[0].message
                    if hasattr(message, 'content'):
                        self._current_thought = message.content
                        # ✅ 完整记录 LLM 思考过程（修复）
                        logger.info(f"LLM Thought ({len(self._current_thought)} chars):")
                        logger.info(f"  {self._current_thought}")
                    else:
                        logger.debug("LLM message has no content attribute")
        except Exception as e:
            logger.warning(f"Failed to extract thought from LLM response: {e}")
            self._current_thought = None

    def on_agent_action(
        self,
        action: AgentAction,
        **kwargs: Any,
    ) -> Any:
        """
        Called when Agent takes an action (tool call).

        Captures the action name and input arguments.
        """
        if not self.enable_action_capture:
            return

        try:
            self._current_action = action.tool
            self._current_input = action.tool_input
            self._step_start_time = time.time()

            logger.debug(
                f"Agent action: {self._current_action}, "
                f"input keys: {list(self._current_input.keys()) if isinstance(self._current_input, dict) else 'N/A'}"
            )

        except Exception as e:
            logger.warning(f"Failed to capture agent action: {e}")
            self._current_action = None
            self._current_input = None
            self._step_start_time = None

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        """Called when tool execution starts."""
        # ✅ 记录工具开始时间（修复）
        self._step_start_time = time.time()
        tool_name = serialized.get("name", "unknown")
        logger.debug(f"Tool start: {tool_name}")

    def on_tool_end(
        self,
        output: str,
        **kwargs: Any,
    ) -> Any:
        """
        Called when tool execution finishes.

        Records the complete step (thought, action, input, result).
        """
        if not self.enable_result_capture:
            return

        try:
            # Calculate duration
            duration = 0.0
            if self._step_start_time:
                duration = time.time() - self._step_start_time

            # Determine if tool execution was successful
            # Note: LangChain doesn't provide explicit success flag, so we assume
            # success if we reach this handler (exceptions go to on_tool_error)
            success = True

            # Log the complete step
            if self.execution_logger.enable_trajectory:
                # Use current thought (from LLM) or default
                thought = self._current_thought or "Agent action"
                action = self._current_action or "unknown"
                input_data = self._current_input or {}

                self.execution_logger.log_step(
                    thought=thought,
                    action=action,
                    input_data=input_data
                )

                # Log the result
                self.execution_logger.log_step_result(
                    step_number=self._step_number,
                    result=output,
                    success=success,
                    duration=duration
                )

                logger.debug(
                    f"Logged step {self._step_number}: {action} "
                    f"(success={success}, duration={duration:.2f}s)"
                )

                # Increment step counter
                self._step_number += 1

            # Reset state for next step
            self._current_thought = None
            self._current_action = None
            self._current_input = None
            self._step_start_time = None

        except Exception as e:
            logger.warning(f"Failed to log tool result: {e}")

    def on_tool_error(
        self,
        error: Exception,
        **kwargs: Any,
    ) -> Any:
        """
        Called when tool execution raises an exception.

        Records the failed step with error information.
        """
        if not self.enable_result_capture:
            return

        try:
            # Calculate duration
            duration = 0.0
            if self._step_start_time:
                duration = time.time() - self._step_start_time

            # Log the failed step
            if self.execution_logger.enable_trajectory:
                thought = self._current_thought or "Agent action (failed)"
                action = self._current_action or "unknown"
                input_data = self._current_input or {}

                self.execution_logger.log_step(
                    thought=thought,
                    action=action,
                    input_data=input_data
                )

                # Log error result
                self.execution_logger.log_step_result(
                    step_number=self._step_number,
                    result=str(error),
                    success=False,
                    duration=duration
                )

                logger.debug(
                    f"Logged failed step {self._step_number}: {action} "
                    f"(error={str(error)[:100]}, duration={duration:.2f}s)"
                )

                # Increment step counter
                self._step_number += 1

            # Reset state for next step
            self._current_thought = None
            self._current_action = None
            self._current_input = None
            self._step_start_time = None

        except Exception as e:
            logger.warning(f"Failed to log tool error: {e}")

    def on_agent_finish(
        self,
        finish: AgentFinish,
        **kwargs: Any,
    ) -> Any:
        """
        Called when Agent finishes execution.

        Logs the final output.
        """
        try:
            output = finish.return_values.get("output", "")
            logger.debug(f"Agent finish: {len(output)} chars output")

            if self.execution_logger.enable_trajectory:
                self.execution_logger.log_final_output(output)

        except Exception as e:
            logger.warning(f"Failed to log agent finish: {e}")

    @property
    def ignore_llm(self) -> bool:
        """Whether to ignore LLM callbacks."""
        return False

    @property
    def ignore_agent(self) -> bool:
        """Whether to ignore agent callbacks."""
        return False

    @property
    def ignore_chain(self) -> bool:
        """Whether to ignore chain callbacks."""
        return True

    @property
    def ignore_retriever(self) -> bool:
        """Whether to ignore retriever callbacks."""
        return True

    @property
    def raise_errors(self) -> bool:
        """
        Whether to raise errors in callbacks.

        We return False to ensure callback errors don't interrupt execution.
        """
        return False


def create_trajectory_callback_handler(
    execution_logger: "AgentExecutionLogger",
    enable_thought_capture: bool = True,
    enable_action_capture: bool = True,
    enable_result_capture: bool = True,
) -> TrajectoryCallbackHandler:
    """
    Factory function to create a TrajectoryCallbackHandler.

    Args:
        execution_logger: AgentExecutionLogger instance
        enable_thought_capture: Whether to capture LLM output as thought
        enable_action_capture: Whether to capture agent actions
        enable_result_capture: Whether to capture tool results

    Returns:
        Configured TrajectoryCallbackHandler instance

    Example:
        ```python
        with AgentExecutionLogger("task_name") as exec_logger:
            handler = create_trajectory_callback_handler(exec_logger)
            response = await agent.ainvoke(
                messages,
                config={"callbacks": [handler]}
            )
        ```
    """
    return TrajectoryCallbackHandler(
        execution_logger=execution_logger,
        enable_thought_capture=enable_thought_capture,
        enable_action_capture=enable_action_capture,
        enable_result_capture=enable_result_capture,
    )
