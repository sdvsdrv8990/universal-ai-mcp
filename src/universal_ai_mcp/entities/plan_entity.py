"""ExecutionPlan entity — structured plan produced by the planning gate.

No tool invocation proceeds without an approved ExecutionPlan.
Inspired by GSD's planning artifacts and phase-gate workflow.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class PlanStepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PlanStep(BaseModel):
    """Single actionable step within an ExecutionPlan."""

    id: UUID = Field(default_factory=uuid4)
    order: int
    title: str
    description: str
    tool_name: str | None = Field(default=None, description="MCP tool to invoke for this step")
    estimated_tokens: int = Field(default=0)
    depends_on: list[UUID] = Field(default_factory=list, description="Step IDs this step requires")
    status: PlanStepStatus = PlanStepStatus.PENDING
    result_summary: str | None = None

    @property
    def is_ready(self) -> bool:
        """True when all dependencies are completed."""
        return self.status == PlanStepStatus.PENDING


class ExecutionPlan(BaseModel):
    """Complete plan that must be approved before any execution begins."""

    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    title: str
    objective: str = Field(description="What the plan achieves")
    complexity: str = Field(description="simple | medium | complex")
    steps: list[PlanStep] = Field(default_factory=list)
    clarifying_questions: list[str] = Field(
        default_factory=list,
        description="Questions posed to the user before this plan was finalized",
    )
    selected_tools: list[str] = Field(
        default_factory=list,
        description="MCP tools selected with justification",
    )
    tool_justifications: dict[str, str] = Field(
        default_factory=dict,
        description="tool_name -> reason for selection",
    )
    approved: bool = Field(default=False)
    approved_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def total_estimated_tokens(self) -> int:
        return sum(s.estimated_tokens for s in self.steps)

    @property
    def pending_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == PlanStepStatus.PENDING]

    @property
    def completed_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == PlanStepStatus.COMPLETED]

    def approve(self) -> None:
        self.approved = True
        self.approved_at = datetime.now(UTC)
