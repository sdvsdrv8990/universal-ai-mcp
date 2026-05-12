"""LLM provider registry — builds and manages provider instances from settings."""

from __future__ import annotations

import structlog
from pydantic import SecretStr

from universal_ai_mcp.core.config import ServerSettings
from universal_ai_mcp.entities.provider_entity import LLMProvider, ProviderName
from universal_ai_mcp.modules.llm.providers.anthropic_provider import AnthropicProvider
from universal_ai_mcp.modules.llm.providers.ollama_provider import OllamaProvider
from universal_ai_mcp.modules.llm.providers.openrouter_provider import OpenRouterProvider

log = structlog.get_logger(__name__)

AnyProvider = AnthropicProvider | OpenRouterProvider | OllamaProvider


class LLMProviderRegistry:
    """Holds all configured LLM providers ordered by priority."""

    def __init__(self) -> None:
        self._providers: dict[ProviderName, AnyProvider] = {}

    @classmethod
    def from_settings(cls, settings: ServerSettings) -> "LLMProviderRegistry":
        registry = cls()

        if settings.anthropic_api_key:
            config = LLMProvider(
                name=ProviderName.ANTHROPIC,
                base_url="https://api.anthropic.com",
                api_key=settings.anthropic_api_key,
                default_model=settings.llm_planning_model,
                available_models=[
                    "claude-opus-4-7",
                    "claude-sonnet-4-6",
                    "claude-haiku-4-5-20251001",
                ],
                priority=0,
            )
            registry.register(AnthropicProvider(config))

        if settings.openrouter_api_key:
            config = LLMProvider(
                name=ProviderName.OPENROUTER,
                base_url="https://openrouter.ai/api/v1",
                api_key=settings.openrouter_api_key,
                default_model="anthropic/claude-sonnet-4-6",
                priority=1,
            )
            registry.register(OpenRouterProvider(config))

        ollama_config = LLMProvider(
            name=ProviderName.OLLAMA,
            base_url=settings.ollama_base_url,
            api_key=None,
            default_model="qwen3.5:9b",
            available_models=["qwen3.5:9b"],
            priority=2,
        )
        registry.register(OllamaProvider(ollama_config))

        log.info("provider_registry_built", providers=list(registry._providers.keys()))
        return registry

    def register(self, provider: AnyProvider) -> None:
        self._providers[provider.PROVIDER_NAME] = provider

    def get(self, name: ProviderName) -> AnyProvider | None:
        return self._providers.get(name)

    def get_by_priority(self) -> list[AnyProvider]:
        return sorted(
            self._providers.values(),
            key=lambda p: p.config.priority,
        )

    def list_names(self) -> list[ProviderName]:
        return list(self._providers.keys())
