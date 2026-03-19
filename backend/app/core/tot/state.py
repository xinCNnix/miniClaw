"""
Tree of Thoughts State Management

Defines the state schema for LangGraph-based Tree of Thoughts reasoning.
"""

from typing import TypedDict, List, Optional, Dict, Any
from typing_extensions import Annotated
from pydantic import BaseModel, Field, ConfigDict
from langchain_core.messages import BaseMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool


def add_thoughts(left: List["Thought"], right: List["Thought"]) -> List["Thought"]:
    """
    Reducer function for adding thoughts to state.
    LangGraph requires this for managing state updates.
    """
    return left + right


class Thought(BaseModel):
    """A single thought in the reasoning tree."""

    id: str = Field(description="Unique thought identifier")
    parent_id: Optional[str] = Field(
        default=None, description="Parent thought ID for tree structure"
    )
    content: str = Field(description="Thought description/reasoning")
    tool_calls: List[Dict[str, Any]] = Field(
        default_factory=list, description="Tools to execute for this thought"
    )
    tool_results: List[Dict[str, Any]] = Field(
        default_factory=list, description="Results from executed tools"
    )
    evaluation_score: Optional[float] = Field(
        default=None, description="Thought quality score (0-10)"
    )
    criteria_scores: Optional[Dict[str, float]] = Field(
        default=None, description="Individual criteria scores"
    )
    status: str = Field(
        default="pending",
        description="Thought status: pending/evaluated/pruned/selected"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "thought_1",
                "parent_id": None,
                "content": "Search for information about quantum computing",
                "tool_calls": [],
                "tool_results": [],
                "evaluation_score": 8.5,
                "criteria_scores": {"relevance": 9.0, "feasibility": 8.0, "novelty": 8.5},
                "status": "evaluated"
            }
        }
    )


class ToTState(TypedDict):
    """
    State for Tree of Thoughts reasoning in LangGraph.

    This state is passed between nodes in the reasoning graph and
    maintains all information about the current reasoning process.
    """

    # Input
    user_query: str
    session_context: Dict[str, Any]
    messages: List[BaseMessage]  # LangChain message history

    # Reasoning Tree
    thoughts: Annotated[List[Thought], add_thoughts]
    current_depth: int
    max_depth: int
    branching_factor: int  # Branching factor for thought generation

    # Best Path Tracking
    best_path: List[str]  # List of thought IDs forming best path
    best_score: float

    # Execution Context
    tools: List[BaseTool]
    llm: BaseChatModel  # Base LLM for thought generation
    llm_with_tools: BaseChatModel  # LLM with tools bound for tool calling
    system_prompt: str

    # Research-specific (optional)
    research_sources: Optional[List[Dict[str, Any]]]
    research_stage: Optional[str]

    # Results
    final_answer: Optional[str]

    # Metadata
    reasoning_trace: List[Dict[str, Any]]  # For streaming to frontend
    fallback_to_simple: bool  # Flag to fall back to simple agent


def get_depth_of_thought(thought: Thought, all_thoughts: List[Thought]) -> int:
    """
    Calculate the depth of a thought in the reasoning tree.

    Args:
        thought: The thought to calculate depth for
        all_thoughts: List of all thoughts for reference

    Returns:
        Depth level (0 for root thoughts)
    """
    depth = 0
    current_id = thought.parent_id

    while current_id:
        # Find parent thought
        parent = next((t for t in all_thoughts if t.id == current_id), None)
        if parent:
            depth += 1
            current_id = parent.parent_id
        else:
            break

    return depth


def get_thoughts_at_depth(
    all_thoughts: List[Thought], target_depth: int
) -> List[Thought]:
    """
    Get all thoughts at a specific depth level.

    Args:
        all_thoughts: List of all thoughts
        target_depth: Target depth level

    Returns:
        List of thoughts at the target depth
    """
    return [
        t for t in all_thoughts
        if get_depth_of_thought(t, all_thoughts) == target_depth
    ]
