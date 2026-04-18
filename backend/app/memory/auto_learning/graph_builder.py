"""LangGraph builder for pattern memory component."""

from collections.abc import AsyncIterator
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, StateGraph

from app.memory.auto_learning.logging_config import setup_logger
from app.memory.auto_learning.nodes import (
    PatternState,
    agent_node,
    extract_pattern_node,
    retrieve_patterns_node,
)
from app.memory.auto_learning.streaming import PatternLearningEventStreamer

logger = setup_logger(__name__)


def build_pattern_learning_graph() -> StateGraph:
    """
    Build LangGraph for pattern learning.

    Graph Structure:
    retrieve_patterns → agent → extract_pattern → END

    This graph follows the same pattern as miniclaw's Tree of Thoughts graph,
    using StateGraph with explicit node definitions and edges.

    Returns:
        Compiled StateGraph ready for execution
    """
    logger.info("Building pattern learning graph")

    # Create graph with PatternState
    graph = StateGraph(PatternState)

    # Add nodes
    graph.add_node("retrieve_patterns", retrieve_patterns_node)
    graph.add_node("agent", agent_node)
    graph.add_node("extract_pattern", extract_pattern_node)

    logger.info("Added 3 nodes to graph")

    # Define entry point
    graph.set_entry_point("retrieve_patterns")

    # Define linear edges
    graph.add_edge("retrieve_patterns", "agent")
    graph.add_edge("agent", "extract_pattern")
    graph.add_edge("extract_pattern", END)

    logger.info("Defined linear edges")

    # Compile graph
    compiled_graph = graph.compile()

    logger.info("Successfully compiled pattern learning graph")

    return compiled_graph


class AgentWithPatternLearning:
    """
    Agent wrapper with automatic pattern learning.

    This class wraps a LangGraph agent with pattern memory integration,
    enabling automatic pattern injection and learning.

    Example:
        >>> from langchain_openai import ChatOpenAI
        >>> from app.memory.auto_learning.graph_builder import AgentWithPatternLearning
        >>>
        >>> llm = ChatOpenAI(model="gpt-4")
        >>> tools = [...]  # Your tools
        >>>
        >>> agent = AgentWithPatternLearning(llm=llm, tools=tools)
        >>> result = await agent.invoke("What is the capital of France?")
        >>> print(result["final_answer"])
    """

    def __init__(
        self,
        llm: BaseChatModel,
        tools: list[BaseTool],
        system_prompt: str | None = None,
    ):
        """Initialize the agent with pattern learning.

        Args:
            llm: Base LLM instance
            tools: List of tools available to the agent
            system_prompt: Optional custom system prompt
        """
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt or "You are a helpful AI assistant."
        self.graph = build_pattern_learning_graph()

        logger.info("AgentWithPatternLearning initialized")

    async def invoke(self, query: str) -> dict[str, Any]:
        """
        Execute task with pattern learning.

        This method:
        1. Prepares the initial state
        2. Invokes the pattern learning graph
        3. Returns the result

        Args:
            query: User query

        Returns:
            Result dict with:
                - final_answer: Agent's final answer
                - extracted_pattern: Newly extracted pattern
                - retrieved_patterns: Patterns retrieved from memory
        """
        logger.info(f"Invoking agent with query: {query[:50]}...")

        # Prepare initial state
        initial_state: PatternState = {
            "user_query": query,
            "messages": [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=query),
            ],
            "retrieved_patterns": [],
            "extracted_pattern": None,
            "tools": self.tools,
            "llm": self.llm,
            "llm_with_tools": self.llm.bind_tools(tools=self.tools),
            "system_prompt": self.system_prompt,
            "final_answer": None,
        }

        # Invoke graph
        result = await self.graph.ainvoke(initial_state)

        logger.info("Agent execution completed")

        return {
            "final_answer": result["final_answer"],
            "extracted_pattern": result["extracted_pattern"],
            "retrieved_patterns": result["retrieved_patterns"],
        }

    async def stream(self, query: str) -> AsyncIterator[dict[str, Any]]:
        """
        流式执行任务并实时返回事件。

        This method:
        1. Prepares the initial state
        2. Streams the pattern learning graph execution
        3. Yields events in real-time

        Args:
            query: User query

        Yields:
            事件字典，格式：{"type": str, "data": Dict}

        事件类型：
        - start: 执行开始
        - patterns_retrieved: 检索到的模式
        - agent_thinking: Agent 思考过程
        - tool_call: 工具调用
        - pattern_extracted: 提取的新模式
        - final_answer: 最终答案
        - done: 执行完成
        - error: 错误信息

        Example:
            >>> async for event in agent.stream("What is the capital of France?"):
            ...     print(event["type"], event)
        """
        logger.info(f"Streaming agent execution for query: {query[:50]}...")

        streamer = PatternLearningEventStreamer()

        try:
            # 发送开始事件
            yield streamer.create_start_event()

            # Prepare initial state
            initial_state: PatternState = {
                "user_query": query,
                "messages": [
                    SystemMessage(content=self.system_prompt),
                    HumanMessage(content=query),
                ],
                "retrieved_patterns": [],
                "extracted_pattern": None,
                "tools": self.tools,
                "llm": self.llm,
                "llm_with_tools": self.llm.bind_tools(tools=self.tools),
                "system_prompt": self.system_prompt,
                "final_answer": None,
            }

            # Stream graph execution
            async for chunk in self.graph.astream(initial_state):
                # chunk 是一个字典，包含节点名称和状态
                # 格式：{"node_name": state} 或 {"__end__": state}
                for node_name, state in chunk.items():
                    logger.debug(f"Streamed node: {node_name}")

                    # 跳过结束节点
                    if node_name == "__end__":
                        continue

                    # 发送节点事件
                    async for event in streamer.stream_node_events(node_name, state):
                        yield event

            # 获取最终结果并发送最终答案事件
            result = await self.graph.ainvoke(initial_state)
            if result.get("final_answer"):
                yield streamer.create_final_answer_event(result["final_answer"])

            # 发送完成事件
            yield streamer.create_done_event()

            logger.info("Agent streaming completed")

        except Exception as e:
            logger.error(f"Agent streaming failed: {e}", exc_info=True)
            yield streamer.create_error_event(str(e))
