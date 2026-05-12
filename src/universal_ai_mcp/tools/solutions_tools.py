"""Solutions module MCP tools — find ready solutions, optimize deps, plan integration.

Registered tools:
  - solutions_find         : search GitHub for repos matching a requirement
  - solutions_optimize_deps: trim dependencies to minimum required subset
  - solutions_plan_integration: generate layer-by-layer integration plan
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from universal_ai_mcp.core.registry import ToolRegistry
from universal_ai_mcp.entities.module_entity import Module, ModuleScenario, ScenarioType

MODULE_DEFINITION = Module(
    name="solutions",
    display_name="Ready Solutions Finder",
    description=(
        "Searches GitHub for existing implementations before writing code from scratch. "
        "Optimizes dependencies to minimum required set. "
        "Generates layer-by-layer integration plans referencing actual source code."
    ),
    scenarios=[
        ModuleScenario(
            name="find_before_build",
            description="Search for existing solution before starting implementation",
            scenario_type=ScenarioType.SYSTEM,
            required_tools=["solutions_find"],
        ),
        ModuleScenario(
            name="adopt_library",
            description="User wants to integrate a specific library with minimal deps",
            scenario_type=ScenarioType.USER,
            required_tools=["solutions_optimize_deps", "solutions_plan_integration"],
        ),
    ],
    mcp_tools=["solutions_find", "solutions_optimize_deps", "solutions_plan_integration"],
)


def register_solutions_tools(mcp: FastMCP, registry: ToolRegistry) -> None:
    registry.register_module(MODULE_DEFINITION)

    @mcp.tool()
    async def solutions_find(
        requirement: str,
        language: str | None = None,
        min_stars: int = 100,
    ) -> str:
        """Search GitHub for open-source repositories matching a requirement.

        Always call this before implementing a feature from scratch.
        Returns top candidates with stars, description, and license.
        """
        from universal_ai_mcp.core.config import get_settings
        from universal_ai_mcp.modules.solutions.github_finder import GitHubFinder

        settings = get_settings()
        token = settings.github_token.get_secret_value() if settings.github_token else None
        finder = GitHubFinder(token, settings.github_search_max_results)

        candidates = await finder.search(requirement, language, min_stars)

        return json.dumps({
            "query": requirement,
            "results": [
                {
                    "name": c.full_name,
                    "stars": c.stars,
                    "description": c.description,
                    "url": c.url,
                    "language": c.language,
                    "license": c.license_name,
                    "topics": c.topics[:5],
                }
                for c in candidates
            ],
        }, indent=2)

    @mcp.tool()
    async def solutions_optimize_deps(
        library_name: str,
        features_used: str,
        dependency_tree: str,
    ) -> str:
        """Analyze a library's dependency tree and identify minimum required deps.

        Args:
            library_name: Name of the library being integrated.
            features_used: Comma-separated list of features actually used.
            dependency_tree: Output of pip tree / npm ls / cargo tree etc.
        """
        from universal_ai_mcp.core.config import get_settings
        from universal_ai_mcp.modules.llm.provider_registry import LLMProviderRegistry
        from universal_ai_mcp.modules.llm.router import LLMRouter
        from universal_ai_mcp.modules.solutions.dependency_optimizer import DependencyOptimizer

        settings = get_settings()
        router = LLMRouter(LLMProviderRegistry.from_settings(settings), settings)
        optimizer = DependencyOptimizer(router)

        features = [f.strip() for f in features_used.split(",") if f.strip()]
        result = await optimizer.optimize(library_name, features, dependency_tree)
        return json.dumps(result, indent=2)

    @mcp.tool()
    async def solutions_plan_integration(
        solution_name: str,
        target_feature: str,
        session_id: str,
    ) -> str:
        """Generate a layer-by-layer integration plan for adopting a ready solution.

        Fetches the solution README, analyzes the code to extract, and creates
        a per-layer plan with adapted file names matching project conventions.
        """
        from uuid import UUID

        from universal_ai_mcp.core.config import get_settings
        from universal_ai_mcp.modules.llm.provider_registry import LLMProviderRegistry
        from universal_ai_mcp.modules.llm.router import LLMRouter
        from universal_ai_mcp.modules.project_detection.convention_adapter import ConventionAdapter
        from universal_ai_mcp.modules.solutions.github_finder import GitHubFinder
        from universal_ai_mcp.modules.solutions.integration_planner import IntegrationPlanner

        settings = get_settings()
        router = LLMRouter(LLMProviderRegistry.from_settings(settings), settings)
        token = settings.github_token.get_secret_value() if settings.github_token else None
        finder = GitHubFinder(token)
        adapter = ConventionAdapter()
        planner = IntegrationPlanner(router, adapter)

        session = mcp.state.session_store.get(UUID(session_id))
        if not session or not session.project_context:
            return json.dumps({"error": "No project context. Call project_detect first."})

        readme = await finder.get_readme(solution_name)
        plan = await planner.plan(solution_name, readme, target_feature, session.project_context)
        return json.dumps(plan, indent=2)
