"""Dependency optimizer — trims a solution's dependencies to the minimum required.

Given a candidate library/repo and the actual features used, this optimizer:
  1. Identifies which transitive deps are actually needed
  2. Flags optional extras that can be omitted
  3. Suggests lighter alternatives for heavy deps
  4. Warns about known security issues or abandoned packages
"""

from __future__ import annotations

import json

import structlog

from universal_ai_mcp.entities.provider_entity import LLMMessage, LLMRequest
from universal_ai_mcp.modules.llm.router import LLMRouter

log = structlog.get_logger(__name__)

OPTIMIZER_SYSTEM_PROMPT = """You are a dependency minimization specialist.

Given:
- A library/repo being integrated
- The specific features actually used
- Its full dependency tree

Your task:
1. Identify which deps are REQUIRED for the specific features used.
2. Identify which deps can be OMITTED (extras, optional, dev-only).
3. Suggest LIGHTER alternatives for heavy deps where possible.
4. Flag any SECURITY risks (CVEs, abandoned packages, overly broad permissions).

Output ONLY valid JSON:
{
  "required": [{"package": "name", "reason": "why needed"}],
  "optional_omit": [{"package": "name", "reason": "why safe to skip"}],
  "lighter_alternatives": [{"original": "name", "alternative": "name", "reason": "..."}],
  "security_flags": [{"package": "name", "issue": "description"}],
  "estimated_size_reduction": "~40%"
}
"""


class DependencyOptimizer:
    """Uses LLM reasoning to identify minimum viable dependency set."""

    def __init__(self, router: LLMRouter) -> None:
        self._router = router

    async def optimize(
        self,
        library_name: str,
        features_used: list[str],
        dependency_tree: str,
    ) -> dict:
        user_message = (
            f"Library: {library_name}\n"
            f"Features used: {', '.join(features_used)}\n\n"
            f"Dependency tree:\n{dependency_tree}\n\n"
            f"Minimize dependencies."
        )
        request = LLMRequest(
            model="auto",
            messages=[LLMMessage(role="user", content=user_message)],
            system_prompt=OPTIMIZER_SYSTEM_PROMPT,
            max_tokens=2048,
            temperature=0.2,
        )
        response = await self._router.complete(request, tier="balanced")

        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            log.warning("optimizer_parse_failed", library=library_name)
            return {"error": "Could not parse optimization result"}
