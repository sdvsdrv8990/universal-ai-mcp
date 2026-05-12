"""Integration planner — creates a step-by-step plan to adopt a chosen ready solution.

Given a selected repository or library, generates:
  1. The exact code from the ready solution to copy/adapt
  2. Integration steps layer by layer (data → service → API → tests)
  3. Convention-adapted file names matching the user's project
  4. Docs per layer (what was taken, what was adapted, why)
"""

from __future__ import annotations

import json

import structlog

from universal_ai_mcp.entities.project_entity import ProjectContext
from universal_ai_mcp.entities.provider_entity import LLMMessage, LLMRequest
from universal_ai_mcp.modules.llm.router import LLMRouter
from universal_ai_mcp.modules.project_detection.convention_adapter import ConventionAdapter

log = structlog.get_logger(__name__)

INTEGRATION_SYSTEM_PROMPT = """You are a senior engineer who integrates ready solutions
into projects with minimal modification.

Rules:
1. Reuse as much source code as possible verbatim — document what was taken.
2. Adapt ONLY what is necessary for the target project's conventions.
3. Structure the integration in layers: models → repositories → services → API → tests.
4. Each layer produces: source_code (extracted from solution), integration_code (adapted), docs.
5. Output ONLY valid JSON.

JSON schema:
{
  "layers": [
    {
      "name": "layer name",
      "order": 0,
      "source_code": "exact code extracted from ready solution",
      "integration_code": "adapted code for target project",
      "target_file": "path/in/target/project.py",
      "docs": "What was taken, what was changed, why"
    }
  ],
  "total_files": 3,
  "estimated_effort": "2h"
}
"""


class IntegrationPlanner:
    """Builds a layered integration plan for adopting a ready solution."""

    def __init__(self, router: LLMRouter, adapter: ConventionAdapter) -> None:
        self._router = router
        self._adapter = adapter

    async def plan(
        self,
        solution_name: str,
        solution_readme: str,
        target_feature: str,
        project_context: ProjectContext,
    ) -> dict:
        conventions_summary = (
            f"File naming: {project_context.conventions.file_case}\n"
            f"Source dir: {project_context.conventions.source_directory}\n"
            f"Test dir: {project_context.conventions.test_directory}\n"
            f"Language: {project_context.stack.primary_language}"
        )
        user_message = (
            f"Ready solution: {solution_name}\n"
            f"Target feature: {target_feature}\n\n"
            f"Target project conventions:\n{conventions_summary}\n\n"
            f"Solution README (excerpt):\n{solution_readme[:3000]}\n\n"
            f"Create a layered integration plan."
        )
        request = LLMRequest(
            model="auto",
            messages=[LLMMessage(role="user", content=user_message)],
            system_prompt=INTEGRATION_SYSTEM_PROMPT,
            max_tokens=8192,
            temperature=0.2,
        )
        response = await self._router.complete(request, tier="balanced")

        try:
            plan_data: dict = json.loads(response.content)
        except json.JSONDecodeError:
            log.warning("integration_planner_parse_failed", solution=solution_name)
            return {"error": "Could not generate integration plan"}

        for layer in plan_data.get("layers", []):
            if "target_file" in layer and project_context.conventions:
                layer["target_file"] = self._adapter.adapt_directory(
                    layer["target_file"], project_context.conventions
                )

        return plan_data
