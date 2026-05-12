"""Memory indexer — converts raw text into indexed vector entries.

Isolation contract:
  - Depends on: MemoryVectorStore, OllamaEmbeddingProvider (both in this module)
  - Optional dep: GitHubFinder (from modules/solutions/) — injected, not imported globally
  - Does NOT import from tools/ or core/ (except config for defaults)

Chunking strategy:
  - Max 512 tokens per chunk (tiktoken cl100k_base)
  - 50-token overlap between consecutive chunks for context continuity
  - Chunks smaller than 20 tokens are merged into the next chunk

Deduplication:
  - content_hash = sha256(content) stored in ChromaDB metadata
  - Before indexing a source, existing hashes are fetched
  - Chunks whose hash already exists in the collection are skipped
  - This makes repeated calls to index_text() idempotent
"""

from __future__ import annotations

import hashlib
import uuid
from typing import TYPE_CHECKING

import structlog

from universal_ai_mcp.entities.memory_entity import (
    IndexResult,
    MemoryEntry,
    MemoryScope,
)
from universal_ai_mcp.modules.memory.embedding_provider import (
    EmbeddingError,
    OllamaEmbeddingProvider,
)
from universal_ai_mcp.modules.memory.vector_store import MemoryVectorStore, VectorStoreError

if TYPE_CHECKING:
    from universal_ai_mcp.modules.solutions.github_finder import GitHubFinder

log = structlog.get_logger(__name__)

_MAX_CHUNK_TOKENS = 512
_OVERLAP_TOKENS = 50
_MIN_CHUNK_TOKENS = 20
_BATCH_SIZE = 16  # embed N chunks per HTTP call


def _get_encoding() -> object:
    import tiktoken  # already a project dependency
    return tiktoken.get_encoding("cl100k_base")


def _chunk_text(text: str, enc: object) -> list[str]:
    """Split text into overlapping chunks of ≤512 tokens."""
    import tiktoken
    assert isinstance(enc, tiktoken.Encoding)

    token_ids = enc.encode(text)
    if not token_ids:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(token_ids):
        end = min(start + _MAX_CHUNK_TOKENS, len(token_ids))
        chunk_tokens = token_ids[start:end]
        if len(chunk_tokens) >= _MIN_CHUNK_TOKENS or not chunks:
            chunks.append(enc.decode(chunk_tokens))
        else:
            # Merge tiny tail into the previous chunk
            combined = enc.decode(token_ids[max(0, start - _OVERLAP_TOKENS): end])
            if chunks:
                chunks[-1] = combined
            else:
                chunks.append(combined)
        start += _MAX_CHUNK_TOKENS - _OVERLAP_TOKENS

    return [c for c in chunks if c.strip()]


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class MemoryIndexer:
    """Orchestrates text → chunk → embed → store pipeline.

    Constructed with pre-built store and embedder; GitHub finder is optional.
    If github_finder is None, index_github_repo() will raise.
    """

    def __init__(
        self,
        store: MemoryVectorStore,
        embedder: OllamaEmbeddingProvider,
        github_finder: "GitHubFinder | None" = None,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._finder = github_finder
        self._enc = _get_encoding()

    async def index_text(
        self,
        text: str,
        source: str,
        scope: MemoryScope,
        project_path: str | None = None,
        library_name: str | None = None,
    ) -> IndexResult:
        """Index arbitrary text. Idempotent — skips unchanged chunks."""
        collection = MemoryEntry.collection_name_for(scope, project_path)

        chunks = _chunk_text(text, self._enc)
        if not chunks:
            return IndexResult(
                source=source,
                scope=scope,
                chunks_indexed=0,
                chunks_skipped=0,
                embedding_model=self._embedder.model,
            )

        # Fetch existing hashes for this source to enable deduplication
        existing = self._store.get_by_source_hash(collection, source)
        existing_hashes = {str(row.get("content_hash", "")) for row in existing}

        new_chunks: list[str] = []
        new_indices: list[int] = []
        skipped = 0

        for idx, chunk in enumerate(chunks):
            h = _content_hash(chunk)
            if h in existing_hashes:
                skipped += 1
            else:
                new_chunks.append(chunk)
                new_indices.append(idx)

        if not new_chunks:
            log.debug("index_skip_all", source=source, chunks=len(chunks))
            return IndexResult(
                source=source,
                scope=scope,
                chunks_indexed=0,
                chunks_skipped=skipped,
                embedding_model=self._embedder.model,
            )

        # Embed in batches
        try:
            all_embeddings = await self._embed_batched(new_chunks)
        except EmbeddingError as exc:
            return IndexResult(
                source=source,
                scope=scope,
                chunks_indexed=0,
                chunks_skipped=skipped,
                embedding_model=self._embedder.model,
                status="error",
                error=str(exc),
            )

        from datetime import UTC, datetime
        now = datetime.now(UTC)

        entries = [
            MemoryEntry(
                id=str(uuid.uuid4()),
                content=chunk,
                source=source,
                scope=scope,
                project_path=project_path,
                library_name=library_name,
                embedding_model=self._embedder.model,
                content_hash=_content_hash(chunk),
                chunk_index=idx,
                created_at=now,
                updated_at=now,
            )
            for chunk, idx in zip(new_chunks, new_indices)
        ]

        try:
            self._store.upsert(
                collection_name=collection,
                ids=[e.id for e in entries],
                documents=[e.content for e in entries],
                embeddings=all_embeddings,
                metadatas=[e.to_chroma_metadata() for e in entries],
            )
        except VectorStoreError as exc:
            return IndexResult(
                source=source,
                scope=scope,
                chunks_indexed=0,
                chunks_skipped=skipped,
                embedding_model=self._embedder.model,
                status="error",
                error=str(exc),
            )

        log.info(
            "indexed",
            source=source,
            scope=scope.value,
            new=len(entries),
            skipped=skipped,
        )
        return IndexResult(
            source=source,
            scope=scope,
            chunks_indexed=len(entries),
            chunks_skipped=skipped,
            embedding_model=self._embedder.model,
        )

    async def index_github_repo(
        self,
        repo_full_name: str,
        scope: MemoryScope = MemoryScope.GLOBAL,
        project_path: str | None = None,
    ) -> IndexResult:
        """Fetch a GitHub repo's README and index it.

        Uses the injected GitHubFinder. Raises RuntimeError if finder is None.
        Source key: "github:<repo_full_name>" for dedup tracking.
        """
        if self._finder is None:
            raise RuntimeError(
                "GitHubFinder not configured. Pass github_finder= to MemoryIndexer."
            )

        source = f"github:{repo_full_name}"
        log.info("index_github", repo=repo_full_name)

        readme = await self._finder.get_readme(repo_full_name)
        if not readme:
            return IndexResult(
                source=source,
                scope=scope,
                chunks_indexed=0,
                embedding_model=self._embedder.model,
                status="error",
                error=f"README not found for {repo_full_name}",
            )

        # Use repo name as library_name for GLOBAL scope
        library_name = repo_full_name.split("/")[-1] if scope == MemoryScope.GLOBAL else None
        return await self.index_text(
            text=readme,
            source=source,
            scope=scope,
            project_path=project_path,
            library_name=library_name,
        )

    async def _embed_batched(self, texts: list[str]) -> list[list[float]]:
        """Embed texts in batches of _BATCH_SIZE to avoid large payloads."""
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            batch = texts[i: i + _BATCH_SIZE]
            embeddings = await self._embedder.embed(batch)
            all_embeddings.extend(embeddings)
        return all_embeddings
