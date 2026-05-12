"""Tests for orchestrator entities: AuditReport, JanitorAction, DevSession."""

from uuid import uuid4

import pytest
import yaml

from universal_ai_mcp.entities import (
    AuditReport,
    AuditSeverity,
    DevSession,
    JanitorAction,
    JanitorChangeType,
    OrchestratorPhase,
)


class TestAuditReport:
    def test_is_blocking_only_for_high(self):
        session_id = uuid4()
        low = AuditReport(session_id=session_id, phase="verify", severity=AuditSeverity.LOW)
        med = AuditReport(session_id=session_id, phase="verify", severity=AuditSeverity.MED)
        high = AuditReport(session_id=session_id, phase="verify", severity=AuditSeverity.HIGH)

        assert not low.is_blocking
        assert not med.is_blocking
        assert high.is_blocking

    def test_fields_default_to_empty_lists(self):
        report = AuditReport(session_id=uuid4(), phase="plan_gate", severity=AuditSeverity.LOW)
        assert report.missed_actions == []
        assert report.questionable_choices == []

    def test_roundtrip_json(self):
        report = AuditReport(
            session_id=uuid4(),
            phase="wave_execute",
            severity=AuditSeverity.HIGH,
            missed_actions=["tests not written"],
            questionable_choices=["skipped planning gate"],
        )
        restored = AuditReport.model_validate_json(report.model_dump_json())
        assert restored.severity == AuditSeverity.HIGH
        assert restored.missed_actions == ["tests not written"]


class TestJanitorAction:
    def test_mark_applied(self):
        action = JanitorAction(
            session_id=uuid4(),
            file_path="docs/project/overview.md",
            change_type=JanitorChangeType.UPDATE,
            description="Updated public API section",
        )
        assert not action.applied
        assert action.applied_at is None

        action.mark_applied()
        assert action.applied
        assert action.applied_at is not None

    def test_change_type_enum_values(self):
        assert JanitorChangeType.CREATE == "create"
        assert JanitorChangeType.UPDATE == "update"
        assert JanitorChangeType.APPEND == "append"


class TestDevSession:
    def test_initial_phase_is_profile_select(self):
        session = DevSession(task="add dark mode")
        assert session.current_phase == OrchestratorPhase.PROFILE_SELECT
        assert session.phases_completed == []

    def test_advance_phase_tracks_history(self):
        session = DevSession(task="refactor auth module")
        session.advance_phase(OrchestratorPhase.CONTEXT_BUILD)

        assert OrchestratorPhase.PROFILE_SELECT in session.phases_completed
        assert session.current_phase == OrchestratorPhase.CONTEXT_BUILD

    def test_complete_seals_session(self):
        session = DevSession(task="write tests")
        session.advance_phase(OrchestratorPhase.FINALIZE)
        session.complete()

        assert session.completed_at is not None
        assert OrchestratorPhase.FINALIZE in session.phases_completed

    def test_complete_idempotent_on_phase(self):
        session = DevSession(task="idempotent test")
        session.complete()
        count_before = len(session.phases_completed)
        session.complete()
        assert len(session.phases_completed) == count_before

    def test_janitor_scope_override_optional(self):
        session = DevSession(task="no override")
        assert session.janitor_scope_override is None

        session_with_override = DevSession(
            task="custom scope", janitor_scope_override=["custom/docs/"]
        )
        assert session_with_override.janitor_scope_override == ["custom/docs/"]


class TestOrchestratorYaml:
    def test_config_loads_and_has_required_keys(self):
        import pathlib
        config_path = pathlib.Path(__file__).parent.parent / "config" / "orchestrator.yaml"
        config = yaml.safe_load(config_path.read_text())

        assert "auditor" in config
        assert "janitor" in config
        assert "pipeline" in config
        assert config["auditor"]["model"] == "qwen3:8b"
        assert config["janitor"]["model"] == "qwen3:8b"
        assert "scope_whitelist" in config["janitor"]
        assert config["janitor"]["allow_per_session_override"] is True
        assert config["pipeline"]["audit_after_each_phase"] is True
