# Stabilization & Reconnect Pass (v0.3.2) — Design

**Date:** 2026-08-02
**Status:** Approved
**Branch:** `chore/stabilization-0.3.2`

## Context

A five-agent analysis of the codebase (MCP server/CLI/config, PM layer, vault builder,
MMU, docs/roadmap) found that the architecture is largely built and well-tested
(~979 tests, 94.35% coverage baseline, no TODO markers), but several components that
work in isolation are disconnected from each other, seven confirmed bugs exist, and
the docs/packaging drift from the code. This pass fixes the bugs, makes every
documented config key honest (works or is removed), reconnects built-but-unwired
code, and ships as v0.3.2.

Out of scope, each deferred to its own future push:

- Learning-loop closure (routing-outcome writer, keyword graduation/HITL apply step,
  `decision_capture` wiring, real `aggregate_memories` merging).
- Linear adapter parity (the 7–8 `NotImplementedError` methods, real status
  transitions, query filtering).
- Vault-builder incrementality (per-file skip, stale-file cleanup, `preserve`).
- Git-history scrub of the leaked checkpoint files (`git filter-repo`/BFG) — operator
  runs this; it rewrites shared history on a public repo.

## Pre-work already done on this branch

- Deleted `checkpoints/2026-04-15-...` and `checkpoints/2026-04-16-...` — committed
  session checkpoints from an unrelated project (real names, third-party auth notes)
  in a public repo. Residue of the pre-0.3.1 checkpoint-path bug.
- Added `checkpoints/` to `.gitignore`.

## Track 1 — Bug fixes

Each fix lands with a regression test that fails before and passes after.

1. **Init data-loss (SESSION.md / PROJECT-STATE.md format mismatch).**
   `cli.py::_create_session_md` and `_create_project_state` emit `- task: ...` plain
   bullets, but `state/session_state.py` / `state/project_state.py` parse
   `**Task:** ...` bold fields. First `session_end` round-trip therefore blanks the
   user's project/focus/task. Fix the CLI templates to emit the bold-field format.
   Regression test: round-trip CLI-generated files through
   `parse_session_state`/`parse_project_state`, assert no populated field parses empty.

2. **Routing-journal path mismatch.** Hooks write `~/.library/routing.jsonl`
   (cli init/doctor create it there); `server.py` `library_memory_health` /
   `library_memory_learn` read `~/.library/learning/routing-journal.jsonl` — a file
   nothing writes. Fix: server reads the hooks' path, derived from one shared helper
   used by both sides so they cannot diverge again. Rewrite the `test_server.py` test
   that currently writes directly to the wrong path.

3. **Redaction bypasses on archival.** `pre_compact.py` raw-copies the full
   transcript JSONL to the vault; `session_end.py` raw-copies SESSION.md and logs
   unredacted exception text. Fix: transcript archived line-by-line through
   `redact()`; SESSION.md content redacted before archival; `session_end.py` stderr
   path uses `redact_exception`. Tests plant a fake secret and assert it never
   reaches the vault copy.

4. **Linear silent status drop.** `LinearAdapter.update_task(status=...)` ignores the
   status argument — the exact silent-no-op class `TransitionNotAvailableError`
   exists to prevent. Fix: when `status` is passed, raise
   `TransitionNotAvailableError` (current status fetched, empty available-transitions
   list) so the tool layer returns its structured error dict. Real Linear
   transitions remain deferred to the parity push.

5. **Jira ADF description dump in vault-builder extractor.**
   `extractors/jira.py` does `str(description)` — a Python-repr blob when Jira v3
   returns rich-formatted descriptions as ADF dicts. Fix: extract the ADF→text logic
   already in `JiraAdapter.get_issue` into a shared helper (`pm/` module) and use it
   in the extractor when the description is a dict. Test with a realistic ADF
   payload fixture.

6. **Safety-gate bypass in `library_vault_builder_extract`.** The single-extractor
   tool calls `orch.build()` without `detect_vault_state`/`check_safety_gate`,
   allowing a create-mode build to silently overwrite an existing vault. Fix: run
   the same gate as `library_vault_builder_build`; add a `force` parameter.

7. **Dropped `project_type_key`.** `library_pm_create_project` accepts it but never
   forwards it; every project is created as `"software"`. Fix: add the parameter to
   `PMAdapter.create_project` and `JiraAdapter.create_project`, thread through to
   `JiraClient.create_project`.

## Track 2 — Release hygiene

- **CHANGELOG.md**: retroactive entries for the two unrecorded merges
  (`3e4a385` perf: JiraClient connection reuse/retry + config cache; `b1377e3`
  stabilization pass), plus a `[0.3.2]` entry for this pass.
