"""Solutions module — find ready solutions, optimize deps, plan integration."""

from universal_ai_mcp.modules.solutions.dependency_optimizer import DependencyOptimizer
from universal_ai_mcp.modules.solutions.github_finder import GitHubFinder
from universal_ai_mcp.modules.solutions.integration_planner import IntegrationPlanner

__all__ = ["GitHubFinder", "DependencyOptimizer", "IntegrationPlanner"]
