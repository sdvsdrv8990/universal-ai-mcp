"""LLM module MCP tools — multi-provider routing and model management.

Registered tools:
  - llm_complete      : send a prompt to the best-fit provider
  - llm_list_providers: list configured providers and their status
  - llm_list_models   : list available models per provider
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from universal_ai_mcp.core.registry import ToolRegistry
from universal_ai_mcp.entities.module_entity import Module, ModuleScenario, ScenarioType

MODULE_DEFINITION = Module(
    name="llm",
    display_name="LLM Router",
    description=(
        "Routes prompts to Anthropic Claude, OpenRouter, or Ollama "
        "based on task tier (heavy/balanced/fast) and provider priority."
    ),
    scenarios=[
        ModuleScenario(
            name="direct_completion",
            description="Send a prompt directly to a specified provider/model",
            scenario_type=ScenarioType.USER,
            required_tools=["llm_complete"],
        ),
        ModuleScenario(
            name="provider_audit",
            description="Check which providers are active and what models are available",
            scenario_type=ScenarioType.USER,
            required_tools=["llm_list_providers", "llm_list_models"],
        ),
    ],
    mcp_tools=["llm_complete", "llm_list_providers", "llm_list_models"],
)


def register_llm_tools(mcp: FastMCP, registry: ToolRegistry) -> None:
    registry.register_module(MODULE_DEFINITION)

    @mcp.tool()
    async def llm_complete(
        prompt: str,
        system_prompt: str | None = None,
        tier: str = "balanced",
        provider: str | None = None,
        max_tokens: int = 4096,
    ) -> str:
        """Send a prompt to the configured LLM and return the response.

        Args:
            prompt: User message.
            system_prompt: Optional system context.
            tier: Model tier — heavy | balanced | fast (default: balanced).
            provider: Force specific provider — anthropic | openrouter | ollama.
            max_tokens: Maximum tokens in response.
        """
        from universal_ai_mcp.core.config import get_settings
        from universal_ai_mcp.entities.provider_entity import LLMMessage, LLMRequest, ProviderName
        from universal_ai_mcp.modules.llm.provider_registry import LLMProviderRegistry
        from universal_ai_mcp.modules.llm.router import LLMRouter

        settings = get_settings()
        router = LLMRouter(LLMProviderRegistry.from_settings(settings), settings)

        preferred = ProviderName(provider) if provider else None
        request = LLMRequest(
            model="auto",
            messages=[LLMMessage(role="user", content=prompt)],
            system_prompt=system_prompt,
            max_tokens=max_tokens,
        )
        response = await router.complete(request, tier=tier, preferred_provider=preferred)  # type: ignore[arg-type]

        return json.dumps({
            "content": response.content,
            "provider": response.provider.value,
            "model": response.model,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "total_tokens": response.total_tokens,
        }, indent=2)

    @mcp.tool()
    async def llm_list_providers() -> str:
        """List all configured LLM providers and their enabled status."""
        from universal_ai_mcp.core.config import get_settings
        from universal_ai_mcp.modules.llm.provider_registry import LLMProviderRegistry

        settings = get_settings()
        reg = LLMProviderRegistry.from_settings(settings)

        providers = []
        for provider in reg.get_by_priority():
            providers.append({
                "name": provider.PROVIDER_NAME.value,
                "enabled": provider.config.enabled,
                "default_model": provider.config.default_model,
                "priority": provider.config.priority,
            })
        return json.dumps({"providers": providers}, indent=2)

    @mcp.tool()
    async def llm_list_models(provider: str = "ollama") -> str:
        """List available models for the specified provider.

        For Ollama, this queries the local instance.
        For Anthropic/OpenRouter, returns the known model list.
        """
        from universal_ai_mcp.core.config import get_settings
        from universal_ai_mcp.entities.provider_entity import ProviderName
        from universal_ai_mcp.modules.llm.provider_registry import LLMProviderRegistry

        settings = get_settings()
        reg = LLMProviderRegistry.from_settings(settings)

        try:
            pname = ProviderName(provider)
        except ValueError:
            return json.dumps({"error": f"Unknown provider: {provider}"})

        p = reg.get(pname)
        if not p:
            return json.dumps({"error": f"Provider {provider} not configured"})

        models = p.config.available_models
        if pname == ProviderName.OLLAMA:
            from universal_ai_mcp.modules.llm.providers.ollama_provider import OllamaProvider
            if isinstance(p, OllamaProvider):
                models = await p.list_models()

        return json.dumps({"provider": provider, "models": models}, indent=2)
