"""Tests for orchestrator Phase C modules: LocalAuditor, LocalJanitor, DevSessionRunner."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from universal_ai_mcp.entities.audit_report_entity import AuditReport, AuditSeverity
from universal_ai_mcp.entities.dev_session_entity import DevSession, OrchestratorPhase
from universal_ai_mcp.entities.janitor_action_entity import JanitorAction, JanitorChangeType
from universal_ai_mcp.modules.orchestrator.local_auditor import AuditorUnavailableError, LocalAuditor
from universal_ai_mcp.modules.orchestrator.local_janitor import LocalJanitor
from universal_ai_mcp.modules.orchestrator.orchestrator_config import (
    AuditorConfig,
    JanitorConfig,
    OrchestratorConfig,
    PipelineConfig,
    load_orchestrator_config,
)
from universal_ai_mcp.modules.orchestrator.dev_session_runner import DevSessionRunner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(required: bool = False) -> OrchestratorConfig:
    return OrchestratorConfig(
        auditor=AuditorConfig(
            provider="ollama",
            model="qwen3:8b",
            required=required,
            fallback_provider=None,
            fallback_model=None,
        ),
        janitor=JanitorConfig(
            provider="ollama",
            model="qwen3:8b",
            scope_whitelist=["docs/", "CHANGELOG.md", ".planning/STATE.md"],
            allow_per_session_override=True,
        ),
        pipeline=PipelineConfig(
            phases=["profile_select", "context_build", "finalize"],
            audit_after_each_phase=True,
            janitor_runs_after="verify",
        ),
    )


def _make_router(response_text: str) -> MagicMock:
    """Router that returns a mock LLM response with the given content."""
    mock_response = MagicMock()
    mock_response.content = response_text
    router = MagicMock()
    router.complete = AsyncMock(return_value=mock_response)
    return router


def _make_session(task: str = "implement feature X") -> DevSession:
    return DevSession(task=task)


# ---------------------------------------------------------------------------
# LocalAuditor tests
# ---------------------------------------------------------------------------

class TestLocalAuditor:
    @pytest.mark.asyncio
    async def test_returns_low_severity_when_ollama_unavailable_and_not_required(self):
        router = MagicMock()
        router.complete = AsyncMock(side_effect=ConnectionError("Ollama down"))
        auditor = LocalAuditor(router=router, config=_make_config(required=False))
        session = _make_session()

        report = await auditor.audit_phase(session, OrchestratorPhase.PLAN_GATE)

        assert report.severity == AuditSeverity.LOW
        assert not report.is_blocking

    @pytest.mark.asyncio
    async def test_raises_when_ollama_unavailable_and_required(self):
        router = MagicMock()
        router.complete = AsyncMock(side_effect=ConnectionError("Ollama down"))
        auditor = LocalAuditor(router=router, config=_make_config(required=True))
        session = _make_session()

        with pytest.raises(AuditorUnavailableError):
            await auditor.audit_phase(session, OrchestratorPhase.PLAN_GATE)

    @pytest.mark.asyncio
    async def test_returns_blocking_on_high_severity_response(self):
        payload = json.dumps({
            "severity": "high",
            "missed_actions": ["plan not approved before execution"],
            "questionable_choices": [],
        })
        router = _make_router(payload)
        auditor = LocalAuditor(router=router, config=_make_config())
        session = _make_session()

        report = await auditor.audit_phase(session, OrchestratorPhase.WAVE_EXECUTE)

        assert report.is_blocking
        assert report.severity == AuditSeverity.HIGH
        assert "plan not approved before execution" in report.missed_actions

    @pytest.mark.asyncio
    async def test_returns_non_blocking_on_low_severity(self):
        payload = json.dumps({"severity": "low", "missed_actions": [], "questionable_choices": []})
        router = _make_router(payload)
        auditor = LocalAuditor(router=router, config=_make_config())
        session = _make_session()

        report = await auditor.audit_phase(session, OrchestratorPhase.CONTEXT_BUILD)

        assert not report.is_blocking
        assert report.session_id == session.id

    @pytest.mark.asyncio
    async def test_falls_back_to_fallback_provider_when_primary_fails(self):
        config = OrchestratorConfig(
            auditor=AuditorConfig(
                provider="ollama",
                model="qwen3:8b",
                required=True,
                fallback_provider="anthropic",
                fallback_model="claude-haiku-4-5-20251001",
            ),
            janitor=JanitorConfig(),
            pipeline=PipelineConfig(),
        )
        good_response = MagicMock()
        good_response.content = json.dumps({"severity": "low", "missed_actions": [], "questionable_choices": []})

        call_count = 0

        async def side_effect(request, preferred_provider=None):
            nonlocal call_count
            call_count += 1
            if preferred_provider == "ollama":
                raise ConnectionError("Ollama down")
            return good_response

        router = MagicMock()
        router.complete = AsyncMock(side_effect=side_effect)
        auditor = LocalAuditor(router=router, config=config)
        session = _make_session()

        report = await auditor.audit_phase(session, OrchestratorPhase.PLAN_GATE)

        assert not report.is_blocking
        assert call_count == 2  # primary attempt + fallback


# ---------------------------------------------------------------------------
# LocalJanitor tests
# ---------------------------------------------------------------------------

class TestLocalJanitor:
    def test_is_path_allowed_whitelist(self):
        janitor = LocalJanitor(router=MagicMock(), config=_make_config())
        session = _make_session()

        assert janitor.is_path_allowed("docs/api.md", session)
        assert janitor.is_path_allowed("CHANGELOG.md", session)
        assert janitor.is_path_allowed(".planning/STATE.md", session)

    def test_is_path_allowed_rejects_disallowed_path(self):
        janitor = LocalJanitor(router=MagicMock(), config=_make_config())
        session = _make_session()

        assert not janitor.is_path_allowed("src/core/server.py", session)
        assert not janitor.is_path_allowed("pyproject.toml", session)

    def test_is_path_allowed_session_override(self):
        janitor = LocalJanitor(router=MagicMock(), config=_make_config())
        session = DevSession(task="task", janitor_scope_override=["reports/"])

        assert janitor.is_path_allowed("reports/summary.md", session)

    def test_is_path_allowed_override_disabled_by_config(self):
        config = _make_config()
        config.janitor.allow_per_session_override = False
        janitor = LocalJanitor(router=MagicMock(), config=config)
        session = DevSession(task="task", janitor_scope_override=["reports/"])

        assert not janitor.is_path_allowed("reports/summary.md", session)

    @pytest.mark.asyncio
    async def test_finalize_applies_allowed_actions(self, tmp_path: Path):
        payload = json.dumps([
            {"file_path": "docs/update.md", "change_type": "update", "description": "document changes"},
            {"file_path": "src/secret.py", "change_type": "update", "description": "inject code"},
        ])
        router = _make_router(payload)
        config = _make_config()
        config.janitor.scope_whitelist = ["docs/"]
        janitor = LocalJanitor(router=router, config=config, project_path=tmp_path)
        session = _make_session()
        session.phases_completed = list(OrchestratorPhase)

        actions = await janitor.finalize(session)

        # Only the allowed path action should be applied
        assert len(actions) == 1
        assert actions[0].file_path == "docs/update.md"
        assert actions[0].applied

    @pytest.mark.asyncio
    async def test_finalize_returns_empty_list_when_llm_unavailable(self):
        router = MagicMock()
        router.complete = AsyncMock(side_effect=ConnectionError("down"))
        janitor = LocalJanitor(router=router, config=_make_config())
        session = _make_session()

        actions = await janitor.finalize(session)

        assert actions == []


# ---------------------------------------------------------------------------
# DevSessionRunner tests
# ---------------------------------------------------------------------------

class TestDevSessionRunner:
    def _make_runner(self, audit_severity: str = "low") -> tuple[DevSessionRunner, dict]:
        store: dict = {}
        audit_payload = json.dumps({
            "severity": audit_severity,
            "missed_actions": [] if audit_severity != "high" else ["critical error"],
            "questionable_choices": [],
        })
        router = _make_router(audit_payload)
        config = _make_config()
        auditor = LocalAuditor(router=router, config=config)
        janitor_router = _make_router("[]")
        janitor = LocalJanitor(router=janitor_router, config=config)
        runner = DevSessionRunner(auditor=auditor, janitor=janitor, config=config, session_store=store)
        return runner, store

    @pytest.mark.asyncio
    async def test_completes_all_phases_on_low_severity(self):
        runner, store = self._make_runner("low")

        result = await runner.run(task="add logging module")

        assert result["status"] == "completed"
        assert len(result["phases_completed"]) == 7
        assert "session_id" in result

    @pytest.mark.asyncio
    async def test_blocked_on_high_severity_audit(self):
        runner, store = self._make_runner("high")

        result = await runner.run(task="deploy to prod")

        assert result["status"] == "blocked"
        assert "blocked_at_phase" in result
        assert result["audit_report"]["severity"] == "high"

    @pytest.mark.asyncio
    async def test_session_stored_in_store(self):
        runner, store = self._make_runner("low")

        result = await runner.run(task="implement feature")

        session_id = result["session_id"]
        from uuid import UUID
        assert UUID(session_id) in store

    @pytest.mark.asyncio
    async def test_audit_summary_contains_all_phases(self):
        runner, _ = self._make_runner("low")

        result = await runner.run(task="refactor module")

        assert result["status"] == "completed"
        assert len(result["audit_summary"]) == 7


# ---------------------------------------------------------------------------
# Config loading test
# ---------------------------------------------------------------------------

class TestOrchestratorConfig:
    def test_load_orchestrator_config_reads_yaml(self):
        config = load_orchestrator_config()

        assert config.auditor.provider == "ollama"
        assert config.auditor.model == "qwen3:8b"
        assert config.auditor.required is False
        assert config.auditor.fallback_provider == "anthropic"
        assert config.janitor.scope_whitelist  # non-empty
        assert "profile_select" in config.pipeline.phases

    def test_load_orchestrator_config_returns_defaults_for_missing_file(self, tmp_path: Path):
        missing = tmp_path / "nonexistent.yaml"
        config = load_orchestrator_config(path=missing)

        assert isinstance(config, OrchestratorConfig)
        assert config.auditor.provider == "ollama"
