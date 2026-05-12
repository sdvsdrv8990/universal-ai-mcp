"""DevSession entity — orchestrator-level session for the dual-AI pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class OrchestratorPhase(str, Enum):
    PROFILE_SELECT = "profile_select"
    CONTEXT_BUILD = "context_build"
    PLAN_GATE = "plan_gate"
    WAVE_EXECUTE = "wave_execute"
    STATE_PERSIST = "state_persist"
    VERIFY = "verify"
    FINALIZE = "finalize"


class DevSession(BaseModel):
    """Tracks one end-to-end orchestrator run: heavy driver + auditor + janitor."""

    id: UUID = Field(default_factory=uuid4)
    task: str = Field(description="Original task description passed to dev_session_run")
    profile_id: str | None = Field(default=None, description="Active workflow profile name")
    current_phase: OrchestratorPhase = OrchestratorPhase.PROFILE_SELECT
    phases_completed: list[OrchestratorPhase] = Field(default_factory=list)
    audit_history: list[UUID] = Field(
        default_factory=list,
        description="Ordered list of AuditReport IDs produced after each phase",
    )
    janitor_actions: list[UUID] = Field(
        default_factory=list,
        description="JanitorAction IDs applied during finalize phase",
    )
    janitor_scope_override: list[str] | None = Field(
        default=None,
        description="Per-session extra paths appended to the global janitor whitelist",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    def advance_phase(self, next_phase: OrchestratorPhase) -> None:
        """Mark current phase done and move to the next."""
        self.phases_completed.append(self.current_phase)
        self.current_phase = next_phase

    def complete(self) -> None:
        """Seal the session after finalize phase."""
        if self.current_phase not in self.phases_completed:
            self.phases_completed.append(self.current_phase)
        self.completed_at = datetime.now(UTC)
