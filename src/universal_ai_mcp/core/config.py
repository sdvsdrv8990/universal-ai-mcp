"""Server configuration loaded from environment and YAML files."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerSettings(BaseSettings):
    """Top-level server settings resolved from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server identity
    mcp_server_name: str = Field(default="universal-ai-mcp", alias="MCP_SERVER_NAME")
    mcp_server_version: str = Field(default="1.0.0", alias="MCP_SERVER_VERSION")
    mcp_transport: Literal["http", "stdio"] = Field(default="http", alias="MCP_TRANSPORT")
    mcp_host: str = Field(default="0.0.0.0", alias="MCP_HOST")
    mcp_port: int = Field(default=8000, alias="MCP_PORT")
    mcp_auth_secret: SecretStr = Field(default="dev-secret", alias="MCP_AUTH_SECRET")

    # LLM providers
    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    openrouter_api_key: SecretStr | None = Field(default=None, alias="OPENROUTER_API_KEY")
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")

    # Default routing
    llm_default_provider: str = Field(default="anthropic", alias="LLM_DEFAULT_PROVIDER")
    llm_planning_model: str = Field(default="claude-sonnet-4-6", alias="LLM_PLANNING_MODEL")
    llm_context_model: str = Field(
        default="claude-haiku-4-5-20251001", alias="LLM_CONTEXT_MODEL"
    )
    llm_execution_model: str = Field(default="claude-sonnet-4-6", alias="LLM_EXECUTION_MODEL")

    # Context optimization
    context_max_tokens: int = Field(default=150000, alias="CONTEXT_MAX_TOKENS")
    context_target_ratio: float = Field(default=0.6, alias="CONTEXT_TARGET_RATIO")
    idea_block_merge_threshold: float = Field(
        default=0.85, alias="IDEA_BLOCK_MERGE_THRESHOLD"
    )

    # Planning gate
    planning_complexity_threshold_medium: int = Field(
        default=3, alias="PLANNING_COMPLEXITY_THRESHOLD_MEDIUM"
    )
    planning_complexity_threshold_complex: int = Field(
        default=7, alias="PLANNING_COMPLEXITY_THRESHOLD_COMPLEX"
    )
    planning_require_approval: bool = Field(default=True, alias="PLANNING_REQUIRE_APPROVAL")

    # GitHub integration
    github_token: SecretStr | None = Field(default=None, alias="GITHUB_TOKEN")
    github_search_max_results: int = Field(default=10, alias="GITHUB_SEARCH_MAX_RESULTS")

    # Memory module
    memory_data_dir: str = Field(
        default="~/.universal-ai-mcp/memory", alias="MEMORY_DATA_DIR"
    )
    memory_embedding_model: str = Field(
        default="nomic-embed-text", alias="MEMORY_EMBEDDING_MODEL"
    )

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: Literal["json", "text"] = Field(default="json", alias="LOG_FORMAT")


_settings: ServerSettings | None = None


def get_settings() -> ServerSettings:
    global _settings
    if _settings is None:
        _settings = ServerSettings()  # type: ignore[call-arg]
    return _settings


CONFIG_DIR = Path(__file__).parent.parent.parent.parent / "config"
