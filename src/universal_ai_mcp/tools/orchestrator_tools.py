"""Orchestrator module MCP tools — dual-AI pipeline entry point.

Registered tools:
  - dev_session_run : execute a full development session through the orchestrator pipeline
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from mcp.server.fastmcp import FastMCP

from universal_ai_mcp.core.registry import ToolRegistry
from universal_ai_mcp.entities.dev_session_entity import DevSession
from universal_ai_mcp.entities.module_entity import Module, ModuleScenario, ScenarioType

MODULE_DEFINITION = Module(
    name="orchestrator",
    display_name="Orchestrator",
    description=(
        "Dual-AI development pipeline: heavy driver (Claude) executes tasks "
        "while a local auditor (Ollama/qwen3:8b) reviews each phase and blocks "
        "on critical issues. A local janitor finalizes docs after verification."
    ),
    scenarios=[
        ModuleScenario(
            name="orchestrated_dev_session",
            description="Run a full task through the 7-phase pipeline with auditor + janitor",
            scenario_type=ScenarioType.USER,
            required_tools=["dev_session_run"],
        ),
    ],
    mcp_tools=["dev_session_run"],
)

# Module-level store: session_id → DevSession (in-memory, per-process lifetime)
_dev_sessions: dict[UUID, DevSession] = {}


def register_orchestrator_tools(mcp: FastMCP, registry: ToolRegistry) -> None:
    registry.register_module(MODULE_DEFINITION)

    @mcp.tool()
    async def dev_session_run(
        task: str,
        project_path: str,
        file_deltas: list[str] | None = None,
        janitor_scope: list[str] | None = None,
        xml_context: str = "",
    ) -> str:
        """Run a development task through the full dual-AI orchestrator pipeline.

        Phases: profile_select → context_build → plan_gate → wave_execute →
                state_persist → verify → finalize (janitor).

        The local auditor (Ollama/qwen3:8b) reviews after every phase.
        severity=high halts the pipeline and returns a blocking audit report.
        The janitor runs synchronously after verify, updating docs/state within
        the configured scope_whitelist.

        Args:
            task:          Description of the development task to orchestrate.
            project_path:  Absolute path to the project root (for janitor writes).
            file_deltas:   Optional list of file-change summaries (e.g. "src/foo.py: +15/-3").
                           Pass what the heavy driver changed during execution.
            janitor_scope: Optional extra paths the janitor may write this session,
                           in addition to the global scope_whitelist.
            xml_context:   Optional compressed XML context string for the auditor.

        Returns:
            JSON string with keys: status, session_id, phases_completed,
            audit_summary, janitor_actions_applied.
        """
        try:
            from universal_ai_mcp.core.config import get_settings
            from universal_ai_mcp.modules.llm.provider_registry import LLMProviderRegistry
            from universal_ai_mcp.modules.llm.router import LLMRouter
            from universal_ai_mcp.modules.orchestrator.dev_session_runner import DevSessionRunner
            from universal_ai_mcp.modules.orchestrator.local_auditor import LocalAuditor
            from universal_ai_mcp.modules.orchestrator.local_janitor import LocalJanitor
            from universal_ai_mcp.modules.orchestrator.orchestrator_config import load_orchestrator_config

            settings = get_settings()
            router = LLMRouter(LLMProviderRegistry.from_settings(settings), settings)
            config = load_orchestrator_config()

            auditor = LocalAuditor(router=router, config=config)
            janitor = LocalJanitor(
                router=router,
                config=config,
                project_path=Path(project_path).resolve(),
            )
            runner = DevSessionRunner(
                auditor=auditor,
                janitor=janitor,
                config=config,
                session_store=_dev_sessions,
            )

            result = await runner.run(
                task=task,
                file_deltas=file_deltas,
                janitor_scope=janitor_scope,
                xml_context=xml_context,
                router=router,
            )
            return json.dumps(result, indent=2)

        except Exception as exc:
            return json.dumps({"status": "error", "error": str(exc)}, indent=2)
