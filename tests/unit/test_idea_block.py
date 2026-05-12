"""Unit tests for IdeaBlock entity and IdeaBlockCollection."""

from __future__ import annotations

from uuid import UUID

import pytest

from universal_ai_mcp.entities.idea_block_entity import IdeaBlock, IdeaBlockCollection


def make_block(name: str, answer: str, tags: list[str] | None = None) -> IdeaBlock:
    return IdeaBlock(
        name=name,
        critical_question=f"What is {name}?",
        trusted_answer=answer,
        tags=tags or [],
        token_count=len(answer) // 4,
    )


def test_idea_block_to_xml_contains_required_fields() -> None:
    block = make_block("auth", "JWT-based authentication with 24h expiry", ["auth", "security"])
    xml = block.to_xml()
    assert "<IdeaBlock" in xml
    assert "CriticalQuestion" in xml
    assert "TrustedAnswer" in xml
    assert "JWT-based authentication" in xml


def test_idea_block_collection_total_tokens() -> None:
    blocks = [make_block(f"block_{i}", "x" * 100) for i in range(5)]
    collection = IdeaBlockCollection(blocks=blocks)
    assert collection.total_tokens() == sum(b.token_count for b in blocks)


def test_idea_block_collection_filter_by_tags() -> None:
    b1 = make_block("auth", "JWT auth", tags=["auth"])
    b2 = make_block("db", "PostgreSQL schema", tags=["database"])
    b3 = make_block("api", "REST endpoints", tags=["auth", "api"])
    collection = IdeaBlockCollection(blocks=[b1, b2, b3])

    filtered = collection.filter_by_tags(["auth"])
    assert len(filtered.blocks) == 2
    assert all("auth" in b.tags for b in filtered.blocks)


def test_idea_block_collection_xml_context_includes_all_blocks() -> None:
    blocks = [make_block(f"b{i}", f"answer {i}") for i in range(3)]
    collection = IdeaBlockCollection(blocks=blocks)
    xml = collection.to_xml_context()
    assert "blocks='3'" in xml
    for i in range(3):
        assert f"answer {i}" in xml
