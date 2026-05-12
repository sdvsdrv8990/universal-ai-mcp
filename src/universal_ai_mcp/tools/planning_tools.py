"""Planning module MCP tools — enforce plan-before-execute for every task.

Registered tools:
  - task_analyze      : classify complexity + return clarifying questions
  - task_plan_build   : build ExecutionPlan after user answers questions
  - task_plan_approve : mark plan as approved, enabling execution
  - task_plan_status  : show current plan status
"""

from __future__ import annotations

import json
from uuid import UUID

import structlog
from mcp.server.fastmcp import FastMCP

from universal_ai_mcp.core.registry import ToolRegistry
from universal_ai_mcp.entities.module_entity import Module, ModuleScenario, ScenarioType

log = structlog.get_logger(__name__)

MODULE_DEFINITION = Module(
    name="planning",
    display_name="Planning Gate",
    description=(
        "Forces creation and approval of an ExecutionPlan before any work begins. "
        "Generates clarifying questions, selects tools with justification, "
        "and decomposes tasks into ordered, atomic steps."
    ),
    scenarios=[
        ModuleScenario(
            name="analyze_and_question",
            description="Classify task complexity and generate clarifying questions",
            scenario_type=ScenarioType.USER,
            required_tools=["task_analyze"],
        ),
        ModuleScenario(
            name="build_and_approve",
            description="Build execution plan from answered questions",
            scenario_type=ScenarioType.USER,
            required_tools=["task_plan_build", "task_plan_approve"],
        ),
        ModuleScenario(
            name="check_gate",
            description="Internal: verify plan is approved before executing a step",
            scenario_type=ScenarioType.SYSTEM,
            required_tools=["task_plan_status"],
        ),
    ],
    mcp_tools=["task_analyze", "task_plan_build", "task_plan_approve", "task_plan_status"],
)


def register_planning_tools(mcp: FastMCP, registry: ToolRegistry) -> None:
    registry.register_module(MODULE_DEFINITION)

    @mcp.tool()
    async def task_analyze(task_description: str, session_id: str | None = None) -> str:
        """Classify task complexity and return clarifying questions.

        MUST be called before task_plan_build. Returns complexity level
        (simple/medium/complex) and a list of questions to answer.
        No execution can proceed without an approved plan.
        """
        from universal_ai_mcp.core.config import get_settings
        from universal_ai_mcp.modules.llm.provider_registry import LLMProviderRegistry
        from universal_ai_mcp.modules.llm.router import LLMRouter
        from universal_ai_mcp.modules.planning.planner import Planner
        from universal_ai_mcp.modules.planning.question_engine import QuestionEngine
        from universal_ai_mcp.modules.planning.tool_selector import ToolSelector

        settings = get_settings()
        provider_reg = LLMProviderRegistry.from_settings(settings)
        router = LLMRouter(provider_reg, settings)
        engine = QuestionEngine(router)
        selector = ToolSelector(router)
        planner = Planner(router, settings, engine, selector)

        session_store = mcp.state.session_store
        session = session_store.get_or_create(UUID(session_id) if session_id else None)
        project_ctx = session.project_context

        complexity, questions = await planner.get_clarifying_questions(task_description, project_ctx)

        result = {
            "session_id": str(session.id),
            "complexity": complexity,
            "questions": questions,
            "instruction": (
                "Answer the questions above, then call task_plan_build with your answers "
                "to create an execution plan. No work will proceed without an approved plan."
            ),
        }
        return json.dumps(result, indent=2)

    @mcp.tool()
    async def task_plan_build(
        task_description: str,
        complexity: str,
        answers: str,
        session_id: str,
    ) -> str:
        """Build an ExecutionPlan from task description and answered questions.

        Args:
            task_description: Original task.
            complexity: From task_analyze output (simple/medium/complex).
            answers: JSON object mapping question→answer.
            session_id: From task_analyze output.

        Returns plan JSON including steps, tools, and justifications.
        User must call task_plan_approve to enable execution.
        """
        from universal_ai_mcp.core.config import get_settings
        from universal_ai_mcp.modules.llm.provider_registry import LLMProviderRegistry
        from universal_ai_mcp.modules.llm.router import LLMRouter
        from universal_ai_mcp.modules.planning.planner import Planner
        from universal_ai_mcp.modules.planning.question_engine import QuestionEngine
        from universal_ai_mcp.modules.planning.tool_selector import ToolSelector

        settings = get_settings()
        provider_reg = LLMProviderRegistry.from_settings(settings)
        router = LLMRouter(provider_reg, settings)
        engine = QuestionEngine(router)
        selector = ToolSelector(router)
        planner = Planner(router, settings, engine, selector)

        try:
            qa: dict[str, str] = json.loads(answers)
        except json.JSONDecodeError:
            return json.dumps({"error": "answers must be valid JSON object"})

        session_store = mcp.state.session_store
        session = session_store.get_or_create(UUID(session_id))
        tool_names = registry.list_tool_names()

        plan = await planner.build_plan(
            session_id=session.id,
            task=task_description,
            complexity=complexity,  # type: ignore[arg-type]
            questions_and_answers=qa,
            available_tools=tool_names,
            project_context=session.project_context,
        )

        session.active_plan = plan
        session.plan_history.append(plan.id)

        return json.dumps({
            "plan_id": str(plan.id),
            "title": plan.title,
            "complexity": plan.complexity,
            "steps": [{"order": s.order, "title": s.title, "tool": s.tool_name} for s in plan.steps],
            "selected_tools": plan.selected_tools,
            "tool_justifications": plan.tool_justifications,
            "estimated_tokens": plan.total_estimated_tokens,
            "approved": plan.approved,
            "instruction": "Review the plan. Call task_plan_approve with the plan_id to begin execution.",
        }, indent=2)

    @mcp.tool()
    async def task_plan_approve(plan_id: str, session_id: str) -> str:
        """Approve an ExecutionPlan, enabling execution of its steps.

        This is the mandatory gate before any execution tool runs.
        """
        session_store = mcp.state.session_store
        session = session_store.get_or_create(UUID(session_id))

        if not session.active_plan or str(session.active_plan.id) != plan_id:
            return json.dumps({"error": f"Plan {plan_id} not found in session {session_id}"})

        session.active_plan.approve()
        log.info("plan_approved", plan_id=plan_id, session=session_id)

        return json.dumps({
            "approved": True,
            "plan_id": plan_id,
            "message": "Plan approved. You may now call workflow_execute_plan.",
        })

    @mcp.tool()
    async def task_plan_status(session_id: str) -> str:
        """Return current plan status for the session."""
        session_store = mcp.state.session_store
        session = session_store.get(UUID(session_id))

        if not session:
            return json.dumps({"error": "Session not found"})

        if not session.active_plan:
            return json.dumps({"status": "no_active_plan", "session_state": session.state.value})

        plan = session.active_plan
        return json.dumps({
            "plan_id": str(plan.id),
            "title": plan.title,
            "approved": plan.approved,
            "steps_total": len(plan.steps),
            "steps_completed": len(plan.completed_steps),
            "steps_pending": len(plan.pending_steps),
            "session_state": session.state.value,
        }, indent=2)
