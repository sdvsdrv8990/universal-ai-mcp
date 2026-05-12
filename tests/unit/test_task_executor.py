"""Unit tests for TaskExecutor wave decomposition and execution gating."""

from __future__ import annotations

from pathlib import Path

import pytest

from universal_ai_mcp.entities.plan_entity import ExecutionPlan, PlanStep
from universal_ai_mcp.entities.session_entity import AgentSession
from universal_ai_mcp.entities.task_entity import TaskStatus
from universal_ai_mcp.modules.workflow.state_manager import StateManager
from universal_ai_mcp.modules.workflow.task_executor import TaskExecutor


def make_plan(session: AgentSession, steps: list[PlanStep]) -> ExecutionPlan:
    plan = ExecutionPlan(
        session_id=session.id,
        title="Test",
        objective="Test plan",
        complexity="simple",
        steps=steps,
    )
    return plan


@pytest.mark.asyncio
async def test_executor_raises_without_approval(
    tmp_path: Path, agent_session: AgentSession
) -> None:
    plan = make_plan(agent_session, [PlanStep(order=0, title="S", description="d")])

    state = StateManager(tmp_path)
    executor = TaskExecutor(state)

    with pytest.raises(RuntimeError, match="not been approved"):
        await executor.execute_plan(plan)


@pytest.mark.asyncio
async def test_executor_runs_approved_plan(
    tmp_path: Path, agent_session: AgentSession
) -> None:
    steps = [PlanStep(order=0, title="Step A", description="d", tool_name="test_tool")]
    plan = make_plan(agent_session, steps)
    plan.approve()

    state = StateManager(tmp_path)
    executor = TaskExecutor(state)

    call_log: list[str] = []

    async def test_tool_handler(step: PlanStep) -> str:
        call_log.append(step.title)
        return "done"

    executor.register_tool_handler("test_tool", test_tool_handler)
    tasks = await executor.execute_plan(plan)

    assert len(tasks) == 1
    assert tasks[0].status == TaskStatus.COMPLETED
    assert "Step A" in call_log


@pytest.mark.asyncio
async def test_wave_decomposition_independent_steps_run_in_parallel(
    tmp_path: Path, agent_session: AgentSession
) -> None:
    s0 = PlanStep(order=0, title="A", description="d")
    s1 = PlanStep(order=1, title="B", description="d")  # independent of s0
    plan = make_plan(agent_session, [s0, s1])
    plan.approve()

    state = StateManager(tmp_path)
    executor = TaskExecutor(state)

    waves = executor._build_waves(plan.steps)
    assert len(waves) == 1
    assert len(waves[0]) == 2
