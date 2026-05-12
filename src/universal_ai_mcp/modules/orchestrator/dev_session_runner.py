"""DevSessionRunner — phase state machine for the dual-AI orchestrator pipeline.

Runs phases in order, auditing after each. Blocks on severity=high audit.
Runs janitor synchronously after verify succeeds.

Phase execution model:
  Each phase calls _execute_phase() which returns (context_addition, file_deltas).
  When optional deps (dynamic_config, block_retriever) are injected, phases do real
  work. Without them, phases fall back to description strings — auditor still runs.
  This ensures existing tests (no deps injected) pass unchanged.
"""

from __future__ import annotations

import structlog
from pathlib import Path
from datetime import UTC, datetime
from uuid import UUID

from universal_ai_mcp.entities.audit_report_entity import AuditReport
from universal_ai_mcp.entities.dev_session_entity import DevSession, OrchestratorPhase
from universal_ai_mcp.entities.janitor_action_entity import JanitorAction
from universal_ai_mcp.modules.orchestrator.local_auditor import AuditorUnavailableError, LocalAuditor
from universal_ai_mcp.modules.orchestrator.local_janitor import LocalJanitor
from universal_ai_mcp.modules.orchestrator.orchestrator_config import OrchestratorConfig

log = structlog.get_logger(__name__)

PHASE_ORDER = [
    OrchestratorPhase.PROFILE_SELECT,
    OrchestratorPhase.CONTEXT_BUILD,
    OrchestratorPhase.PLAN_GATE,
    OrchestratorPhase.WAVE_EXECUTE,
    OrchestratorPhase.STATE_PERSIST,
    OrchestratorPhase.VERIFY,
    OrchestratorPhase.FINALIZE,
]


