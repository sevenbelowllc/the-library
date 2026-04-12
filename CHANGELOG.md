# Changelog

All notable changes to The Library are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/). Versions follow [Semantic Versioning](https://semver.org/).

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
