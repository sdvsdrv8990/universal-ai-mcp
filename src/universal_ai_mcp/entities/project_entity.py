"""ProjectContext entity — detected project structure and tech stack."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class StackLanguage(str, Enum):
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    GO = "go"
    RUST = "rust"
    JAVA = "java"
    CSHARP = "csharp"
    RUBY = "ruby"
    PHP = "php"
    UNKNOWN = "unknown"


class StackFramework(str, Enum):
    FASTAPI = "fastapi"
    DJANGO = "django"
    FLASK = "flask"
    EXPRESS = "express"
    NEXTJS = "nextjs"
    REACT = "react"
    VUE = "vue"
    ANGULAR = "angular"
    NESTJS = "nestjs"
    SPRING = "spring"
    RAILS = "rails"
    UNKNOWN = "unknown"


class ProjectStack(BaseModel):
    """Detected technology stack of a project."""

    primary_language: StackLanguage = StackLanguage.UNKNOWN
    frameworks: list[StackFramework] = Field(default_factory=list)
    package_manager: str | None = None
    test_framework: str | None = None
    has_docker: bool = False
    has_ci: bool = False
    has_migrations: bool = False
    dependency_file: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class NamingConventions(BaseModel):
    """Project-specific naming and file organization conventions."""

    file_case: str = "snake_case"        # snake_case | camelCase | kebab-case | PascalCase
    component_suffix: str | None = None  # e.g. "_service", "Service"
    test_prefix: str = "test_"
    test_directory: str = "tests"
    source_directory: str = "src"
    config_directory: str = "config"


class ProjectContext(BaseModel):
    """Full context about the current user project."""

    root_path: Path
    name: str
    stack: ProjectStack = Field(default_factory=ProjectStack)
    conventions: NamingConventions = Field(default_factory=NamingConventions)
    entry_points: list[str] = Field(default_factory=list)
    key_directories: dict[str, str] = Field(default_factory=dict)
    environment_variables: list[str] = Field(
        default_factory=list,
        description="Env var names detected (not values)",
    )
    existing_modules: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_detected(self) -> bool:
        return self.stack.confidence > 0.5
