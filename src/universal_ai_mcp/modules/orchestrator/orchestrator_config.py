"""Orchestrator module configuration — loads and validates config/orchestrator.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

_CONFIG_PATH = Path(__file__).parent.parent.parent.parent.parent / "config" / "orchestrator.yaml"


class AuditorConfig(BaseModel):
    provider: str = "ollama"
    model: str = "qwen3:8b"
    required: bool = False
    fallback_provider: str | None = None
    fallback_model: str | None = None
    severity_thresholds: dict[str, object] = Field(default_factory=dict)


class JanitorConfig(BaseModel):
    provider: str = "ollama"
    model: str = "qwen3:8b"
    scope_whitelist: list[str] = Field(default_factory=list)
    allow_per_session_override: bool = True


class PipelineConfig(BaseModel):
    phases: list[str] = Field(default_factory=list)
    audit_after_each_phase: bool = True
    janitor_runs_after: str = "verify"


class OrchestratorConfig(BaseModel):
    auditor: AuditorConfig = Field(default_factory=AuditorConfig)
    janitor: JanitorConfig = Field(default_factory=JanitorConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)


def load_orchestrator_config(path: Path = _CONFIG_PATH) -> OrchestratorConfig:
    """Load and validate orchestrator.yaml. Returns defaults if file is missing."""
    if not path.exists():
        return OrchestratorConfig()
    raw = yaml.safe_load(path.read_text())
    return OrchestratorConfig.model_validate(raw or {})
