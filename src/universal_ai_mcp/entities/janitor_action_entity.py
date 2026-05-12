"""JanitorAction entity — a single file-modification action taken by the local janitor."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class JanitorChangeType(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    APPEND = "append"


class JanitorAction(BaseModel):
    """One atomic write/update performed by local_janitor on a whitelisted path."""

    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    file_path: str = Field(description="Relative path from project root, must be in scope whitelist")
    change_type: JanitorChangeType
    description: str = Field(description="Human-readable summary of what was changed and why")
    applied: bool = False
    applied_at: datetime | None = None

    def mark_applied(self) -> None:
        self.applied = True
        self.applied_at = datetime.now(UTC)
