"""
DAG Scheduler - builds execution layers from plan steps for parallel execution.

Uses Kahn's algorithm (topological sort) to convert a flat list of PlanSteps
into layered execution groups where steps in the same layer have no mutual
dependencies and can be safely executed in parallel.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Set

logger = logging.getLogger(__name__)

# Safety classification for parallel tool execution
SAFE_PARALLEL_TOOLS = {"read_file", "fetch_url", "search_kb"}
UNSAFE_PARALLEL_TOOLS = {"write_file", "terminal", "python_repl"}
MAX_PARALLEL = 4


@dataclass
class ExecutionLayer:
    """Single layer of steps that can be executed in parallel."""

    layer_index: int
    steps: List[Dict[str, Any]]
    step_ids: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.step_ids:
            self.step_ids = [s.get("id", f"?{i}") for i, s in enumerate(self.steps)]


def build_execution_layers(
    plan: List[Dict[str, Any]],
) -> List[ExecutionLayer]:
    """Build DAG execution layers from a plan using Kahn's algorithm.

    Algorithm:
    1. Build step_id -> step mapping
    2. Compute in-degrees and dependents adjacency list
    3. BFS level-by-level: each level = one ExecutionLayer
    4. Detect circular dependencies

    Args:
        plan: List of PlanStep dicts with 'id' and 'depends_on' fields.

    Returns:
        List of ExecutionLayer sorted by layer_index.

    Raises:
        ValueError: If circular dependency detected.
    """
    if not plan:
        return []

    # Step 1: Build mappings
    step_map: Dict[str, Dict[str, Any]] = {}
    for step in plan:
        step_id = step.get("id", "")
        if not step_id:
            continue
        step_map[step_id] = step

    if not step_map:
        # Fallback: all steps in one layer (no valid IDs)
        return [ExecutionLayer(layer_index=0, steps=list(plan))]

    # Step 2: Compute in-degrees and dependents
    in_degree: Dict[str, int] = {sid: 0 for sid in step_map}
    dependents: Dict[str, List[str]] = {sid: [] for sid in step_map}

    for sid, step in step_map.items():
        deps = step.get("depends_on", [])
        if not isinstance(deps, list):
            deps = []
        for dep_id in deps:
            if dep_id in step_map:
                in_degree[sid] += 1
                dependents[dep_id].append(sid)

    # Step 3: BFS level-by-level (Kahn's)
    layers: List[ExecutionLayer] = []
    processed: Set[str] = set()

    # Find initial zero-degree nodes
    current_level = [sid for sid, deg in in_degree.items() if deg == 0]

    layer_idx = 0
    while current_level:
        layer_steps = [step_map[sid] for sid in current_level if sid in step_map]
        layers.append(ExecutionLayer(
            layer_index=layer_idx,
            steps=layer_steps,
        ))

        processed.update(current_level)

        # Compute next level
        next_level: List[str] = []
        for sid in current_level:
            for dependent in dependents.get(sid, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    next_level.append(dependent)

        current_level = next_level
        layer_idx += 1

    # Step 4: Circular dependency check
    if len(processed) != len(step_map):
        unprocessed = set(step_map.keys()) - processed
        raise ValueError(
            f"Circular dependency detected among steps: {unprocessed}"
        )

    return layers


def get_max_parallelism(layers: List[ExecutionLayer]) -> int:
    """Return maximum parallelism (max steps in any single layer)."""
    if not layers:
        return 0
    return max(len(layer.steps) for layer in layers)


def adjust_parallelism(layers: List[ExecutionLayer]) -> List[ExecutionLayer]:
    """Adjust layers based on tool safety for parallel execution.

    Rules:
    1. Safe tools (read_file, fetch_url, search_kb) can run in parallel
    2. Unsafe tools (write_file, terminal, python_repl) are forced serial
    3. Max parallelism capped at MAX_PARALLEL (4)
    4. Same skill_group steps keep their original dependencies

    Args:
        layers: Original execution layers from build_execution_layers().

    Returns:
        Adjusted layers with unsafe tools separated into individual layers.
    """
    if not layers:
        return []

    adjusted: List[ExecutionLayer] = []

    for layer in layers:
        safe_steps: List[Dict[str, Any]] = []
        unsafe_steps: List[Dict[str, Any]] = []

        for step in layer.steps:
            tool = step.get("tool", "")
            if tool in SAFE_PARALLEL_TOOLS:
                safe_steps.append(step)
            else:
                unsafe_steps.append(step)

        # Safe steps: batch up to MAX_PARALLEL
        if safe_steps:
            for i in range(0, len(safe_steps), MAX_PARALLEL):
                batch = safe_steps[i:i + MAX_PARALLEL]
                adjusted.append(ExecutionLayer(
                    layer_index=len(adjusted),
                    steps=batch,
                ))

        # Unsafe steps: each gets its own layer (serial execution)
        for step in unsafe_steps:
            adjusted.append(ExecutionLayer(
                layer_index=len(adjusted),
                steps=[step],
            ))

    return adjusted
