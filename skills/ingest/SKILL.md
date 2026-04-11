---
name: ingest
description: "Ingest source material into the vault. Single mode for one source, batch mode (--batch) for multiple sources during setup or bulk import."
---

# library:ingest — Source Ingestion

Add source material to the vault's sources layer.

## When to Use

- Adding new source material (PRDs, session notes, research papers)
- Initial vault population after `library:config --init-vault`
- Importing a batch of files from another location

## Single Mode (default)

Takes one file, directory, or URL.

### Step 1: Classify Source
Determine contamination tier:
- **raw** — unedited human-authored content (PRDs, meeting notes, specs)
- **curated** — human-edited but may include AI assistance
- **llm-generated** — primarily AI-generated content (session transcripts, compiled articles)
- **external** — third-party content (vendor docs, framework references)

Ask user to confirm tier if ambiguous.

### Step 2: Categorize
Determine content category (e.g., "prds", "session-notes", "security-audits").
Suggest based on filename/content. Ask user to confirm.

### Step 3: Ingest
Call `library_vault_ingest` with vault_path, source_path, tier, category.

### Step 4: Report
Display: what was ingested, where it landed, what compile targets it affects.

### Step 5: Rebuild Graph (if enabled)
If `graphify.auto_rebuild: true` in config, call `library_graph_rebuild`.

## Batch Mode (--batch)

Loop for multiple sources:

1. Prompt: "Add a source path (or 'done'):"
2. User provides path → classify tier → categorize → ingest → report
3. Repeat until user says "done"
4. Display batch summary: total files, categories created, compile targets affected
5. Single graph rebuild at the end (not per-source)

## Chained from config

When `library:config --init-vault` completes, it asks "Want to ingest sources now?"
If yes, enters batch mode automatically.

## MCP Tools Used

- `library_vault_ingest` — classify and bucket source material
- `library_graph_rebuild` — rebuild knowledge graph (if enabled)
- `library_config_get` — read vault path and graphify settings
