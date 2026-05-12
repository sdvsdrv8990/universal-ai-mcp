"""Tests for modules/llm/json_extractor.py."""

import json

import pytest

from universal_ai_mcp.modules.llm.json_extractor import extract_json


@pytest.mark.parametrize(
    "text,expected",
    [
        # Clean JSON — fast path (Anthropic native, Ollama with format param)
        ('{"blocks": []}', {"blocks": []}),
        ('[1, 2, 3]', [1, 2, 3]),
        # Fenced with ```json ... ``` — qwen3.5:9b, many open models
        ('```json\n{"blocks": [{"name": "x"}]}\n```', {"blocks": [{"name": "x"}]}),
        # Fenced without json label
        ('```\n{"ok": true}\n```', {"ok": True}),
        # Prose wrapping the JSON — last-resort path
        ('Here is the result:\n{"key": "value"}\nDone.', {"key": "value"}),
        # Whitespace around fence
        ('   ```json\n  {"a": 1}  \n```   ', {"a": 1}),
    ],
)
def test_extract_json_variants(text: str, expected) -> None:
    assert extract_json(text) == expected


def test_extract_json_raises_on_garbage() -> None:
    with pytest.raises(json.JSONDecodeError):
        extract_json("no json here at all")


def test_extract_json_raises_on_malformed_fence() -> None:
    with pytest.raises(json.JSONDecodeError):
        extract_json("```json\nnot valid json\n```")
