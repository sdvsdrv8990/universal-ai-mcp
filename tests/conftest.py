"""Shared pytest fixtures for all test suites."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from universal_ai_mcp.entities.plan_entity import ExecutionPlan, PlanStep
from universal_ai_mcp.entities.project_entity import (
    NamingConventions,
    ProjectContext,
    ProjectStack,
    StackLanguage,
)
from universal_ai_mcp.entities.session_entity import AgentSession


@pytest.fixture
def python_project_context(tmp_path: Path) -> ProjectContext:
    return ProjectContext(
        root_path=tmp_path,
        name="test-project",
        stack=ProjectStack(
            primary_language=StackLanguage.PYTHON,
            package_manager="uv",
            confidence=0.95,
        ),
        conventions=NamingConventions(
            file_case="snake_case",
            test_prefix="test_",
            test_directory="tests",
            source_directory="src",
        ),
    )


@pytest.fixture
def agent_session(python_project_context: ProjectContext) -> AgentSession:
    session = AgentSession()
    session.project_context = python_project_context
    return session


@pytest.fixture
def simple_plan(agent_session: AgentSession) -> ExecutionPlan:
    steps = [
        PlanStep(order=0, title="Step A", description="First step", tool_name="llm_complete"),
        PlanStep(order=1, title="Step B", description="Second step", tool_name="workflow_verify_work"),
    ]
    plan = ExecutionPlan(
        session_id=agent_session.id,
        title="Test Plan",
        objective="Test the execution engine",
        complexity="simple",
        steps=steps,
    )
    return plan
