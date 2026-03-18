"""
LangGraph Builder for Tree of Thoughts

Builds the StateGraph for ToT reasoning workflow.
"""

import logging
from pathlib import Path
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

from app.core.tot.state import ToTState
from app.core.tot.nodes import (
    thought_generator_node,
    thought_evaluator_node,
    thought_executor_node,
    termination_checker_node
)
from app.core.tot.nodes.termination_checker import should_continue_reasoning

logger = logging.getLogger(__name__)


def build_tot_graph(
    checkpoint_path: str = "data/tot_checkpoints.db"
) -> StateGraph:
    """
    Build LangGraph for Tree of Thoughts reasoning.

    Graph Structure:
    ┌──────────────────┐
    │ Thought Generator│ ─┐
    └──────────────────┘  │
          │               │
          ▼               │
    ┌──────────────────┐  │ Loop until
    │Thought Evaluator │ ─┘ termination
    └──────────────────┘
          │
          ▼
    ┌──────────────────┐
    │Thought Executor  │
    └──────────────────┘
          │
          ▼
    ┌──────────────────┐
    │Termination Check │ ─── continue → Thought Generator
    └──────────────────┘
          │
          └── finalize → END

    Args:
        checkpoint_path: Path to SQLite checkpoint database

    Returns:
        Compiled StateGraph ready for execution
    """
    logger.info("Building Tree of Thoughts graph")

    # Create graph with ToTState schema
    graph = StateGraph(ToTState)

    # Add nodes
    graph.add_node("generate_thoughts", thought_generator_node)
    graph.add_node("evaluate_thoughts", thought_evaluator_node)
    graph.add_node("execute_thoughts", thought_executor_node)
    graph.add_node("check_termination", termination_checker_node)

    logger.info("Added 4 nodes to graph")

    # Define entry point
    graph.set_entry_point("generate_thoughts")

    # Define linear edges (main flow)
    graph.add_edge("generate_thoughts", "evaluate_thoughts")
    graph.add_edge("evaluate_thoughts", "execute_thoughts")
    graph.add_edge("execute_thoughts", "check_termination")

    logger.info("Defined linear edges")

    # Add conditional edge for termination decision
    graph.add_conditional_edges(
        "check_termination",
        should_continue_reasoning,
        {
            "continue": "generate_thoughts",
            "finalize": END
        }
    )

    logger.info("Added conditional routing")

    # Compile graph WITHOUT checkpointer to avoid serialization issues
    # TODO: Implement custom state serialization for tools
    compiled_graph = graph.compile()

    logger.info("Successfully compiled Tree of Thoughts graph (no checkpointer)")

    return compiled_graph


def visualize_graph(graph: StateGraph, output_path: str = "tot_graph.png"):
    """
    Visualize the graph structure (requires graphviz).

    Args:
        graph: Compiled StateGraph
        output_path: Path to save visualization
    """
    try:
        from IPython.display import Image, display

        # Generate visualization
        img = Image(graph.get_graph().draw_mermaid_png())

        # Save to file
        with open(output_path, "wb") as f:
            f.write(img.data)

        logger.info(f"Graph visualization saved to {output_path}")

    except ImportError:
        logger.warning("IPython not available, skipping visualization")
    except Exception as e:
        logger.error(f"Failed to visualize graph: {e}")


def print_graph_structure(graph: StateGraph):
    """
    Print the graph structure for debugging.

    Args:
        graph: Compiled StateGraph
    """
    logger.info("=== Tree of Thoughts Graph Structure ===")

    # Print nodes
    logger.info(f"\nNodes: {list(graph.nodes)}")

    # Print entry point
    logger.info(f"Entry Point: {graph.get_graph().entry_point}")

    # Print edges
    logger.info("\nEdges:")
    for edge in graph.get_graph().edges:
        logger.info(f"  {edge}")

    logger.info("\n=====================================")
