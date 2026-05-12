"""Workflow module MCP tools — execute, verify, and persist GSD-style workflows.

Registered tools:
  - workflow_execute_plan   : run an approved ExecutionPlan
  - workflow_verify_work    : verify completed steps against acceptance criteria
  - workflow_save_state     : persist session state to .planning/ artifacts
  - workflow_load_state     : restore session from .planning/ artifacts
  - workflow_append_context : add a decision or finding to CONTEXT.md
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from mcp.server.fastmcp import FastMCP

from universal_ai_mcp.core.registry import ToolRegistry
from universal_ai_mcp.entities.module_entity import Module, ModuleScenario, ScenarioType

MODULE_DEFINITION = Module(
    name="workflow",
    display_name="Workflow Engine",
    description=(
        "Executes approved plans in dependency-ordered parallel waves. "
        "Verifies completed work against objectives. "
        "Persists state to .planning/ for cross-session continuity (GSD pattern)."
    ),
    scenarios=[
        ModuleScenario(
            name="execute_approved_plan",
            description="Run all steps of an approved ExecutionPlan",
            scenario_type=ScenarioType.USER,
            required_tools=["workflow_execute_plan"],
        ),
        ModuleScenario(
            name="verify_and_fix",
            description="Check completed work and get a fix plan for gaps",
            scenario_type=ScenarioType.USER,
            required_tools=["workflow_verify_work"],
        ),
        ModuleScenario(
            name="resume_session",
            description="Restore planning state and context after a session restart",
            scenario_type=ScenarioType.SYSTEM,
            required_tools=["workflow_load_state", "workflow_read_context"],
        ),
    ],
    mcp_tools=[
        "workflow_execute_plan",
        "workflow_verify_work",
        "workflow_save_state",
        "workflow_load_state",
        "workflow_append_context",
        "workflow_read_context",
    ],
)


def register_workflow_tools(mcp: FastMCP, registry: ToolRegistry) -> None:
    registry.register_module(MODULE_DEFINITION)

    @mcp.tool()
    async def workflow_execute_plan(session_id: str, project_path: str) -> str:
        """Execute the active approved plan for this session.

        Requires: plan must be approved via task_plan_approve first.
        Runs steps in dependency-ordered waves (independent steps run in parallel).
        """
        from universal_ai_mcp.modules.workflow.state_manager import StateManager
        from universal_ai_mcp.modules.workflow.task_executor import TaskExecutor

        session = mcp.state.session_store.get(UUID(session_id))
        if not session:
            return json.dumps({"error": "Session not found"})
        if not session.active_plan:
            return json.dumps({"error": "No active plan. Call task_plan_build first."})
        if not session.active_plan.approved:
            return json.dumps({"error": "Plan not approved. Call task_plan_approve first."})

        root = Path(project_path).resolve()
        state_mgr = StateManager(root)
        executor = TaskExecutor(state_mgr)

        tasks = await executor.execute_plan(session.active_plan)
        state_mgr.write_state(session)

        return json.dumps({
            "plan_id": str(session.active_plan.id),
            "tasks_total": len(tasks),
            "tasks_completed": sum(1 for t in tasks if t.status.value == "completed"),
            "tasks_failed": sum(1 for t in tasks if t.status.value == "failed"),
            "results": [
                {
                    "task": t.title,
                    "status": t.status.value,
                    "error": t.result.error_message if t.result and not t.result.success else None,
                }
                for t in tasks
            ],
        }, indent=2)

    @mcp.tool()
    async def workflow_verify_work(session_id: str) -> str:
        """Verify completed plan steps against acceptance criteria.

        Returns objective_achieved status, list of gaps with severity,
        and concrete fix descriptions for each gap.
        """
        from universal_ai_mcp.core.config import get_settings
        from universal_ai_mcp.modules.llm.provider_registry import LLMProviderRegistry
        from universal_ai_mcp.modules.llm.router import LLMRouter
        from universal_ai_mcp.modules.workflow.work_verifier import WorkVerifier

        session = mcp.state.session_store.get(UUID(session_id))
        if not session or not session.active_plan:
            return json.dumps({"error": "No active plan in session"})

        settings = get_settings()
        router = LLMRouter(LLMProviderRegistry.from_settings(settings), settings)
        verifier = WorkVerifier(router)

        result = await verifier.verify(session.active_plan, [])
        return json.dumps(result, indent=2)

    @mcp.tool()
    async def workflow_save_state(session_id: str, project_path: str) -> str:
        """Persist current session state to .planning/ for cross-session continuity."""
        from universal_ai_mcp.modules.workflow.state_manager import StateManager

        session = mcp.state.session_store.get(UUID(session_id))
        if not session:
            return json.dumps({"error": "Session not found"})

        root = Path(project_path).resolve()
        state_mgr = StateManager(root)
        state_mgr.write_state(session)
        if session.active_plan:
            plan_file = state_mgr.save_plan(session.active_plan)
            return json.dumps({"saved": True, "plan_file": str(plan_file)})
        return json.dumps({"saved": True, "plan_file": None})

    @mcp.tool()
    async def workflow_load_state(plan_id: str, session_id: str, project_path: str) -> str:
        """Restore a previously saved plan into the current session."""
        from universal_ai_mcp.modules.workflow.state_manager import StateManager

        session = mcp.state.session_store.get_or_create(UUID(session_id))
        root = Path(project_path).resolve()
        state_mgr = StateManager(root)
        plan = state_mgr.load_plan(plan_id)

        if not plan:
            return json.dumps({"error": f"Plan {plan_id} not found in {project_path}/.planning/"})

        session.active_plan = plan
        return json.dumps({
            "loaded": True,
            "plan_id": plan_id,
            "title": plan.title,
            "approved": plan.approved,
            "steps_completed": len(plan.completed_steps),
        }, indent=2)

    @mcp.tool()
    async def workflow_append_context(
        key: str,
        value: str,
        project_path: str,
    ) -> str:
        """Append a decision or finding to the project CONTEXT.md artifact.

        Equivalent to GSD's CONTEXT.md — persists important decisions
        that should survive session boundaries.
        """
        from universal_ai_mcp.modules.workflow.state_manager import StateManager

        root = Path(project_path).resolve()
        state_mgr = StateManager(root)
        state_mgr.append_context(key, value)
        return json.dumps({"appended": True, "key": key})

    @mcp.tool()
    async def workflow_read_context(project_path: str) -> str:
        """Read the accumulated CONTEXT.md artifact for this project.

        Returns all decisions and findings written via workflow_append_context.
        Use at session start to restore context from prior sessions (GSD resume pattern).
        Returns empty string if no CONTEXT.md exists yet.
        """
        from universal_ai_mcp.modules.workflow.state_manager import StateManager

        root = Path(project_path).resolve()
        state_mgr = StateManager(root)
        content = state_mgr.read_context()
        return json.dumps({"project_path": project_path, "context": content})
