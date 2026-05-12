"""Planner — orchestrates the full planning gate sequence.

Sequence enforced by this module:
  1. Classify task complexity (simple / medium / complex)
  2. Generate clarifying questions (via QuestionEngine)
  3. Return questions to caller for user answers
  4. Select tools with justifications (via ToolSelector)
  5. Build ExecutionPlan with ordered steps
  6. Return plan for user approval — NO execution until plan.approved == True

Complexity classification rules (from settings):
  simple  = estimated steps < MEDIUM threshold (default 3)
  medium  = MEDIUM ≤ steps < COMPLEX threshold (default 7)
  complex = steps ≥ COMPLEX threshold
"""

from __future__ import annotations

import json
from uuid import UUID

import structlog

from universal_ai_mcp.core.config import ServerSettings
from universal_ai_mcp.entities.plan_entity import ExecutionPlan, PlanStep
from universal_ai_mcp.entities.project_entity import ProjectContext
from universal_ai_mcp.entities.provider_entity import LLMMessage, LLMRequest
from universal_ai_mcp.modules.llm.json_extractor import extract_json
from universal_ai_mcp.modules.llm.router import LLMRouter
from universal_ai_mcp.modules.planning.question_engine import QuestionEngine
from universal_ai_mcp.modules.planning.tool_selector import ToolSelector
from universal_ai_mcp.types.module_types import ComplexityLevel

log = structlog.get_logger(__name__)

PLANNER_SYSTEM_PROMPT = """You are a senior software architect and project planner.
Decompose the given task into an ordered list of concrete, atomic steps.

Rules:
1. Each step must have a clear title, description, and the single MCP tool that executes it.
2. Mark dependencies between steps using step indexes (0-based).
3. Estimate token cost per step: simple file op = 500, LLM call = 2000-8000.
4. Output ONLY valid JSON:
{
  "title": "Plan title",
  "objective": "What this plan achieves",
  "steps": [
    {
      "order": 0,
      "title": "Step title",
      "description": "What this step does",
      "tool_name": "mcp_tool_name",
      "estimated_tokens": 1000,
      "depends_on_indexes": []
    }
  ]
}
"""


class Planner:
    """Full planning gate: questions → tool selection → step decomposition."""

    def __init__(
        self,
        router: LLMRouter,
        settings: ServerSettings,
        question_engine: QuestionEngine,
        tool_selector: ToolSelector,
    ) -> None:
        self._router = router
        self._settings = settings
        self._questions = question_engine
        self._selector = tool_selector

    async def get_clarifying_questions(
        self,
        task: str,
        project_context: ProjectContext | None = None,
    ) -> tuple[ComplexityLevel, list[str]]:
        """Step 1 & 2: classify complexity and return questions for the user."""
        complexity = await self._classify_complexity(task)
        questions = await self._questions.generate_questions(task, complexity, project_context)
        return complexity, questions

    async def build_plan(
        self,
        session_id: UUID,
        task: str,
        complexity: ComplexityLevel,
        questions_and_answers: dict[str, str],
        available_tools: list[str],
        project_context: ProjectContext | None = None,
    ) -> ExecutionPlan:
        """Step 4 & 5: select tools, decompose steps, assemble plan."""
        selected_tools, justifications = await self._selector.select_tools(
            task, available_tools, questions_and_answers
        )

        step_plan = await self._decompose_steps(
            task, complexity, questions_and_answers, selected_tools
        )

        steps = [
            PlanStep(
                order=s["order"],
                title=s["title"],
                description=s["description"],
                tool_name=s.get("tool_name"),
                estimated_tokens=s.get("estimated_tokens", 1000),
            )
            for s in step_plan.get("steps", [])
        ]

        plan = ExecutionPlan(
            session_id=session_id,
            title=step_plan.get("title", task[:80]),
            objective=step_plan.get("objective", task),
            complexity=complexity,
            steps=steps,
            clarifying_questions=list(questions_and_answers.keys()),
            selected_tools=selected_tools,
            tool_justifications=justifications,
        )
        log.info(
            "plan_built",
            plan_id=str(plan.id),
            complexity=complexity,
            steps=len(steps),
            tools=selected_tools,
        )
        return plan

    async def _classify_complexity(self, task: str) -> ComplexityLevel:
        request = LLMRequest(
            model="auto",
            messages=[LLMMessage(
                role="user",
                content=(
                    f"Estimate the number of implementation steps for:\n{task}\n\n"
                    f'Output ONLY a JSON object: {{"estimated_steps": <integer>}}'
                ),
            )],
            max_tokens=64,
            temperature=0.0,
        )
        response = await self._router.complete(request, tier="fast")
        try:
            data = extract_json(response.content)
            steps = int(data.get("estimated_steps", 5))
        except (json.JSONDecodeError, ValueError, AttributeError):
            steps = 5

        med = self._settings.planning_complexity_threshold_medium
        cplx = self._settings.planning_complexity_threshold_complex
        if steps < med:
            return "simple"
        if steps < cplx:
            return "medium"
        return "complex"

    async def _decompose_steps(
        self,
        task: str,
        complexity: ComplexityLevel,
        qa: dict[str, str],
        tools: list[str],
    ) -> dict:
        qa_block = "\n".join(f"Q: {q}\nA: {a}" for q, a in qa.items())
        tools_str = ", ".join(tools) or "any available"
        user_message = (
            f"Task: {task}\n"
            f"Complexity: {complexity}\n"
            f"Available tools: {tools_str}\n"
            f"Clarifications:\n{qa_block or 'None'}\n\n"
            f"Decompose into steps."
        )
        request = LLMRequest(
            model="auto",
            messages=[LLMMessage(role="user", content=user_message)],
            system_prompt=PLANNER_SYSTEM_PROMPT,
            max_tokens=4096,
            temperature=0.3,
        )
        response = await self._router.complete(request, tier="balanced")
        try:
            return extract_json(response.content)
        except json.JSONDecodeError:
            log.warning("planner_parse_failed", raw=response.content[:300])
            return {"title": task[:80], "objective": task, "steps": []}
