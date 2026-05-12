"""Task entity — atomic unit of work within an execution plan."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskResult(BaseModel):
    """Output produced by a completed task."""

    success: bool
    output: Any = None
    error_message: str | None = None
    token_cost: int = 0
    duration_ms: float = 0.0
    artifacts: list[str] = Field(
        default_factory=list,
        description="File paths or resource identifiers produced",
    )


class Task(BaseModel):
    """Single atomic unit of work, traceable and verifiable."""

    id: UUID = Field(default_factory=uuid4)
    plan_id: UUID
    step_id: UUID
    title: str
    tool_name: str
    tool_input: dict[str, Any] = Field(default_factory=dict)
    status: TaskStatus = TaskStatus.QUEUED
    result: TaskResult | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def mark_running(self) -> None:
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.now(UTC)

    def mark_completed(self, result: TaskResult) -> None:
        self.status = TaskStatus.COMPLETED
        self.result = result
        self.completed_at = datetime.now(UTC)

    def mark_failed(self, error: str) -> None:
        self.status = TaskStatus.FAILED
        self.result = TaskResult(success=False, error_message=error)
        self.completed_at = datetime.now(UTC)
