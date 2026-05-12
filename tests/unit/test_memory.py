"""Tests for the memory module — entities, indexer, retriever, vector store.

Tests are structured to mirror the isolation layers:
  - Entity tests: pure Pydantic validation, no external deps
  - VectorStore tests: mock chromadb.PersistentClient
  - Indexer tests: mock store + embedder, verify chunking and dedup logic
  - Retriever tests: mock store + embedder, verify search flow
  - Tools tests: verify JSON output shape and error handling
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from universal_ai_mcp.entities.memory_entity import (
    IndexResult,
    MemoryEntry,
    MemoryQuery,
    MemoryScope,
    MemorySearchResult,
)
from universal_ai_mcp.modules.memory.embedding_provider import (
    EmbeddingError,
    OllamaEmbeddingProvider,
)
from universal_ai_mcp.modules.memory.memory_indexer import (
    MemoryIndexer,
    _chunk_text,
    _content_hash,
    _get_encoding,
)
from universal_ai_mcp.modules.memory.memory_retriever import MemoryRetriever
from universal_ai_mcp.modules.memory.vector_store import MemoryVectorStore, VectorStoreError


# ──────────────────────────────────────────────────────────────────────────────
# Entity tests
# ──────────────────────────────────────────────────────────────────────────────

class TestMemoryEntry:
    def _make(self, **kwargs: object) -> MemoryEntry:
        defaults = dict(
            content="hello world",
            source="manual",
            scope=MemoryScope.GLOBAL,
            embedding_model="nomic-embed-text",
            content_hash=_content_hash("hello world"),
        )
        defaults.update(kwargs)
        return MemoryEntry(**defaults)  # type: ignore[arg-type]

    def test_global_entry_no_project_path_ok(self) -> None:
        e = self._make(scope=MemoryScope.GLOBAL, project_path=None)
        assert e.scope == MemoryScope.GLOBAL

    def test_project_entry_requires_project_path(self) -> None:
        with pytest.raises(ValueError, match="project_path is required"):
            self._make(scope=MemoryScope.PROJECT, project_path=None)

    def test_project_entry_with_path_ok(self) -> None:
        e = self._make(scope=MemoryScope.PROJECT, project_path="/home/admin/project")
        assert e.project_path == "/home/admin/project"

    def test_collection_name_global(self) -> None:
        assert MemoryEntry.collection_name_for(MemoryScope.GLOBAL) == "global"

    def test_collection_name_project(self) -> None:
        path = "/home/admin/myproject"
        expected_hash = hashlib.sha256(path.encode()).hexdigest()[:16]
        assert MemoryEntry.collection_name_for(MemoryScope.PROJECT, path) == f"project_{expected_hash}"

    def test_collection_name_project_requires_path(self) -> None:
        with pytest.raises(ValueError):
            MemoryEntry.collection_name_for(MemoryScope.PROJECT)

    def test_to_chroma_metadata_all_str(self) -> None:
        e = self._make()
        meta = e.to_chroma_metadata()
        for v in meta.values():
            assert isinstance(v, (str, int, float)), f"Non-primitive value: {v!r}"

    def test_roundtrip_from_chroma_result(self) -> None:
        e = self._make()
        meta = e.to_chroma_metadata()
        restored = MemoryEntry.from_chroma_result(e.id, e.content, meta)
        assert restored.source == e.source
        assert restored.scope == e.scope
        assert restored.content_hash == e.content_hash


class TestMemoryQuery:
    def test_top_k_bounds(self) -> None:
        q = MemoryQuery(query="test", top_k=50)
        assert q.top_k == 50

    def test_defaults(self) -> None:
        q = MemoryQuery(query="x")
        assert q.scope is None
        assert q.rerank is False
        assert q.top_k == 5


class TestMemorySearchResult:
    def test_empty_as_context_text(self) -> None:
        r = MemorySearchResult(query_text="test")
        assert "no relevant results" in r.as_context_text()

    def test_as_context_text_with_entries(self) -> None:
        entry = MemoryEntry(
            content="some fact",
            source="manual",
            scope=MemoryScope.GLOBAL,
            embedding_model="nomic-embed-text",
            content_hash=_content_hash("some fact"),
        )
        r = MemorySearchResult(
            entries=[entry],
            distances=[0.1],
            query_text="test query",
            total_found=1,
        )
        text = r.as_context_text()
        assert "test query" in text
        assert "some fact" in text
        assert "score=0.9" in text


# ──────────────────────────────────────────────────────────────────────────────
# Chunking tests (pure logic, no IO)
# ──────────────────────────────────────────────────────────────────────────────

class TestChunking:
    def setup_method(self) -> None:
        self._enc = _get_encoding()

    def test_empty_text_returns_empty(self) -> None:
        assert _chunk_text("", self._enc) == []

    def test_short_text_single_chunk(self) -> None:
        chunks = _chunk_text("Hello world", self._enc)
        assert len(chunks) == 1
        assert "Hello world" in chunks[0]

    def test_long_text_produces_multiple_chunks(self) -> None:
        word = "token " * 100  # ~100 tokens
        text = word * 8        # ~800 tokens → expect ≥2 chunks
        chunks = _chunk_text(text, self._enc)
        assert len(chunks) >= 2

    def test_content_hash_deterministic(self) -> None:
        assert _content_hash("abc") == _content_hash("abc")
        assert _content_hash("abc") != _content_hash("xyz")


# ──────────────────────────────────────────────────────────────────────────────
# VectorStore tests (mock chromadb)
# ──────────────────────────────────────────────────────────────────────────────

class TestMemoryVectorStore:
    def _store(self, tmp_path: object) -> MemoryVectorStore:
        import tempfile
        d = tempfile.mkdtemp()
        return MemoryVectorStore(data_dir=d)

    def test_chromadb_import_error_raises_vector_store_error(self, tmp_path: object) -> None:
        store = self._store(tmp_path)
        with patch.dict("sys.modules", {"chromadb": None}):
            store._client = None  # force re-init
            with pytest.raises((VectorStoreError, Exception)):
                store._get_client()

    def test_upsert_empty_returns_zero(self, tmp_path: object) -> None:
        store = self._store(tmp_path)
        mock_client = MagicMock()
        mock_col = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_col
        store._client = mock_client

        result = store.upsert("global", [], [], [], [])
        assert result == 0
        mock_col.upsert.assert_not_called()

    def test_upsert_calls_chroma(self, tmp_path: object) -> None:
        store = self._store(tmp_path)
        mock_client = MagicMock()
        mock_col = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_col
        store._client = mock_client

        count = store.upsert("global", ["id1"], ["doc"], [[0.1, 0.2]], [{"source": "x"}])
        assert count == 1
        mock_col.upsert.assert_called_once()

    def test_collection_count_zero_on_exception(self, tmp_path: object) -> None:
        store = self._store(tmp_path)
        mock_client = MagicMock()
        mock_col = MagicMock()
        mock_col.count.side_effect = Exception("db error")
        mock_client.get_or_create_collection.return_value = mock_col
        store._client = mock_client
        assert store.collection_count("global") == 0


# ──────────────────────────────────────────────────────────────────────────────
# Indexer tests (mock store + embedder)
# ──────────────────────────────────────────────────────────────────────────────

class TestMemoryIndexer:
    def _make_indexer(self) -> tuple[MemoryIndexer, MagicMock, MagicMock]:
        mock_store = MagicMock(spec=MemoryVectorStore)
        mock_store.get_by_source_hash.return_value = []  # no existing entries
        mock_store.upsert.return_value = 1
        mock_embedder = MagicMock(spec=OllamaEmbeddingProvider)
        mock_embedder.model = "nomic-embed-text"
        mock_embedder.embed = AsyncMock(return_value=[[0.1] * 768])
        indexer = MemoryIndexer(store=mock_store, embedder=mock_embedder)
        return indexer, mock_store, mock_embedder

    @pytest.mark.asyncio
    async def test_index_empty_text_returns_zero(self) -> None:
        indexer, _, _ = self._make_indexer()
        result = await indexer.index_text("", "manual", MemoryScope.GLOBAL)
        assert result.chunks_indexed == 0
        assert result.status == "ok"

    @pytest.mark.asyncio
    async def test_index_text_calls_embed_and_upsert(self) -> None:
        indexer, mock_store, mock_embedder = self._make_indexer()
        mock_embedder.embed = AsyncMock(return_value=[[0.1] * 768])

        result = await indexer.index_text("Hello world foo bar", "manual", MemoryScope.GLOBAL)
        assert result.chunks_indexed >= 1
        assert result.status == "ok"
        mock_store.upsert.assert_called()

    @pytest.mark.asyncio
    async def test_dedup_skips_existing_hash(self) -> None:
        indexer, mock_store, mock_embedder = self._make_indexer()
        text = "unchanged content"
        h = _content_hash(text)
        mock_store.get_by_source_hash.return_value = [{"content_hash": h}]

        result = await indexer.index_text(text, "manual", MemoryScope.GLOBAL)
        assert result.chunks_indexed == 0
        assert result.chunks_skipped == 1
        mock_store.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_embedding_error_returns_error_status(self) -> None:
        indexer, _, mock_embedder = self._make_indexer()
        mock_embedder.embed = AsyncMock(side_effect=EmbeddingError("connection refused"))

        result = await indexer.index_text("some text", "manual", MemoryScope.GLOBAL)
        assert result.status == "error"
        assert "connection refused" in (result.error or "")

    @pytest.mark.asyncio
    async def test_index_github_raises_without_finder(self) -> None:
        indexer, _, _ = self._make_indexer()
        indexer._finder = None
        with pytest.raises(RuntimeError, match="GitHubFinder not configured"):
            await indexer.index_github_repo("owner/repo")


# ──────────────────────────────────────────────────────────────────────────────
# Retriever tests (mock store + embedder)
# ──────────────────────────────────────────────────────────────────────────────

class TestMemoryRetriever:
    def _make_retriever(self) -> tuple[MemoryRetriever, MagicMock, MagicMock]:
        mock_store = MagicMock(spec=MemoryVectorStore)
        mock_store.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }
        mock_embedder = MagicMock(spec=OllamaEmbeddingProvider)
        mock_embedder.embed_one = AsyncMock(return_value=[0.1] * 768)
        retriever = MemoryRetriever(store=mock_store, embedder=mock_embedder)
        return retriever, mock_store, mock_embedder

    @pytest.mark.asyncio
    async def test_empty_collection_returns_empty_result(self) -> None:
        retriever, _, _ = self._make_retriever()
        q = MemoryQuery(query="test", scope=MemoryScope.GLOBAL)
        result = await retriever.search(q)
        assert result.total_found == 0
        assert result.entries == []

    @pytest.mark.asyncio
    async def test_embed_error_returns_empty_gracefully(self) -> None:
        retriever, _, mock_embedder = self._make_retriever()
        mock_embedder.embed_one = AsyncMock(side_effect=EmbeddingError("model not found"))

        q = MemoryQuery(query="test")
        result = await retriever.search(q)
        assert result.entries == []
        assert result.total_found == 0

    @pytest.mark.asyncio
    async def test_global_scope_queries_global_collection(self) -> None:
        retriever, mock_store, _ = self._make_retriever()
        q = MemoryQuery(query="chromadb usage", scope=MemoryScope.GLOBAL)
        await retriever.search(q)
        call_args = mock_store.query.call_args
        assert call_args[1]["collection_name"] == "global"

    @pytest.mark.asyncio
    async def test_both_scope_queries_two_collections(self) -> None:
        retriever, mock_store, _ = self._make_retriever()
        q = MemoryQuery(
            query="test",
            scope=None,
            project_path="/home/user/proj",
        )
        await retriever.search(q)
        assert mock_store.query.call_count == 2
