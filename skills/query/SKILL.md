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

## Subagent Orchestration (--report mode)

When generating a full status report, dispatch parallel subagents:

- **Agent 1:** Call `library_vault_parse` + summarize vault state
- **Agent 2:** Call `library_pm_sync` + summarize PM state
- **Agent 3:** Call `library_memory_scan` + summarize memory health
- **Agent 4:** Call `library_checkpoint_list` + summarize recent checkpoints

Main context merges summaries into formatted report.

For simple queries (not --report), single tool call — no subagents needed.

### Fallback

If subagents unavailable, make sequential tool calls in main context.

## Token Budget

**Weight:** Light (simple query), Medium (--report without subagents), Light (--report with subagents)
**Estimated context cost:** ~500 tokens (simple), ~1500 tokens (--report with subagents)
**Subagent delegation:** Yes — --report mode parallelizes data collection

## MCP Tools Used

- `library:vault:parse` — vault content queries
- `library:graph:query` — relationship queries
- `library:graph:path` — path tracing
- `library:pm:query` — task state
- `library:pm:sync` — project state (for report)
- `library:memory:scan` — memory health
- `library:checkpoint:read` — session state
- `library:config:get` — check what's enabled
