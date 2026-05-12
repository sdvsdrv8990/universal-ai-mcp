"""Question engine — generates targeted clarifying questions before planning.

Rules:
- Simple tasks (< MEDIUM threshold steps): 0-2 questions
- Medium tasks: 3-5 questions
- Complex tasks: up to 8 questions covering all system/interface layers
- Questions must resolve ambiguity; never ask what can be inferred from context
"""

from __future__ import annotations

import json

import structlog

from universal_ai_mcp.entities.project_entity import ProjectContext
from universal_ai_mcp.entities.provider_entity import LLMMessage, LLMRequest
from universal_ai_mcp.modules.llm.json_extractor import extract_json
from universal_ai_mcp.modules.llm.router import LLMRouter
from universal_ai_mcp.types.module_types import ComplexityLevel

log = structlog.get_logger(__name__)

QUESTION_SYSTEM_PROMPT = """You are a senior software architect. Your job is to identify
the minimum set of clarifying questions needed before creating an execution plan.

Rules:
1. Only ask questions whose answers would CHANGE the plan significantly.
2. Never ask about things you can infer from the task description or project context.
3. Group questions by concern: scope, constraints, tech choices, integration points.
4. For complex tasks: also ask about failure modes, rollback, and monitoring.
5. Output ONLY valid JSON: {"questions": ["q1", "q2", ...]}.
6. Maximum questions: simple=2, medium=5, complex=8.
"""


class QuestionEngine:
    """Generates the minimum set of clarifying questions for a given task."""

    def __init__(self, router: LLMRouter) -> None:
        self._router = router

    async def generate_questions(
        self,
        task_description: str,
        complexity: ComplexityLevel,
        project_context: ProjectContext | None = None,
    ) -> list[str]:
        context_summary = self._summarize_context(project_context)
        user_message = (
            f"Task: {task_description}\n\n"
            f"Complexity level: {complexity}\n\n"
            f"Project context:\n{context_summary}\n\n"
            f"Generate clarifying questions."
        )
        request = LLMRequest(
            model="auto",
            messages=[LLMMessage(role="user", content=user_message)],
            system_prompt=QUESTION_SYSTEM_PROMPT,
            max_tokens=1024,
            temperature=0.3,
        )
        response = await self._router.complete(request, tier="fast")

        try:
            data = extract_json(response.content)
            questions: list[str] = data.get("questions", [])
        except (json.JSONDecodeError, KeyError, AttributeError):
            log.warning("question_parse_failed", raw=response.content[:200])
            questions = []

        max_questions = {"simple": 2, "medium": 5, "complex": 8}[complexity]
        return questions[:max_questions]

    def _summarize_context(self, ctx: ProjectContext | None) -> str:
        if not ctx:
            return "No project context available."
        return (
            f"Project: {ctx.name}\n"
            f"Language: {ctx.stack.primary_language}\n"
            f"Frameworks: {', '.join(str(f) for f in ctx.stack.frameworks) or 'none detected'}\n"
            f"Conventions: {ctx.conventions.file_case} files, "
            f"tests in '{ctx.conventions.test_directory}'"
        )
