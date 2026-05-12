"""Embedding provider — wraps Ollama /api/embeddings for async vector generation.

Isolation contract:
  - Depends only on httpx and structlog (both already in project deps)
  - No imports from other universal_ai_mcp modules
  - Raises EmbeddingError on failure so callers can handle it explicitly

Ollama embedding models:
  nomic-embed-text  — 768-dim, 274MB, best quality for RAG (recommended)
  mxbai-embed-large — 1024-dim, 670MB, highest quality
  all-minilm        — 384-dim, 45MB, lightest option

Pull a model: ollama pull nomic-embed-text
"""

from __future__ import annotations

import structlog

import httpx

log = structlog.get_logger(__name__)


class EmbeddingError(RuntimeError):
    """Raised when the Ollama embedding endpoint fails."""


class OllamaEmbeddingProvider:
    """Async embedding provider backed by a local Ollama instance.

    Designed to be constructed once and reused across requests.
    All methods are async to allow concurrent embedding batches.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
        timeout: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    @property
    def model(self) -> str:
        return self._model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns one embedding vector per text.

        Ollama /api/embed (batch) is used when available; falls back to
        sequential /api/embeddings calls for older Ollama versions.
        """
        if not texts:
            return []

        try:
            return await self._embed_batch(texts)
        except EmbeddingError:
            raise
        except Exception as exc:
            raise EmbeddingError(f"Embedding failed: {exc}") from exc

    async def embed_one(self, text: str) -> list[float]:
        """Convenience wrapper for a single text."""
        results = await self.embed([text])
        return results[0]

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """POST to /api/embed (Ollama ≥0.1.26) which accepts a list input."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/api/embed",
                json={"model": self._model, "input": texts},
            )
            if response.status_code in (404, 501):
                # 404: older Ollama without /api/embed
                # 501: endpoint exists but model doesn't support batch embed
                return await self._embed_sequential(texts)
            response.raise_for_status()
            data = response.json()

        embeddings = data.get("embeddings")
        if not embeddings or len(embeddings) != len(texts):
            raise EmbeddingError(
                f"Unexpected response from /api/embed: got {len(embeddings or [])} "
                f"embeddings for {len(texts)} texts"
            )
        log.debug("embedded_batch", model=self._model, count=len(texts))
        return embeddings

    async def _embed_sequential(self, texts: list[str]) -> list[list[float]]:
        """Fallback: one request per text using legacy /api/embeddings."""
        results: list[list[float]] = []
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for text in texts:
                response = await client.post(
                    f"{self._base_url}/api/embeddings",
                    json={"model": self._model, "prompt": text},
                )
                response.raise_for_status()
                data = response.json()
                embedding = data.get("embedding")
                if not embedding:
                    raise EmbeddingError(f"No embedding in response for model {self._model!r}")
                results.append(embedding)
        log.debug("embedded_sequential", model=self._model, count=len(texts))
        return results

    async def check_model_available(self) -> bool:
        """Return True if the configured model is available in Ollama."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self._base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
            names = [m["name"] for m in data.get("models", [])]
            # nomic-embed-text and nomic-embed-text:latest are the same
            return any(n == self._model or n.startswith(f"{self._model}:") for n in names)
        except Exception:
            return False
