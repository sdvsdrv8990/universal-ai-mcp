"""Tool and module registry — single authoritative source for all registered MCP tools.

Every module registers its tools here at startup. The server exposes only
tools present in this registry; nothing is registered implicitly.
"""

from __future__ import annotations

import structlog
from mcp.server.fastmcp import FastMCP

from universal_ai_mcp.entities.module_entity import Module

log = structlog.get_logger(__name__)


class ToolRegistry:
    """Central registry mapping module names to their Module definitions and MCP tools."""

    def __init__(self) -> None:
        self._modules: dict[str, Module] = {}
        self._tool_to_module: dict[str, str] = {}

    def register_module(self, module: Module) -> None:
        if module.name in self._modules:
            raise ValueError(f"Module '{module.name}' is already registered")
        self._modules[module.name] = module
        for tool_name in module.mcp_tools:
            self._tool_to_module[tool_name] = module.name
        log.info("module_registered", module=module.name, tools=module.mcp_tools)

    def get_module(self, name: str) -> Module | None:
        return self._modules.get(name)

    def get_module_for_tool(self, tool_name: str) -> str | None:
        return self._tool_to_module.get(tool_name)

    def list_modules(self) -> list[Module]:
        return list(self._modules.values())

    def list_tool_names(self) -> list[str]:
        return list(self._tool_to_module.keys())

    def is_tool_registered(self, tool_name: str) -> bool:
        return tool_name in self._tool_to_module

    def enable_module(self, name: str) -> bool:
        """Enable a registered module. Returns False if the module is not found."""
        module = self._modules.get(name)
        if module is None:
            return False
        module.enabled = True
        log.info("module_enabled", module=name)
        return True

    def disable_module(self, name: str) -> bool:
        """Disable a registered module. Returns False if the module is not found."""
        module = self._modules.get(name)
        if module is None:
            return False
        module.enabled = False
        log.info("module_disabled", module=name)
        return True

    def list_active_modules(self) -> list[Module]:
        return [m for m in self._modules.values() if m.enabled]

    def list_active_tool_names(self) -> list[str]:
        active_module_names = {m.name for m in self.list_active_modules()}
        return [
            tool for tool, mod in self._tool_to_module.items()
            if mod in active_module_names
        ]

    def is_tool_active(self, tool_name: str) -> bool:
        mod_name = self._tool_to_module.get(tool_name)
        if mod_name is None:
            return False
        module = self._modules.get(mod_name)
        return module is not None and module.enabled


def register_all_modules(mcp: FastMCP, registry: ToolRegistry) -> None:
    """Wire all module tool registrations to the MCP server instance."""
    from universal_ai_mcp.tools.config_tools import register_config_tools
    from universal_ai_mcp.tools.context_tools import register_context_tools
    from universal_ai_mcp.tools.llm_tools import register_llm_tools
    from universal_ai_mcp.tools.memory_tools import register_memory_tools
    from universal_ai_mcp.tools.orchestrator_tools import register_orchestrator_tools
    from universal_ai_mcp.tools.planning_tools import register_planning_tools
    from universal_ai_mcp.tools.project_tools import register_project_tools
    from universal_ai_mcp.tools.solutions_tools import register_solutions_tools
    from universal_ai_mcp.tools.workflow_tools import register_workflow_tools

    register_planning_tools(mcp, registry)
    register_context_tools(mcp, registry)
    register_llm_tools(mcp, registry)
    register_project_tools(mcp, registry)
    register_solutions_tools(mcp, registry)
    register_workflow_tools(mcp, registry)
    register_config_tools(mcp, registry)
    register_memory_tools(mcp, registry)
    register_orchestrator_tools(mcp, registry)

    log.info(
        "all_modules_registered",
        module_count=len(registry.list_modules()),
        tool_count=len(registry.list_tool_names()),
    )
