# Structured Output Research — Provider-Agnostic JSON
**Date:** 2026-05-11  
**Context:** Fixing Bug 2 (IdeaBlockBuilder returns 0 blocks because JSON parsing fails)  
**Goal:** Design a solution that works identically across Ollama, Anthropic, OpenRouter

---

## The Problem

`IdeaBlockBuilder._ingest()` calls `json.loads(response.content)` directly.
Different models wrap JSON differently:

| Provider / Model | What it returns when asked for JSON |
|---|---|
| qwen3.5:9b (Ollama, no format param) | `` ```json\n{...}\n``` `` — always wrapped |
| Claude Sonnet/Haiku (no format param) | Usually clean `{...}` but not guaranteed |
| GPT-4o (no format param) | Usually clean, sometimes wrapped |
| Mistral (OpenRouter) | Varies by model version |

Hardcoding regex stripping for Ollama will either over-strip or break on clean responses.

---

## What the Ecosystem Offers

### 1. Native structured output — per provider (2025-2026)

**Ollama** — JSON schema mode (v0.5+):
```python
payload = {
    "model": model,
    "messages": [...],
    "format": {           # ← constrained decoding, NOT prompting
        "type": "object",
        "properties": { "blocks": { "type": "array", ... } },
        "required": ["blocks"]
    }
}
```
Output is always valid JSON — no fences, no markdown. Guaranteed at token generation level.

**Anthropic Claude** — Structured Outputs (beta, Nov 2025):
```python
# Requires header: anthropic-beta: structured-outputs-2025-11-13
# Works with Sonnet 4.5, Opus 4.1 (Haiku coming)
response = client.beta.messages.create(
    model="claude-sonnet-4-5",
    output_format={"type": "json_schema", "json_schema": schema},
    ...
)
```
Also constrained decoding — schema-guaranteed output.

**OpenRouter** — passes `response_format` to the underlying model:
```python
payload = { "response_format": {"type": "json_object"}, ... }
```
Compliance depends on the underlying model — not all support it.

### 2. Instructor library (jxnl/instructor — 12k+ stars)

Wraps provider SDKs with Pydantic validation + auto-retry:
```python
import instructor
from pydantic import BaseModel

client = instructor.from_provider("ollama/qwen3.5:9b")
result = client.chat.completions.create(
    response_model=IdeaBlockList,
    messages=[...]
)
# result is already a validated Pydantic object — no JSON parsing needed
```
- Same code for Ollama, Anthropic, OpenAI, OpenRouter
- Auto-retries with validation error feedback to the model
- Requires switching from httpx to provider SDKs (ollama-python, anthropic)
- Heavy dependency — brings in the full provider SDK chain

### 3. Simple `json_extractor.py` (no new deps)

A thin utility that applies a decision cascade:
1. `json.loads(text)` — try direct parse (works for Anthropic, some OpenRouter)
2. Strip markdown fences via regex — works for Ollama/qwen and most open models
3. Retry the LLM call with explicit `format` param — provider-native constraint
4. Raise `StructuredOutputError` after N retries

---

## Recommended Architecture — Option C (no new deps, provider-aware)

**Why not Instructor:** Requires swapping all httpx calls for SDK clients. Adds 3+ heavy deps
(anthropic, ollama-python, openai). Over-engineering for what is a thin extraction layer.

**Why not Outlines:** Only works locally, 40s+ compile times for complex schemas, not
suitable for an MCP server that serves multiple concurrent requests.

**Why Option C:** Fits current architecture, zero new deps, progressive enhancement.

### Changes required

#### 1. Add `response_format` to `LLMRequest` entity
```python
# entities/provider_entity.py
class LLMRequest(BaseModel):
    ...
    response_format: dict | None = None   # {"type": "json_object"} or full JSON schema
```

#### 2. Each provider adapter reads `response_format` and applies natively

**Ollama** (`ollama_provider.py`):
```python
if request.response_format:
    payload["format"] = request.response_format
```

**Anthropic** (future `anthropic_provider.py`):
```python
if request.response_format:
    payload["output_format"] = {"type": "json_schema", "json_schema": request.response_format}
    headers["anthropic-beta"] = "structured-outputs-2025-11-13"
```

