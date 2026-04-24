"""
LangGraph Builder for Tree of Thoughts

Builds the StateGraph for ToT reasoning workflow.
Unified enhanced graph supports both standard ToT and research modes.
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
from app.core.tot.nodes.synthesis_node import synthesis_node
from app.core.tot.nodes.post_execution_evaluator import post_execution_evaluator_node

# Research nodes imported lazily inside build_tot_graph() to avoid circular imports

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Research-mode conditional routing functions
# ---------------------------------------------------------------------------

def route_after_extraction(state: ToTState) -> str:
    """Route after extractor_node.

    In research mode: if citation chase rounds remain AND coverage < 0.7,
    go to citation_planner; otherwise go to coverage.
    In standard mode: extractor does passthrough, always go to coverage.
    """
    task_mode = state.get("task_mode", "standard")

    if task_mode != "research":
        # Standard mode: skip research sub-graph, go to coverage
        return "coverage"

    # Research mode: check citation chase budget and coverage
    citation_rounds = state.get("citation_chase_rounds", 0)
    citation_max = state.get("citation_chase_max", 2)
    coverage_map = state.get("coverage_map")
    coverage_score = 0.0
    if coverage_map and isinstance(coverage_map, dict):
        coverage_score = coverage_map.get("coverage_score", 0.0)

    if citation_rounds < citation_max and coverage_score < 0.7:
        return "citation_planner"

    return "coverage"


def route_after_contradiction(state: ToTState) -> str:
    """Route after contradiction_node.

    In research mode: if coverage_delta >= min_delta OR first round, call writer;
    otherwise skip writer and go to check_termination.
    In standard mode: skip directly to check_termination.
    """
    task_mode = state.get("task_mode", "standard")

    if task_mode != "research":
        # Standard mode: skip writer
        return "check_termination"

    # Research mode: decide whether to call writer
    coverage_map = state.get("coverage_map")
    coverage_score = 0.0
    if coverage_map and isinstance(coverage_map, dict):
        coverage_score = coverage_map.get("coverage_score", 0.0)

    prev_score = state.get("prev_coverage_score", 0.0)
    min_delta = state.get("writer_min_delta", 0.15)
    research_round = state.get("research_round", 0)

    delta = coverage_score - prev_score
    if delta >= min_delta or research_round <= 1:
        return "write"

    return "check_termination"


def should_re_evaluate(state: ToTState) -> str:
    """Route after execute_thoughts: only re-evaluate when best_score >= threshold.

    Saves LLM calls by skipping re-evaluation when termination is not imminent.
    """
    best_score = state.get("best_score", 0.0)
    quality_threshold = 8.0

    if best_score >= quality_threshold:
        logger.info(
            f"[PostEval-Route] best_score={best_score:.2f} >= {quality_threshold}, "
            f"triggering re-evaluation"
        )
        return "re_evaluate"
    return "skip_to_extractor"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_tot_graph(
    checkpoint_path: str = "data/tot_checkpoints.db"
) -> StateGraph:
    """
    Build LangGraph for Tree of Thoughts reasoning.

    Unified Enhanced Graph (supports both standard and research modes):

    generate → evaluate → execute → [best_score >= 8.0?]
                                       │              │
                                      yes             no
                                       │              │
                                  re_evaluate          │
                                       │              │
                                       └──────┬───────┘
                                              ▼
                                         extractor
                                              │
                                ┌─────────────┴─────────────┐
                                │ route_after_extraction()    │
                                │ citation_chase rounds left? │
                                ▼                            ▼
                          citation_planner            coverage
                                │                            │
                          citation_fetch            contradiction
                                │                     ┌──────┴──────┐
                          (回到 extractor)     write(skip?)    skip
                                                  │              │
                                            check_termination    │
                                             ┌────┴────┐        │
                                      continue   finalize ───────┘
                                         │           │
                                      generate   synthesize_answer
                                                     │
                                                    END

    Non-research mode behavior:
    - extractor: passthrough (raw_sources → evidence_store)
    - coverage/contradiction: skip (set defaults)
    - writer: skip (draft="")
    - citation_*: skip (direct to coverage route)

    Args:
        checkpoint_path: Path to SQLite checkpoint database

    Returns:
        Compiled StateGraph ready for execution
    """
    logger.info("Building unified enhanced Tree of Thoughts graph")

    # Lazy import research nodes to avoid circular imports
    # (research/__init__.py → research_agent → router → graph_builder)
    from app.core.tot.research.nodes.extractor_node import extractor_node
    from app.core.tot.research.nodes.coverage_node import coverage_node
    from app.core.tot.research.nodes.contradiction_node import contradiction_node
    from app.core.tot.research.nodes.writer_node import writer_node
    from app.core.tot.research.nodes.citation_chasing_planner_node import citation_chasing_planner_node
    from app.core.tot.research.nodes.citation_fetch_node import citation_fetch_node

    # Create graph with ToTState schema
    graph = StateGraph(ToTState)

    # --- Core ToT nodes ---
    graph.add_node("generate_thoughts", thought_generator_node)
    graph.add_node("evaluate_thoughts", thought_evaluator_node)
    graph.add_node("execute_thoughts", thought_executor_node)
    graph.add_node("re_evaluate", post_execution_evaluator_node)
    graph.add_node("check_termination", termination_checker_node)
    graph.add_node("synthesize_answer", synthesis_node)

    # --- Research nodes ---
    graph.add_node("extractor", extractor_node)
    graph.add_node("coverage", coverage_node)
    graph.add_node("contradiction", contradiction_node)
    graph.add_node("write", writer_node)
    graph.add_node("citation_planner", citation_chasing_planner_node)
    graph.add_node("citation_fetch", citation_fetch_node)

    logger.info("Added 12 nodes to graph (6 core + 6 research)")

    # --- Entry point ---
    graph.set_entry_point("generate_thoughts")

    # --- Core ToT linear flow ---
    graph.add_edge("generate_thoughts", "evaluate_thoughts")
    graph.add_edge("evaluate_thoughts", "execute_thoughts")

    # execute_thoughts → conditional: re_evaluate or skip to extractor
    graph.add_conditional_edges(
        "execute_thoughts",
        should_re_evaluate,
        {
            "re_evaluate": "re_evaluate",
            "skip_to_extractor": "extractor",
        }
    )
    graph.add_edge("re_evaluate", "extractor")

    # --- Research sub-graph routing ---
    # extractor → route_after_extraction
    graph.add_conditional_edges(
        "extractor",
        route_after_extraction,
        {
            "citation_planner": "citation_planner",
            "coverage": "coverage",
        }
    )

    # citation_planner → citation_fetch (conditional) / coverage (escape hatch)
    def _route_after_citation_planner(state):
        targets = state.get("citation_targets")
        if not targets:
            logger.info("citation_planner returned no targets → routing to coverage")
            return "coverage"
        return "citation_fetch"

    graph.add_conditional_edges(
        "citation_planner",
        _route_after_citation_planner,
        {"citation_fetch": "citation_fetch", "coverage": "coverage"},
    )
    graph.add_edge("citation_fetch", "extractor")

    # coverage → contradiction
    graph.add_edge("coverage", "contradiction")

    # contradiction → route_after_contradiction
    graph.add_conditional_edges(
        "contradiction",
        route_after_contradiction,
        {
            "write": "write",
            "check_termination": "check_termination",
        }
    )

    # write → check_termination
    graph.add_edge("write", "check_termination")

    # --- Termination routing (Phase 5: 三路路由) ---
    graph.add_conditional_edges(
        "check_termination",
        should_continue_reasoning,
        {
            "continue": "generate_thoughts",
            "regenerate": "generate_thoughts",  # Phase 5: 回溯重生成也路由到 generator
            "finalize": "synthesize_answer"
        }
    )

    # synthesize_answer → END
    graph.add_edge("synthesize_answer", END)

    logger.info("Defined all edges and conditional routing")

    # --- Compile ---
    compiled_graph = graph.compile()

    logger.info("Successfully compiled unified enhanced Tree of Thoughts graph")

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