class DevSessionRunner:
    """Orchestrates one end-to-end development session through all pipeline phases."""

    def __init__(
        self,
        auditor: LocalAuditor,
        janitor: LocalJanitor,
        config: OrchestratorConfig,
        session_store: dict[UUID, DevSession] | None = None,
        dynamic_config: object = None,
        block_retriever: object = None,
        project_path: Path | None = None,
    ) -> None:
        self._auditor = auditor
        self._janitor = janitor
        self._config = config
        self._store: dict[UUID, DevSession] = session_store if session_store is not None else {}
        self._dynamic_config = dynamic_config
        self._block_retriever = block_retriever
        self._project_path = project_path

    async def run(
        self,
        task: str,
        file_deltas: list[str] | None = None,
        janitor_scope: list[str] | None = None,
        xml_context: str = "",
        router: object = None,
    ) -> dict:
        """Execute full pipeline. Returns result dict (never raises)."""
        session = DevSession(task=task, janitor_scope_override=janitor_scope)
        self._store[session.id] = session
        audit_reports: list[AuditReport] = []
        accumulated_deltas: list[str] = list(file_deltas or [])

        log.info("dev_session_started", session_id=str(session.id), task=task[:80])

        for i, phase in enumerate(PHASE_ORDER):
            log.info("phase_started", phase=phase.value, session_id=str(session.id))

            phase_context, phase_deltas = await self._execute_phase(
                session, phase, router, xml_context
            )
            accumulated_deltas.extend(phase_deltas)

            try:
                report = await self._auditor.audit_phase(
                    session,
                    phase,
                    xml_context=f"{xml_context}\n{phase_context}".strip(),
                    file_deltas=accumulated_deltas,
                )
            except AuditorUnavailableError as exc:
                return self._error_result(session, str(exc), audit_reports, [])

            session.audit_history.append(report.id)
            audit_reports.append(report)

            if report.is_blocking:
                log.warning(
                    "pipeline_blocked",
                    phase=phase.value,
                    session_id=str(session.id),
                    missed=report.missed_actions,
                )
                return {
                    "status": "blocked",
                    "session_id": str(session.id),
                    "blocked_at_phase": phase.value,
                    "audit_report": {
                        "severity": report.severity.value,
                        "missed_actions": report.missed_actions,
                        "questionable_choices": report.questionable_choices,
                    },
                    "phases_completed": [p.value for p in session.phases_completed],
                }

            if i < len(PHASE_ORDER) - 1:
                session.advance_phase(PHASE_ORDER[i + 1])

        # All phases passed — run janitor synchronously
        janitor_actions: list[JanitorAction] = await self._janitor.finalize(session)
        session.janitor_actions = [a.id for a in janitor_actions]
        session.complete()
        self._store[session.id] = session

        log.info(
            "dev_session_completed",
            session_id=str(session.id),
            phases=len(session.phases_completed),
            janitor_actions=len(janitor_actions),
        )

        return {
            "status": "completed",
            "session_id": str(session.id),
            "phases_completed": [p.value for p in session.phases_completed],
            "audit_summary": [
                {
                    "phase": r.phase,
                    "severity": r.severity.value,
                    "issues": len(r.missed_actions) + len(r.questionable_choices),
                }
                for r in audit_reports
            ],
            "janitor_actions_applied": [
                {"path": a.file_path, "type": a.change_type.value, "description": a.description}
                for a in janitor_actions
                if a.applied
            ],
        }

    # ──────────────────────────────────────────────────────────────
    # Phase execution
    # ──────────────────────────────────────────────────────────────

    async def _execute_phase(
        self,
        session: DevSession,
        phase: OrchestratorPhase,
        router: object,
        current_xml: str,
    ) -> tuple[str, list[str]]:
        """Execute one pipeline phase. Returns (auditor_context, file_deltas).

        Falls back to a description string when optional deps are absent so that
        the auditor always receives meaningful context regardless of wiring.
        """
        if phase == OrchestratorPhase.PROFILE_SELECT and self._dynamic_config and router:
            return await self._phase_profile_select(session, router)

        if phase == OrchestratorPhase.CONTEXT_BUILD and self._block_retriever:
            return await self._phase_context_build(session)

        if phase == OrchestratorPhase.STATE_PERSIST and self._project_path:
            return await self._phase_state_persist(session)

        return self._describe_phase(session, phase, router), []

    async def _phase_profile_select(
        self, session: DevSession, router: object
    ) -> tuple[str, list[str]]:
        try:
            profile, confidence = await self._dynamic_config.analyze_task(  # type: ignore[union-attr]
                session.task, router
            )
            context = (
                f"profile_select: chose '{profile.name}' "
                f"(confidence={confidence:.2f}). "
                f"required_modules={profile.required_modules}"
            )
            log.info("phase_profile_selected", profile=profile.name, confidence=confidence)
            return context, []
        except Exception as exc:
            log.warning("phase_profile_select_failed", error=str(exc))
            return f"profile_select: classification failed ({exc}), using default.", []

    async def _phase_context_build(self, session: DevSession) -> tuple[str, list[str]]:
        try:
            blocks = await self._block_retriever.query(session.task, limit=5)  # type: ignore[union-attr]
            if not blocks:
                return "context_build: no relevant IdeaBlocks found in index.", []
            from universal_ai_mcp.entities.idea_block_entity import IdeaBlockCollection
            xml = IdeaBlockCollection(blocks=blocks).to_xml_context()
            context = f"context_build: retrieved {len(blocks)} IdeaBlocks.\n{xml}"
            log.info("phase_context_built", blocks=len(blocks))
            return context, []
        except Exception as exc:
            log.warning("phase_context_build_failed", error=str(exc))
            return f"context_build: retrieval failed ({exc}).", []

    async def _phase_state_persist(self, session: DevSession) -> tuple[str, list[str]]:
        assert self._project_path is not None
        state_path = self._project_path / ".planning" / "STATE.md"
        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            phases_done = ", ".join(p.value for p in session.phases_completed)
            content = (
                f"# Session State\n\n"
                f"**Session ID:** {session.id}\n"
                f"**Task:** {session.task}\n"
                f"**Phases completed:** {phases_done}\n"
                f"**Timestamp:** {datetime.now(UTC).isoformat()}\n"
            )
            state_path.write_text(content)
            log.info("phase_state_persisted", path=str(state_path))
            return (
                f"state_persist: wrote snapshot to {state_path}",
                [f"{state_path}: session state snapshot"],
            )
        except OSError as exc:
            log.warning("phase_state_persist_failed", path=str(state_path), error=str(exc))
            return f"state_persist: failed to write {state_path} ({exc}).", []

    # ──────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────

    def _describe_phase(
        self,
        session: DevSession,
        phase: OrchestratorPhase,
        router: object,
    ) -> str:
        """Fallback context string when a phase has no real executor wired."""
        descriptions = {
            OrchestratorPhase.PROFILE_SELECT: (
                f"Selecting workflow profile for task: {session.task[:120]}"
            ),
            OrchestratorPhase.CONTEXT_BUILD: "Building compressed semantic context from session history.",
            OrchestratorPhase.PLAN_GATE: "Verifying approved execution plan exists before proceeding.",
            OrchestratorPhase.WAVE_EXECUTE: "Executing plan steps in dependency-ordered waves.",
            OrchestratorPhase.STATE_PERSIST: "Persisting session state to .planning/ artifacts.",
            OrchestratorPhase.VERIFY: "Verifying completed work against acceptance criteria.",
            OrchestratorPhase.FINALIZE: "Running local janitor to update docs and state artifacts.",
        }
        return descriptions.get(phase, phase.value)

    @staticmethod
    def _error_result(
        session: DevSession,
        error: str,
        reports: list[AuditReport],
        actions: list[JanitorAction],
    ) -> dict:
        return {
            "status": "error",
            "session_id": str(session.id),
            "error": error,
            "phases_completed": [p.value for p in session.phases_completed],
            "audit_summary": [],
            "janitor_actions_applied": [],
        }
