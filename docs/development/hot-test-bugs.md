# Hot Test — Bug Report
**Date:** 2026-05-11  
**Test method:** Live MCP tool calls via Claude Code terminal  
**Tester:** Hot test session (all 14 active tools exercised)

---

## Bug 1 — Ollama token counts always return 0

**Severity:** Low (cosmetic)  
**Status:** Open

**File:** `src/universal_ai_mcp/modules/llm/providers/ollama_provider.py:55`

**Cause:**  
`LLMResponse` is constructed without reading `prompt_eval_count` / `eval_count`
from the Ollama `/api/chat` response. Both fields default to `0`.

**Evidence:**
```json
{ "input_tokens": 0, "output_tokens": 0, "total_tokens": 0 }
```
Ollama response payload contains:
```json
{ "prompt_eval_count": 42, "eval_count": 87 }
```

**Fix:**
```python
return LLMResponse(
    request_id=request.id,
    provider=self.PROVIDER_NAME,
    model=request.model,
    content=content,
    finish_reason=finish_reason,
    input_tokens=data.get("prompt_eval_count", 0),
    output_tokens=data.get("eval_count", 0),
    raw=data,
)
```

---

## Bug 2 — `context_add_content` always returns `blocks_created: 0`

**Severity:** High (Blockify compression is completely non-functional)  
**Status:** Open — see design note below

**File:** `src/universal_ai_mcp/modules/context/idea_block_builder.py:97`

**Cause:**  
`IdeaBlockBuilder._ingest()` calls `json.loads(response.content)` directly.
qwen3.5:9b (and many other models) wrap JSON in a markdown code fence:

```
```json
{ "blocks": [...] }
```
```

`json.loads()` raises `JSONDecodeError` on the backticks.  
The exception is silently swallowed — `_ingest()` returns `[]`.

**Confirmed via `llm_complete` test:** raw response starts with `` ```json ``.

**Naive fix (Ollama-only, NOT recommended):**
```python
import re
match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
```

**Why this is not a safe fix:**  
- Anthropic Claude returns clean JSON without fences when instructed
- OpenRouter models vary by model family
- Regex strips fences but breaks if the model returns nested JSON with fences inside
- See Bug 2 design note and the Solutions Research doc for the right approach

---

## Bug 3 — ContextManager state lost between tool calls

**Severity:** High (context accumulation never works)  
**Status:** Open — must be fixed together with Bug 2

**File:** `src/universal_ai_mcp/tools/context_tools.py` (every tool handler)

**Cause:**  
Each MCP tool call instantiates a fresh `ContextManager()`:
```python
ctx_mgr = ContextManager(settings, builder, compressor)
```
`ContextManager._collections` is a plain instance dict.  
On the next call the dict is empty — previously built IdeaBlocks are gone.

The `AgentSession` object persists (via `session_store`) but only stores
`context_token_usage: int`, not the actual `IdeaBlockCollection`.

**Consequence:**  
Even after Bug 2 is fixed, blocks built in one call are invisible to all
subsequent calls. `context_get_xml` always returns `<KnowledgeContext blocks='0'/>`.

**Fix direction:**  
Option A — store `ContextManager` as a singleton on `mcp.state` (set once at startup).  
Option B — store `IdeaBlockCollection` on `AgentSession` (move state to entity layer).  
Option B is architecturally cleaner: state belongs with the session, not the manager.

---

## Summary

| # | Severity | File | Fix complexity |
|---|---|---|---|
| 1 | Low | `ollama_provider.py:55` | 2 lines |
| 2 | High | `idea_block_builder.py:97` | Needs provider-agnostic solution (see research) |
| 3 | High | `context_tools.py` + `session_entity.py` | Medium refactor |

Bugs 2 and 3 must be addressed together.  
Bug 2 fix strategy depends on the solutions research — do not hardcode for Ollama.
