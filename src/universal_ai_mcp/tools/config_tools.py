"""Dynamic config MCP tools — AI-driven workflow profile management.

Registered tools:
  - config_analyze_task      : Classify a task and recommend a workflow profile
  - config_activate_profile  : Switch the active workflow profile (enable/disable modules)
  - config_get_active_profile: Return the currently active profile and module states
  - config_list_profiles     : List all available workflow profiles with their module sets
  - config_reload_profiles   : Hot-reload workflow_profiles.yaml without server restart
  - config_toggle_module     : Manually enable or disable a single module
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from universal_ai_mcp.core.dynamic_config import get_dynamic_config
from universal_ai_mcp.core.registry import ToolRegistry
from universal_ai_mcp.entities.module_entity import Module, ModuleScenario, ScenarioType

MODULE_DEFINITION = Module(
    name="config",
    display_name="Dynamic Config",
    description=(
        "AI-driven workflow profile manager. Analyzes a task description and "
        "activates the right set of modules. Supports hot-reload of profile YAML."
    ),
    scenarios=[
        ModuleScenario(
            name="auto_select_workflow",
            description="AI analyzes a task and selects the appropriate workflow profile",
            scenario_type=ScenarioType.SYSTEM,
            required_tools=["config_analyze_task", "config_activate_profile"],
            example_prompt="I need to refactor the authentication module",
        ),
        ModuleScenario(
            name="manual_profile_switch",
            description="Operator manually switches to a named workflow profile",
            scenario_type=ScenarioType.USER,
            required_tools=["config_activate_profile"],
        ),
        ModuleScenario(
            name="inspect_active_config",
            description="Inspect which modules are active and which profile is selected",
            scenario_type=ScenarioType.USER,
            required_tools=["config_get_active_profile"],
        ),
    ],
    mcp_tools=[
        "config_analyze_task",
        "config_activate_profile",
        "config_get_active_profile",
        "config_list_profiles",
        "config_reload_profiles",
        "config_toggle_module",
    ],
)


def register_config_tools(mcp: FastMCP, registry: ToolRegistry) -> None:
    registry.register_module(MODULE_DEFINITION)

    @mcp.tool()
    async def config_analyze_task(task_description: str) -> str:
        """Analyze a task description and recommend the best workflow profile.

        The AI classifies the task and returns the profile name, confidence score,
        and the list of modules that would be activated. Does NOT activate anything —
        call config_activate_profile to apply the recommendation.
        """
        from universal_ai_mcp.core.config import get_settings
        from universal_ai_mcp.modules.llm.provider_registry import LLMProviderRegistry
        from universal_ai_mcp.modules.llm.router import LLMRouter

        settings = get_settings()
        router = LLMRouter(LLMProviderRegistry.from_settings(settings), settings)
        mgr = get_dynamic_config()

        profile, confidence = await mgr.analyze_task(task_description, router)

        return json.dumps({
            "recommended_profile": profile.name,
            "display_name": profile.display_name,
            "confidence": round(confidence, 2),
            "description": profile.description,
            "required_modules": profile.required_modules,
            "optional_modules": profile.optional_modules,
            "feature_overrides": profile.feature_overrides,
            "llm_tier": profile.llm_tier,
            "max_tokens_budget": profile.max_tokens_budget,
        }, indent=2)

    @mcp.tool()
    async def config_activate_profile(
        profile_name: str,
        task_description: str = "",
    ) -> str:
        """Activate a workflow profile — enables required modules, disables the rest.

        After activation, only tools belonging to active modules will respond.
        Feature flag overrides from the profile are applied immediately.

        Args:
            profile_name: One of the profile names returned by config_list_profiles.
            task_description: Optional — the task that prompted this switch (for logging).
        """
        mgr = get_dynamic_config()
        state = mgr.activate_profile(profile_name, registry, task_description)

        return json.dumps({
            "activated": True,
            "profile": state.profile.name,
            "display_name": state.profile.display_name,
            "modules_activated": state.activated_modules,
            "modules_deactivated": state.deactivated_modules,
            "feature_flags": state.feature_flags,
            "active_modules": [m.name for m in registry.list_active_modules()],
            "active_tools_count": len(registry.list_active_tool_names()),
        }, indent=2)

    @mcp.tool()
    async def config_get_active_profile() -> str:
        """Return the currently active workflow profile and the state of all modules.

        Use this to inspect what is currently active before starting a task.
        """
        mgr = get_dynamic_config()
        state = mgr.get_active_state()

        active_modules = [
            {
                "name": m.name,
                "display_name": m.display_name,
                "enabled": m.enabled,
                "tools": m.mcp_tools,
            }
            for m in registry.list_modules()
        ]

        if state is None:
            return json.dumps({
                "active_profile": None,
                "message": "No profile activated yet — all registered modules are active by default",
                "modules": active_modules,
            }, indent=2)

        return json.dumps({
            "active_profile": state.profile.name,
            "display_name": state.profile.display_name,
            "description": state.profile.description,
            "classification_confidence": state.classification_confidence,
            "task_description": state.task_description,
            "feature_flags": state.feature_flags,
            "modules": active_modules,
            "active_tools_count": len(registry.list_active_tool_names()),
        }, indent=2)

    @mcp.tool()
    async def config_list_profiles() -> str:
        """List all available workflow profiles with their module requirements.

        Use this to understand what profiles exist before calling config_activate_profile
        or config_analyze_task.
        """
        mgr = get_dynamic_config()
        profiles = mgr.list_profiles()

        return json.dumps({
            "profiles": [
                {
                    "name": p.name,
                    "display_name": p.display_name,
                    "description": p.description,
                    "required_modules": p.required_modules,
                    "optional_modules": p.optional_modules,
                    "llm_tier": p.llm_tier,
                    "max_tokens_budget": p.max_tokens_budget,
                    "feature_overrides": p.feature_overrides,
                }
                for p in profiles
            ],
            "default_profile": mgr.get_default_profile().name,
            "total": len(profiles),
        }, indent=2)

    @mcp.tool()
    async def config_reload_profiles() -> str:
        """Hot-reload workflow_profiles.yaml without restarting the server.

        Use after editing config/workflow_profiles.yaml to apply changes immediately.
        The currently active profile state is preserved; module activation is NOT
        automatically re-applied — call config_activate_profile again if needed.
        """
        mgr = get_dynamic_config()
        count = mgr.reload_profiles()
        return json.dumps({"reloaded": True, "profiles_loaded": count})

    @mcp.tool()
    async def config_toggle_module(module_name: str, enabled: bool) -> str:
        """Manually enable or disable a single registered module.

        This bypasses profile logic — use for fine-grained control or debugging.
        Changes are NOT persisted to disk; they reset on the next profile activation.

        Args:
            module_name: Exact module name (e.g. "planning", "solutions").
            enabled: True to enable, False to disable.
        """
        if enabled:
            success = registry.enable_module(module_name)
        else:
            success = registry.disable_module(module_name)

        if not success:
            return json.dumps({
                "error": f"Module '{module_name}' is not registered",
                "registered_modules": [m.name for m in registry.list_modules()],
            })

        return json.dumps({
            "module": module_name,
            "enabled": enabled,
            "active_modules": [m.name for m in registry.list_active_modules()],
        }, indent=2)
