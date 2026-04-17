# Skills Reference

Complete reference for all 12 Library skills. Skills are Claude Code prompt templates that orchestrate MCP tools into multi-step workflows.

## Skill Pipeline

Skills connect in a directed workflow. The typical project lifecycle flows left-to-right, top-to-bottom:

```
config --> ingest --> compile --> triage --> plan
                                       |
                sync <-- checkpoint <-- [work] --> review
                              |
                            audit --> query
                              |
                            memory
```

- **config** bootstraps everything: Reading Room, vault, PM, Graphify
- **ingest** and **compile** populate the vault from raw sources
- **triage** and **plan** convert vault tags and specs into PM tasks
- **[work]** is the developer doing actual implementation
- **review** validates completion claims with evidence
- **checkpoint** captures session state for continuity
- **sync** pulls PM state to detect drift
- **audit** runs three-way gap analysis (spec vs vault vs code)
- **query** routes questions to the right data source
- **memory** maintains knowledge health across sessions
- **build** (new) runs the vault builder pipeline end-to-end

---

## Skills Catalog

### config

| | |
|---|---|
| **Invoke** | `/library:config` or `/library:config <subcommand>` |
| **When to use** | First-time setup, or to update Reading Room, vault, PM, Graphify, branding, or MCP settings |
| **MCP tools** | `library_config_get`, `library_config_set`, `library_vault_init`, `library_vault_validate`, `library_graph_rebuild` |
| **Token weight** | Medium |
| **Subcommands** | `branding`, `vault`, `pm`, `graphify`, `mcp` |

Example:
```
/library:config pm
```

---

### ingest

| | |
|---|---|
| **Invoke** | `/library:ingest` (single) or `/library:ingest --batch` (multi) |
| **When to use** | Adding source material to the vault (PRDs, session notes, research) |
| **MCP tools** | `library_vault_ingest`, `library_graph_rebuild`, `library_config_get` |
| **Token weight** | Light (single), Medium (batch) |

Example:
```
/library:ingest ~/docs/feature-spec.md
```

Sources are classified into contamination tiers: **raw** (human-authored), **curated** (human-edited), **llm-generated** (AI-produced), **external** (third-party).

---

### compile

| | |
|---|---|
| **Invoke** | `/library:compile` |
| **When to use** | After ingesting new sources; when wiki articles need updating |
| **MCP tools** | `library_config_get`, `library_vault_parse`, `library_graph_rebuild` |
| **Token weight** | Heavy |

Example:
```
/library:compile
```

Compiles wiki articles from raw vault sources. Tags uncertainties with `[VERIFY]`, `[CONFLICT]`, and `[PLANNED]`. Recompilation is idempotent -- articles are rebuilt from scratch each time.

---

### query

| | |
|---|---|
| **Invoke** | `/library:query <question>` or `/library:query --report` |
| **When to use** | Asking questions about project state, dependencies, blocked work, or vault content |
| **MCP tools** | `library_vault_parse`, `library_graph_query`, `library_graph_path`, `library_pm_query`, `library_pm_sync`, `library_memory_scan`, `library_checkpoint_read`, `library_config_get` |
| **Token weight** | Light (single question), Medium (report) |

Example:
```
/library:query What depends on the auth middleware?
/library:query --report
```

Routes questions to the appropriate data source: vault parser for content, Graphify for relationships, PM adapter for task state.

---

### memory

| | |
|---|---|
| **Invoke** | `/library:memory` |
| **When to use** | Periodic maintenance (every few sessions); when memory index is long; after major project changes |
| **MCP tools** | `library_memory_scan`, `library_memory_aggregate`, `library_memory_prune`, `library_memory_health`, `library_memory_learn`, `library_config_get` |
| **Token weight** | Medium |

Example:
```
/library:memory
```

Operations: scan, validate references, aggregate related entries, prune stale entries, detect conflicts, run health report, optimize by offloading to vault. All destructive operations require dry-run preview and user approval.

---

### sync

| | |
|---|---|
| **Invoke** | `/library:sync` |
| **When to use** | Start of session; after completing work; periodically to detect stale tasks |
| **MCP tools** | `library_pm_sync`, `library_vault_parse`, `library_pm_create_task`, `library_config_get` |
| **Token weight** | Medium |

Example:
```
/library:sync
```

