"""Extract JSON from LLM response text regardless of markdown wrapping.

Decision cascade:
  1. Direct json.loads — fast path for Anthropic, Ollama with format param, clean OpenRouter
  2. Strip markdown code fence — handles qwen3.5:9b, Mistral, most open models
  3. Extract first {...} or [...] block — last-resort for freeform responses
"""

from __future__ import annotations

import json
import re

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json(text: str) -> dict | list:
    """Return parsed JSON from text, stripping markdown fences when present.

    Raises:
        json.JSONDecodeError: if no valid JSON found after all fallbacks
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = _FENCE_RE.search(text)
    if match:
        return json.loads(match.group(1))

    for pattern in (r"\{.*\}", r"\[.*\]"):
        m = re.search(pattern, text, re.DOTALL)
        if m:
            return json.loads(m.group(0))

    raise json.JSONDecodeError("No JSON found in LLM response", text, 0)
