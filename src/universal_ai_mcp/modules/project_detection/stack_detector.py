"""Stack detector — identifies project language, frameworks, and conventions.

Detection is purely file-based (no LLM needed):
  - pyproject.toml / setup.py / requirements.txt → Python
  - package.json → Node.js (check dependencies for framework)
  - go.mod → Go
  - Cargo.toml → Rust
  - pom.xml / build.gradle → Java
  etc.
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from universal_ai_mcp.entities.project_entity import (
    NamingConventions,
    ProjectContext,
    ProjectStack,
    StackFramework,
    StackLanguage,
)

log = structlog.get_logger(__name__)

FRAMEWORK_INDICATORS: dict[StackFramework, list[str]] = {
    StackFramework.FASTAPI: ["fastapi"],
    StackFramework.DJANGO: ["django"],
    StackFramework.FLASK: ["flask"],
    StackFramework.EXPRESS: ["express"],
    StackFramework.NEXTJS: ["next"],
    StackFramework.REACT: ["react"],
    StackFramework.VUE: ["vue"],
    StackFramework.ANGULAR: ["@angular/core"],
    StackFramework.NESTJS: ["@nestjs/core"],
    StackFramework.RAILS: ["rails"],
}


class StackDetector:
    """Detects tech stack and conventions by scanning project files."""

    async def detect(self, root_path: Path) -> ProjectContext:
        name = root_path.name
        stack = self._detect_stack(root_path)
        conventions = self._detect_conventions(root_path, stack)
        entry_points = self._find_entry_points(root_path, stack)

        ctx = ProjectContext(
            root_path=root_path,
            name=name,
            stack=stack,
            conventions=conventions,
            entry_points=entry_points,
            existing_modules=self._list_modules(root_path),
        )
        log.info(
            "stack_detected",
            project=name,
            language=stack.primary_language,
            frameworks=[str(f) for f in stack.frameworks],
            confidence=stack.confidence,
        )
        return ctx

    def _detect_stack(self, root: Path) -> ProjectStack:
        if (root / "pyproject.toml").exists() or (root / "setup.py").exists():
            return self._python_stack(root)
        if (root / "package.json").exists():
            return self._node_stack(root)
        if (root / "go.mod").exists():
            return ProjectStack(
                primary_language=StackLanguage.GO,
                package_manager="go",
                has_docker=(root / "Dockerfile").exists(),
                has_ci=self._has_ci(root),
                confidence=0.95,
            )
        if (root / "Cargo.toml").exists():
            return ProjectStack(
                primary_language=StackLanguage.RUST,
                package_manager="cargo",
                confidence=0.95,
            )
        return ProjectStack(primary_language=StackLanguage.UNKNOWN, confidence=0.0)

    def _python_stack(self, root: Path) -> ProjectStack:
        frameworks: list[StackFramework] = []
        pkg_manager = "uv" if (root / "uv.lock").exists() else "pip"
        dep_file = "pyproject.toml" if (root / "pyproject.toml").exists() else "requirements.txt"

        deps_text = self._read_deps_text(root)
        for fw, indicators in FRAMEWORK_INDICATORS.items():
            if any(ind.lower() in deps_text for ind in indicators):
                if fw in (StackFramework.FASTAPI, StackFramework.DJANGO, StackFramework.FLASK):
                    frameworks.append(fw)

        test_fw = "pytest" if "pytest" in deps_text else None
        return ProjectStack(
            primary_language=StackLanguage.PYTHON,
            frameworks=frameworks,
            package_manager=pkg_manager,
            test_framework=test_fw,
            has_docker=(root / "Dockerfile").exists(),
            has_ci=self._has_ci(root),
            dependency_file=dep_file,
            confidence=0.95,
        )

    def _node_stack(self, root: Path) -> ProjectStack:
        frameworks: list[StackFramework] = []
        try:
            pkg = json.loads((root / "package.json").read_text())
            all_deps = {
                **pkg.get("dependencies", {}),
                **pkg.get("devDependencies", {}),
            }
            for fw, indicators in FRAMEWORK_INDICATORS.items():
                if any(ind in all_deps for ind in indicators):
                    if fw in (
                        StackFramework.EXPRESS,
                        StackFramework.NEXTJS,
                        StackFramework.REACT,
                        StackFramework.VUE,
                        StackFramework.ANGULAR,
                        StackFramework.NESTJS,
                    ):
                        frameworks.append(fw)
        except (json.JSONDecodeError, OSError):
            pass

        has_ts = (root / "tsconfig.json").exists()
        pkg_manager = (
            "bun" if (root / "bun.lockb").exists()
            else "pnpm" if (root / "pnpm-lock.yaml").exists()
            else "yarn" if (root / "yarn.lock").exists()
            else "npm"
        )
        return ProjectStack(
            primary_language=StackLanguage.TYPESCRIPT if has_ts else StackLanguage.JAVASCRIPT,
            frameworks=frameworks,
            package_manager=pkg_manager,
            has_docker=(root / "Dockerfile").exists(),
            has_ci=self._has_ci(root),
            dependency_file="package.json",
            confidence=0.9,
        )

    def _detect_conventions(self, root: Path, stack: ProjectStack) -> NamingConventions:
        conv = NamingConventions()
        if stack.primary_language == StackLanguage.PYTHON:
            conv.file_case = "snake_case"
            conv.test_prefix = "test_"
        elif stack.primary_language in (StackLanguage.TYPESCRIPT, StackLanguage.JAVASCRIPT):
            conv.file_case = "kebab-case"
            conv.test_prefix = ""

        for candidate in ("tests", "test", "__tests__", "spec"):
            if (root / candidate).is_dir():
                conv.test_directory = candidate
                break

        for candidate in ("src", "app", "lib"):
            if (root / candidate).is_dir():
                conv.source_directory = candidate
                break

        return conv

    def _find_entry_points(self, root: Path, stack: ProjectStack) -> list[str]:
        candidates: dict[StackLanguage, list[str]] = {
            StackLanguage.PYTHON: ["src/main.py", "main.py", "app.py", "src/app.py"],
            StackLanguage.TYPESCRIPT: ["src/index.ts", "index.ts", "src/main.ts"],
            StackLanguage.JAVASCRIPT: ["src/index.js", "index.js"],
        }
        found = []
        for rel in candidates.get(stack.primary_language, []):
            if (root / rel).exists():
                found.append(rel)
        return found

    def _list_modules(self, root: Path) -> list[str]:
        src = root / "src"
        if not src.is_dir():
            return []
        return [d.name for d in src.iterdir() if d.is_dir() and not d.name.startswith("_")]

    def _read_deps_text(self, root: Path) -> str:
        for fname in ("pyproject.toml", "requirements.txt", "setup.py"):
            p = root / fname
            if p.exists():
                try:
                    return p.read_text().lower()
                except OSError:
                    pass
        return ""

    def _has_ci(self, root: Path) -> bool:
        return (
            (root / ".github" / "workflows").is_dir()
            or (root / ".gitlab-ci.yml").exists()
            or (root / "Jenkinsfile").exists()
        )
