---
name: library-build
description: "Build the knowledge vault from configured sources. Runs the ETL pipeline: survey sources, preview extraction, execute parallel build, generate Graphify knowledge graph. Supports building all sources or specific ones (e.g., `library:build jira` or `library:build axon_bridge,specs`)."
---

# library:build — Vault Builder ETL Pipeline

Build the knowledge vault from configured sources using the ETL pipeline.

## When to Use

- First vault population after setup
- After adding new source repos or Jira projects
- After significant code changes that should be reflected in the vault
- When you want to rebuild specific sources (e.g., just Jira or just code analysis)

## Arguments

- No arguments: build all enabled sources
- Source names (comma-separated): build specific sources only
  - Valid sources: `specs`, `jira`, `axon_bridge`, `obsidian_vault`, `claude_memory`, `session_context`, `notebooklm`

## Process

### Step 1: Check Config

Call `library_vault_builder_config` to show enabled sources and validation status.
If config is invalid or missing, stop and suggest running `library:config vault` first.

### Step 2: Determine Scope

- If arguments provided, use those sources
- Otherwise ask: "Build all enabled sources, or specific ones?"

### Step 3: Verify Prerequisites

Dispatch parallel Explore subagents to check:

- Axon CLI available (if `axon_bridge` selected)
- Jira auth working (if `jira` selected) — check `JIRA_EMAIL` and `JIRA_API_TOKEN` env vars
- Graphify importable (if enabled in config)

Report pass/fail per check. If any critical check fails, warn before proceeding.

### Step 4: Survey Sources

Call `library_vault_builder_survey(sources)` to show file counts and health.
Each source reports: status (healthy/degraded/missing), file count, last modified.

### Step 5: Preview

Call `library_vault_builder_preview(sources)` to show what files will be created.
Display: new files, updated files, unchanged files, estimated duration.

### Step 6: Confirm

Present summary and ask user to confirm before building:

> "Ready to build [N] sources. [X] files will be created/updated. Proceed?"

### Step 7: Build

Call `library_vault_builder_build(sources, force)` to run parallel extraction + Graphify.
Stream progress if available. For single-source runs, use `library_vault_builder_extract` instead.

### Step 8: Report

Show results:

- Files extracted per source
- Graphify status (if enabled)
- Manifest path
- Duration
- Any warnings or errors

## Quality Gates

- Survey must show at least 1 healthy source before proceeding
- Preview confirmation required before build
- Build result must show at least 1 successful extractor
- If all extractors fail, report error and suggest running `library_vault_builder_config` to check setup

## Token Budget

**Weight:** Light
**Estimated context cost:** ~500 tokens (orchestration only)
**Subagent delegation:** Yes — prerequisite checks dispatched as parallel Explore subagents

## MCP Tools Used

- `library_vault_builder_config` — read configuration
- `library_vault_builder_survey` — check source health
- `library_vault_builder_preview` — dry run
- `library_vault_builder_build` — execute build
- `library_vault_builder_extract` — single extractor (when specific source requested)
