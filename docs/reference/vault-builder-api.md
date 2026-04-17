# Vault Builder API Reference

Developer reference for extending the vault builder with custom extractors.

## Architecture

```
library-config.yaml
        |
  VaultBuilderConfig
        |
  VaultBuildOrchestrator
        |
  PluginRegistry ──> [BaseExtractor, BaseExtractor, ...]
        |
  OutputWriter ──> raw/<subdir>/*.md (YAML frontmatter)
        |
  GraphifyRunner (optional post-processing)
        |
  _build-manifest.md
```

The vault builder follows a three-phase pipeline for each extractor: **survey** (what exists?), **preview** (what would be extracted?), **extract** (write structured Markdown).

---

## BaseExtractor ABC

**Module:** `src/library_server/vault_builder/extractors/base.py`

All extractors must subclass `BaseExtractor` and implement its four abstract methods.

### Class Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Unique identifier used in config and registry (e.g., `"specs"`, `"jira"`) |
| `display_name` | `str` | Human-readable name for reports and manifest |
| `source_description` | `str` | One-line description of what this extractor pulls from |
| `output_subdir` | `str` | Subdirectory under `raw/` where files are written. Must be unique across all extractors. |

### Constructor

```python
def __init__(self, config: dict[str, Any]) -> None:
```

Receives the source-specific config dict from `vault_builder.sources.<name>` in `library-config.yaml`. Store as `self.config`.

### Properties

| Property | Returns | Description |
|----------|---------|-------------|
| `is_enabled` | `bool` | Returns `self.config.get("enabled", True)`. Disabled extractors are skipped by the orchestrator. |

### Abstract Methods

#### `async def survey(self) -> SurveyResult`

Inspect the source without writing anything. Report file count, total size, structure summary, health status, and last modification time.

#### `async def preview(self) -> PreviewResult`

Dry run. Report which files would be created, estimated token count, and any warnings (e.g., missing permissions, stale data).

#### `async def extract(self, output_dir: Path) -> ExtractResult`

Extract data from the source and write structured Markdown files to `output_dir`. Use `OutputWriter` for consistent frontmatter. Return the list of files written, files skipped, any errors, duration, and success status.

#### `def validate_config(self) -> list[str]`

Validate the extractor's config dict. Return an empty list if valid, or a list of human-readable error strings.

---

## Type Contracts

**Module:** `src/library_server/vault_builder/types.py`

### VaultState (Enum)

Detected state of the target vault directory before a build:

| Value | Meaning |
|-------|---------|
| `NEW_VAULT` | Directory does not exist or is empty |
| `EXISTING_VAULT_NO_RAW` | Vault directory exists but has no `raw/` subdirectory |
| `EXISTING_VAULT_WITH_RAW` | Vault with existing `raw/` content |
| `PREVIOUS_BUILD` | Contains a `_build-manifest.md` from a prior run |
| `NON_VAULT_DIRECTORY` | Directory exists but is not a vault |

### SurveyResult

```python
@dataclass
class SurveyResult:
    source_name: str           # Extractor name
    file_count: int            # Number of files in source
    total_size_bytes: int      # Total size across all files
    structure_summary: str     # Human-readable structure description
    health: str                # "healthy", "stale", "unknown"
    last_modified: datetime | None  # Most recent file modification
```

### PreviewResult

```python
@dataclass
class PreviewResult:
    source_name: str           # Extractor name
    files_to_create: list[str] # Relative paths of files that would be written
    estimated_tokens: int      # Rough token count for all output
    warnings: list[str]        # Non-fatal issues (e.g., missing optional config)
```

### ExtractResult

```python
@dataclass
class ExtractResult:
    source_name: str           # Extractor name
    files_written: list[str]   # Paths of files actually written
    files_skipped: list[str]   # Paths skipped (e.g., unchanged, errors)
    errors: list[str]          # Error messages for failed files
    duration_seconds: float    # Wall-clock time for this extractor
    success: bool              # True if extraction completed without critical errors
```

### BuildResult

```python
@dataclass
class BuildResult:
    status: str                           # "completed", "completed_with_warnings", "failed"
    extract_results: list[ExtractResult]  # Per-extractor results
    graphify_status: str                  # "completed", "failed", "skipped"
    graphify_message: str                 # Detail message from Graphify runner
    duration_seconds: float               # Total build duration
    manifest_path: str                    # Path to _build-manifest.md
    config_warnings: dict[str, list[str]] # Per-extractor config warnings
```

Property `any_succeeded` returns `True` if at least one extractor succeeded.

---

## OutputWriter

