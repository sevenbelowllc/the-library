# Changelog

All notable changes to The Library are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/). Versions follow [Semantic Versioning](https://semver.org/).

## [0.4.0] - 2026-08-08

### Changed
- **BREAKING (config):** the `axon_bridge` vault-builder source is replaced by `code_repo`, powered by graphify's in-process Python API instead of the `axon` CLI. Rename `vault_builder.sources.axon_bridge` to `sources.code_repo` in library-config.yaml (`validate` reports a targeted error for the old key). Same vault artifacts: `repos/<name>/repo-summary.md` + `repos/<name>/communities/*.md`, now with cohesion scores and ~25-language support including Terraform.
- graphifyy dependency floor raised to 0.9.32, pinned by a real-API (unmocked) compatibility test.
- `library_vault_builder_config` no longer returns `axon_enabled`.

### Removed
- `axon_bridge` extractor, the `vault_builder.axon` config block, and the axon CLI install prerequisite — no system CLI needed for code analysis.

## [0.3.2] - 2026-08-02

### Added
- `library_pm_autodetect_workflow` MCP tool — derives a `pm.workflow` block from a live Jira project's statuses (wires the previously uncalled `autodetect_jira_workflow`). Tool count is now 37.
- `library_checkpoint_write` accepts `changes`, `open_decisions` ("question|options|impact"), and `memory_updates` ("file|type|content") — the renderer supported these sections but the tool could never populate them.
- `library doctor` now repairs hook registration in `.claude/settings.json` and rewrites hook wrapper scripts — everything `library validate` flags, `doctor` can fix.
- Vault builder honors `parallel`, `max_parallel_extractors`, and `fail_fast`.
- `pm.workflow.blocked` is validated and documented.
- `library-config.example.yaml` documents the `vault_builder` section.

### Fixed
- `library init` wrote SESSION.md/PROJECT-STATE.md in a bullet format the state parsers could not read; the first session-end round-trip blanked project/focus/task. Bootstrap now uses the canonical renderers.
- `library_memory_health`/`library_memory_learn` read `~/.library/learning/routing-journal.jsonl` while hooks write `~/.library/routing.jsonl`; both now use the shared `routing_journal_path()` helper.
- PreCompact transcript archival and SessionEnd SESSION.md archival bypassed redaction (raw file copies into the vault); both now redact at write time. `session_end` stderr uses `redact_exception`.
- Linear `update_task(status=...)` silently ignored the status; it now raises `TransitionNotAvailableError` (real Linear transitions remain unimplemented).
- Jira vault-builder extractor dumped ADF description/comment dicts as Python reprs; ADF is now flattened to text via the shared `pm/adf.py` helper.
- `library_vault_builder_extract` bypassed the create-mode safety gate; it now applies the same gate as full builds and accepts `force`.
- `library_pm_create_project` dropped its `project_type_key` parameter; it is now threaded through to Jira.
- `aggregate_memories` claimed `applied: true` without performing any merge; it now always reports `applied: false` (analysis only).

### Changed
- Removed the inert `vault_builder.preserve` config key (deferred to the incrementality push) and the out-of-domain `bin/library-clerk-pollution-scan` tooling.
- Docs: added `library_pm_get_issue` to the MCP tool reference and Linear capability docs; corrected CONTRIBUTING's stale colon-form tool naming; corrected the test plan's stale coverage-floor description (the ratchet against `coverage-baseline.txt` is the only floor).
- CI: capped `mcp[cli]<2` (2.x drops `mcp.server.fastmcp`) and pinned ruff to `>=0.6,<0.16` in dev deps and the lint job — unpinned installs had let CI drift red since April independent of code changes.

### Performance (previously unreleased, mid-2026 merges)
- JiraClient: HTTP connection reuse plus retry/backoff on 429/502/503/504 honoring `Retry-After`; config loading cached on `(mtime_ns, size)`.
- Stop hook emits `systemMessage` instead of `hookSpecificOutput` (Stop event schema fix).

## [0.3.1] - 2026-04-17

### Added
- **Reading Room boundary for checkpoints (hard rule)**: `resolve_checkpoint_dir()` enforces that checkpoint files always land under `reading_room.path`. If `checkpoints.path` is unset, defaults to `<reading_room.path>/checkpoints`; if set, validated to resolve under the Reading Room.
- **Topic slugification**: `library_checkpoint_write` sanitizes topics to kebab-case so filenames are always shell-safe (no spaces, em dashes, or mixed case).

### Changed
- `library_checkpoint_write` and `library_checkpoint_list` now require `reading_room.path` to be configured. They return a structured error instead of silently falling back to `./checkpoints` relative to the MCP server's CWD.

### Fixed
- Root cause for orphaned checkpoint files appearing at the MCP server's CWD instead of the Reading Room.

## [0.3.0] - 2026-04-12

### Added
- **CLI bootstrap**: `library init` — one-command project setup (config, vault, hooks, domains, state files, validation)
- **CLI diagnostics**: `library validate` (19-point health check) and `library doctor` (auto-fix)
- **Vault Builder**: parallel extraction pipeline with 7 source extractors (specs, Obsidian, Jira, Claude memory, session context, NotebookLM, Axon Bridge)
- **Memory Management Unit (MMU)**: 6 lifecycle hooks for session continuity, domain-aware context injection, keyword auto-learning
- **Claude Code plugin packaging**: marketplace.json, plugin.json for `claude plugins install`
- **Unified naming**: all MCP tools use `library:<module>:<action>` convention

### Changed
- CLI binary renamed from `library-server` to `library`
- MCP tool names changed from `library_x_y` to `library:x:y` (27 tools)
- Entry point moved from `server:main` to `cli:main` (server runs as default subcommand)

### Fixed
- Version consistency: `__init__.py`, `pyproject.toml`, and `plugin.json` all report `0.3.0`
- Removed stale build artifacts from git tracking
- Removed user-specific config from git

## [0.2.0] - 2026-04-11

### Added
- Memory tools: `library:memory:health`, `library:memory:learn`
- Graph tools: `library:graph:rebuild`, `library:graph:query`, `library:graph:path`
- Hook scripts: session_start, prompt_scan, stop_capture, pre_compact, session_end, status_line
- Domain seeder: auto-creates domain manifests from CLAUDE.md patterns
- Hook installer: generates Claude Code settings.json hook configuration

### Changed
- Expanded from 20 to 27 MCP tools

## [0.1.0] - 2026-04-10

### Added
- Initial MCP server with FastMCP
- Core tools: config (get/set), checkpoint (write/read/list), memory (scan/aggregate/prune), vault (init/validate/parse/ingest), PM (create_task/create_epic/sync/update/query)
- 11 Claude Code skills: config, ingest, compile, query, memory, sync, triage, plan, audit, review, checkpoint
- PM adapters: Jira (via Atlassian MCP), Linear (via httpx)
- Configuration via `library-config.yaml`
- 456 tests, 81% code coverage

[0.3.0]: https://github.com/sevenbelowllc/the-library/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/sevenbelowllc/the-library/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/sevenbelowllc/the-library/releases/tag/v0.1.0
