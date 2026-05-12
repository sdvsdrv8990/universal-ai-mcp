"""Unit tests for BlockRetriever — semantic search over indexed IdeaBlocks."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from universal_ai_mcp.entities.idea_block_entity import IdeaBlock, IdeaBlockCollection
from universal_ai_mcp.modules.context.block_retriever import (
    BlockRetriever,
    _from_chroma_result,
    _to_metadata,
    _to_search_text,
)
from universal_ai_mcp.modules.memory.embedding_provider import EmbeddingError
from universal_ai_mcp.modules.memory.vector_store import VectorStoreError


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

def _make_block(
    name: str = "test block",
    critical_question: str = "What is X?",
    trusted_answer: str = "X is Y.",
    tags: list[str] | None = None,
    entities: list[str] | None = None,
    keywords: list[str] | None = None,
) -> IdeaBlock:
    return IdeaBlock(
        name=name,
        critical_question=critical_question,
        trusted_answer=trusted_answer,
        tags=tags or [],
        entities=entities or [],
        keywords=keywords or [],
        token_count=10,
    )


def _make_store(upsert_ok: bool = True) -> MagicMock:
    store = MagicMock()
    if upsert_ok:
        store.upsert.return_value = 1
    else:
        store.upsert.side_effect = VectorStoreError("store down")
    return store


def _make_embedder(vectors: list[list[float]] | None = None) -> MagicMock:
    """Embedder that returns unit vectors by default."""
    embedder = MagicMock()
    default = vectors or [[0.1, 0.2, 0.3]]
    embedder.embed = AsyncMock(return_value=default)
    embedder.embed_one = AsyncMock(return_value=default[0])
    return embedder


def _make_chroma_result(blocks: list[IdeaBlock]) -> dict[str, Any]:
    """Build a ChromaDB-shaped result dict from real IdeaBlock objects."""
    ids = [[str(b.id) for b in blocks]]
    metas = [[_to_metadata(b) for b in blocks]]
    docs = [[_to_search_text(b) for b in blocks]]
    dists = [[0.1 * (i + 1) for i in range(len(blocks))]]
    return {"ids": ids, "documents": docs, "metadatas": metas, "distances": dists}


# ──────────────────────────────────────────────────────────────────────────────
# Serialization helpers
# ──────────────────────────────────────────────────────────────────────────────

class TestSerializationHelpers:
    def test_to_search_text_format(self):
        block = _make_block(critical_question="What?", trusted_answer="This.")
        text = _to_search_text(block)
        assert text == "Q: What?\n\nA: This."

    def test_to_metadata_stores_all_fields(self):
        block = _make_block(
            name="auth block",
            tags=["auth", "security"],
            entities=["UserService"],
            keywords=["jwt", "token"],
            trusted_answer="Use JWT.",
        )
        meta = _to_metadata(block)
        assert meta["name"] == "auth block"
        assert json.loads(meta["tags"]) == ["auth", "security"]
        assert json.loads(meta["entities"]) == ["UserService"]
        assert json.loads(meta["keywords"]) == ["jwt", "token"]
        assert meta["trusted_answer"] == "Use JWT."
        assert meta["token_count"] == 10
        assert "created_at" in meta

    def test_to_metadata_none_source_ref_becomes_empty_string(self):
        block = _make_block()
        assert block.source_ref is None
        meta = _to_metadata(block)
        assert meta["source_ref"] == ""

    def test_from_chroma_result_roundtrip(self):
        original = _make_block(
            name="round trip",
            tags=["a", "b"],
            entities=["Foo"],
            keywords=["bar"],
        )
        raw = _make_chroma_result([original])
        reconstructed = _from_chroma_result(raw)

        assert len(reconstructed) == 1
        r = reconstructed[0]
        assert r.id == original.id
        assert r.name == original.name
        assert r.critical_question == original.critical_question
        assert r.trusted_answer == original.trusted_answer
        assert r.tags == ["a", "b"]
        assert r.entities == ["Foo"]
        assert r.keywords == ["bar"]

    def test_from_chroma_result_empty(self):
        raw = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        assert _from_chroma_result(raw) == []

    def test_from_chroma_result_skips_bad_entry(self):
        block = _make_block()
        raw = _make_chroma_result([block])
        # Corrupt the first metadata entry
        raw["metadatas"][0][0]["created_at"] = "not-a-date"
        result = _from_chroma_result(raw)
        # Bad entry is skipped, no crash
        assert result == []


# ──────────────────────────────────────────────────────────────────────────────
# BlockRetriever.index()
# ──────────────────────────────────────────────────────────────────────────────

class TestBlockRetrieverIndex:
    @pytest.mark.asyncio
    async def test_index_empty_collection_returns_zero(self):
        retriever = BlockRetriever(_make_store(), _make_embedder())
        count = await retriever.index(IdeaBlockCollection())
        assert count == 0

    @pytest.mark.asyncio
    async def test_index_calls_upsert_with_correct_ids(self):
        store = _make_store()
        b1 = _make_block(name="A")
        b2 = _make_block(name="B")
        embedder = _make_embedder([[0.1, 0.2], [0.3, 0.4]])
        retriever = BlockRetriever(store, embedder)

        count = await retriever.index(IdeaBlockCollection(blocks=[b1, b2]))

        assert count == 2
        call_kwargs = store.upsert.call_args.kwargs
        assert call_kwargs["ids"] == [str(b1.id), str(b2.id)]
        assert call_kwargs["collection_name"] == "idea_blocks"

    @pytest.mark.asyncio
    async def test_index_stores_tags_as_json_in_metadata(self):
        store = _make_store()
        block = _make_block(tags=["auth", "security"])
        retriever = BlockRetriever(store, _make_embedder())

        await retriever.index(IdeaBlockCollection(blocks=[block]))

        meta_list = store.upsert.call_args.kwargs["metadatas"]
        assert json.loads(meta_list[0]["tags"]) == ["auth", "security"]

    @pytest.mark.asyncio
    async def test_index_returns_zero_when_embedder_unavailable(self):
        embedder = MagicMock()
        embedder.embed = AsyncMock(side_effect=EmbeddingError("Ollama down"))
        retriever = BlockRetriever(_make_store(), embedder)
        block = _make_block()

        count = await retriever.index(IdeaBlockCollection(blocks=[block]))

        assert count == 0  # fail-open, no exception raised


# ──────────────────────────────────────────────────────────────────────────────
# BlockRetriever.query()
# ──────────────────────────────────────────────────────────────────────────────

class TestBlockRetrieverQuery:
    @pytest.mark.asyncio
    async def test_query_returns_idea_blocks(self):
        block = _make_block(name="result block", tags=["api"])
        store = _make_store()
        store.query = MagicMock(return_value=_make_chroma_result([block]))
        retriever = BlockRetriever(store, _make_embedder())

        results = await retriever.query("api design")

        assert len(results) == 1
        assert isinstance(results[0], IdeaBlock)
        assert results[0].name == "result block"

    @pytest.mark.asyncio
    async def test_query_returns_empty_list_when_embedder_fails(self):
        embedder = MagicMock()
        embedder.embed_one = AsyncMock(side_effect=EmbeddingError("Ollama down"))
        retriever = BlockRetriever(_make_store(), embedder)

        results = await retriever.query("anything")

        assert results == []  # fail-open

    @pytest.mark.asyncio
    async def test_query_returns_empty_list_when_store_fails(self):
        store = _make_store()
        store.query = MagicMock(side_effect=VectorStoreError("DB error"))
        retriever = BlockRetriever(store, _make_embedder())

        results = await retriever.query("anything")

        assert results == []  # fail-open

    @pytest.mark.asyncio
    async def test_query_respects_limit(self):
        blocks = [_make_block(name=f"block {i}") for i in range(10)]
        store = _make_store()
        store.query = MagicMock(return_value=_make_chroma_result(blocks))
        retriever = BlockRetriever(store, _make_embedder())

        results = await retriever.query("anything", limit=3)

        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_filter_tags_keeps_only_matching_blocks(self):
        auth_block = _make_block(name="auth", tags=["auth", "security"])
        db_block = _make_block(name="db", tags=["database"])
        store = _make_store()
        store.query = MagicMock(return_value=_make_chroma_result([auth_block, db_block]))
        retriever = BlockRetriever(store, _make_embedder())

        results = await retriever.query("something", filter_tags=["auth"])

        assert len(results) == 1
        assert results[0].name == "auth"

    @pytest.mark.asyncio
    async def test_filter_tags_none_returns_all(self):
        blocks = [_make_block(tags=["a"]), _make_block(tags=["b"])]
        store = _make_store()
        store.query = MagicMock(return_value=_make_chroma_result(blocks))
        retriever = BlockRetriever(store, _make_embedder())

        results = await retriever.query("something", filter_tags=None)

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_filter_tags_oversamples_fetch(self):
        """When filter_tags set, store.query is called with limit*3."""
        store = _make_store()
        store.query = MagicMock(return_value=_make_chroma_result([]))
        retriever = BlockRetriever(store, _make_embedder())

        await retriever.query("x", limit=4, filter_tags=["auth"])

        call_kwargs = store.query.call_args.kwargs
        assert call_kwargs["top_k"] == 4 * 3  # _TAG_OVERSAMPLE = 3

    @pytest.mark.asyncio
    async def test_no_oversampling_without_filter_tags(self):
        store = _make_store()
        store.query = MagicMock(return_value=_make_chroma_result([]))
        retriever = BlockRetriever(store, _make_embedder())

        await retriever.query("x", limit=7, filter_tags=None)

        call_kwargs = store.query.call_args.kwargs
        assert call_kwargs["top_k"] == 7