**Module:** `src/library_server/vault_builder/output.py`

Writes structured Markdown files with YAML frontmatter to the vault's `raw/` directory.

### Constructor

```python
OutputWriter(base_dir: Path)
```

`base_dir` is the root of the `raw/` output directory.

### write_file()

```python
def write_file(
    self,
    subdir: str,          # Subdirectory under base_dir (e.g., "specs", "jira")
    filename: str,        # File name (e.g., "GLOSSARY.md", "COS-123.md")
    title: str,           # Document title
    source_type: str,     # Source classification (e.g., "spec", "issue", "memory")
    source_path: str,     # Original source location (file path or URL)
    extractor: str,       # Extractor name that produced this file
    trust: float,         # Trust score 0.0-1.0 (1.0 = human-authored canonical)
    domain: str,          # Domain classification (e.g., "core", "security", "infra")
    tags: list[str],      # Searchable tags
    related: list[str],   # Related document references
    body: str,            # Markdown body content
) -> Path:               # Returns path to the written file
```

### YAML Frontmatter Schema

Every file written by `OutputWriter` has this frontmatter:

```yaml
---
title: "Document Title"
source_type: spec
source_path: /path/to/original/file.md
extracted_at: "2026-04-16T12:00:00+00:00"
extractor: specs
trust: 1.0
domain: core
tags:
  - glossary
  - terminology
related:
  - DOMAINS.md
---
```

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Document title |
| `source_type` | string | Classification: `spec`, `issue`, `memory`, `session`, `notebook`, `wiki` |
| `source_path` | string | Original source location |
| `extracted_at` | ISO 8601 | UTC timestamp of extraction |
| `extractor` | string | Name of the extractor that produced this file |
| `trust` | float | 0.0 (AI-generated) to 1.0 (human-authored canonical) |
| `domain` | string | Domain tag for routing and categorization |
| `tags` | list[str] | Searchable tags |
| `related` | list[str] | Cross-references to related documents |

### write_manifest()

```python
def write_manifest(
    self,
    results: list[ExtractResult],
    total_duration: float,
) -> Path:
```

Writes `_build-manifest.md` summarizing the build. Includes a table of per-extractor status, file counts, and durations, plus an errors section if any extractor failed.

---

## PluginRegistry

**Module:** `src/library_server/vault_builder/registry.py`

Thread-safe registry for extractor instances.

### Methods

| Method | Description |
|--------|-------------|
| `register(extractor)` | Register an extractor. Raises `ValueError` on duplicate `name` or duplicate `output_subdir`. |
| `get(name) -> BaseExtractor \| None` | Look up an extractor by name. |
| `list_extractors() -> list[str]` | List all registered extractor names. |
| `get_enabled() -> list[BaseExtractor]` | Return all extractors where `is_enabled` is `True`. |
| `get_by_names(names) -> list[BaseExtractor]` | Look up multiple extractors by name. Silently ignores unknown names. |
| `validate_all() -> dict[str, list[str]]` | Run `validate_config()` on all enabled extractors. Returns a dict of extractor name to error list (only extractors with errors are included). |

---

## Configuration

**Module:** `src/library_server/vault_builder/config.py`

### VaultBuilderConfig

```python
@dataclass
class VaultBuilderConfig:
    mode: str = "create"                # "create" or "enrich"
    output_vault: Path | None = None    # Required: path to output vault
    parallel: bool = True               # Run extractors in parallel
    max_parallel_extractors: int = 8    # Concurrency limit
    fail_fast: bool = False             # Stop on first extractor failure
    sources: dict[str, dict[str, Any]]  # Per-extractor config dicts
    graphify: dict[str, Any]            # Graphify post-processing config
    axon: dict[str, Any]                # Axon bridge config
    preserve: list[str]                 # Paths to preserve across builds
```

### YAML Schema

```yaml
vault_builder:
  mode: create              # "create" (fresh) or "enrich" (additive)
  output_vault: /path/to/vault
  parallel: true
  max_parallel_extractors: 8
  fail_fast: false
  preserve:
    - wiki/              # Directories to keep across rebuilds

  sources:
    specs:
      enabled: true
      source_path: /path/to/specs
    claude_memory:
      enabled: true
      source_path: ~/.claude/projects/.../memory
    session_context:
      enabled: true
      source_path: ~/.library/sessions
    notebooklm:
      enabled: true
      source_path: /path/to/notebooks
    obsidian_vault:
      enabled: true
      source_path: /path/to/obsidian/vault
    jira:
      enabled: true
      project_keys:
        - COS
        - PLT
    axon_bridge:
      enabled: true
      command: axon

  graphify:
    enabled: true
    command: graphify
    mode: deep
    auto_rebuild: true

  axon:
    enabled: false
    command: axon
```

