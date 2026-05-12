"""Module and ModuleScenario entities — system's modular functional units.

A Module is a logical grouping of related functions.
A ModuleScenario is a named set of functions available within a module.
Scenarios are either user-facing (user-triggered) or system-internal.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ScenarioType(str, Enum):
    USER = "user"       # Triggered by user intent
    SYSTEM = "system"   # Triggered by internal orchestration


class ModuleScenario(BaseModel):
    """Named usage pattern within a module."""

    name: str
    description: str
    scenario_type: ScenarioType
    required_tools: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_description: str = ""
    example_prompt: str | None = None


class Module(BaseModel):
    """Self-contained functional unit with multiple usage scenarios."""

    name: str = Field(description="Unique module identifier (snake_case)")
    display_name: str
    description: str
    version: str = "1.0.0"
    scenarios: list[ModuleScenario] = Field(default_factory=list)
    depends_on: list[str] = Field(
        default_factory=list,
        description="Names of other modules this module requires",
    )
    mcp_tools: list[str] = Field(
        default_factory=list,
        description="MCP tool names registered by this module",
    )
    enabled: bool = True

    def get_user_scenarios(self) -> list[ModuleScenario]:
        return [s for s in self.scenarios if s.scenario_type == ScenarioType.USER]

    def get_system_scenarios(self) -> list[ModuleScenario]:
        return [s for s in self.scenarios if s.scenario_type == ScenarioType.SYSTEM]
