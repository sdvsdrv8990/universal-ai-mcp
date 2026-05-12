"""Local auditor — reviews each pipeline phase using a local LLM (Ollama/qwen3:8b).

Runs after every phase in the orchestrator pipeline. Returns an AuditReport whose
is_blocking property determines whether the pipeline should halt.
"""

from __future__ import annotations

import json
import structlog

from universal_ai_mcp.entities.audit_report_entity import AuditReport, AuditSeverity
from universal_ai_mcp.entities.dev_session_entity import DevSession, OrchestratorPhase
from universal_ai_mcp.modules.llm.json_extractor import extract_json
from universal_ai_mcp.modules.orchestrator.orchestrator_config import OrchestratorConfig

log = structlog.get_logger(__name__)

_AUDIT_SYSTEM_PROMPT = """\
You are a blocking code-review auditor embedded in an AI development pipeline.
After each pipeline phase completes, you receive:
  - task: the original development task
  - phase: which pipeline phase just finished
  - xml_context: compressed semantic context of what was built so far
  - file_deltas: list of file changes made during this phase

Your job: detect missed actions, questionable choices, or outright errors.

Respond ONLY with valid JSON:
{
  "severity": "low" | "med" | "high",
  "missed_actions": ["<description>", ...],
  "questionable_choices": ["<description>", ...]
}

Use severity=high ONLY for critical problems (security holes, wrong files touched,
plan violations). Use med for important concerns. Use low for minor suggestions.
If everything looks correct, return severity=low with empty lists.
"""


class AuditorUnavailableError(RuntimeError):
    """Raised when auditor LLM is unreachable and auditor.required=true."""


class LocalAuditor:
    """Audits each pipeline phase using a local LLM. Blocking on severity=high."""

    def __init__(self, router: object, config: OrchestratorConfig) -> None:
        self._router = router
        self._config = config

    async def audit_phase(
        self,
        session: DevSession,
        phase: OrchestratorPhase,
        xml_context: str = "",
        file_deltas: list[str] | None = None,
    ) -> AuditReport:
        """Run auditor LLM for the given phase. Returns AuditReport."""
        from universal_ai_mcp.entities.provider_entity import LLMMessage, LLMRequest

        user_content = (
            f"task: {session.task}\n"
            f"phase: {phase.value}\n"
            f"xml_context:\n{xml_context or '(none provided)'}\n"
            f"file_deltas:\n{json.dumps(file_deltas or [], indent=2)}"
        )
        request = LLMRequest(
            model=self._config.auditor.model,
            messages=[LLMMessage(role="user", content=user_content)],
            system_prompt=_AUDIT_SYSTEM_PROMPT,
            max_tokens=512,
            temperature=0.0,
        )

        raw_text = await self._call_with_fallback(request)
        return self._parse_report(raw_text, session, phase)

    async def _call_with_fallback(self, request: object) -> str:
        from universal_ai_mcp.entities.provider_entity import LLMRequest

        assert isinstance(request, LLMRequest)
        cfg = self._config.auditor

        try:
            response = await self._router.complete(
                request, preferred_provider=cfg.provider
            )
            return response.content
        except Exception as primary_exc:
            log.warning(
                "auditor_primary_unavailable",
                provider=cfg.provider,
                model=cfg.model,
                error=str(primary_exc),
            )

            if cfg.fallback_provider and cfg.fallback_model:
                try:
                    fallback_req = request.model_copy(
                        update={"model": cfg.fallback_model}
                    )
                    response = await self._router.complete(
                        fallback_req, preferred_provider=cfg.fallback_provider
                    )
                    log.info("auditor_fallback_used", provider=cfg.fallback_provider)
                    return response.content
                except Exception as fallback_exc:
                    log.warning(
                        "auditor_fallback_unavailable",
                        provider=cfg.fallback_provider,
                        error=str(fallback_exc),
                    )

            if cfg.required:
                raise AuditorUnavailableError(
                    f"Auditor unavailable and auditor.required=true: {primary_exc}"
                ) from primary_exc

            log.warning("auditor_skipped_fail_open", phase="unknown")
            return '{"severity": "low", "missed_actions": [], "questionable_choices": []}'

    def _parse_report(
        self,
        raw_text: str,
        session: DevSession,
        phase: OrchestratorPhase,
    ) -> AuditReport:
        try:
            data = extract_json(raw_text)
            assert isinstance(data, dict)
            severity = AuditSeverity(data.get("severity", "low"))
            missed = [str(x) for x in data.get("missed_actions", [])]
            questionable = [str(x) for x in data.get("questionable_choices", [])]
        except Exception as exc:
            log.warning("auditor_parse_failed", error=str(exc), raw=raw_text[:200])
            severity = AuditSeverity.LOW
            missed = []
            questionable = [f"Auditor response unparseable: {exc}"]

        report = AuditReport(
            session_id=session.id,
            phase=phase.value,
            severity=severity,
            missed_actions=missed,
            questionable_choices=questionable,
        )
        log.info(
            "audit_complete",
            phase=phase.value,
            severity=severity.value,
            blocking=report.is_blocking,
        )
        return report
