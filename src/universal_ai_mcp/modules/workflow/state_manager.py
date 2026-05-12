"""State manager — persists workflow state to disk for cross-session continuity.

Writes structured artifacts to .planning/ directory (GSD pattern):
  - STATE.md    — current phase, active plan ID, last checkpoint
  - CONTEXT.md  — project decisions, constraints, key findings
  - PLANS/      — one JSON file per ExecutionPlan
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import structlog

from universal_ai_mcp.entities.plan_entity import ExecutionPlan
from universal_ai_mcp.entities.session_entity import AgentSession

log = structlog.get_logger(__name__)

PLANNING_DIR = ".planning"


class StateManager:
    """Reads and writes GSD-style planning artifacts for session continuity."""

    def __init__(self, project_root: Path) -> None:
        self._root = project_root
        self._planning_dir = project_root / PLANNING_DIR
        self._plans_dir = self._planning_dir / "PLANS"

    def initialize_directories(self) -> None:
        self._planning_dir.mkdir(exist_ok=True)
        self._plans_dir.mkdir(exist_ok=True)
        log.info("planning_dir_initialized", path=str(self._planning_dir))

    def save_plan(self, plan: ExecutionPlan) -> Path:
        self.initialize_directories()
        plan_file = self._plans_dir / f"{plan.id}.json"
        plan_file.write_text(plan.model_dump_json(indent=2))
        log.info("plan_saved", plan_id=str(plan.id), path=str(plan_file))
        return plan_file

    def load_plan(self, plan_id: str) -> ExecutionPlan | None:
        plan_file = self._plans_dir / f"{plan_id}.json"
        if not plan_file.exists():
            return None
        try:
            data = json.loads(plan_file.read_text())
            return ExecutionPlan.model_validate(data)
        except (json.JSONDecodeError, Exception) as e:
            log.error("plan_load_failed", plan_id=plan_id, error=str(e))
            return None

    def write_state(self, session: AgentSession) -> None:
        self.initialize_directories()
        state_file = self._planning_dir / "STATE.md"
        plan_id = str(session.active_plan.id) if session.active_plan else "none"
        content = (
            f"# State\n\n"
            f"Updated: {datetime.now(UTC).isoformat()}\n\n"
            f"Session: {session.id}\n"
            f"Phase: {session.state.value}\n"
            f"Active Plan: {plan_id}\n"
            f"Token Usage: {session.total_token_usage}\n"
        )
        state_file.write_text(content)

    def append_context(self, key: str, value: str) -> None:
        self.initialize_directories()
        ctx_file = self._planning_dir / "CONTEXT.md"
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
        entry = f"\n## {key} ({timestamp})\n\n{value}\n"
        with ctx_file.open("a") as f:
            f.write(entry)

    def read_context(self) -> str:
        ctx_file = self._planning_dir / "CONTEXT.md"
        if not ctx_file.exists():
            return ""
        return ctx_file.read_text()