- **Version bump**: `pyproject.toml` → 0.3.2.
- **Hand-maintained packaging sync**: `.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json`, `skills/plugin.json` → version 0.3.2, correct
  tool count (37 after the new autodetect tool) and "12 skills".
- **Docs drift**:
  - `docs/reference/mcp-tools.md`: add `library_pm_get_issue` (quick-reference row +
    full entry), correct the tool total, add the new autodetect tool.
  - `docs/guides/pm-integration.md`: add a "Get issue" capability row.
  - `docs/setup/linear-setup.md`: list `get_issue` as the 8th unsupported method.
  - `library-config.example.yaml`: add the missing `vault_builder:` section
    (reflecting post-Track-3 reality: no `preserve`, no `cloud_id`/`auth: mcp`).
  - `CONTRIBUTING.md`: correct the stale `library:<module>:<action>` colon-form tool
    naming to the underscore form `server.py` actually uses.
  - `docs/reference/test-plan.md`: correct the "88% floor via pytest-cov in
    pyproject" claims to the ratchet mechanism (`coverage-baseline.txt` +
    `bin/library-coverage-ratchet`).
  - `docs/reference/vault-builder-api.md`: fix the stale `server.py` line reference
    and remove claims for config keys deleted in Track 3.
- **Cosmetic**: remove the `and not True` dead conditional in `cli.py`
  (hook-wrapper overwrite path).

## Track 3 — Reconnects

Built-but-unwired code either gets a production caller or is removed.

- **`autodetect_jira_workflow` entry point**: new MCP tool
  `library_pm_autodetect_workflow(project_key)` (lazy import, per convention)
  returning a proposed `pm.workflow` block from live Jira project statuses; applied
  by the user via existing `library_config_set`. README tool table + docs updated.
  Tool count becomes 37.
- **Vault-builder config keys become honest**:
  - `parallel` / `max_parallel_extractors`: implemented — orchestrator wraps
    extractor coroutines in an `asyncio.Semaphore` (`parallel: false` ⇒ limit 1).
  - `fail_fast`: implemented — stop dispatching further extractors after the first
    failed `ExtractResult`; already-running extractors finish and are reported.
  - `preserve`: removed from `VaultBuilderConfig` and docs (meaningless without
    incremental builds; revisit in the incrementality push).
  - Axon `command` override: `validate_vault_builder_config`'s configured command is
    passed into `AxonBridgeExtractor` and used for all subprocess calls instead of
    the hardcoded `"axon"`.
  - Jira `cloud_id` / `auth: mcp` doc claims: removed (feature does not exist; auth
    is env-var based).
  - Graphify `flags` / `auto_rebuild` / `incremental` doc claims: removed.
    `GraphifyRunner.is_available()` (dead in production, checks a CLI that is never
    shelled out to) deleted along with its tests.
  - Dead discarded `any(...)` expressions in `orchestrator.py` (~lines 126–131):
    deleted.
- **`pm.workflow.blocked`**: added to `validate_config`'s consistency check and to
  documentation (it is load-bearing today but unvalidated/undocumented).
  `in_progress`/`in_review` keys stay — the autodetect tool emits them — but richer
  5-bucket `sync_state` classification is explicitly deferred.
- **`library_checkpoint_write`**: expose the three renderable-but-unreachable
  `CheckpointData` fields (`changes`, `open_decisions`, `memory_updates`) as
  optional tool parameters.
- **`doctor` repairs hooks**: `_cmd_doctor` also runs `_install_hooks` +
  `_ensure_hook_scripts`, so everything `validate` can flag, `doctor` can fix.
- **`aggregate_memories` honesty**: stop reporting `applied: true` when no merge is
  ever performed; return suggestions only (real merging deferred to the
  learning-loop push).
- **`bin/library-clerk-pollution-scan`** and `tests/test_clerk_pollution_scan.py`:
  removed — out-of-domain tooling from a sibling project, referenced by no doc or
  workflow in this repo.

## Testing & verification

- New regression tests per Track 1 item; new unit tests for semaphore/fail-fast
  behavior, autodetect tool, checkpoint fields, doctor hook repair.
- Full suite: `pytest --ignore=tests/test_jira_integration.py` (live-Jira suite
  self-skips regardless), `bin/library-coverage-ratchet`, `ruff check .`, `mypy`.
- Final diff review for unintended changes before commit.

## Sequencing

1. Track 1 bugs (independent of each other, testable in isolation).
2. Track 3 reconnects (some touch the same files as Track 1 — orchestrator, cli).
3. Track 2 hygiene last (docs/CHANGELOG/versions describe the final state).
