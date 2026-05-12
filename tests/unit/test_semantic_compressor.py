"""Unit tests for SemanticCompressor token budget enforcement."""

from __future__ import annotations

import pytest

from universal_ai_mcp.entities.idea_block_entity import IdeaBlock, IdeaBlockCollection
from universal_ai_mcp.modules.context.semantic_compressor import SemanticCompressor


def make_collection(token_sizes: list[int]) -> IdeaBlockCollection:
    blocks = [
        IdeaBlock(
            name=f"block_{i}",
            critical_question=f"Q {i}?",
            trusted_answer="x" * (size * 4),
            tags=["tag"] * (3 - i % 3),
            entities=["Entity"] * (i % 3),
            keywords=["kw"] * (i + 1),
            token_count=size,
        )
        for i, size in enumerate(token_sizes)
    ]
    return IdeaBlockCollection(blocks=blocks, source_token_count=sum(token_sizes))


@pytest.mark.asyncio
async def test_compressor_respects_token_budget() -> None:
    collection = make_collection([100, 200, 300, 150, 250])
    compressor = SemanticCompressor()

    result = await compressor.compress(collection, target_tokens=400)

    assert result.total_tokens() <= 400


@pytest.mark.asyncio
async def test_compressor_no_op_when_under_budget() -> None:
    collection = make_collection([50, 50, 50])
    compressor = SemanticCompressor()

    result = await compressor.compress(collection, target_tokens=1000)

    assert len(result.blocks) == 3


@pytest.mark.asyncio
async def test_compressor_preserves_high_value_blocks() -> None:
    low_value = IdeaBlock(
        name="low", critical_question="Q?", trusted_answer="a",
        tags=[], entities=[], keywords=[], token_count=100,
    )
    high_value = IdeaBlock(
        name="high", critical_question="Q?", trusted_answer="a",
        tags=["t1", "t2", "t3"], entities=["E1", "E2"],
        keywords=["k1", "k2", "k3", "k4"], token_count=100,
    )
    collection = IdeaBlockCollection(blocks=[low_value, high_value], source_token_count=200)
    compressor = SemanticCompressor()

    result = await compressor.compress(collection, target_tokens=100)

    assert len(result.blocks) == 1
    assert result.blocks[0].name == "high"
