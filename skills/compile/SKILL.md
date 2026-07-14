---
name: compile
description: "Compile wiki articles from vault sources. The Librarian's core job: raw sources become structured wiki articles tagged with [VERIFY], [CONFLICT], [PLANNED]."
---

# library:compile — Wiki Compilation

Compile wiki articles from raw vault sources following the Karpathy pattern.

## When to Use

- After ingesting new sources
- When wiki articles need updating
- When `kb.yaml` compile order changes
- Periodic recompilation to catch drift

## Process

### Step 1: Load Compile Order
Call `library_config_get` to get vault path.
Read `kb.yaml` from vault root for compile order and category list.

### Step 2: For Each Target Article

For each entry in compile order:

1. **Gather sources**: Read all files in `sources/` that map to this wiki article's category
2. **Compile**: Synthesize sources into a structured wiki article
3. **Tag uncertainties**:
   - `[VERIFY]` — claims that need validation against running code
   - `[CONFLICT]` — contradictions between sources
   - `[PLANNED]` — features or work described as future/planned
4. **Write**: Save to `wiki/<article-name>.md`

When `vault.obsidian.wikilinks` is `true` in config, use `[[wikilinks]]` and `#tags` for Obsidian-native output.

### Step 3: Add Frontmatter
Each wiki article gets YAML frontmatter. **The `related:` array is mandatory** — it mirrors every inline `[[wikilink]]` in the body so Graphify's `build_from_vault` can wire cross-reference edges. Inline wikilinks alone are invisible to the graph.

```yaml
---
title: Article Title
domain: core | ui | infra | security
compiled_from:
  - sources/raw/prds/feature-x.md
  - sources/llm-generated/session-notes/2026-04-10.md
last_compiled: 2026-04-10
related:
  - "[[other-article]]"
  - "[[yet-another]]"
---
```

### Step 4: Rebuild Graph — ALWAYS
Call `library_graph_rebuild` after every compile. The whole point of compile is to enrich the graph — wiki articles aren't useful until the graph reflects them.

This goes through the free `build_from_vault()` frontmatter path (no LLM cost). The `graphify.auto_rebuild` config flag gates ingest-triggered rebuilds, NOT the compile path.

**Safety:** `GraphifyRunner.build_from_vault()` takes a `regenerate_wiki: bool = False` kwarg. The orchestrator passes `True` only when both `mode == "create"` AND `wiki/` is empty — protecting compiled articles from the `to_wiki()` auto-stub regeneration that historically destroyed them.

### Step 5: Verify
After rebuild, assert:
- `jq '.nodes | length' <graph.json>` > pre-compile node count
- At least one node where `source_file` matches `wiki/<your-article>.md`

If either fails, compile is incomplete. Surface to operator.

### Step 6: Report
Display: articles compiled, tags generated, sources consumed, graph node delta.

## Idempotency

Recompiling an article replaces its content entirely from sources.
No incremental merge — fresh compile every time. Sources are immutable.

## Subagent Orchestration (Batch Mode)

When compiling multiple articles, delegate source parsing to parallel subagents:

- **Agent 1:** Parse and summarize code sources (repos/)
- **Agent 2:** Parse and summarize PM sources (jira/)
- **Agent 3:** Parse and summarize archive sources (vault/, memory/, sessions/)

Main context receives structured summaries → synthesizes into wiki articles.

For single article compilation, sequential processing is fine — no subagents needed.

### Fallback

If subagents unavailable, process all sources sequentially in main context.

## Token Budget

**Weight:** Light (batch with subagents), Medium (single article or no subagents)
**Estimated context cost:** ~1000 tokens per article with subagents
**Subagent delegation:** Yes — batch source parsing

## MCP Tools Used

- `library_config_get` — vault path
- `library_vault_parse` — read existing wiki state
- `library_graph_rebuild` — rebuild graph after compilation
