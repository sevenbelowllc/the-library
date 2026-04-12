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
| Vault content (tags, articles, sources) | Vault parser | `library:vault:parse` |
| Relationships ("depends on", "connects to") | Graphify | `library:graph:query` |
| Path tracing ("how does A relate to B") | Graphify | `library:graph:path` |
| Task state ("blocked", "overdue", "open") | PM adapter | `library:pm:query` |
| Status report | PM adapter (all projects) | `library:pm:sync` |
| Session state | Checkpoint | `library:checkpoint:read` |

## Report Mode (--report)

Generate a formatted status summary:

1. Call `library:pm:sync` for each configured project
2. Call `library:vault:parse` for tag counts
3. Call `library:memory:scan` for memory health
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

- `library:vault:parse` — vault content queries
- `library:graph:query` — relationship queries
- `library:graph:path` — path tracing
- `library:pm:query` — task state
- `library:pm:sync` — project state (for report)
- `library:memory:scan` — memory health
- `library:checkpoint:read` — session state
- `library:config:get` — check what's enabled
