# Claude Code Best-Practice — Source Pointer

> Полное содержимое слоёв вынесено в skills.

**Источник:** github.com/shanraisshan/claude-code-best-practice

## Skills (runtime слои)

| Skill | Layer | Status |
|-------|-------|--------|
| `uai-layer-bp-workflow` | Research→Plan→Execute→Review→Ship (design contract) | implemented |
| `uai-layer-bp-context-rules` | Auto-compression, tag-based injection, file caps | implemented |
| `uai-layer-bp-subagent-patterns` | True subprocess context isolation | planned (v2.0) |

## MCP Integration (как подключить сервер)

### HTTP (SSE transport)
```json
{
  "mcpServers": {
    "universal-ai": {
      "url": "https://your-server.com/sse",
      "headers": { "Authorization": "Bearer ${UNIVERSAL_AI_MCP_SECRET}" }
    }
  }
}
```

### stdio (local)
```json
{
  "mcpServers": {
    "universal-ai": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/universal-ai-mcp", "universal-ai-mcp"],
      "env": { "MCP_TRANSPORT": "stdio", "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}" }
    }
  }
}
```

## Что заимствовано

| Best-practice концепт | Реализация |
|-----------------------|------------|
| Commands as MCP tools | Все `*_tools.py` в `src/.../tools/` |
| Skills as scenarios | Workflow profiles в `config/workflow_profiles.yaml` |
| Plan-Execute-Review-Ship | См. `uai-layer-bp-workflow` |
| 200-line cap on rules | См. `uai-layer-bp-context-rules` |
| Subagent patterns | См. `uai-layer-bp-subagent-patterns` (v2.0) |
| Commit per file | Реализовано в `StateManager.save_plan()` (atomic) |
