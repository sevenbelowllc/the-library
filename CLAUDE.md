# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -e ".[dev]"        # dev setup (Python 3.10–3.12)

pytest                          # full suite; coverage flags come from pyproject addopts
pytest tests/test_config.py                     # single file
pytest tests/test_config.py::test_name -v       # single test
pytest --ignore=tests/vault_builder/integration --ignore=tests/test_jira_integration.py

ruff check .                    # lint (CI gate)
mypy                            # types; pyproject pins files = src/library_server

bin/library-coverage-ratchet            # re-runs tests, fails on any drop vs coverage-baseline.txt
bin/library-coverage-ratchet --bump     # raise the baseline after an intentional improvement
bin/library-mutation-smoke              # scoped mutation testing over src/library_server/pm/
bin/library-mutation-smoke --list       # candidate mutants without running them
bin/library-pm-pollution-scan           # dry-run scan for stale INTEGRATION-TEST/DELETE-ME/ZZT* artefacts
```

CI (`.github/workflows/test.yml`) runs four jobs: `test` (3.10/3.11/3.12, with the coverage ratchet as a follow-on step), `lint` (ruff), `typecheck` (mypy), and `mutation-smoke`. `coverage-baseline.txt` is the single source of truth for the coverage floor — there is no static threshold in pyproject.

`tests/test_jira_integration.py` hits live Jira and self-skips unless `ATLASSIAN_EMAIL` and `JIRA_API_TOKEN` are set. Any test that creates external state must register teardown in a `try/finally` `yield` fixture — `jira_cleanup` in that file is the canonical pattern.

## Architecture

One package, `src/library_server/`, ships three independent surfaces:

1. **MCP server** (`server.py`, FastMCP over stdio) — the `library-server` entry point.
2. **CLI** (`cli.py`) — the `library` entry point: `init`, `validate`, `doctor`, plus the server as default subcommand.
3. **Zero-token hooks** (`hooks/scripts/*.py`) — standalone processes Claude Code invokes on lifecycle events. They read a JSON payload on stdin and print `hookSpecificOutput` JSON on stdout. They must never consume LLM tokens, and must degrade quietly (missing files warn to stderr, never crash the session).

`server.py` is deliberately thin: every `@mcp.tool` function does a **lazy local import** of its implementation module. Keep it that way — it keeps startup fast and optional dependencies (graphify) genuinely optional.

### Config

`config.py` loads `library-config.yaml` from the CWD. Results are cached keyed on `(mtime_ns, size)` and deep-copied in and out, so callers that mutate a `LibraryConfig` without saving cannot poison the cache. `library-config.example.yaml` documents every section.

Two invariants live here rather than in callers:
- `resolve_checkpoint_dir()` — checkpoints MUST resolve under `reading_room.path`. An explicit `checkpoints.path` outside it raises; there is no silent fallback to CWD (that was the 0.3.1 bug).
- `resolve_standards()` — malformed `standards` entries raise instead of being skipped.

### PM layer (`pm/`)

`adapter.py` defines the `PMAdapter` ABC; `jira.py` and `linear.py` implement it, selected by `pm.provider`. `jira_client.py` is a direct Jira REST v3 client (httpx, connection reuse, retry/backoff) — not an MCP passthrough. `md_to_adf.py` converts Markdown descriptions to Atlassian Document Format.

- Workflow state names are **configuration**, not constants: `pm.workflow.{states,in_progress,in_review,closed}` feed the adapters' classification. Don't hardcode "Done"/"In Progress".
- `TransitionNotAvailableError` exists because silently accepting an unreachable status transition was a real audit failure. Errors here surface as structured error dicts from the tool layer; never restore a silent no-op.
- `server._get_pm_adapter()` caches the adapter keyed on `repr(pm_config)` so the HTTP pool survives across tool calls.

### Vault Builder (`vault_builder/`)

An ETL pipeline: `PluginRegistry` holds `BaseExtractor` subclasses (`extractors/`), `VaultBuildOrchestrator` runs their `extract()` coroutines concurrently via `asyncio.gather(..., return_exceptions=True)` — an extractor raising becomes a failed `ExtractResult`, never a failed build. `detect_vault_state()` + `check_safety_gate()` block a `create`-mode build over an existing vault unless `force=True`. `graphify_runner.py` optionally builds the knowledge graph afterward; `output.py` writes `raw/_build-manifest.md`.

Every extractor implements `survey()` / `preview()` / `extract()` / `validate_config()`.

### MMU (`hooks/`, `memory/`, `state/`)

The Memory Management Unit keeps ~800 tokens of context alive across sessions. `session_start` renders PROJECT-STATE.md + SESSION.md + standards under a 4000-char budget; `prompt_scan` matches the prompt against `vault/domains/*.md` manifests, injects on first hit, dedups on repeats, and appends to a routing journal; `learning.py` analyzes that journal for keyword accuracy and drift; `stop_capture` heartbeats SESSION.md so a crash loses at most one turn.

Runtime state lives outside the repo in `~/.library/` (`sessions/`, `state/`, `routing.jsonl`, `learning/`).

`redaction.py` is the single write-time chokepoint for secrets — apply it before anything reaches transcripts, checkpoints, SESSION.md, the vault, or PM descriptions. Never redact at read time.

### Skills and plugin packaging

`skills/<name>/SKILL.md` (frontmatter `name` + `description`) are the 12 Claude Code skills. `.claude-plugin/{plugin,marketplace}.json` package the repo for `claude plugins install`.

## Conventions and gotchas

- `from __future__ import annotations` at the top of every module.
- **MCP tool names use underscores** — `library_pm_create_task`, as registered in `server.py`. CHANGELOG, CONTRIBUTING, and parts of `docs/` describe a `library:<module>:<action>` colon form that does not match the code; `server.py` is authoritative (README flags this too). Skill names (`library:config`) and CLI subcommands (`library init`) do use the colon/space forms.
- No hardcoded paths — read from config or the `~/.library/` convention.
- Adding an MCP tool: decorate in `server.py` with a lazy import, add tests, update the tool table in `README.md`.
- Adding an extractor: subclass `BaseExtractor`, add it to `extractor_map` in `server._get_vault_orchestrator()`, and give it a `vault_builder.sources.<name>` config block (an absent block means the extractor is not registered at all).
- Hook changes are two-sided: the real logic lives in `hooks/scripts/<name>.py`, but `cli.py::_ensure_hook_scripts` generates the thin `.claude/hooks/` wrappers that supply default stdin fields. Change a required payload field in one and update the other.
- The package version comes from installed metadata (`importlib.metadata`), but `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, and `skills/plugin.json` carry hand-maintained version and tool-count strings that already drift from `pyproject.toml`. Update them deliberately when bumping.
