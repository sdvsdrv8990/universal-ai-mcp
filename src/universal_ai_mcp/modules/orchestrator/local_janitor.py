"""Local janitor — finalizes a session by updating docs and planning artifacts.

Runs synchronously (blocking) after the verify phase succeeds.
Only writes to paths in scope_whitelist + per-session overrides.
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from universal_ai_mcp.entities.dev_session_entity import DevSession
from universal_ai_mcp.entities.janitor_action_entity import JanitorAction, JanitorChangeType
from universal_ai_mcp.modules.llm.json_extractor import extract_json
from universal_ai_mcp.modules.orchestrator.orchestrator_config import OrchestratorConfig

log = structlog.get_logger(__name__)

_JANITOR_SYSTEM_PROMPT = """\
You are a project janitor. After a development session ends you review what changed
and propose atomic documentation/state updates to keep the project tidy.

You receive:
  - task: the completed development task
  - phases_completed: list of pipeline phases that ran
  - allowed_paths: paths you are permitted to write/update

Respond ONLY with valid JSON — a list of proposed actions:
[
  {
    "file_path": "<relative path from project root>",
    "change_type": "create" | "update" | "append",
    "description": "<one sentence: what to write and why>"
  },
  ...
]

Only propose actions for paths inside allowed_paths. If nothing needs updating,
return an empty list [].
"""


class LocalJanitor:
    """Proposes and applies file-system cleanup actions after a session completes."""

    def __init__(
        self,
        router: object,
        config: OrchestratorConfig,
        project_path: Path | None = None,
    ) -> None:
        self._router = router
        self._config = config
        self._project_path = project_path or Path(".")

    def is_path_allowed(self, file_path: str, session: DevSession) -> bool:
        """Return True if file_path is inside the scope whitelist for this session."""
        whitelist = list(self._config.janitor.scope_whitelist)
        if self._config.janitor.allow_per_session_override and session.janitor_scope_override:
            whitelist.extend(session.janitor_scope_override)
        return any(file_path.startswith(allowed) for allowed in whitelist)

    async def finalize(self, session: DevSession) -> list[JanitorAction]:
        """Propose and apply doc/state updates for the completed session (blocking)."""
        from universal_ai_mcp.entities.provider_entity import LLMMessage, LLMRequest

        allowed = list(self._config.janitor.scope_whitelist)
        if self._config.janitor.allow_per_session_override and session.janitor_scope_override:
            allowed.extend(session.janitor_scope_override)

        user_content = (
            f"task: {session.task}\n"
            f"phases_completed: {[p.value for p in session.phases_completed]}\n"
            f"allowed_paths: {json.dumps(allowed)}"
        )
        request = LLMRequest(
            model=self._config.janitor.model,
            messages=[LLMMessage(role="user", content=user_content)],
            system_prompt=_JANITOR_SYSTEM_PROMPT,
            max_tokens=1024,
            temperature=0.0,
        )

        try:
            response = await self._router.complete(
                request, preferred_provider=self._config.janitor.provider
            )
            raw = response.content
        except Exception as exc:
            log.warning("janitor_llm_unavailable", error=str(exc))
            return []

        proposed = self._parse_actions(raw, session)
        applied: list[JanitorAction] = []
        for action in proposed:
            if not self.is_path_allowed(action.file_path, session):
                log.warning(
                    "janitor_path_rejected",
                    path=action.file_path,
                    session_id=str(session.id),
                )
                continue
            self._apply_action(action)
            applied.append(action)

        log.info(
            "janitor_finalized",
            proposed=len(proposed),
            applied=len(applied),
            session_id=str(session.id),
        )
        return applied

    def _parse_actions(self, raw: str, session: DevSession) -> list[JanitorAction]:
        try:
            data = extract_json(raw)
            assert isinstance(data, list)
        except Exception as exc:
            log.warning("janitor_parse_failed", error=str(exc))
            return []

        actions: list[JanitorAction] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                actions.append(
                    JanitorAction(
                        session_id=session.id,
                        file_path=str(item["file_path"]),
                        change_type=JanitorChangeType(item.get("change_type", "update")),
                        description=str(item.get("description", "")),
                    )
                )
            except Exception as exc:
                log.warning("janitor_action_parse_error", item=item, error=str(exc))
        return actions

    def _apply_action(self, action: JanitorAction) -> None:
        target = self._project_path / action.file_path
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if action.change_type == JanitorChangeType.APPEND and target.exists():
                with target.open("a") as f:
                    f.write(f"\n<!-- janitor: {action.description} -->\n")
            elif action.change_type == JanitorChangeType.CREATE:
                target.write_text(f"<!-- janitor: {action.description} -->\n")
            else:
                content = target.read_text() if target.exists() else ""
                target.write_text(content + f"\n<!-- janitor: {action.description} -->\n")
            action.mark_applied()
            log.info("janitor_action_applied", path=action.file_path, type=action.change_type.value)
        except OSError as exc:
            log.warning("janitor_action_failed", path=action.file_path, error=str(exc))
