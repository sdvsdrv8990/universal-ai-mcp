"""Stack advisor — recommends an optimal tech stack for new or evolving projects.

Uses an LLM to reason over project requirements and propose a stack with:
  - Primary language + runtime
  - Frameworks (minimal, purpose-fit)
  - Package manager
  - Testing approach
  - Deployment target
  - Dependency rationale (why each dep was chosen)
"""

from __future__ import annotations

import json

import structlog

from universal_ai_mcp.entities.provider_entity import LLMMessage, LLMRequest
from universal_ai_mcp.modules.llm.router import LLMRouter

log = structlog.get_logger(__name__)

ADVISOR_SYSTEM_PROMPT = """You are a senior software architect with deep knowledge of
modern tech stacks. Your goal: recommend the MINIMAL, most effective stack for the
described project.

Principles:
1. Prefer battle-tested, widely-adopted choices.
2. Minimize the total number of dependencies.
3. Justify EVERY library — if a job can be done with stdlib, say so.
4. Consider team size, project scale, and deployment target.
5. Warn about known trade-offs.

Output ONLY valid JSON:
{
  "language": "python",
  "runtime": "cpython 3.12",
  "package_manager": "uv",
  "frameworks": [{"name": "fastapi", "reason": "async-first, fast, OpenAPI out of the box"}],
  "testing": {"framework": "pytest", "strategy": "unit + integration, no mocks for DB"},
  "deployment": "docker + cloud run",
  "dependencies": [{"package": "pydantic", "reason": "data validation at boundaries"}],
  "trade_offs": ["FastAPI requires async discipline; sync code blocks event loop"],
  "alternatives_considered": ["Flask: simpler but no async; Django: too heavy for API-only"]
}
"""


class StackAdvisor:
    """Recommends an optimal tech stack using LLM reasoning."""

    def __init__(self, router: LLMRouter) -> None:
        self._router = router

    async def recommend(
        self,
        project_description: str,
        team_size: int = 1,
        deployment_target: str = "cloud",
        constraints: list[str] | None = None,
    ) -> dict:
        constraints_str = "\n".join(f"- {c}" for c in (constraints or []))
        user_message = (
            f"Project: {project_description}\n"
            f"Team size: {team_size}\n"
            f"Deployment: {deployment_target}\n"
            f"Constraints:\n{constraints_str or 'none'}\n\n"
            f"Recommend the optimal tech stack."
        )
        request = LLMRequest(
            model="auto",
            messages=[LLMMessage(role="user", content=user_message)],
            system_prompt=ADVISOR_SYSTEM_PROMPT,
            max_tokens=2048,
            temperature=0.3,
        )
        response = await self._router.complete(request, tier="balanced")

        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            log.warning("stack_advisor_parse_failed", raw=response.content[:200])
            return {"error": "Could not parse stack recommendation", "raw": response.content}
