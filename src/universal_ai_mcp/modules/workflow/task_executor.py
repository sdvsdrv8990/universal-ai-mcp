"""Task executor — runs approved plan steps sequentially or in parallel waves.

A "wave" is a group of steps with no mutual dependencies that can execute
in parallel. Steps within a wave are independent; waves execute sequentially.

Enforces: plan.approved == True before any execution starts.
"""

from __future__ import annotations

import asyncio
import time
from uuid import UUID

import structlog

from universal_ai_mcp.entities.plan_entity import ExecutionPlan, PlanStep, PlanStepStatus
from universal_ai_mcp.entities.task_entity import Task, TaskResult, TaskStatus
from universal_ai_mcp.modules.workflow.state_manager import StateManager

log = structlog.get_logger(__name__)


class TaskExecutor:
    """Executes an approved ExecutionPlan in dependency-ordered waves."""

    def __init__(self, state_manager: StateManager) -> None:
        self._state = state_manager
        self._tool_handlers: dict[str, object] = {}

    def register_tool_handler(self, tool_name: str, handler: object) -> None:
        self._tool_handlers[tool_name] = handler

    async def execute_plan(self, plan: ExecutionPlan) -> list[Task]:
        if not plan.approved:
            raise RuntimeError(
                f"Plan {plan.id} has not been approved. "
                "Call plan.approve() before executing."
            )

        log.info("plan_execution_started", plan_id=str(plan.id), steps=len(plan.steps))
        self._state.save_plan(plan)

        waves = self._build_waves(plan.steps)
        all_tasks: list[Task] = []

        for wave_idx, wave in enumerate(waves):
            log.info("wave_started", wave=wave_idx, steps=len(wave))
            wave_tasks = await asyncio.gather(
                *[self._execute_step(plan, step) for step in wave],
                return_exceptions=False,
            )
            all_tasks.extend(wave_tasks)

            failed = [t for t in wave_tasks if t.status == TaskStatus.FAILED]
            if failed:
                log.error("wave_failed", wave=wave_idx, failed_steps=[str(t.step_id) for t in failed])
                break

        self._state.save_plan(plan)
        return all_tasks

    async def _execute_step(self, plan: ExecutionPlan, step: PlanStep) -> Task:
        task = Task(
            plan_id=plan.id,
            step_id=step.id,
            title=step.title,
            tool_name=step.tool_name or "noop",
            tool_input={},
        )
        task.mark_running()
        step.status = PlanStepStatus.IN_PROGRESS
        start = time.monotonic()

        try:
            handler = self._tool_handlers.get(task.tool_name)
            if handler and callable(handler):
                output = await handler(step)  # type: ignore[call-arg]
            else:
                log.warning("no_handler_for_tool", tool=task.tool_name)
                output = f"No handler registered for tool '{task.tool_name}'"

            duration_ms = (time.monotonic() - start) * 1000
            result = TaskResult(
                success=True,
                output=output,
                duration_ms=duration_ms,
            )
            task.mark_completed(result)
            step.status = PlanStepStatus.COMPLETED
            step.result_summary = str(output)[:200]
            log.info("step_completed", step=step.title, ms=f"{duration_ms:.0f}")

        except Exception as exc:
            task.mark_failed(str(exc))
            step.status = PlanStepStatus.FAILED
            log.error("step_failed", step=step.title, error=str(exc))

        return task

    def _build_waves(self, steps: list[PlanStep]) -> list[list[PlanStep]]:
        """Group steps into waves by dependency order."""
        if not steps:
            return []

        id_to_step = {s.id: s for s in steps}
        completed_ids: set[UUID] = set()
        remaining = list(steps)
        waves: list[list[PlanStep]] = []

        while remaining:
            ready = [
                s for s in remaining
                if all(dep in completed_ids for dep in s.depends_on)
            ]
            if not ready:
                log.warning("dependency_deadlock_detected_falling_back")
                ready = [remaining[0]]

            waves.append(ready)
            for s in ready:
                completed_ids.add(s.id)
                remaining.remove(s)

        return waves