### Validation

`validate_vault_builder_config()` checks:

- `mode` is `"create"` or `"enrich"`
- `output_vault` is set and its parent directory exists
- If Axon is enabled, its CLI binary is on `$PATH`
- If Graphify is enabled, its CLI binary is on `$PATH`
- For each enabled source, `source_path` exists (if specified)

---

## Built-in Extractors

Registered in `server.py` lines 489-530:

| Name | Class | Output Subdir | Description |
|------|-------|---------------|-------------|
| `specs` | `SpecsExtractor` | `specs` | Canonical spec files from the Reading Room |
| `claude_memory` | `ClaudeMemoryExtractor` | `claude_memory` | Claude Code auto-memory entries |
| `session_context` | `SessionContextExtractor` | `session_context` | Session context files from `~/.library/sessions` |
| `notebooklm` | `NotebookLMExtractor` | `notebooklm` | Google NotebookLM exports |
| `obsidian_vault` | `ObsidianVaultExtractor` | `obsidian_vault` | Obsidian vault Markdown files |
| `jira` | `JiraExtractor` | `jira` | Jira issues via REST API |
| `axon_bridge` | `AxonBridgeExtractor` | `axon_bridge` | Axon CLI knowledge bridge |

---

## How to Add a New Extractor

### Step 1: Create the extractor module

Create `src/library_server/vault_builder/extractors/my_source.py`:

```python
"""MySource extractor for the vault builder."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from library_server.vault_builder.extractors.base import BaseExtractor
from library_server.vault_builder.output import OutputWriter
from library_server.vault_builder.types import (
    ExtractResult,
    PreviewResult,
    SurveyResult,
)


class MySourceExtractor(BaseExtractor):
    name = "my_source"
    display_name = "My Source"
    source_description = "Pulls data from My Source system"
    output_subdir = "my_source"  # Must be unique across all extractors

    async def survey(self) -> SurveyResult:
        source_path = Path(self.config.get("source_path", ""))
        # Inspect the source, count files, check health
        return SurveyResult(
            source_name=self.name,
            file_count=0,
            total_size_bytes=0,
            structure_summary="Description of source structure",
            health="healthy",
        )

    async def preview(self) -> PreviewResult:
        # Determine what would be extracted without writing
        return PreviewResult(
            source_name=self.name,
            files_to_create=["my_source/file1.md", "my_source/file2.md"],
            estimated_tokens=5000,
            warnings=[],
        )

    async def extract(self, output_dir: Path) -> ExtractResult:
        writer = OutputWriter(output_dir)
        files_written = []
        errors = []

        # Extract and write each file
        path = writer.write_file(
            subdir=self.output_subdir,
            filename="file1.md",
            title="My Document",
            source_type="my_type",
            source_path="/original/path",
            extractor=self.name,
            trust=0.8,
            domain="core",
            tags=["my-tag"],
            related=["other-doc.md"],
            body="# Content\n\nMarkdown body here.",
        )
        files_written.append(str(path))

        return ExtractResult(
            source_name=self.name,
            files_written=files_written,
            errors=errors,
            success=len(errors) == 0,
        )

    def validate_config(self) -> list[str]:
        errors = []
        source_path = self.config.get("source_path")
        if source_path and not Path(source_path).exists():
            errors.append(f"source_path does not exist: {source_path}")
        return errors
```

### Step 2: Register the extractor

In `src/library_server/server.py`, add your extractor to the `_get_vault_orchestrator()` function:

```python
from library_server.vault_builder.extractors.my_source import MySourceExtractor

extractor_map = {
    # ... existing extractors ...
    "my_source": MySourceExtractor,
}
```

### Step 3: Add configuration

In your `library-config.yaml`:

```yaml
vault_builder:
  sources:
    my_source:
      enabled: true
      source_path: /path/to/my/source
```

### Step 4: Write tests

Create `tests/vault_builder/test_my_source_extractor.py` covering:

- `survey()` returns correct file count and health
- `preview()` lists expected output files
- `extract()` writes files with correct frontmatter
- `validate_config()` catches missing/invalid paths
- Edge cases: empty source, permission errors, malformed data

### Step 5: Run the build

```bash
# Survey to check source health
library_vault_builder_survey

# Preview to see what would be extracted
library_vault_builder_preview --extractors my_source

# Extract
library_vault_builder_extract --extractors my_source

# Full build (all enabled extractors + Graphify)
library_vault_builder_build
```
