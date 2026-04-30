"""
Mutator — Generates trajectory mutations for Dream exploration.

Supports 8 mutation strategies:
  constraint_flip, scale_up, scale_down, error_injection,
  goal_variant, tool_restriction, edge_case, adversarial
"""

import json
import logging
import uuid
from typing import List

from app.core.dream.models import (
    DreamBatch,
    DreamState,
    DreamTrajectory,
    MutationSpec,
)

logger = logging.getLogger(__name__)

# Mutation templates (offline, no LLM required for basic mutations)
_CONSTRAINT_FLIP_TEMPLATES = [
    ("Reverse the ordering requirement", ["reverse order", "sort descending"]),
    ("Change strict to fuzzy matching", ["fuzzy match", "approximate"]),
    ("Remove one constraint and add another", ["relaxed constraint"]),
    ("Invert the success criteria", ["inverted expectation"]),
]

_SCALE_UP_TEMPLATES = [
    ("Handle 10x more data", ["large scale", "batch processing"]),
    ("Apply to multiple files instead of one", ["multi-file"]),
    ("Expand scope to full system", ["system-wide"]),
]

_SCALE_DOWN_TEMPLATES = [
    ("Handle minimal input", ["minimal input", "edge case"]),
    ("Single file only", ["single file"]),
    ("Reduce to core logic only", ["minimal scope"]),
]

_ERROR_INJECTION_TEMPLATES = [
    ("File not found scenario", ["missing file", "file not found"]),
    ("Network timeout scenario", ["timeout", "network error"]),
    ("Invalid input format", ["invalid input", "malformed data"]),
    ("Permission denied", ["permission denied", "access denied"]),
]

_GOAL_VARIANT_TEMPLATES = [
    ("Achieve the same result with different approach", ["alternative approach"]),
    ("Optimize for speed instead of correctness", ["speed optimization"]),
    ("Optimize for memory efficiency", ["memory optimization"]),
]

_TOOL_RESTRICTION_TEMPLATES = [
    ("Solve without using terminal", ["no terminal", "restricted tools"]),
    ("Solve without code execution", ["no code execution"]),
    ("Use only read-only tools", ["read-only mode"]),
]

_EDGE_CASE_TEMPLATES = [
    ("Empty input", ["empty input"]),
    ("Unicode and special characters", ["unicode", "special chars"]),
    ("Very long input string", ["long input"]),
    ("Concurrent access scenario", ["concurrency", "race condition"]),
]

_ADVERSARIAL_TEMPLATES = [
    ("Prompt injection attempt", ["injection", "security"]),
    ("Conflicting instructions", ["conflict", "ambiguous"]),
    ("Resource exhaustion scenario", ["resource limit", "OOM"]),
]

_TEMPLATE_MAP = {
    "constraint_flip": _CONSTRAINT_FLIP_TEMPLATES,
    "scale_up": _SCALE_UP_TEMPLATES,
    "scale_down": _SCALE_DOWN_TEMPLATES,
    "error_injection": _ERROR_INJECTION_TEMPLATES,
    "goal_variant": _GOAL_VARIANT_TEMPLATES,
    "tool_restriction": _TOOL_RESTRICTION_TEMPLATES,
    "edge_case": _EDGE_CASE_TEMPLATES,
    "adversarial": _ADVERSARIAL_TEMPLATES,
}

_DIFFICULTY_MAP = {
    "edge_case": "easy",
    "constraint_flip": "medium",
    "scale_down": "easy",
    "scale_up": "hard",
    "error_injection": "medium",
    "goal_variant": "medium",
    "tool_restriction": "hard",
    "adversarial": "hard",
}

MUTATION_TYPES = list(_TEMPLATE_MAP.keys())


