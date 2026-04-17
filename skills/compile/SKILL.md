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
Call `library:config:get` to get vault path.
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
Each wiki article gets YAML frontmatter:
```yaml
---
title: Article Title
domain: core | ui | infra | security
compiled_from:
  - sources/raw/prds/feature-x.md
  - sources/llm-generated/session-notes/2026-04-10.md
last_compiled: 2026-04-10
---
```

### Step 4: Rebuild Graph
If `graphify.auto_rebuild: true`, call `library:graph:rebuild`.

### Step 5: Report
Display: articles compiled, tags generated, sources consumed.

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

- `library:config:get` — vault path
- `library:vault:parse` — read existing wiki state
- `library:graph:rebuild` — rebuild graph after compilation
