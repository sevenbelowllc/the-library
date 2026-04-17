# MCP Tools Reference

Complete reference for all MCP tools exposed by The Library's MCP server.

**Source of truth:** `src/library_server/server.py`

## Quick Reference

| Module | Tools | Count |
|--------|-------|-------|
| Config | `config_get`, `config_set` | 2 |
| Checkpoint | `checkpoint_write`, `checkpoint_read`, `checkpoint_list` | 3 |
| Memory | `memory_scan`, `memory_aggregate`, `memory_prune`, `memory_health`, `memory_learn` | 5 |
| Vault | `vault_init`, `vault_validate`, `vault_parse`, `vault_ingest` | 4 |
| Vault Builder | `vault_builder_config`, `vault_builder_survey`, `vault_builder_preview`, `vault_builder_build`, `vault_builder_extract` | 5 |
| Project Management | `pm_create_task`, `pm_create_epic`, `pm_sync`, `pm_update`, `pm_query`, `pm_create_project`, `pm_list_projects`, `pm_get_project`, `pm_update_project`, `pm_assign_task`, `pm_link_issues`, `pm_get_link_types` | 12 |
| Graph | `graph_rebuild`, `graph_query`, `graph_path` | 3 |
| Dev | `dev_token_report` | 1 |
| **Total** | | **35** |

All tools are prefixed with `library_` in the MCP namespace (e.g., `library_config_get`).

---

## Config

### library_config_get

**Description:** Read current library configuration. Pass a section name (e.g. 'vault', 'pm') or empty for all.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| section | str | No | `""` | Config section name (e.g. `vault`, `pm`, `checkpoints`, `graphify`) |

**Returns:** `dict` -- Full config object when no section specified, or the section's key-value pairs.

**Used by skills:** config, compile, ingest, memory, plan, query, review, sync, triage, audit (10 skills)

---

### library_config_set

**Description:** Update a configuration value. Example: section='pm', key='provider', value='linear'.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| section | str | Yes | -- | Config section to update |
| key | str | Yes | -- | Key within the section |
| value | str | Yes | -- | New value to set |

**Returns:** `dict` -- `{status, section, key, value}` confirming the update.

**Used by skills:** config

---

## Checkpoint

### library_checkpoint_write

**Description:** Write a session checkpoint. Lists are semicolon-separated strings.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| topic | str | Yes | -- | Session topic or work area |
| status | str | Yes | -- | Current status (e.g. "in-progress", "blocked", "complete") |
| next_session | str | Yes | -- | What the next session should focus on |
| accomplished | str | No | `""` | Semicolon-separated list of accomplishments |
| next_actions | str | No | `""` | Semicolon-separated list of next actions |
| key_context | str | No | `""` | Semicolon-separated list of context items to remember |

**Returns:** `dict` -- Path to written checkpoint file and parsed data.

**Used by skills:** checkpoint

---

### library_checkpoint_read

**Description:** Read and parse a checkpoint file. Returns structured session state.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| checkpoint_path | str | Yes | -- | Path to the checkpoint file to read |

**Returns:** `dict` -- Parsed checkpoint with topic, date, status, accomplished, next_actions, key_context.

**Used by skills:** query

---

### library_checkpoint_list

**Description:** List all checkpoint files. Uses config path if no directory specified.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| checkpoint_dir | str | No | `""` | Directory to scan; falls back to config `checkpoints.path` |

**Returns:** `dict` -- List of checkpoint file paths with metadata.

**Used by skills:** (available for direct use)

---

## Memory

### library_memory_scan

**Description:** Scan memory files for staleness and metadata. Returns entries with stale flags.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| memory_path | str | No | `""` | Memory directory; falls back to config `memory.path` |
| stale_threshold_days | int | No | `30` | Days after which a memory is considered stale |

**Returns:** `dict` -- List of memory entries with file path, age, stale flag, and metadata.

**Used by skills:** memory, query

---

### library_memory_aggregate

**Description:** Find merge opportunities for related memories. Set dry_run=False to apply.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| memory_path | str | No | `""` | Memory directory; falls back to config `memory.path` |
| dry_run | bool | No | `True` | Preview merge groups without applying changes |

**Returns:** `dict` -- Merge candidates grouped by topic similarity.

**Used by skills:** memory

---

### library_memory_prune

**Description:** Remove stale memory files. Set dry_run=False to delete. Updates MEMORY.md index.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| memory_path | str | No | `""` | Memory directory; falls back to config `memory.path` |
| stale_threshold_days | int | No | `30` | Days threshold for staleness |
| dry_run | bool | No | `True` | Preview deletions without applying |

**Returns:** `dict` -- List of pruned (or would-be-pruned) files and updated index status.

**Used by skills:** memory

---

### library_memory_health