def _generate_mutations_for_traj(
    traj: DreamTrajectory,
    count: int,
) -> List[MutationSpec]:
    """Generate mutations for a single trajectory using templates."""
    import random

    specs: List[MutationSpec] = []
    # Select mutation types, weighted toward error_injection and goal_variant
    types = list(_TEMPLATE_MAP.keys())
    weights = [
        1.5 if t in ("error_injection", "goal_variant", "constraint_flip") else 1.0
        for t in types
    ]

    selected_types = []
    for _ in range(count):
        # Weighted selection
        total = sum(weights)
        r = random.uniform(0, total)
        cumulative = 0.0
        pick = types[0]
        for t, w in zip(types, weights):
            cumulative += w
            if r <= cumulative:
                pick = t
                break
        selected_types.append(pick)

    for mut_type in selected_types:
        templates = _TEMPLATE_MAP[mut_type]
        template = random.choice(templates)
        desc, constraints = template

        # Build new task description
        base_task = traj.task or "unknown task"
        if mut_type == "constraint_flip":
            new_task = f"[Flipped constraints] {base_task} — {desc}"
        elif mut_type == "scale_up":
            new_task = f"[Scale up] {base_task} — {desc}"
        elif mut_type == "scale_down":
            new_task = f"[Scale down] {base_task} — {desc}"
        elif mut_type == "error_injection":
            new_task = f"[Error injected] {base_task} — {desc}"
        elif mut_type == "goal_variant":
            new_task = f"[Variant goal] {base_task} — {desc}"
        elif mut_type == "tool_restriction":
            new_task = f"[Tool restricted] {base_task} — {desc}"
        elif mut_type == "edge_case":
            new_task = f"[Edge case] {base_task} — {desc}"
        elif mut_type == "adversarial":
            new_task = f"[Adversarial] {base_task} — {desc}"
        else:
            new_task = f"[{mut_type}] {base_task}"

        specs.append(MutationSpec(
            mutation_id=f"mut_{uuid.uuid4().hex[:8]}",
            mutation_type=mut_type,
            new_task=new_task,
            new_constraints=constraints,
            expected_difficulty=_DIFFICULTY_MAP.get(mut_type, "medium"),
            rationale=desc,
        ))

    return specs


async def _generate_mutations_with_llm(
    traj: DreamTrajectory,
    count: int,
    llm=None,
) -> List[MutationSpec]:
    """Generate mutations using LLM for more sophisticated variations."""
    if llm is None:
        return _generate_mutations_for_traj(traj, count)

    prompt = f"""Generate {count} diverse mutations for this task trajectory.

Original task: {traj.task}
Success: {traj.success}
Failure type: {traj.failure_type or 'none'}
Constraints: {traj.constraints}

Generate mutations in these categories: constraint_flip, scale_up, scale_down,
error_injection, goal_variant, tool_restriction, edge_case, adversarial.

Output a JSON array of objects with keys:
- mutation_type: one of the categories above
- new_task: the mutated task description
- new_constraints: array of new constraints
- expected_difficulty: "easy" | "medium" | "hard"
- rationale: why this mutation is useful

JSON only, no markdown:"""

    try:
        response = await llm.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        # Strip markdown code fences if present
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

        items = json.loads(content)
        specs = []
        for item in items[:count]:
            specs.append(MutationSpec(
                mutation_id=f"mut_{uuid.uuid4().hex[:8]}",
                mutation_type=item.get("mutation_type", "goal_variant"),
                new_task=item.get("new_task", traj.task),
                new_constraints=item.get("new_constraints", []),
                expected_difficulty=item.get("expected_difficulty", "medium"),
                rationale=item.get("rationale"),
            ))
        return specs
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"LLM mutation generation failed, falling back to templates: {e}")
        return _generate_mutations_for_traj(traj, count)


def mutator_node(state: DreamState) -> DreamState:
    """Dream Subgraph node: generate mutations for sampled trajectories."""
    import random

    trajectories = state.get("sampled_trajectories", [])
    batches = state.get("dream_batches", [])
    mutations_per_traj = state.get("mutations_per_traj", 5)

    if not trajectories or not batches:
        logger.warning("Mutator: no trajectories or batches to mutate")
        state["dream_batches"] = []
        return state

    # Match batches to trajectories by traj_id
    traj_map = {t.traj_id: t for t in trajectories}

    for batch in batches:
        traj = traj_map.get(batch.base_traj_id)
        if traj is None:
            continue
        batch.mutation_specs = _generate_mutations_for_traj(
            traj, mutations_per_traj
        )

    total_mutations = sum(len(b.mutation_specs) for b in batches)
    logger.info(
        f"Mutator: {total_mutations} mutations across {len(batches)} batches"
    )

    state["dream_batches"] = batches
    return state
