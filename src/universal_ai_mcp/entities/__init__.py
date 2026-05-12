"""Domain entities — each entity class is declared exactly once here.

Import entities from this package, never from individual files directly,
to maintain a single authoritative source of truth.
"""

from universal_ai_mcp.entities.idea_block_entity import IdeaBlock, IdeaBlockCollection
from universal_ai_mcp.entities.module_entity import Module, ModuleScenario
from universal_ai_mcp.entities.plan_entity import ExecutionPlan, PlanStep, PlanStepStatus
from universal_ai_mcp.entities.project_entity import ProjectContext, ProjectStack
from universal_ai_mcp.entities.provider_entity import LLMProvider, LLMRequest, LLMResponse
from universal_ai_mcp.entities.session_entity import AgentSession, SessionState
from universal_ai_mcp.entities.task_entity import Task, TaskResult, TaskStatus
from universal_ai_mcp.entities.memory_entity import (
    IndexResult,
    MemoryEntry,
    MemoryQuery,
    MemoryScope,
    MemorySearchResult,
)
from universal_ai_mcp.entities.workflow_profile_entity import (
    ActiveProfileState,
    WorkflowProfile,
)
from universal_ai_mcp.entities.audit_report_entity import AuditReport, AuditSeverity
from universal_ai_mcp.entities.janitor_action_entity import JanitorAction, JanitorChangeType
from universal_ai_mcp.entities.dev_session_entity import DevSession, OrchestratorPhase

__all__ = [
    "IdeaBlock",
    "IdeaBlockCollection",
    "Module",
    "ModuleScenario",
    "ExecutionPlan",
    "PlanStep",
    "PlanStepStatus",
    "ProjectContext",
    "ProjectStack",
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "AgentSession",
    "SessionState",
    "Task",
    "TaskResult",
    "TaskStatus",
    "WorkflowProfile",
    "ActiveProfileState",
    "MemoryScope",
    "MemoryEntry",
    "MemoryQuery",
    "MemorySearchResult",
    "IndexResult",
    "AuditReport",
    "AuditSeverity",
    "JanitorAction",
    "JanitorChangeType",
    "DevSession",
    "OrchestratorPhase",
]