**Description:** Get memory system health report -- keyword accuracy, vault stats, CLAUDE.md lines.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| memory_path | str | No | `""` | Memory directory path |
| vault_path | str | No | `""` | Vault path for counting domains/decisions |

**Returns:** `dict` -- `{vault_file_count, domain_count, decision_count, keyword_accuracy, status}`.

**Used by skills:** memory

---

### library_memory_learn

**Description:** Analyze routing journal and propose keyword improvements.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| vault_path | str | No | `""` | Vault path (used for config resolution) |

**Returns:** `dict` -- `{accuracy, drifts, status}` with per-keyword accuracy scores and drift detection.

**Used by skills:** memory

---

## Vault

### library_vault_init

**Description:** Bootstrap a new vault with Karpathy 3-layer structure (`_schema/`, `sources/`, `wiki/`, `archive/`).

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| vault_path | str | Yes | -- | Directory to create the vault in |

**Returns:** `dict` -- Created directory structure and status.

**Used by skills:** config

---

### library_vault_validate

**Description:** Validate vault structure against schema. Returns `{valid: bool, issues: list}`.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| vault_path | str | Yes | -- | Vault directory to validate |

**Returns:** `dict` -- `{valid: bool, issues: list}` with structural validation results.

**Used by skills:** config

---

### library_vault_parse

**Description:** Parse vault wiki articles. Returns tags (`[VERIFY]`/`[CONFLICT]`/`[PLANNED]`), frontmatter, headings.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| vault_path | str | Yes | -- | Vault directory to parse |

**Returns:** `dict` -- Parsed wiki articles with tags, frontmatter metadata, and heading structure.

**Used by skills:** audit, compile, query, review, sync, triage (6 skills)

---

### library_vault_ingest

**Description:** Ingest a file or directory into vault `sources/<tier>/<category>/`. Updates `kb.yaml`.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| vault_path | str | Yes | -- | Target vault directory |
| source_path | str | Yes | -- | File or directory to ingest |
| tier | str | Yes | -- | Source tier (e.g. `t1`, `t2`, `t3`) |
| category | str | Yes | -- | Category within the tier |

**Returns:** `dict` -- Ingested file count, paths, and updated `kb.yaml` status.

**Used by skills:** ingest

---

## Vault Builder

### library_vault_builder_config

**Description:** Show current Vault Builder configuration and validation status.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| section | str | No | `""` | Source name to show detail for (e.g. `specs`, `jira`) |

**Returns:** `dict` -- `{mode, output_vault, parallel, sources, graphify_enabled, axon_enabled, validation_errors, valid}`. Includes `source_detail` if section specified.

**Used by skills:** (available for direct use)

---

### library_vault_builder_survey

**Description:** Survey all or specific vault builder sources. Returns file counts and health.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| sources | str | No | `""` | Comma-separated source names; empty for all |

**Returns:** `dict` -- `{vault_state, sources}` with per-source file counts and health status.

**Used by skills:** (available for direct use)

---

### library_vault_builder_preview

**Description:** Dry run -- show what would be extracted without writing.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| sources | str | No | `""` | Comma-separated source names; empty for all |

**Returns:** `dict` -- `{sources}` with per-source preview of files that would be extracted.

**Used by skills:** (available for direct use)

---

### library_vault_builder_build

**Description:** Full parallel extraction + Graphify build. Pass force=True to overwrite existing vault.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| sources | str | No | `""` | Comma-separated source names; empty for all |
| force | bool | No | `False` | Overwrite existing vault (bypasses safety gate) |

**Returns:** `dict` -- `{status, extract_results[], graphify_status, duration_seconds, manifest_path}`. Each extract result has `{source, success, files, errors}`.

**Used by skills:** (available for direct use)

---

### library_vault_builder_extract

**Description:** Run a single extractor by name. Set dry_run=True for preview only.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| extractor | str | Yes | -- | Extractor name (e.g. `specs`, `jira`, `obsidian_vault`, `claude_memory`) |
| dry_run | bool | No | `False` | Preview mode -- show what would be extracted |

**Returns:** `dict` -- Same as `vault_builder_build` for single extractor, or preview output if dry_run.

**Used by skills:** (available for direct use)

---

## Project Management

PM tools use the configured adapter (Jira or Linear) via `pm.provider` in `library-config.yaml`.

### Workflow Tools

Used by skills to manage tasks as part of automated workflows.

#### library_pm_create_task

**Description:** Create a task in the configured PM tool (Jira or Linear).

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| project_key | str | Yes | -- | Project key (e.g. `COS`, `LIBRARY`) |
| summary | str | Yes | -- | Task title |
| description | str | Yes | -- | Task description |
| labels | str | No | `""` | Comma-separated labels |

**Returns:** `dict` -- `{task_id, summary, url}`.

**Used by skills:** audit, plan, sync, triage (4 skills)

---

#### library_pm_create_epic

