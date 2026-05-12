"""AuditReport entity — result of a local auditor run after each orchestrator phase."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AuditSeverity(str, Enum):
    LOW = "low"
    MED = "med"
    HIGH = "high"


class AuditReport(BaseModel):
    """Structured result from local_auditor after a single pipeline phase."""

    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    phase: str = Field(description="OrchestratorPhase value that triggered this audit")
    severity: AuditSeverity
    missed_actions: list[str] = Field(default_factory=list)
    questionable_choices: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_blocking(self) -> bool:
        """True when severity=high — pipeline must halt."""
        return self.severity == AuditSeverity.HIGH
