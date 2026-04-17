# Vault Builder Guide

The Vault Builder is an ETL pipeline that extracts data from multiple sources, transforms it into structured Markdown with YAML frontmatter, and loads it into a connected Obsidian knowledge vault via Graphify.

## How It Works

### Extract

Seven extractors pull data from different sources:

| Extractor | Source | What It Extracts | Output Subdir | Trust |
|-----------|--------|------------------|---------------|-------|
| `axon_bridge` | Source code repos | Architectural communities, symbols, domains via Axon CLI | `repos/` | 1.0 |
| `jira` | Jira REST API | Issues, epics, status, labels, comments, issue links | `jira/` | 0.5--0.8 |
| `specs` | Reading Room `specs/` | Canonical spec files with domain detection | `specs/` | 1.0 |
| `obsidian_vault` | Existing Obsidian vault | Markdown files with trust scoring and stale detection | `vault/` | 0.1--0.5 |
| `claude_memory` | Claude Code auto-memory | Memory files with type-based domain mapping | `memory/` | 0.7 |
| `session_context` | Session context files | Historical session data with decision detection | `sessions/` | 0.6 |
| `notebooklm` | NotebookLM exports | AI-generated summaries and raw exports | `notebooklm/` | 0.4 |

Trust scores reflect source reliability. Specs and code get 1.0 (canonical); NotebookLM exports get 0.4 (AI-generated, unverified). The Obsidian vault extractor further penalizes files that contain stale markers (e.g., references to deprecated technologies like "Supabase" or "Auth0").

### Transform

All extractors normalize output to Markdown files with YAML frontmatter via `OutputWriter`:

```yaml
---
title: "COS-123: Implement RLS policies"
source_type: jira_issue
source_path: sevenbelow.atlassian.net/browse/COS-123
extracted_at: "2026-04-16T12:00:00+00:00"
extractor: jira
trust: 0.6
domain: project-management
tags:
  - source/jira
  - trust/medium
  - in-progress
related:
  - "[[COS-100]]"
  - "[[COS-124]]"
---

# COS-123: Implement RLS policies

**Type:** Story
**Status:** In Progress
**Assignee:** Dan Kramer
...
```

Key frontmatter fields:

- **title** -- Node label in the knowledge graph
- **source_type** -- One of: `code_repo`, `jira_issue`, `spec`, `vault_archive`, `claude_memory`, `session_context`, `notebooklm`
- **trust** -- Float 0.0--1.0 indicating source reliability
- **domain** -- Detected domain (e.g., `auth`, `tenancy`, `api`, `compliance`, `infra`)
- **tags** -- Searchable tags combining source, trust level, and status
- **related** -- Wikilinks (`[[target]]`) that become graph edges

### Load

Graphify reads the frontmatter from all extracted files, builds a knowledge graph, and generates:

