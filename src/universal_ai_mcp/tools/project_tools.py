"""Project detection module MCP tools.

Registered tools:
  - project_detect          : auto-detect stack and conventions from path
  - project_map_codebase    : produce structured file-tree + architecture overview (GSD entrypoint)
  - project_recommend_stack : get AI-powered stack recommendation for new project
  - project_adapt_name      : rewrite a file/dir name to match project conventions
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from mcp.server.fastmcp import FastMCP

from universal_ai_mcp.core.registry import ToolRegistry
from universal_ai_mcp.entities.module_entity import Module, ModuleScenario, ScenarioType

MODULE_DEFINITION = Module(
    name="project_detection",
    display_name="Project Detector & Stack Advisor",
    description=(
        "Auto-detects project stack and naming conventions from the filesystem. "
        "Recommends optimal tech stack for new projects. "
        "Adapts all server suggestions to match detected conventions."
    ),
    scenarios=[
        ModuleScenario(
            name="session_init_detection",
            description="Detect project at session start before any work begins",
            scenario_type=ScenarioType.SYSTEM,
            required_tools=["project_detect"],
        ),
        ModuleScenario(
            name="codebase_mapping",
            description="Produce full file-tree and architecture overview for GSD map-codebase step",
            scenario_type=ScenarioType.USER,
            required_tools=["project_map_codebase"],
        ),
        ModuleScenario(
            name="greenfield_stack_selection",
            description="User starting a new project needs stack recommendation",
            scenario_type=ScenarioType.USER,
            required_tools=["project_recommend_stack"],
        ),
    ],
    mcp_tools=["project_detect", "project_map_codebase", "project_recommend_stack", "project_adapt_name"],
)


def register_project_tools(mcp: FastMCP, registry: ToolRegistry) -> None:
    registry.register_module(MODULE_DEFINITION)

    @mcp.tool()
    async def project_detect(project_path: str, session_id: str | None = None) -> str:
        """Detect the tech stack and naming conventions of a project.

        Call at the start of each session. The detected context is stored
        in the session and used by all subsequent tools.
        """
        from universal_ai_mcp.modules.project_detection.stack_detector import StackDetector

        root = Path(project_path).resolve()
        if not root.is_dir():
            return json.dumps({"error": f"Path not found: {project_path}"})

        detector = StackDetector()
        ctx = await detector.detect(root)

        session_store = mcp.state.session_store
        session = session_store.get_or_create(UUID(session_id) if session_id else None)
        session.project_context = ctx

        return json.dumps({
            "session_id": str(session.id),
            "project": ctx.name,
            "language": ctx.stack.primary_language.value,
            "frameworks": [f.value for f in ctx.stack.frameworks],
            "package_manager": ctx.stack.package_manager,
            "test_framework": ctx.stack.test_framework,
            "conventions": {
                "file_case": ctx.conventions.file_case,
                "test_prefix": ctx.conventions.test_prefix,
                "source_dir": ctx.conventions.source_directory,
                "test_dir": ctx.conventions.test_directory,
            },
            "has_docker": ctx.stack.has_docker,
            "has_ci": ctx.stack.has_ci,
            "confidence": f"{ctx.stack.confidence:.0%}",
            "existing_modules": ctx.existing_modules,
        }, indent=2)

    @mcp.tool()
    async def project_map_codebase(project_path: str, max_depth: int = 4) -> str:
        """Produce a structured file-tree and architecture overview of a project.

        Equivalent to GSD's gsd-map-codebase step. Returns:
          - Annotated directory tree up to max_depth levels
          - File counts and dominant extensions per directory
          - Entry points, config files, and test locations

        Call once at the start of a session before planning or task analysis.
        """
        root = Path(project_path).resolve()
        if not root.is_dir():
            return json.dumps({"error": f"Path not found: {project_path}"})

        ignore_dirs = {
            ".git", "__pycache__", ".pytest_cache", "node_modules",
            ".venv", "venv", ".tox", "dist", "build", ".eggs",
            ".mypy_cache", ".ruff_cache", "htmlcov", ".planning",
        }

        def _walk(path: Path, depth: int) -> dict:
            node: dict = {"name": path.name, "type": "dir", "children": []}
            if depth == 0:
                node["truncated"] = True
                return node
            try:
                entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
            except PermissionError:
                return node
            for entry in entries:
                if entry.name.startswith(".") and entry.name not in {".env.example", ".github"}:
                    continue
                if entry.is_dir() and entry.name in ignore_dirs:
                    continue
                if entry.is_dir():
                    node["children"].append(_walk(entry, depth - 1))
                else:
                    node["children"].append({"name": entry.name, "type": "file"})
            return node

        tree = _walk(root, max_depth)

        py_files = list(root.rglob("*.py"))
        entry_points = [
            str(f.relative_to(root))
            for f in py_files
            if f.name in ("main.py", "server.py", "app.py", "__main__.py", "cli.py")
        ]
        config_files = [
            str(f.relative_to(root))
            for f in root.iterdir()
            if f.is_file() and f.suffix in (".toml", ".yaml", ".yml", ".json", ".cfg", ".ini")
        ]
        test_dirs = sorted({
            str(f.parent.relative_to(root))
            for f in py_files
            if "test" in f.parent.name or f.name.startswith("test_")
        })

        return json.dumps({
            "root": str(root),
            "tree": tree,
            "entry_points": entry_points,
            "config_files": config_files,
            "test_directories": test_dirs,
            "python_file_count": len(py_files),
        }, indent=2)

    @mcp.tool()
    async def project_recommend_stack(
        project_description: str,
        team_size: int = 1,
        deployment_target: str = "cloud",
        constraints: str = "",
    ) -> str:
        """Get an AI-powered tech stack recommendation for a new project.

        Returns language, frameworks, package manager, testing approach,
        dependency rationale, and trade-offs.
        """
        from universal_ai_mcp.core.config import get_settings
        from universal_ai_mcp.modules.llm.provider_registry import LLMProviderRegistry
        from universal_ai_mcp.modules.llm.router import LLMRouter
        from universal_ai_mcp.modules.project_detection.stack_advisor import StackAdvisor

        settings = get_settings()
        router = LLMRouter(LLMProviderRegistry.from_settings(settings), settings)
        advisor = StackAdvisor(router)

        constraint_list = [c.strip() for c in constraints.split(",") if c.strip()]
        recommendation = await advisor.recommend(
            project_description, team_size, deployment_target, constraint_list
        )
        return json.dumps(recommendation, indent=2)

    @mcp.tool()
    async def project_adapt_name(name: str, session_id: str, kind: str = "file") -> str:
        """Rewrite a name to match the detected project's naming convention.

        Args:
            name: The name to adapt (file, directory, class, etc.).
            session_id: Current session with detected project context.
            kind: 'file' | 'test_file' | 'directory'.
        """
        from universal_ai_mcp.modules.project_detection.convention_adapter import ConventionAdapter

        session = mcp.state.session_store.get(UUID(session_id))
        if not session or not session.project_context:
            return json.dumps({"error": "No project context in session. Call project_detect first."})

        adapter = ConventionAdapter()
        conventions = session.project_context.conventions

        if kind == "test_file":
            adapted = adapter.adapt_test_filename(name, conventions)
        elif kind == "directory":
            adapted = adapter.adapt_directory(name, conventions)
        else:
            adapted = adapter.adapt_filename(name, conventions)

        return json.dumps({"original": name, "adapted": adapted, "convention": conventions.file_case})
