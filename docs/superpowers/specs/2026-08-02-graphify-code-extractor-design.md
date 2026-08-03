# Graphify 0.9 Upgrade & Axon Retirement — Design

**Date:** 2026-08-02
**Status:** Approved (direction); executes as the push immediately after v0.3.2
**Branch (planned):** `feat/graphify-code-extractor`

## Context and decision

The `axon_bridge` extractor shells out to the `axon` CLI (axoniq) for source-code
analysis, but the-library consumes only three of its capabilities: repo indexing
(`axon analyze --no-embeddings`), community names/cohesion (one cypher query), and
community members (one cypher query), plus `axon status` counts. Everything
distinctive about axon — persistent Kuzu index, live cypher, embeddings/hybrid
search, MCP server, web UI — is unused here, and its parser surface is Python +
TypeScript only. The extractor's Terraform path never touches axon at all
(hand-rolled regex).

Graphify (already a declared dependency, used by `GraphifyRunner` and the
`library_graph_*` tools) covers all of it in-process as of 0.9.x:

| the-library needs | axon | graphify 0.9 |
|---|---|---|
| Symbol extraction | Python + TS only | ~25 languages incl. Terraform |
| Communities + cohesion | Kuzu + cypher | `cluster()` + `score_all()` |
| Named communities | yes | `label_communities_by_hub()` |
| Members per community | cypher | `cluster()` result maps community → nodes |
| Summary counts | `axon status` | node/edge/community counts from extraction |
| Stable communities across rebuilds | persistent index | `remap_communities_to_previous()` |

Additional forcing function: the axon CLI is currently broken in the dev
environment (typer/click import incompatibility), and `axon_bridge`'s health check
(`shutil.which("axon")`) cannot detect it — surveys report "connected" while every
extraction fails.

**Decision (2026-08-02):** retire axon from the-library. Replace `axon_bridge` with
a graphify-powered code extractor. Axon remains installed on the operator's machine
for any direct use (its MCP server, web UI, cypher) — that is out of this repo's
scope.

## Part 1 — Graphify dependency upgrade

- Bump pins: `graphifyy>=0.8.0` → `graphifyy>=0.9.32` in all three places in
  `pyproject.toml` (`graphify` extra, `all` extra, dev dependencies).
- `graphify_runner.py` imports nine `graphify.*` modules (`detect`, `extract`,
  `build`, `cluster`, `analyze`, `report`, `export`, `wiki`, `cache`); all nine
  still exist in 0.9.32. Verify call signatures against the installed 0.9.x
  (`extract`, `collect_files`, `build_from_json`, `cluster`, `score_all`,
  `god_nodes`, `surprising_connections`, `generate`, `to_json`, `to_html`,
  `to_wiki`, `check_semantic_cache`) and adapt where changed.
- Full `tests/vault_builder/` suite plus the graph-tool tests must pass against
  0.9.x before Part 2 begins.

## Part 2 — `code_repo` extractor (replaces `axon_bridge`)

New extractor `vault_builder/extractors/code_repo.py`, name `code_repo`, config
block `vault_builder.sources.code_repo`, output subdir `repos` (unchanged, so
existing vaults keep their layout).

- **Config**: same shape as `axon_bridge`'s — `repos: [{name, path, type?,
  language?}]`. `language` becomes optional metadata only (graphify detects
  languages itself); no `axon:` block.
- **survey()**: per-repo — path exists, `graphify.detect` file counts. Health
  reflects reality (no CLI-presence proxy; graphify is an importable dependency
  whose absence is reported as an error with the install hint).
- **preview()**: honest — lists `repo-summary.md` per repo (community filenames are
  not fabricated; the preview states communities are computed at extract time,
  fixing `axon_bridge`'s made-up preview).
- **extract()** per repo, all in-process:
  1. `collect_files(repo_path)` → `extract(files)` → nodes/edges (all languages,
     including Terraform via graphify's native extractor — the regex TF path is
     deleted).
  2. `build_from_json` → graph; `cluster(graph)` → communities;
     `label_communities_by_hub` → names; `score_all` → cohesion.
  3. Write the same vault artifacts as before, same frontmatter contract
     (`source_type: code_repo`, trust 1.0, domain via the existing
     `_DOMAIN_PATTERNS` heuristic, `related` links):
     - `repos/<name>/repo-summary.md` — counts now node/edge/community totals.
     - `repos/<name>/communities/<slug>.md` — community name, cohesion, member
       symbols with file paths.
- **Removal**: delete `extractors/axon_bridge.py` + its tests; remove
  `axon_bridge` from `server._get_vault_orchestrator()` `extractor_map` and
  register `code_repo`; remove the `axon:` config handling from
  `vault_builder/config.py` (`validate_vault_builder_config`'s axon CLI check
  included); purge axon from docs (`vault-builder.md`, `vault-builder-api.md`,
  example yaml section added in v0.3.2, README mentions) and from the pyproject
  comment block.
- **Migration**: a config still naming `sources.axon_bridge` gets a clear
  validation error naming the rename (`axon_bridge` → `code_repo`), not a silent
  ignore (an absent/unknown source block currently just never registers — that
  silence is exactly what we don't want for a renamed key).

## Acceptance test

Run the new extractor against a real repo previously extracted via axon (the
operator picks one, e.g. this repo itself) and compare community groupings
side-by-side with the old axon output for sanity — this replaces a separate
graphify-vs-axon spike. Automated tests mock graphify's API at the same boundary
the old tests mocked the axon CLI, mirroring `test_axon_bridge.py`'s "mocks
reflect the REAL output format" discipline against real 0.9.x return shapes.

## Testing & verification

- Unit tests: survey/preview/extract/validate_config for `code_repo` (happy path,
  graphify-missing path, empty repo, multi-repo, Terraform repo, slug collisions).
- Orchestrator integration: `code_repo` registered and buildable end-to-end.
- Full suite + coverage ratchet + ruff + mypy.

## Out of scope

- Any change to axon on the operator's machine.
- Exposing graphify's per-repo code graph via new MCP query tools (the existing
  `library_graph_*` tools remain the query surface).
- Vault-builder incrementality (`remap_communities_to_previous` noted as the hook
  for stable community naming when that push happens).