Pulls PM state for all configured projects. Cross-references vault `[VERIFY]` tags against closed PM tasks to catch items closed without verification. Flags stale (>14 days) and blocked (>7 days) tasks.

---

### triage

| | |
|---|---|
| **Invoke** | `/library:triage` |
| **When to use** | After compile generates tagged articles; after ingest adds new sources; periodically |
| **MCP tools** | `library_vault_parse`, `library_pm_query`, `library_pm_create_task`, `library_config_get` |
| **Token weight** | Medium |

Example:
```
/library:triage
```

Scans vault for `[VERIFY]`, `[CONFLICT]`, `[PLANNED]` tags. Deduplicates against existing PM tasks. Presents candidates for user approval before creating tasks. Removes tags from wiki articles after tasks are created.

---

### plan

| | |
|---|---|
| **Invoke** | `/library:plan <spec-file>` |
| **When to use** | After a design spec is approved; when breaking an initiative into trackable work |
| **MCP tools** | `library_pm_create_epic`, `library_pm_create_task`, `library_pm_update`, `library_config_get` |
| **Token weight** | Heavy |

Example:
```
/library:plan ~/specs/vault-builder-design.md
```

Parses a spec into sections, maps sections to epics, maps deliverables to tasks. Presents the proposed PM hierarchy for approval before creating anything.

---

### audit

| | |
|---|---|
| **Invoke** | `/library:audit` |
| **When to use** | Before development cycles; after claiming milestones complete; periodically to detect drift |
| **MCP tools** | `library_vault_parse`, `library_graph_query`, `library_pm_create_task`, `library_config_get` |
| **Token weight** | Heavy |

Example:
```
/library:audit
```

Three-way gap analysis comparing canonical specs, vault wiki articles, and actual code. Produces verdicts: VERIFIED, UNVERIFIED, CLAIMED-BUT-BROKEN, MISSING, UNDOCUMENTED, SCOPE CREEP. Optionally creates PM tasks for gaps.

---

### review

| | |
|---|---|
| **Invoke** | `/library:review <task-or-feature>` |
| **When to use** | Before closing a PM task; before claiming a feature is complete; before creating a PR |
| **MCP tools** | `library_pm_update`, `library_vault_parse`, `library_config_get` |
| **Token weight** | Medium |

Example:
```
/library:review COS-42
```

Validates completion claims against running code. Verdict is VERIFIED (all criteria pass with evidence), PARTIAL (some pass), or FAILED (critical criteria fail). Iron rule: no completion claims without fresh verification evidence from the current session.

---

### checkpoint

| | |
|---|---|
| **Invoke** | `/library:checkpoint` |
| **When to use** | End of session; before switching tasks; before context window expires |
| **MCP tools** | `library_checkpoint_write`, `library_pm_update`, `library_pm_sync` |
| **Token weight** | Medium |

Example:
```
/library:checkpoint
```

Captures accomplished work, file changes, next actions, open decisions, and key context. Writes a structured checkpoint file, updates memory, and comments on PM tasks. Quality gates enforce specificity -- no vague actions like "continue working on X."

---

### build (new)

| | |
|---|---|
| **Invoke** | Via MCP tools directly |
| **When to use** | Running the vault builder pipeline to extract structured knowledge from all configured sources |
| **MCP tools** | `library_vault_builder_survey`, `library_vault_builder_preview`, `library_vault_builder_extract`, `library_vault_builder_build`, `library_vault_builder_config` |
| **Token weight** | Heavy |

Example:
```
# Survey all sources
library_vault_builder_survey

# Preview what would be extracted
library_vault_builder_preview

# Full build (extract + Graphify)
library_vault_builder_build
```

Orchestrates all registered extractors (specs, claude_memory, session_context, notebooklm, obsidian_vault, jira, axon_bridge) through the survey-preview-extract pipeline. Writes structured Markdown with YAML frontmatter to the vault's `raw/` directory. Optionally runs Graphify for knowledge graph generation.

---

## Token Weight Guide

| Weight | Approximate Impact | Skills |
|--------|-------------------|--------|
| **Light** | Minimal context consumed; fast single-tool calls | ingest (single), query (single question) |
| **Medium** | Moderate context; multi-step with user interaction | config, memory, sync, triage, review, checkpoint, ingest (batch), query (report) |
| **Heavy** | Large context; reads many files, produces detailed output | compile, plan, audit, build |