**Description:** Create an epic in the configured PM tool.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| project_key | str | Yes | -- | Project key |
| summary | str | Yes | -- | Epic title |
| description | str | Yes | -- | Epic description |

**Returns:** `dict` -- `{epic_id, summary, url}`.

**Used by skills:** plan

---

#### library_pm_sync

**Description:** Pull current state from PM tool. Returns open, stale, blocked, recently closed tasks.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| project_key | str | Yes | -- | Project key to sync |

**Returns:** `dict` -- `{project_key, open, blocked, recently_closed, tasks[]}`. Each task has `{id, summary, status}`.

**Used by skills:** checkpoint, query, sync

---

#### library_pm_update

**Description:** Update a task's status or add a comment.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| task_id | str | Yes | -- | Task ID (e.g. `COS-123`) |
| status | str | No | `""` | New status value |
| comment | str | No | `""` | Comment to add |

**Returns:** `dict` -- `{task_id, status}`.

**Used by skills:** checkpoint, plan, review

---

#### library_pm_query

**Description:** Query tasks by filter. Returns matching tasks.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| project_key | str | Yes | -- | Project key to query |
| status | str | No | `""` | Filter by status |
| labels | str | No | `""` | Comma-separated labels to filter by |

**Returns:** `dict` -- `{count, tasks[]}`. Each task has `{id, summary, status}`.

**Used by skills:** query, triage

---

### Admin Tools

For direct use -- project management and issue linking operations.

#### library_pm_create_project

**Description:** Create a Jira project. Requires admin access.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| name | str | Yes | -- | Project name |
| key | str | Yes | -- | Project key (e.g. `COS`) |
| description | str | No | `""` | Project description |
| project_type_key | str | No | `"software"` | Jira project type |
| workflow_scheme | str | No | `""` | Workflow scheme name; falls back to config default |

**Returns:** `dict` -- `{project_key, name, url}`.

**Used by skills:** (admin -- direct use)

---

#### library_pm_list_projects

**Description:** List all visible projects.

**Parameters:** None.

**Returns:** `dict` -- `{count, projects[]}`. Each project has `{key, name, description}`.

**Used by skills:** (admin -- direct use)

---

#### library_pm_get_project

**Description:** Get project details.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| project_key | str | Yes | -- | Project key |

**Returns:** `dict` -- `{project_key, name, description, lead, url}`.

**Used by skills:** (admin -- direct use)

---

#### library_pm_update_project

**Description:** Update project name or description.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| project_key | str | Yes | -- | Project key |
| name | str | No | `""` | New project name |
| description | str | No | `""` | New project description |

**Returns:** `dict` -- `{project_key, name, url}`.

**Used by skills:** (admin -- direct use)

---

#### library_pm_assign_task

**Description:** Assign a task to a user by account ID.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| task_id | str | Yes | -- | Task ID |
| account_id | str | Yes | -- | Jira/Linear user account ID |

**Returns:** `dict` -- `{task_id, status}`.

**Used by skills:** (admin -- direct use)

---

#### library_pm_link_issues

**Description:** Link two issues (e.g., 'Blocks', 'Relates').

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| type_name | str | Yes | -- | Link type (e.g. `Blocks`, `Relates`, `Cloners`) |
| inward_key | str | Yes | -- | Inward issue key |
| outward_key | str | Yes | -- | Outward issue key |

**Returns:** `dict` -- `{status, type, inward, outward}`.

**Used by skills:** (admin -- direct use)

---

#### library_pm_get_link_types

**Description:** List available issue link types.

**Parameters:** None.

**Returns:** `dict` -- `{types}` with list of available link type names.

**Used by skills:** (admin -- direct use)

---

## Graph

### library_graph_rebuild

**Description:** Trigger Graphify to rebuild the knowledge graph from vault sources.

**Parameters:** None (reads vault and graph paths from config).

**Returns:** `dict` -- Rebuild status, node/edge counts, and duration.

**Used by skills:** config, compile, ingest

---

### library_graph_query

**Description:** Query the knowledge graph. Falls back gracefully if Graphify is disabled.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| query | str | Yes | -- | Natural language or structured query |

**Returns:** `dict` -- Matching nodes, edges, and relevance scores.

**Used by skills:** audit, query

---

### library_graph_path

**Description:** Trace shortest path between two nodes in the knowledge graph.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| node_a | str | Yes | -- | Start node name |
| node_b | str | Yes | -- | End node name |

**Returns:** `dict` -- Shortest path with intermediate nodes and edge types.

**Used by skills:** query

---

## Dev

### library_dev_token_report

**Description:** Show per-component token usage for the current session (dev mode).

**Parameters:** None.

**Returns:** `dict` -- Aggregated token usage from `~/.library/state/token-usage.json`, broken down by component.

**Used by skills:** (dev -- direct use)
