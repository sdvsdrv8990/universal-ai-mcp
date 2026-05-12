"""LLM router — selects the right provider and model for each request type.

Routing strategy:
  - planning tasks → claude-sonnet-4-6 (Anthropic, quality-optimized)
  - context compression → claude-haiku-4-5 (Anthropic, fast + cheap)
  - execution tasks → configured default provider
  - offline/local → Ollama fallback
"""

from __future__ import annotations

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from universal_ai_mcp.core.config import ServerSettings
from universal_ai_mcp.entities.provider_entity import (
    LLMRequest,
    LLMResponse,
    ProviderName,
)
from universal_ai_mcp.modules.llm.provider_registry import AnyProvider, LLMProviderRegistry
from universal_ai_mcp.types.provider_types import ModelTier

log = structlog.get_logger(__name__)

TIER_MODEL_MAP: dict[str, dict[ProviderName, str]] = {
    "heavy": {
        ProviderName.ANTHROPIC: "claude-opus-4-7",
        ProviderName.OPENROUTER: "anthropic/claude-opus-4-7",
        ProviderName.OLLAMA: "qwen3.5:9b",
    },
    "balanced": {
        ProviderName.ANTHROPIC: "claude-sonnet-4-6",
        ProviderName.OPENROUTER: "anthropic/claude-sonnet-4-6",
        ProviderName.OLLAMA: "qwen3.5:9b",
    },
    "fast": {
        ProviderName.ANTHROPIC: "claude-haiku-4-5-20251001",
        ProviderName.OPENROUTER: "anthropic/claude-haiku-4-5",
        ProviderName.OLLAMA: "qwen3.5:9b",
    },
}


class LLMRouter:
    """Routes LLM requests to the appropriate provider based on task tier."""

    def __init__(
        self,
        provider_registry: LLMProviderRegistry,
        settings: ServerSettings,
    ) -> None:
        self._providers = provider_registry
        self._settings = settings

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def complete(
        self,
        request: LLMRequest,
        tier: ModelTier = "balanced",
        preferred_provider: ProviderName | None = None,
    ) -> LLMResponse:
        provider = self._select_provider(preferred_provider)
        request.model = self._resolve_model(provider, tier, request.model)

        log.info(
            "llm_routing",
            provider=provider.PROVIDER_NAME,
            model=request.model,
            tier=tier,
        )
        return await provider.complete(request)

    def _select_provider(self, preferred: ProviderName | None) -> AnyProvider:
        if preferred:
            p = self._providers.get(preferred)
            if p and p.config.enabled:
                return p
        by_priority = self._providers.get_by_priority()
        if not by_priority:
            raise RuntimeError("No LLM providers are configured or enabled")
        return by_priority[0]

    def _resolve_model(
        self,
        provider: AnyProvider,
        tier: ModelTier,
        override: str,
    ) -> str:
        if override and override not in ("", "auto"):
            return override
        tier_map = TIER_MODEL_MAP.get(tier, TIER_MODEL_MAP["balanced"])
        return tier_map.get(provider.PROVIDER_NAME, provider.config.default_model)
