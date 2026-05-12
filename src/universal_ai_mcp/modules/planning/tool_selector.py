"""Tool selector — chooses MCP tools and justifies each selection.

For each step of a plan, the selector picks the most appropriate registered
MCP tool and records the reason. This creates an auditable tool-selection
log that is part of the ExecutionPlan the user approves.
"""

from __future__ import annotations

import json

import structlog

from universal_ai_mcp.entities.provider_entity import LLMMessage, LLMRequest
from universal_ai_mcp.modules.llm.json_extractor import extract_json
from universal_ai_mcp.modules.llm.router import LLMRouter

log = structlog.get_logger(__name__)

TOOL_SELECTOR_SYSTEM_PROMPT = """You are a senior AI systems engineer.
Given a task, available MCP tools, and project context, select the optimal
set of tools and justify each selection.

Rules:
1. Only select tools from the provided list — never invent new ones.
2. For each selected tool, provide a concise (1-sentence) justification.
3. Order tools by execution priority (most foundational first).
4. Output ONLY valid JSON:
   {
     "selected_tools": ["tool_name", ...],
     "justifications": {"tool_name": "reason", ...}
   }
"""


class ToolSelector:
    """Selects and justifies MCP tool choices for a task."""

    def __init__(self, router: LLMRouter) -> None:
        self._router = router

    async def select_tools(
        self,
        task_description: str,
        available_tools: list[str],
        answers_to_questions: dict[str, str] | None = None,
    ) -> tuple[list[str], dict[str, str]]:
        """Returns (selected_tool_names, justifications_dict)."""
        tools_list = "\n".join(f"  - {t}" for t in available_tools)
        qa_block = ""
        if answers_to_questions:
            qa_block = "\n\nUser clarifications:\n" + "\n".join(
                f"  Q: {q}\n  A: {a}" for q, a in answers_to_questions.items()
            )

        user_message = (
            f"Task: {task_description}\n\n"
            f"Available MCP tools:\n{tools_list}"
            f"{qa_block}\n\n"
            f"Select the appropriate tools with justifications."
        )
        request = LLMRequest(
            model="auto",
            messages=[LLMMessage(role="user", content=user_message)],
            system_prompt=TOOL_SELECTOR_SYSTEM_PROMPT,
            max_tokens=1024,
            temperature=0.2,
        )
        response = await self._router.complete(request, tier="fast")

        try:
            data = extract_json(response.content)
            selected: list[str] = data.get("selected_tools", [])
            justifications: dict[str, str] = data.get("justifications", {})
        except (json.JSONDecodeError, KeyError, AttributeError):
            log.warning("tool_selector_parse_failed", raw=response.content[:200])
            selected, justifications = [], {}

        valid = [t for t in selected if t in available_tools]
        return valid, justifications
