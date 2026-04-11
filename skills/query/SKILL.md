---
name: query
description: "Ask the Librarian questions. Routes to vault parsing, Graphify graph queries, or PM state depending on the question. Use --report for formatted status summary."
---

# library:query — Ask the Librarian

Natural language questions routed to the appropriate data source.

## When to Use

- "What's next?" / "What should I work on?"
- "What depends on X?"
- "What's blocked?"
- "What changed since last session?"
- "Show me a status report" (use --report)

## Routing Logic

Analyze the question and route:

| Question Type | Data Source | MCP Tool |
|--------------|------------|----------|
| Vault content (tags, articles, sources) | Vault parser | `library_vault_parse` |
| Relationships ("depends on", "connects to") | Graphify | `library_graph_query` |
| Path tracing ("how does A relate to B") | Graphify | `library_graph_path` |
| Task state ("blocked", "overdue", "open") | PM adapter | `library_pm_query` |
| Status report | PM adapter (all projects) | `library_pm_sync` |
| Session state | Checkpoint | `library_checkpoint_read` |

## Report Mode (--report)

Generate a formatted status summary:

1. Call `library_pm_sync` for each configured project
2. Call `library_vault_parse` for tag counts
3. Call `library_memory_scan` for memory health
4. Format as:

```
## Project Status Report — YYYY-MM-DD

### PM Summary
| Project | Open | Blocked | Recently Closed |
|---------|------|---------|-----------------|

### Vault Health
- Wiki articles: N
- [VERIFY] tags: N
- [CONFLICT] tags: N
- [PLANNED] tags: N

### Memory Health
- Total memories: N
- Stale (>30 days): N
- Merge candidates: N
```

## Graceful Degradation

- Graphify disabled → skip relationship queries, note limitation in response
- PM not configured → skip task state, note limitation
- Vault not configured → only memory and checkpoint queries available

## MCP Tools Used

- `library_vault_parse` — vault content queries
- `library_graph_query` — relationship queries
- `library_graph_path` — path tracing
- `library_pm_query` — task state
- `library_pm_sync` — project state (for report)
- `library_memory_scan` — memory health
- `library_checkpoint_read` — session state
- `library_config_get` — check what's enabled
