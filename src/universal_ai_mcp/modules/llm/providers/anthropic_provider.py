"""Anthropic Claude provider — wraps the Anthropic Python SDK."""

from __future__ import annotations

import anthropic
import structlog

from universal_ai_mcp.entities.provider_entity import (
    LLMMessage,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ProviderName,
)

log = structlog.get_logger(__name__)


class AnthropicProvider:
    """Sends normalized LLMRequests to the Anthropic Messages API."""

    PROVIDER_NAME = ProviderName.ANTHROPIC

    def __init__(self, config: LLMProvider) -> None:
        self._config = config
        api_key = config.api_key.get_secret_value() if config.api_key else None
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    @property
    def config(self) -> LLMProvider:
        return self._config

    async def complete(self, request: LLMRequest) -> LLMResponse:
        messages = self._to_anthropic_messages(request.messages)
        kwargs: dict = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "messages": messages,
        }
        if request.system_prompt:
            kwargs["system"] = request.system_prompt

        log.debug("anthropic_request", model=request.model, messages=len(messages))

        response = await self._client.messages.create(**kwargs)

        content = response.content[0].text if response.content else ""
        return LLMResponse(
            request_id=request.id,
            provider=self.PROVIDER_NAME,
            model=request.model,
            content=content,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            finish_reason=response.stop_reason or "stop",
            raw=response.model_dump(),
        )

    def _to_anthropic_messages(
        self, messages: list[LLMMessage]
    ) -> list[dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
