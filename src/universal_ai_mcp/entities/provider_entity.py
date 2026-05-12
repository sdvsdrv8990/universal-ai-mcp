"""LLMProvider entity — provider configuration and request/response contracts."""

from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, SecretStr


class ProviderName(str, Enum):
    ANTHROPIC = "anthropic"
    OPENROUTER = "openrouter"
    OLLAMA = "ollama"


class LLMProvider(BaseModel):
    """Configuration for a single LLM provider."""

    name: ProviderName
    base_url: str
    api_key: SecretStr | None = None
    default_model: str
    available_models: list[str] = Field(default_factory=list)
    supports_streaming: bool = True
    max_context_tokens: int = 200000
    priority: int = Field(default=0, description="Lower = higher priority for routing")
    enabled: bool = True


class LLMMessage(BaseModel):
    role: str = Field(description="system | user | assistant")
    content: str


class LLMRequest(BaseModel):
    """Normalized request sent to any LLM provider."""

    id: UUID = Field(default_factory=uuid4)
    model: str
    messages: list[LLMMessage]
    system_prompt: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.7
    stream: bool = False
    response_format: dict[str, Any] | None = Field(
        default=None,
        description="Provider-native JSON schema constraint (Ollama format / OpenRouter response_format)",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    """Normalized response from any LLM provider."""

    request_id: UUID
    provider: ProviderName
    model: str
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str = "stop"
    raw: dict[str, Any] = Field(default_factory=dict, description="Original provider response")

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens
