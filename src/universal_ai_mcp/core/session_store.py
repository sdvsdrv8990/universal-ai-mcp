"""In-memory session store — manages AgentSession lifecycle per connection."""

from __future__ import annotations

from uuid import UUID

import structlog

from universal_ai_mcp.entities.session_entity import AgentSession

log = structlog.get_logger(__name__)


class SessionStore:
    """Thread-safe in-memory store for active agent sessions."""

    def __init__(self) -> None:
        self._sessions: dict[UUID, AgentSession] = {}

    def create(self) -> AgentSession:
        session = AgentSession()
        self._sessions[session.id] = session
        log.info("session_created", session_id=str(session.id))
        return session

    def get(self, session_id: UUID) -> AgentSession | None:
        return self._sessions.get(session_id)

    def get_or_create(self, session_id: UUID | None) -> AgentSession:
        if session_id and session_id in self._sessions:
            session = self._sessions[session_id]
            session.touch()
            return session
        return self.create()

    def delete(self, session_id: UUID) -> None:
        self._sessions.pop(session_id, None)
        log.info("session_deleted", session_id=str(session_id))

    def active_count(self) -> int:
        return len(self._sessions)
