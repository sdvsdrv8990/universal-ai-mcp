"""WorkflowProfile entity — describes which modules activate for a task category."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


LLMTier = Literal["fast", "balanced", "quality"]


class WorkflowProfile(BaseModel):
    """A named configuration preset that activates specific modules for a task type."""

    name: str = Field(description="Unique profile identifier (snake_case)")
    display_name: str
    description: str
    task_patterns: list[str] = Field(
        default_factory=list,
        description="Keyword patterns used for heuristic matching",
    )
    required_modules: list[str] = Field(
        default_factory=list,
        description="Modules that must be active when this profile is selected",
    )
    optional_modules: list[str] = Field(
        default_factory=list,
        description="Modules activated only if registered and available",
    )
    feature_overrides: dict[str, Any] = Field(
        default_factory=dict,
        description="Feature flag overrides applied on top of modules.yaml defaults",
    )
    llm_tier: LLMTier = "balanced"
    max_tokens_budget: int = Field(
        default=64000,
        description="Maximum token budget for the whole workflow",
    )

    def all_modules(self) -> list[str]:
        """Return combined list of required + optional module names."""
        return list(dict.fromkeys(self.required_modules + self.optional_modules))

    def is_module_required(self, module_name: str) -> bool:
        return module_name in self.required_modules


class ActiveProfileState(BaseModel):
    """Runtime state tracking the currently active profile."""

    profile: WorkflowProfile
    activated_modules: list[str] = Field(default_factory=list)
    deactivated_modules: list[str] = Field(default_factory=list)
    feature_flags: dict[str, Any] = Field(default_factory=dict)
    task_description: str = ""
    classification_confidence: float = 0.0
