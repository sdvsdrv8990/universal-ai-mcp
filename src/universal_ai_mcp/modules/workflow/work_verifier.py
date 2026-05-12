"""Work verifier — checks completed plan steps against acceptance criteria.

For each completed step, verifies:
  - Output matches expected result
  - No regressions in related areas
  - Generates a fix plan for any gaps found
"""

from __future__ import annotations

import json

import structlog

from universal_ai_mcp.entities.plan_entity import ExecutionPlan, PlanStepStatus
from universal_ai_mcp.modules.llm.json_extractor import extract_json
from universal_ai_mcp.entities.provider_entity import LLMMessage, LLMRequest
from universal_ai_mcp.entities.task_entity import Task
from universal_ai_mcp.modules.llm.router import LLMRouter

log = structlog.get_logger(__name__)

VERIFIER_SYSTEM_PROMPT = """You are a QA engineer performing acceptance testing.

Given:
- The original plan objective
- Completed step summaries
- Any task outputs

Verify:
1. Was the objective achieved?
2. Are there any gaps, missing pieces, or regressions?
3. For each gap: provide a concrete fix description.

Output ONLY valid JSON:
{
  "objective_achieved": true,
  "gaps": [
    {"description": "...", "severity": "critical|major|minor", "fix": "..."}
  ],
  "overall_status": "passed|failed|partial",
  "next_actions": ["action1", "action2"]
}
"""


class WorkVerifier:
    """Validates completed plan work and generates fix plans for gaps."""

    def __init__(self, router: LLMRouter) -> None:
        self._router = router

    async def verify(self, plan: ExecutionPlan, tasks: list[Task]) -> dict:
        completed_summaries = [
            f"Step {s.order}: {s.title} — {s.result_summary or 'no output'}"
            for s in plan.steps
            if s.status == PlanStepStatus.COMPLETED
        ]
        failed_steps = [
            f"Step {s.order}: {s.title} — FAILED"
            for s in plan.steps
            if s.status == PlanStepStatus.FAILED
        ]

        user_message = (
            f"Objective: {plan.objective}\n\n"
            f"Completed steps:\n" + "\n".join(completed_summaries) + "\n\n"
            + (f"Failed steps:\n" + "\n".join(failed_steps) + "\n\n" if failed_steps else "")
            + "Verify the work and identify any gaps."
        )
        request = LLMRequest(
            model="auto",
            messages=[LLMMessage(role="user", content=user_message)],
            system_prompt=VERIFIER_SYSTEM_PROMPT,
            max_tokens=2048,
            temperature=0.2,
        )
        response = await self._router.complete(request, tier="balanced")

        try:
            result: dict = extract_json(response.content)
        except (json.JSONDecodeError, AttributeError):
            log.warning("verifier_parse_failed")
            result = {"objective_achieved": False, "gaps": [], "overall_status": "unknown"}

        log.info(
            "verification_complete",
            plan_id=str(plan.id),
            status=result.get("overall_status"),
            gaps=len(result.get("gaps", [])),
        )
        return result