**OpenRouter** (future `openrouter_provider.py`):
```python
if request.response_format:
    payload["response_format"] = request.response_format
```

#### 3. Add `json_extractor.py` in `modules/llm/` — belt-and-suspenders fallback

```python
# modules/llm/json_extractor.py
"""Extract JSON from LLM response text regardless of markdown wrapping."""

import json
import re

_FENCE_RE = re.compile(r'```(?:json)?\s*(.*?)\s*```', re.DOTALL)


def extract_json(text: str) -> dict | list:
    """Return parsed JSON from text, stripping markdown fences if present.

    Raises:
        json.JSONDecodeError: if no valid JSON found after stripping
    """
    # Fast path: clean JSON (Anthropic native, Ollama with format param)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Slow path: strip markdown code fence
    match = _FENCE_RE.search(text)
    if match:
        return json.loads(match.group(1))

    # Last resort: find first {...} or [...] block in text
    for pattern in (r'\{.*\}', r'\[.*\]'):
        m = re.search(pattern, text, re.DOTALL)
        if m:
            return json.loads(m.group(0))

    raise json.JSONDecodeError("No JSON found in LLM response", text, 0)
```

#### 4. Update `IdeaBlockBuilder._ingest()` — use format param + extractor

```python
async def _ingest(self, content: str, source_ref: str | None) -> list[IdeaBlock]:
    from universal_ai_mcp.modules.llm.json_extractor import extract_json

    request = LLMRequest(
        model="auto",
        messages=[LLMMessage(role="user", content=f"Content to extract:\n\n{content}")],
        system_prompt=INGEST_SYSTEM_PROMPT,
        max_tokens=4096,
        temperature=0.1,
        response_format={"type": "object", "properties": {"blocks": {"type": "array"}},
                         "required": ["blocks"]},   # ← native constraint when supported
    )
    response = await self._router.complete(request, tier="fast")

    try:
        data = extract_json(response.content)   # ← fallback cascade
        return [IdeaBlock(...) for item in data.get("blocks", [])]
    except (json.JSONDecodeError, KeyError):
        log.warning("ingest_parse_failed", source=source_ref, preview=response.content[:200])
        return []
```

---

## Impact Table

| Provider | Before fix | After fix (format param) | After fix (fallback) |
|---|---|---|---|
| Ollama / qwen3.5:9b | ❌ 0 blocks (fence) | ✅ constrained | ✅ fence stripped |
| Anthropic Claude | ✅ usually works | ✅ constrained (beta) | ✅ direct parse |
| OpenRouter (GPT-4o) | ✅ usually works | ✅ json_object mode | ✅ direct parse |
| OpenRouter (Mistral) | ⚠️ unpredictable | ⚠️ partial support | ✅ fence stripped |
| Any future provider | ❌ unpredictable | depends | ✅ fallback handles it |

---

## Implementation Order

1. `entities/provider_entity.py` — add `response_format: dict | None = None` to `LLMRequest`
2. `modules/llm/json_extractor.py` — new file, pure function, no deps
3. `modules/llm/providers/ollama_provider.py` — read `response_format`, add to payload
4. `modules/context/idea_block_builder.py` — use `response_format` + `extract_json()`
5. `modules/context/context_manager.py` / `entities/session_entity.py` — fix Bug 3 (store collections on session)
6. Tests: `tests/test_json_extractor.py` — parametrize: clean JSON, fenced, malformed

---

## Note on `solutions_find` returning empty

GitHub API returns 403 (rate limited) when no `GITHUB_TOKEN` is set.
`GitHubFinder.search()` silently returns `[]` on 403 (`github_rate_limited` warning logged).
Add `GITHUB_TOKEN` env variable in `.env` to unlock full search capability.

---

## Sources

- [Instructor — structured outputs for 15+ providers](https://python.useinstructor.com/)
- [Instructor + Ollama integration](https://python.useinstructor.com/integrations/ollama/)
- [Anthropic Structured Outputs (Nov 2025)](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [Outlines — constrained decoding](https://github.com/dottxt-ai/outlines)
- [Ollama format parameter](https://github.com/ollama/ollama/blob/main/docs/api.md)
