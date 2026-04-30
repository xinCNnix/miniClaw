"""
Executor — Dream execution engine (dual mode).

SimulatedExecutor: Phase 1, returns mock results for offline cost-free testing.
ReplayExecutor: Phase 2, reuses PEVR executor in offline environment.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from app.core.dream.config import DreamConfig
from app.core.dream.models import (
    DreamBatch,
    DreamState,
    DreamTrajectory,
    MutationSpec,
)

logger = logging.getLogger(__name__)


class SimulatedExecutor:
    """Phase 1: Low-cost simulated execution.

    Returns mock tool results based on mutation type and task pattern.
    No real tool execution occurs.
    """

    def __init__(self, config: Optional[DreamConfig] = None):
        self.config = config or DreamConfig()

    def execute(
        self,
        spec: MutationSpec,
        max_steps: int = 8,
    ) -> DreamTrajectory:
        """Execute a mutation spec in simulated mode."""
        steps = self._simulate_steps(spec, max_steps)

        # Simulated execution always "succeeds" but quality varies
        success = self._simulate_success(spec)
        failure_type = None if success else self._simulate_failure(spec)

        return DreamTrajectory(
            traj_id=f"dream_{spec.mutation_id}_{uuid.uuid4().hex[:6]}",
            source="dream",
            task=spec.new_task,
            constraints=spec.new_constraints,
            steps=steps,
            final_answer=self._simulate_answer(spec, success),
            success=success,
            failure_type=failure_type,
            failure_summary=None if success else f"Simulated {failure_type}",
            cost_tokens=self._estimate_tokens(len(steps)),
            cost_time_ms=len(steps) * 500,  # ~500ms per simulated step
            tags=["simulated", spec.mutation_type],
            created_at=None,
        )

    def _simulate_steps(self, spec: MutationSpec, max_steps: int) -> list:
        """Generate simulated step records."""
        from app.core.execution_trace.models import StepRecord

        n_steps = min(max_steps, self._estimate_step_count(spec))
        steps = []
        for i in range(n_steps):
            thought = self._generate_thought(spec, i, n_steps)
            action = self._select_action(spec, i)
            input_data = self._generate_input(spec, action, i)

            steps.append(StepRecord(
                step_number=i + 1,
                thought=thought,
                action=action,
                input_data=input_data,
                result=self._simulate_tool_result(action, input_data, spec),
                success=True,
                duration=0.3 + (i * 0.1),
                timestamp="",
            ))
        return steps

    @staticmethod
    def _estimate_step_count(spec: MutationSpec) -> int:
        difficulty_map = {"easy": 3, "medium": 5, "hard": 7}
        base = difficulty_map.get(spec.expected_difficulty, 5)
        # Adversarial and error_injection need more steps
        if spec.mutation_type in ("adversarial", "error_injection"):
            base += 2
        return base

    @staticmethod
    def _generate_thought(spec: MutationSpec, step: int, total: int) -> str:
        if step == 0:
            return f"Analyzing task: {spec.new_task[:100]}"
        if step == total - 1:
            return "Synthesizing results into final answer"
        return f"Processing step {step + 1}/{total} for {spec.mutation_type} variant"

    @staticmethod
    def _select_action(spec: MutationSpec, step: int) -> str:
        """Select a simulated tool based on mutation type."""
        if spec.mutation_type == "tool_restriction":
            return ["search_kb", "read_file", "python_repl"][step % 3]
        if spec.mutation_type == "error_injection":
            return ["terminal", "read_file", "python_repl"][step % 3]
        return ["search", "read_file", "python_repl", "terminal", "write_file"][step % 5]

    @staticmethod
    def _generate_input(spec: MutationSpec, action: str, step: int) -> dict:
        if action == "search" or action == "search_kb":
            return {"query": spec.new_task[:100]}
        if action == "read_file":
            return {"path": f"/data/test_{step}.txt"}
        if action == "python_repl":
            return {"code": f"# Step {step}\nresult = 'simulated'"}
        if action == "terminal":
            return {"command": f"echo 'step {step}'"}
        if action == "write_file":
            return {"path": f"/data/output_{step}.txt", "content": "simulated output"}
        return {"input": "simulated"}

    @staticmethod
    def _simulate_tool_result(
        action: str, input_data: dict, spec: MutationSpec
    ) -> str:
        """Generate a simulated tool result."""
        if spec.mutation_type == "error_injection":
            import random
            if random.random() < 0.3:
                return f"Error: simulated {spec.mutation_type} failure"
        return f"Simulated result from {action}: OK"

    @staticmethod
    def _simulate_success(spec: MutationSpec) -> bool:
        """Simulate success/failure based on difficulty."""
        import random
        rates = {"easy": 0.85, "medium": 0.6, "hard": 0.35}
        return random.random() < rates.get(spec.expected_difficulty, 0.5)

    @staticmethod
    def _simulate_failure(spec: MutationSpec) -> str:
        """Return a simulated failure type."""
        import random
        types = ["LogicBug", "Timeout", "ToolError", "RuntimeError"]
        return random.choice(types)

    @staticmethod
    def _simulate_answer(spec: MutationSpec, success: bool) -> str:
        if success:
            return f"Simulated successful completion for: {spec.rationale or spec.mutation_type}"
        return f"Simulated failure for: {spec.rationale or spec.mutation_type}"

    @staticmethod
    def _estimate_tokens(n_steps: int) -> int:
        return n_steps * 300  # ~300 tokens per simulated step


class ReplayExecutor:
    """Phase 2: Reuses PEVR executor in an offline environment.

    Injects DreamConfig to enforce:
    - executor_network=False (no network)
    - executor_max_steps limit
    - executor_budget_tokens limit
    """

    def __init__(self, config: Optional[DreamConfig] = None):
        self.config = config or DreamConfig()
        self._perv_graph = None

    async def _ensure_graph(self):
        if self._perv_graph is None:
            from app.core.perv.graph import build_planner_graph
            self._perv_graph = build_planner_graph()

    async def execute(
        self,
        spec: MutationSpec,
        max_steps: int = 8,
    ) -> DreamTrajectory:
        """Execute a mutation spec by replaying through PEVR graph."""
        await self._ensure_graph()

        effective_max = min(max_steps, self.config.executor_max_steps)

        result = await self._perv_graph.ainvoke({
            "task": spec.new_task,
            "plan": [],
            "observations": [],
            "retry_count": 0,
            "max_retries": 1,
            "dream_config": self.config,
            "route_decision": {
                "mode": "perv",
                "risk": "low",
                "max_steps": effective_max,
            },
        })

        return self._to_dream_trajectory(result, spec)

    @staticmethod
    def _to_dream_trajectory(result: dict, spec: MutationSpec) -> DreamTrajectory:
        final_answer = result.get("final_answer", "")
        success = bool(final_answer)

        from app.core.execution_trace.models import StepRecord
        steps = []
        for i, obs in enumerate(result.get("observations", [])):
            steps.append(StepRecord(
                step_number=i + 1,
                thought=obs.get("step_id", ""),
                action=obs.get("tool", ""),
                input_data=obs.get("input", {}),
                result=obs.get("result"),
                success=obs.get("status") != "fail",
            ))

        return DreamTrajectory(
            traj_id=f"dream_{spec.mutation_id}_{uuid.uuid4().hex[:6]}",
            source="dream",
            task=spec.new_task,
            constraints=spec.new_constraints,
            steps=steps,
            final_answer=final_answer,
            success=success,
            failure_type=None if success else "RuntimeError",
            cost_tokens=None,
            cost_time_ms=None,
            tags=["replay", spec.mutation_type],
        )


def executor_node(state: DreamState) -> DreamState:
    """Dream Subgraph node: execute mutations in simulated or replay mode."""
    config = DreamConfig()
    mode = state.get("executor_mode", config.executor_mode)
    max_steps = state.get("max_exec_steps", config.executor_max_steps)

    executor: SimulatedExecutor | ReplayExecutor
    if mode == "replay":
        executor = ReplayExecutor(config)
        # ReplayExecutor is async, handled separately
        _execute_replay(state, executor, max_steps)
    else:
        executor = SimulatedExecutor(config)
        _execute_simulated(state, executor, max_steps)

    return state


def _execute_simulated(
    state: DreamState, executor: SimulatedExecutor, max_steps: int
) -> None:
    """Run simulated execution for all mutation specs."""
    dream_trajs: List[DreamTrajectory] = []
    batches = state.get("dream_batches", [])

    for batch in batches:
        for spec in batch.mutation_specs:
            traj = executor.execute(spec, max_steps)
            dream_trajs.append(traj)

    logger.info(
        f"Executor (simulated): {len(dream_trajs)} dream trajectories generated"
    )
    state["dream_trajectories"] = dream_trajs


def _execute_replay(
    state: DreamState, executor: ReplayExecutor, max_steps: int
) -> None:
    """Prepare replay execution (async execution handled by graph runner)."""
    import asyncio

    dream_trajs: List[DreamTrajectory] = []
    batches = state.get("dream_batches", [])

    async def _run():
        for batch in batches:
            for spec in batch.mutation_specs:
                traj = await executor.execute(spec, max_steps)
                dream_trajs.append(traj)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        asyncio.run(_run())

    logger.info(
        f"Executor (replay): {len(dream_trajs)} dream trajectories generated"
    )
    state["dream_trajectories"] = dream_trajs