- **graph.json** -- NetworkX graph serialized as JSON (nodes, edges, communities)
- **graph.html** -- Interactive force-directed visualization (skipped for graphs over 5,000 nodes)
- **wiki/*.md** -- Community articles synthesized from clustered nodes
- **GRAPH_REPORT.md** -- Analysis summary with god nodes, surprising connections, and cohesion scores

The vault builder uses Graphify's frontmatter-based build path (`build_from_vault`), which creates nodes and edges directly from the YAML metadata. No LLM calls are needed -- all structure is already in the frontmatter.

Graph edges come from two sources:
1. **Explicit** -- `related` wikilinks in frontmatter become `related_to` edges
2. **Implicit** -- Nodes sharing the same `domain` value are connected via virtual domain hub nodes (`belongs_to_domain` edges)

## Building

### Build All Sources

Build every enabled extractor, then run Graphify:

```
library_vault_builder_build
```

Extractors run in parallel by default. The orchestrator gathers results, writes a build manifest, then triggers Graphify if at least one extractor succeeded.

### Build Specific Sources

Build only selected extractors by passing a comma-separated list:

```
library_vault_builder_build sources="specs"
library_vault_builder_build sources="jira,axon_bridge"
library_vault_builder_build sources="obsidian_vault,claude_memory,notebooklm"
```

### Run a Single Extractor

Extract from one source without triggering Graphify:

```
library_vault_builder_extract extractor="specs"
library_vault_builder_extract extractor="jira" dry_run=true
```

Set `dry_run=true` to preview what would be extracted without writing any files.

### The Survey, Preview, Build Workflow

The vault builder provides a three-step safety process before committing to a full build:

**1. Survey** -- Check source connectivity and file counts without reading content.

```
library_vault_builder_survey
library_vault_builder_survey sources="jira,specs"
```

Returns health status for each source (`connected`, `empty`, `degraded`, `error`, `missing`) along with file counts and structure summaries.

**2. Preview** -- Dry run that reports exactly which files would be created and estimated token counts, but writes nothing to disk.

```
library_vault_builder_preview
library_vault_builder_preview sources="axon_bridge"
```

**3. Build** -- Run extraction and write files. Includes a safety gate that blocks `create` mode if the output vault already contains content. Use `force=true` to override or switch to `enrich` mode.

```
library_vault_builder_build
library_vault_builder_build force=true
```

### Safety Gate

When `mode` is set to `create`, the orchestrator detects the current vault state before writing:

| Vault State | Description | Blocked? |
|-------------|-------------|----------|
| `new_vault` | Directory does not exist or is empty | No |
| `previous_build` | Has `raw/_build-manifest.md` from a prior build | No |
| `existing_vault_no_raw` | Has `.obsidian/` but no `raw/` directory | Yes (use `force` or `enrich`) |
| `existing_vault_with_raw` | Has both `.obsidian/` and `raw/` | Yes (use `force` or `enrich`) |
| `non_vault_directory` | Non-empty directory without `.obsidian/` | Yes (use `force` or `enrich`) |

## Configuration

All vault builder settings live in `library-config.yaml` under the `vault_builder` key:

```yaml
vault_builder:
  # Build mode: "create" (fresh vault) or "enrich" (add to existing)
  mode: create

  # Where extracted files and Graphify output are written
  output_vault: /path/to/output-vault

  # Run extractors in parallel (recommended)
  parallel: true
  max_parallel_extractors: 8

  # Stop on first extractor failure
  fail_fast: false

  # Graphify integration
  graphify:
    enabled: true
    command: graphify          # Path to graphify binary
    flags: ["--obsidian", "--wiki"]
    incremental: true          # Reuse cached results when possible

  # Axon CLI settings (used by axon_bridge extractor)
  axon:
    enabled: true
    command: axon
    host_mode: false           # true = connect to running Axon server
    host_url: http://localhost:8420

  # Per-source configuration
  sources:
    axon_bridge:
      enabled: true
      repos:
        - name: compliance-core
          path: /absolute/path/to/compliance-core
          type: backend
          language: typescript
        - name: compliance-ui
          path: /absolute/path/to/compliance-ui
          type: frontend
          language: typescript

    jira:
      enabled: true
      instance: yoursite.atlassian.net
      cloud_id: your-cloud-id
      projects: [COS, PLT, SEC]
      auth: mcp                # Authentication via MCP Jira tools

    specs:
      enabled: true
      source_path: /path/to/library-reading-room/specs

    obsidian_vault:
      enabled: true
      source_path: /path/to/existing-vault
      exclude_dirs:            # Directories to skip
        - .obsidian
        - .git
        - raw/jira-tickets
      include_extensions: [.md, .excalidraw]
      stale_markers:           # Content patterns that reduce trust
        - Supabase
        - Auth0

    claude_memory:
      enabled: true
      memory_paths:
        - ~/.claude/projects/-Users-you-project/memory

    session_context:
      enabled: false           # Legacy source, disabled by default

    notebooklm:
      enabled: true
      source_path: /path/to/notebooklm-exports
      summaries_path: /path/to/notebooklm-summaries
```

### Configuration Validation

Check your configuration before building:

```
library_vault_builder_config
library_vault_builder_config section="jira"
```

Returns validation errors, enabled sources, and optionally the detailed config for a specific source.

### Environment Variables

The Jira extractor requires:

- `JIRA_API_TOKEN` -- Atlassian API token
- `JIRA_EMAIL` -- Email associated with the token

The Axon Bridge extractor requires the `axon` CLI to be installed and available on `$PATH`.

## Output Structure

After a full build, the output vault looks like this:

```
output-vault/
  .obsidian/
    app.json                   # Dark theme config
    graph.json                 # Color groups for Obsidian graph view
  raw/
    _build-manifest.md         # Build summary table with per-extractor status
    repos/
      compliance-core/
        repo-summary.md        # Repository overview (files, symbols, clusters)
        communities/
          services-graphql.md  # Axon community: symbols + members
          auth-clerk-jwt.md
      compliance-ui/
        repo-summary.md
        communities/
          ...
    jira/
      COS/
        COS-1.md               # One file per issue
        COS-2.md
      PLT/
        PLT-1.md
    specs/
      GLOSSARY.md              # Canonical spec files with frontmatter
      DOMAINS.md
      INVARIANTS.md
      ...
    vault/
      wiki/
        article-name.md        # Existing vault files with trust scores
      raw/
        ...
    memory/
      project_greenfield_reset.md
      feedback_testing_required.md
    notebooklm/
      export-name.md
  graphify-out/
    graph.json                 # Knowledge graph
    graph.html                 # Interactive visualization
    GRAPH_REPORT.md            # Analysis report
    .graphify_extract.json     # Raw extraction data
    .graphify_analysis.json    # Communities, cohesion, god nodes
  wiki/
    community-1.md             # Graphify-generated wiki articles
    community-2.md
```

### Build Manifest

Every build writes `raw/_build-manifest.md` with a summary table:

```markdown
| Extractor | Status | Files Written | Duration | Trust |
|-----------|--------|---------------|----------|-------|
| specs | success | 11 | 0.1s | -- |
| jira | success | 47 | 3.2s | -- |
| axon_bridge | success | 14 | 12.5s | -- |
| obsidian_vault | success | 89 | 1.1s | -- |
```

The presence of this manifest marks the vault as `previous_build` state, allowing subsequent builds without the safety gate blocking.

## Troubleshooting

### "Axon CLI not found"

The `axon_bridge` extractor requires the Axon CLI. Install it:

```bash
pip install axoniq
```

Verify with `axon --version`.

### "output_vault contains existing content"

The safety gate is blocking a `create` mode build over an existing directory. Options:

1. Pass `force=true` to the build command
2. Change `mode` to `enrich` in `library-config.yaml`
3. Point `output_vault` to a new directory

### "Missing env var: JIRA_API_TOKEN"

The Jira extractor needs authentication. Set the environment variables:

```bash
export JIRA_API_TOKEN="your-api-token"
export JIRA_EMAIL="your-email@example.com"
```

Generate tokens at https://id.atlassian.com/manage-profile/security/api-tokens.

### "All extractors failed -- Graphify skipped"

Graphify only runs when at least one extractor succeeds. Check the build result for per-extractor errors and fix them individually:

```
library_vault_builder_extract extractor="specs"
```

### "No frontmatter nodes found"

Graphify's `build_from_vault` path requires files to have YAML frontmatter with at least a `title` field. Files starting with `_` (like the build manifest) are skipped. If all files lack frontmatter, the graph will be empty.

### "Graphify is not installed"

Install with the graphify extra:

```bash
pip install 'the-library[graphify]'
```

### Stale trust scores on vault files

The `obsidian_vault` extractor reduces trust by 0.1 for files containing any configured `stale_markers`. Review the markers in your config:

```yaml
obsidian_vault:
  stale_markers:
    - Supabase    # Removed from architecture
    - Auth0       # Replaced by Clerk
```

Files referencing deprecated technologies get lower trust, which affects their weight in the knowledge graph.
