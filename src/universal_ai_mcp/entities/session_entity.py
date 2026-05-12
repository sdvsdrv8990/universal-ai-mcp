"""AgentSession entity — per-connection state for a user agent session."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from universal_ai_mcp.entities.idea_block_entity import IdeaBlockCollection
from universal_ai_mcp.entities.plan_entity import ExecutionPlan
from universal_ai_mcp.entities.project_entity import ProjectContext


class SessionState(str, Enum):
    INITIALIZING = "initializing"   # Detecting project, loading context
    QUESTIONING = "questioning"     # Asking clarifying questions
    PLANNING = "planning"           # Building execution plan
    AWAITING_APPROVAL = "awaiting_approval"  # Plan ready, waiting for user OK
    EXECUTING = "executing"         # Running approved plan
    VERIFYING = "verifying"         # Checking completed work
    IDLE = "idle"                   # No active task


class AgentSession(BaseModel):
    """Stateful session for one connected AI agent."""

    id: UUID = Field(default_factory=uuid4)
    state: SessionState = SessionState.INITIALIZING
    project_context: ProjectContext | None = None
    active_plan: ExecutionPlan | None = None
    plan_history: list[UUID] = Field(default_factory=list)
    idea_block_collection: IdeaBlockCollection | None = Field(
        default=None,
        description="Accumulated IdeaBlocks for this session, persisted between tool calls",
    )
    context_token_usage: int = Field(default=0)
    total_token_usage: int = Field(default=0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_active_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def touch(self) -> None:
        self.last_active_at = datetime.now(UTC)

    def transition(self, new_state: SessionState) -> None:
        self.state = new_state
        self.touch()
