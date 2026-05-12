"""Ollama provider — local models with zero token cost."""

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

log = structlog.get_logger(__name__)


class OllamaProvider:
    """Sends normalized LLMRequests to a local Ollama instance."""

    PROVIDER_NAME = ProviderName.OLLAMA

    def __init__(self, config: LLMProvider) -> None:
        self._config = config
        self._base_url = config.base_url.rstrip("/")

    @property
    def config(self) -> LLMProvider:
        return self._config

    async def complete(self, request: LLMRequest) -> LLMResponse:
        messages = self._to_ollama_messages(request.messages, request.system_prompt)
        payload = {
            "model": request.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {"temperature": request.temperature, "num_predict": request.max_tokens},
        }
        if request.response_format:
            payload["format"] = request.response_format
        log.debug("ollama_request", model=request.model, base_url=self._base_url)

        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{self._base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        msg = data.get("message", {})
        content = msg.get("content") or msg.get("thinking", "")
        finish_reason = data.get("done_reason", "stop")

        return LLMResponse(
            request_id=request.id,
            provider=self.PROVIDER_NAME,
            model=request.model,
            content=content,
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            finish_reason=finish_reason,
            raw=data,
        )

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self._base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
        return [m["name"] for m in data.get("models", [])]

    def _to_ollama_messages(
        self,
        messages: list[LLMMessage],
        system_prompt: str | None,
    ) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})
        result.extend({"role": m.role, "content": m.content} for m in messages)
        return result
