"""OpenRouter provider — access 200+ models via OpenAI-compatible API."""

from __future__ import annotations

import httpx
import structlog

from universal_ai_mcp.entities.provider_entity import (
    LLMMessage,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ProviderName,
)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

log = structlog.get_logger(__name__)


class OpenRouterProvider:
    """Sends normalized LLMRequests to the OpenRouter chat completions endpoint."""

    PROVIDER_NAME = ProviderName.OPENROUTER

    def __init__(self, config: LLMProvider) -> None:
        self._config = config
        api_key = config.api_key.get_secret_value() if config.api_key else ""
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://github.com/universal-ai-mcp",
            "X-Title": "universal-ai-mcp",
            "Content-Type": "application/json",
        }

    @property
    def config(self) -> LLMProvider:
        return self._config

    async def complete(self, request: LLMRequest) -> LLMResponse:
        payload = {
            "model": request.model,
            "messages": self._to_openai_messages(request.messages, request.system_prompt),
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        log.debug("openrouter_request", model=request.model)

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=self._headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        choice = data["choices"][0]
        usage = data.get("usage", {})
        return LLMResponse(
            request_id=request.id,
            provider=self.PROVIDER_NAME,
            model=request.model,
            content=choice["message"]["content"],
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            finish_reason=choice.get("finish_reason", "stop"),
            raw=data,
        )

    def _to_openai_messages(
        self,
        messages: list[LLMMessage],
        system_prompt: str | None,
    ) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})
        result.extend({"role": m.role, "content": m.content} for m in messages)
        return result
