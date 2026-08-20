# Graphify 0.9 Upgrade & Axon Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the axon-CLI-based `axon_bridge` extractor with an in-process graphify-powered `code_repo` extractor and remove every axon touchpoint.

**Architecture:** Upgrade the graphify pin first and prove API compatibility with a real (unmocked) end-to-end test; then build `code_repo` producing the same vault artifacts (`repos/<name>/repo-summary.md` + `repos/<name>/communities/<slug>.md`, same frontmatter contract) from graphify's `collect_files → extract → build_from_json → cluster/label/score` pipeline; then swap the wiring with a loud migration error for old configs; then delete axon code and purge docs. Ships as v0.4.0 (extractor rename is a config-breaking change).

**Tech Stack:** Python 3.10–3.12, graphifyy 0.9.32 (Python API, no CLI), pytest, networkx (transitively via graphify).

**Spec:** `docs/superpowers/specs/2026-08-02-graphify-code-extractor-design.md`

## Global Constraints

- Branch: create `feat/graphify-code-extractor` off current `main` before Task 1.
- Every module starts with `from __future__ import annotations`.
- Commits end with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- graphify is an OPTIONAL dependency — the new extractor must import it under `try/except ImportError` (same pattern as `vault_builder/graphify_runner.py:23-46`) and degrade with the install hint `"pip install 'the-library[graphify]'"`; never crash at import time.
- Vault contract is frozen: output subdir `repos`, `OutputWriter.write_file(...)` frontmatter fields (`title, source_type="code_repo", source_path, extractor, trust=1.0, domain, tags, related, body`), domain heuristic via the `_DOMAIN_PATTERNS` regex list copied verbatim from `axon_bridge.py:16-26`.
- Graphify 0.9.32 API (verified against the wheel — use these exact signatures):
  - `graphify.extract.collect_files(target: Path, *, follow_symlinks=False, root=None) -> list[Path]`
  - `graphify.extract.extract(paths: list[Path], cache_root=None, *, root=None, parallel=True, max_workers=None) -> dict` (keys `nodes`, `edges`; node dicts carry `id`, `label`, `source_file`)
  - `graphify.build.build_from_json(extraction: dict, *, directed=False, root=None) -> nx.Graph` (node attrs preserve `label`, `source_file`)
  - `graphify.cluster.cluster(G, resolution=1.0, exclude_hubs_percentile=None) -> dict[int, list[str]]`
  - `graphify.cluster.label_communities_by_hub(G, communities) -> dict[int, str]`
  - `graphify.cluster.score_all(G, communities) -> dict[int, float]`
- Do not touch `graphify_runner.py`'s `build_from_vault` behavior (the frontmatter path) beyond what Task 1's compat check forces.
- Full verification gate at the end: `pytest --ignore=tests/test_jira_integration.py`, `bin/library-coverage-ratchet`, `ruff check .`, `mypy`, `bin/library-mutation-smoke`.

---

### Task 1: Bump graphify pin to 0.9.32 and prove API compatibility with a real end-to-end test

**Files:**
- Modify: `pyproject.toml:31,36,42` (three `graphifyy>=0.8.0` pins)
- Create: `tests/vault_builder/test_graphify_compat.py`

**Interfaces:**
- Produces: an installed graphify ≥0.9.32 and a real-API (no-mock) regression test later tasks rely on. No repo code changes expected — all nine modules `graphify_runner.py` imports exist in 0.9.32; this task proves the *signatures* still line up.

- [ ] **Step 1: Create the branch and bump the pins**

```bash
git checkout main && git pull && git checkout -b feat/graphify-code-extractor
```

In `pyproject.toml` change all three occurrences of `"graphifyy>=0.8.0"` to `"graphifyy>=0.9.32"` (lines 31 `graphify` extra, 36 `all` extra, 42 dev deps).

- [ ] **Step 2: Install the upgrade**

Run: `pip install -e ".[dev]" -q && pip show graphifyy | head -2`
Expected: `Version: 0.9.32` (or newer).

- [ ] **Step 3: Write the real-API compat test**

Create `tests/vault_builder/test_graphify_compat.py`:

```python
"""Real-API (no mocks) compatibility tests against the installed graphify.

These exist because GraphifyRunner/code_repo tests mock the graphify
functions — a graphify upgrade that changes signatures or return shapes
would otherwise only fail in production. No LLM calls: AST extraction,
clustering, and labeling are fully deterministic and offline.
"""
from __future__ import annotations

from pathlib import Path

import pytest

graphify = pytest.importorskip("graphify")

from graphify.build import build_from_json
from graphify.cluster import cluster, label_communities_by_hub, score_all
from graphify.extract import collect_files, extract


@pytest.fixture()
def tiny_repo(tmp_path: Path) -> Path:
    (tmp_path / "auth.py").write_text(
        "def login(user):\n    return check_token(user)\n\n"
        "def check_token(user):\n    return True\n"
    )
    (tmp_path / "db.py").write_text(
        "from auth import login\n\n"
        "def connect():\n    return login('svc')\n"
    )
    return tmp_path


def test_full_code_pipeline_on_real_api(tiny_repo):
    files = collect_files(tiny_repo, root=tiny_repo)
    assert files, "collect_files found no python files"

    extraction = extract(files, root=tiny_repo, parallel=False)
    assert isinstance(extraction, dict)
    assert extraction["nodes"], "extract produced no nodes"
    node = extraction["nodes"][0]
    assert "id" in node and "label" in node

    graph = build_from_json(extraction, root=tiny_repo)
    assert graph.number_of_nodes() > 0

    communities = cluster(graph)
    assert isinstance(communities, dict)
    for cid, members in communities.items():
        assert isinstance(cid, int) and isinstance(members, list)

    labels = label_communities_by_hub(graph, communities)
    assert set(labels) == set(communities)
    assert all(isinstance(v, str) and v for v in labels.values())

    cohesion = score_all(graph, communities)
    assert set(cohesion) == set(communities)
    assert all(isinstance(v, float) for v in cohesion.values())


def test_runner_imports_still_resolve():
    """Every symbol graphify_runner.py imports must exist in this graphify."""
    from graphify.detect import detect  # noqa: F401
    from graphify.extract import extract, collect_files  # noqa: F401
    from graphify.build import build_from_json  # noqa: F401
    from graphify.cluster import cluster, score_all  # noqa: F401
    from graphify.analyze import god_nodes, surprising_connections  # noqa: F401
    from graphify.report import generate  # noqa: F401
    from graphify.export import to_json, to_html  # noqa: F401
    from graphify.wiki import to_wiki  # noqa: F401
    from graphify.cache import check_semantic_cache  # noqa: F401
```

- [ ] **Step 4: Run the compat test and the existing graphify-adjacent suites**

Run: `pytest tests/vault_builder/test_graphify_compat.py tests/vault_builder/test_graphify_runner.py tests/vault_builder/integration/ -v`
Expected: PASS. If a signature drifted (e.g. `to_wiki` kwargs changed), fix the call site in `graphify_runner.py` minimally and note it in the commit body — that is this task's purpose.

- [ ] **Step 5: Run the full suite as a regression sweep**

Run: `pytest --ignore=tests/test_jira_integration.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/vault_builder/test_graphify_compat.py
git commit -m "chore(deps): graphifyy >=0.9.32 with real-API compat tests

The runner's nine graphify imports and the code-extraction pipeline
(collect_files/extract/build_from_json/cluster/label/score) are now
pinned by an unmocked end-to-end test on a tiny synthetic repo.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `code_repo` extractor

**Files:**
- Create: `src/library_server/vault_builder/extractors/code_repo.py`
- Test: `tests/vault_builder/extractors/test_code_repo.py`

**Interfaces:**
- Consumes: graphify API per Global Constraints; `BaseExtractor.__init__(config: dict)` (`extractors/base.py:20-21`); `OutputWriter(base_dir=...).write_file(subdir, filename, title, source_type, source_path, extractor, trust, domain, tags, related, body)` (same call shape as `axon_bridge.py:146-152`).
- Produces: `CodeRepoExtractor` with class attrs `name="code_repo"`, `display_name="Source Code (Graphify)"`, `source_description="Source code repos analyzed in-process via Graphify"`, `output_subdir="repos"`. Config block shape: `sources.code_repo: {repos: [{name, path, type?, language?}]}` (`language` is descriptive metadata only). Task 3 wires this class into `server._get_vault_orchestrator`.

- [ ] **Step 1: Write the failing tests**

Create `tests/vault_builder/extractors/test_code_repo.py`. Mocks mirror the REAL graphify return shapes proven by Task 1's compat test (same discipline as the old `test_axon_bridge.py`):

```python
"""Tests for CodeRepoExtractor — graphify-powered source code extraction.

Mocks in this file reflect the REAL return shapes of graphify 0.9.x
(pinned by tests/vault_builder/test_graphify_compat.py).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from library_server.vault_builder.extractors.code_repo import CodeRepoExtractor

# Real-shaped graphify fixtures
FAKE_EXTRACTION = {
    "nodes": [
        {"id": "auth.py::login", "label": "login", "source_file": "auth.py"},
        {"id": "auth.py::check_token", "label": "check_token", "source_file": "auth.py"},
        {"id": "db.py::connect", "label": "connect", "source_file": "db.py"},
    ],
    "edges": [
        {"source": "auth.py::login", "target": "auth.py::check_token", "relation": "calls"},
    ],
}
FAKE_COMMUNITIES = {0: ["auth.py::login", "auth.py::check_token"], 1: ["db.py::connect"]}
FAKE_LABELS = {0: "login", 1: "connect"}
FAKE_COHESION = {0: 0.42, 1: 0.1}


class _FakeGraph:
    """Duck-types the nx.Graph surface code_repo uses."""

    def __init__(self, nodes):
        self.nodes = nodes  # dict: node_id -> attr dict

    def number_of_nodes(self):
        return len(self.nodes)

    def number_of_edges(self):
        return 1


FAKE_GRAPH = _FakeGraph({
    "auth.py::login": {"label": "login", "source_file": "auth.py"},
    "auth.py::check_token": {"label": "check_token", "source_file": "auth.py"},
    "db.py::connect": {"label": "connect", "source_file": "db.py"},
})


@pytest.fixture()
def repo_dir(tmp_path):
    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / "auth.py").write_text("def login(): pass\n")
    return repo


@pytest.fixture()
def extractor(repo_dir):
    return CodeRepoExtractor(config={
        "repos": [{"name": "myrepo", "path": str(repo_dir), "type": "service"}],
    })


def _patch_pipeline():
    return patch.multiple(
        "library_server.vault_builder.extractors.code_repo",
        collect_files=lambda target, **kw: [Path("auth.py"), Path("db.py")],
        extract=lambda paths, **kw: FAKE_EXTRACTION,
        build_from_json=lambda extraction, **kw: FAKE_GRAPH,
        cluster=lambda g, **kw: FAKE_COMMUNITIES,
        label_communities_by_hub=lambda g, c: FAKE_LABELS,
        score_all=lambda g, c: FAKE_COHESION,
    )


class TestValidateConfig:
    def test_missing_repos(self):
        ext = CodeRepoExtractor(config={})
        assert any("repos" in e for e in ext.validate_config())

    def test_missing_path(self, repo_dir):
        ext = CodeRepoExtractor(config={"repos": [{"name": "x", "path": str(repo_dir / "nope")}]})
        assert any("does not exist" in e for e in ext.validate_config())

    def test_valid(self, extractor):
        assert extractor.validate_config() == []


class TestSurvey:
    async def test_survey_counts_repos(self, extractor):
        result = await extractor.survey()
        assert result.source_name == "code_repo"
        assert result.file_count == 1
        assert result.health == "connected"

    async def test_survey_missing_path_is_error(self, repo_dir):
        ext = CodeRepoExtractor(config={"repos": [{"name": "x", "path": str(repo_dir / "gone")}]})
        result = await ext.survey()
        assert result.health == "error"


class TestPreview:
    async def test_preview_is_honest(self, extractor):
        result = await extractor.preview()
        assert result.files_to_create == ["repos/myrepo/repo-summary.md"]
        assert any("extract time" in w for w in result.warnings)


class TestExtract:
    async def test_extract_writes_summary_and_communities(self, extractor, tmp_path):
        out = tmp_path / "out" / "repos"
        with _patch_pipeline():
            result = await extractor.extract(out)

        assert result.success
        summary = (out / "myrepo" / "repo-summary.md").read_text()
        assert "**Symbols:** 3" in summary
        assert "**Relationships:** 1" in summary
        assert "**Communities:** 2" in summary

        c0 = (out / "myrepo" / "communities" / "login.md").read_text()
        assert "login" in c0
        assert "Cohesion:** 0.42" in c0
        assert "`check_token` — `auth.py`" in c0
        assert "[[myrepo/repo-summary]]" in c0
        assert sorted(result.files_written) == [
            "myrepo/communities/connect.md",
            "myrepo/communities/login.md",
            "myrepo/repo-summary.md",
        ]

    async def test_extract_repo_error_is_isolated(self, repo_dir, tmp_path):
        ext = CodeRepoExtractor(config={"repos": [
            {"name": "bad", "path": str(repo_dir)},
            {"name": "myrepo", "path": str(repo_dir)},
        ]})

        def boom(paths, **kw):
            raise RuntimeError("parse explosion")

        with _patch_pipeline(), patch(
            "library_server.vault_builder.extractors.code_repo.extract", boom
        ):
            result = await ext.extract(tmp_path / "repos")
        assert not result.success or result.errors  # errors recorded, never raises
        assert any("parse explosion" in e for e in result.errors)

    async def test_slug_collision_deduped(self, extractor, tmp_path):
        with _patch_pipeline(), patch(
            "library_server.vault_builder.extractors.code_repo.label_communities_by_hub",
            lambda g, c: {0: "Same Name", 1: "Same Name"},
        ):
            result = await extractor.extract(tmp_path / "repos")
        names = sorted(f for f in result.files_written if "communities" in f)
        assert names == ["myrepo/communities/same-name-2.md", "myrepo/communities/same-name.md"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/vault_builder/extractors/test_code_repo.py -v`
Expected: FAIL — `ModuleNotFoundError: ... code_repo`.

- [ ] **Step 3: Implement the extractor**

Create `src/library_server/vault_builder/extractors/code_repo.py`:

```python
"""Code Repo extractor — source code repos analyzed in-process via Graphify.

Replaces the axon_bridge extractor: no CLI subprocess, no separate index.
AST extraction, community detection, labeling, and cohesion scoring all run
through the graphify Python API (deterministic, offline, no LLM calls).
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from library_server.vault_builder.extractors.base import BaseExtractor
from library_server.vault_builder.output import OutputWriter
from library_server.vault_builder.types import SurveyResult, PreviewResult, ExtractResult

try:
    from graphify.build import build_from_json
    from graphify.cluster import cluster, label_communities_by_hub, score_all
    from graphify.extract import collect_files, extract
except ImportError:  # pragma: no cover
    build_from_json = None  # type: ignore[assignment]
    cluster = None  # type: ignore[assignment]
    label_communities_by_hub = None  # type: ignore[assignment]
    score_all = None  # type: ignore[assignment]
    collect_files = None  # type: ignore[assignment]
    extract = None  # type: ignore[assignment]

_GRAPHIFY_HINT = "Graphify is not installed. Run: pip install 'the-library[graphify]'"

_DOMAIN_PATTERNS: list[tuple[str, str]] = [
    (r"auth|clerk|jwt|requireAuth", "auth"),
    (r"tenant|org_id|current_tenant|rls", "tenancy"),
    (r"graphql|resolver|typeDef", "api"),
    (r"migration|schema|sql|entity", "database"),
    (r"terraform|gcp|cloudflare", "infra"),
    (r"stripe|billing|subscription", "integration"),
    (r"audit|log|immutable", "audit"),
    (r"compliance|framework|control|evidence", "compliance"),
    (r"encrypt|decrypt|vault|secret", "encryption"),
]

_MEMBER_LIMIT = 50


class CodeRepoExtractor(BaseExtractor):
    name = "code_repo"
    display_name = "Source Code (Graphify)"
    source_description = "Source code repos analyzed in-process via Graphify"
    output_subdir = "repos"

    def validate_config(self) -> list[str]:
        errors: list[str] = []
        repos = self.config.get("repos")
        if not repos:
            errors.append("Missing required config: repos")
            return errors
        if extract is None:
            errors.append(_GRAPHIFY_HINT)
        for repo in repos:
            path = repo.get("path")
            if path and not Path(path).exists():
                errors.append(f"Repo path does not exist: {path}")
        return errors

    async def survey(self) -> SurveyResult:
        repos = self.config.get("repos", [])
        if extract is None:
            return SurveyResult(
                source_name=self.name, file_count=0, total_size_bytes=0,
                structure_summary=_GRAPHIFY_HINT, health="error",
            )
        missing = [r["path"] for r in repos if r.get("path") and not Path(r["path"]).exists()]
        if missing:
            return SurveyResult(
                source_name=self.name, file_count=0, total_size_bytes=0,
                structure_summary=f"{len(missing)} repo path(s) not found: {', '.join(missing)}",
                health="error",
            )
        return SurveyResult(
            source_name=self.name, file_count=len(repos), total_size_bytes=0,
            structure_summary=f"{len(repos)} source code repos", health="connected",
        )

    async def preview(self) -> PreviewResult:
        repos = self.config.get("repos", [])
        files = [f"repos/{r['name']}/repo-summary.md" for r in repos]
        return PreviewResult(
            source_name=self.name,
            files_to_create=files,
            warnings=[
                "Community pages (repos/<name>/communities/*.md) are computed "
                "at extract time and are not listed in this preview."
            ],
        )

    async def extract(self, output_dir: Path) -> ExtractResult:
        writer = OutputWriter(base_dir=output_dir.parent)
        files_written: list[str] = []
        errors: list[str] = []
        start = time.monotonic()

        if extract is None:
            return ExtractResult(
                source_name=self.name, errors=[_GRAPHIFY_HINT],
                duration_seconds=time.monotonic() - start, success=False,
            )

        for repo in self.config.get("repos", []):
            repo_name = repo["name"]
            repo_path = Path(repo["path"])
            try:
                files_written.extend(
                    self._extract_repo(writer, output_dir, repo_name, repo_path, repo)
                )
            except Exception as e:
                errors.append(f"Error analyzing {repo_name}: {e}")

        return ExtractResult(
            source_name=self.name, files_written=files_written, files_skipped=[],
            errors=errors, duration_seconds=time.monotonic() - start,
            success=len(files_written) > 0,
        )

    def _extract_repo(
        self, writer: OutputWriter, output_dir: Path, repo_name: str,
        repo_path: Path, repo_cfg: dict,
    ) -> list[str]:
        files_written: list[str] = []

        code_files = collect_files(repo_path, root=repo_path)
        if not code_files:
            raise RuntimeError(f"no supported code files found under {repo_path}")

        extraction = extract(code_files, root=repo_path)
        graph = build_from_json(extraction, root=repo_path)
        communities = cluster(graph)
        labels = label_communities_by_hub(graph, communities)
        cohesion = score_all(graph, communities)

        # Community pages
        slug_counts: dict[str, int] = {}
        for cid, member_ids in communities.items():
            label = labels.get(cid, f"community-{cid}")
            base_slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or f"community-{cid}"
            count = slug_counts.get(base_slug, 0)
            slug_counts[base_slug] = count + 1
            slug = f"{base_slug}-{count + 1}" if count > 0 else base_slug

            members = [
                (
                    str(graph.nodes[nid].get("label", nid)),
                    str(graph.nodes[nid].get("source_file", "")),
                )
                for nid in member_ids[:_MEMBER_LIMIT]
            ]
            domain = self._detect_domain(" ".join(m[0] for m in members) + " " + label)

            body_parts = [
                f"# {label}",
                "",
                f"**Repo:** {repo_name}  ",
                f"**Symbols:** {len(member_ids)}  ",
                f"**Cohesion:** {cohesion.get(cid, 0.0)}  ",
                f"**Domain:** {domain}",
                "",
                "## Members",
                "",
            ]
            body_parts += [f"- `{sym}` — `{path}`" for sym, path in members]
            if len(member_ids) > _MEMBER_LIMIT:
                body_parts.append(f"- … {len(member_ids) - _MEMBER_LIMIT} more")

            writer.write_file(
                subdir=f"{output_dir.name}/{repo_name}/communities", filename=f"{slug}.md",
                title=label, source_type="code_repo",
                source_path=repo_name, extractor=self.name, trust=1.0,
                domain=domain, tags=["source/code", "trust/high", f"domain/{domain}"],
                related=[f"[[{repo_name}/repo-summary]]"],
                body="\n".join(body_parts),
            )
            files_written.append(f"{repo_name}/communities/{slug}.md")

        # Repo summary
        summary_body = (
            f"# {repo_name}\n\n"
            f"**Type:** {repo_cfg.get('type', 'unknown')}\n"
            f"**Language:** {repo_cfg.get('language', 'auto-detected')}\n"
            f"**Files:** {len(code_files)}\n"
            f"**Symbols:** {graph.number_of_nodes()}\n"
            f"**Relationships:** {graph.number_of_edges()}\n"
            f"**Communities:** {len(communities)}\n"
        )
        writer.write_file(
            subdir=f"{output_dir.name}/{repo_name}", filename="repo-summary.md",
            title=f"{repo_name} Repository", source_type="code_repo",
            source_path=str(repo_path), extractor=self.name, trust=1.0,
            domain=self._detect_domain(repo_name),
            tags=["source/code", "trust/high"], related=[], body=summary_body,
        )
        files_written.append(f"{repo_name}/repo-summary.md")
        return files_written

    @staticmethod
    def _detect_domain(text: str) -> str:
        for pattern, domain in _DOMAIN_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return domain
        return "general"
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/vault_builder/extractors/test_code_repo.py -v`
Expected: PASS. (Note the extract-error-isolation test patches `extract` to raise — confirm the per-repo `try/except` records the error instead of propagating.)

- [ ] **Step 5: Commit**

```bash
git add src/library_server/vault_builder/extractors/code_repo.py tests/vault_builder/extractors/test_code_repo.py
git commit -m "feat(vault-builder): code_repo extractor — graphify-powered code analysis

Same vault artifacts as axon_bridge (repo-summary + community pages,
identical frontmatter/trust/domain contract) computed in-process:
collect_files -> extract -> build_from_json -> cluster/label/score.
Honest preview; per-repo error isolation; ~25-language support incl.
Terraform via graphify's native extractors.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Wire `code_repo` in, with a loud migration error for `axon_bridge` configs

**Files:**
- Modify: `src/library_server/server.py` (`_get_vault_orchestrator` extractor imports/map; `library_vault_builder_config` return dict)
- Modify: `src/library_server/vault_builder/config.py` (remove `axon` field/loader/validation; add migration check)
- Test: `tests/test_server.py`, `tests/vault_builder/test_config.py`

**Interfaces:**
- Consumes: `CodeRepoExtractor` from Task 2.
- Produces: `extractor_map` key `"code_repo"` → `CodeRepoExtractor`; `library_vault_builder_config` result WITHOUT `axon_enabled`; `validate_vault_builder_config` error string `"sources.axon_bridge was renamed to sources.code_repo (axon retired in favor of graphify) — update library-config.yaml"` when the old key is present.

- [ ] **Step 1: Write the failing tests**

In `tests/vault_builder/test_config.py`:

```python
def test_axon_bridge_source_gets_migration_error(tmp_path):
    from library_server.vault_builder.config import (
        VaultBuilderConfig,
        validate_vault_builder_config,
    )

    cfg = VaultBuilderConfig(
        mode="create", output_vault=tmp_path / "vault",
        sources={"axon_bridge": {"repos": [{"name": "x", "path": "."}]}},
    )
    errors = validate_vault_builder_config(cfg)
    assert any("renamed to sources.code_repo" in e for e in errors)


def test_axon_field_is_gone():
    from library_server.vault_builder.config import VaultBuilderConfig
    assert not hasattr(VaultBuilderConfig(), "axon")
```

In `tests/test_server.py` (beside the existing `library_vault_builder_config` test — reuse its config/monkeypatch idiom):

```python
def test_vault_builder_config_has_no_axon_key(monkeypatch, tmp_path):
    from library_server.server import library_vault_builder_config

    monkeypatch.chdir(tmp_path)  # no library-config.yaml -> defaults
    result = library_vault_builder_config()
    assert "axon_enabled" not in result
    assert "graphify_enabled" in result  # neighbor key still present
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/vault_builder/test_config.py -k axon tests/test_server.py -k no_axon_key -v`
Expected: FAIL — no migration error produced; `axon` field exists; `axon_enabled` in result.

- [ ] **Step 3: Implement**

`src/library_server/vault_builder/config.py`:
1. Delete the `axon: dict[str, Any] = field(default_factory=dict)` dataclass field and the `axon=vb.get("axon", {})` loader kwarg.
2. Delete the axon CLI check block in `validate_vault_builder_config` (the `if config.axon.get("enabled"): ... shutil.which(axon_cmd) ...` lines).
3. Add to `validate_vault_builder_config`, before the per-source loop:

```python
    if "axon_bridge" in config.sources:
        errors.append(
            "sources.axon_bridge was renamed to sources.code_repo "
            "(axon retired in favor of graphify) — update library-config.yaml"
        )
```

`src/library_server/server.py`:
1. In `_get_vault_orchestrator`: replace `from library_server.vault_builder.extractors.axon_bridge import AxonBridgeExtractor` with `from library_server.vault_builder.extractors.code_repo import CodeRepoExtractor`, and in `extractor_map` replace `"axon_bridge": AxonBridgeExtractor,` with `"code_repo": CodeRepoExtractor,`.
2. In `library_vault_builder_config`: delete the `"axon_enabled": cfg.axon.get("enabled", False),` line from the result dict.

- [ ] **Step 4: Run the affected suites**

Run: `pytest tests/vault_builder/test_config.py tests/test_server.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/library_server/server.py src/library_server/vault_builder/config.py tests/
git commit -m "feat(vault-builder): register code_repo; migration error for axon_bridge configs

A config still naming sources.axon_bridge gets a loud rename error
instead of the silent never-registered behavior unknown blocks get.
library_vault_builder_config drops the axon_enabled field.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Delete axon_bridge and the pyproject axon remnant

**Files:**
- Delete: `src/library_server/vault_builder/extractors/axon_bridge.py`, `tests/vault_builder/extractors/test_axon_bridge.py`
- Modify: `pyproject.toml:32-35` (comment block about the removed `axon` extra)

- [ ] **Step 1: Delete and clean**

```bash
git rm src/library_server/vault_builder/extractors/axon_bridge.py tests/vault_builder/extractors/test_axon_bridge.py
```

In `pyproject.toml`, delete the comment block at lines ~32-35 (`# \`axon\` is a system CLI binary ...` through the end of that comment).

- [ ] **Step 2: Verify nothing in code still references axon**

Run: `grep -rn "axon" src/ tests/ bin/ scripts/ --include="*.py" | grep -v "^Binary"`
Expected: no output. (Docs references remain — Task 5 handles them.)

- [ ] **Step 3: Run the full suite**

Run: `pytest --ignore=tests/test_jira_integration.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore(vault-builder): remove axon_bridge extractor and axon remnants

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Docs, skills, packaging, and CHANGELOG for v0.4.0

**Files:**
- Modify: `skills/build/SKILL.md`, `docs/guides/skills-reference.md`, `docs/guides/vault-builder.md`, `docs/reference/vault-builder-api.md`, `docs/reference/mcp-tools.md`, `library-config.example.yaml`, `README.md`, `CHANGELOG.md`, `pyproject.toml:3`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `skills/plugin.json`

No code. The code state after Task 4 is authoritative — verify every claim against it.

- [ ] **Step 1: `skills/build/SKILL.md`** — in the frontmatter description and the valid-sources list, replace `axon_bridge` with `code_repo`; delete the "Axon CLI available (if `axon_bridge` selected)" prerequisite line (graphify is a pip extra, already covered by the skill's existing graphify notes if any).

- [ ] **Step 2: `docs/guides/skills-reference.md`** — in the extractor enumeration (~line 254), replace `axon_bridge` with `code_repo`.

- [ ] **Step 3: `docs/guides/vault-builder.md`** — extractor table row: `code_repo | Source code repos | Symbols, communities, cohesion via Graphify (in-process) | repos/ | 1.0`; replace `axon_bridge` in example commands with `code_repo`; delete the `axon:` config block (~lines 175-184) and the "Axon CLI not found" troubleshooting section (~lines 323-331), replacing the latter with a short "Graphify not installed" note pointing at `pip install 'the-library[graphify]'`; update the manifest example row naming axon_bridge.

- [ ] **Step 4: `docs/reference/vault-builder-api.md`** — remove the `axon: dict[str, Any]` line from the config dataclass listing; registry table row `axon_bridge | AxonBridgeExtractor | ...` becomes `code_repo | CodeRepoExtractor | repos | Graphify code analysis`; remove the "If Axon is enabled, its CLI binary is on `$PATH`" prerequisite bullet; update the `sources.axon_bridge` yaml sample to `sources.code_repo`.

- [ ] **Step 5: `docs/reference/mcp-tools.md`** — in the `library_vault_builder_config` entry, remove `axon_enabled` from the documented return dict.

- [ ] **Step 6: `library-config.example.yaml`** — in the vault_builder section: rename the `axon_bridge:` source block to `code_repo:` (keep the `repos:` sample, drop the "being replaced" comment), and delete any `axon:` lines.

- [ ] **Step 7: `README.md`** — update any axon_bridge/Axon mention to code_repo/Graphify (check the extractor list and feature bullets: `grep -n -i axon README.md`).

- [ ] **Step 8: Versions + CHANGELOG** — `pyproject.toml:3` → `0.4.0`; the three packaging JSONs (`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `skills/plugin.json`) → `"version": "0.4.0"` (tool count stays 37, skills stay 12). Insert above `## [0.3.2]` in `CHANGELOG.md`:

```markdown
## [0.4.0] - <today's date>

### Changed
- **BREAKING (config):** the `axon_bridge` vault-builder source is replaced by `code_repo`, powered by graphify's in-process Python API instead of the `axon` CLI. Rename `vault_builder.sources.axon_bridge` to `sources.code_repo` in library-config.yaml (`validate` reports a targeted error for the old key). Same vault artifacts: `repos/<name>/repo-summary.md` + `repos/<name>/communities/*.md`, now with cohesion scores and ~25-language support including Terraform.
- graphifyy dependency floor raised to 0.9.32, pinned by a real-API (unmocked) compatibility test.
- `library_vault_builder_config` no longer returns `axon_enabled`.

### Removed
- `axon_bridge` extractor, the `vault_builder.axon` config block, and the axon CLI install prerequisite — no system CLI needed for code analysis.
```

- [ ] **Step 9: Verify with grep**

```bash
grep -rn -i "axon" skills/ docs/guides/ docs/reference/ docs/setup/ README.md library-config.example.yaml CHANGELOG.md | grep -v "0.4.0\|superpowers\|retired\|renamed\|replaced\|axon_bridge was"
```
Expected: no hits describing axon as a live feature (historical CHANGELOG entries below 0.4.0 and the spec/plan docs are fine).

- [ ] **Step 10: Commit**

```bash
git add skills/ docs/ library-config.example.yaml README.md CHANGELOG.md pyproject.toml .claude-plugin/ skills/plugin.json
git commit -m "docs: v0.4.0 — code_repo replaces axon_bridge across docs/skills/packaging

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Acceptance run on a real repo + full verification gate

Per the spec, the acceptance test replaces a separate graphify-vs-axon spike: run the new extractor against a real repo (this repo itself) and sanity-check the community output.

- [ ] **Step 1: Real extraction against the-library itself**

```bash
python - <<'EOF'
import asyncio, tempfile
from pathlib import Path
from library_server.vault_builder.extractors.code_repo import CodeRepoExtractor

ext = CodeRepoExtractor(config={"repos": [{"name": "the-library", "path": ".", "type": "tool"}]})
out = Path(tempfile.mkdtemp()) / "repos"
result = asyncio.run(ext.extract(out))
print("success:", result.success, "errors:", result.errors[:3])
print("files:", len(result.files_written))
print((out / "the-library" / "repo-summary.md").read_text())
for f in sorted((out / "the-library" / "communities").glob("*.md"))[:5]:
    print("--", f.name)
EOF
```

Expected: `success: True`, a plausible symbol/relationship count for ~60 source files, and community pages whose names/members look like coherent groupings of this codebase (e.g. pm/jira symbols clustering together). Paste the summary and 5 community names into the task report for the human to eyeball — **community quality is the acceptance criterion**.

- [ ] **Step 2: Full verification gate**

Run, in order: `pytest --ignore=tests/test_jira_integration.py -q`, `bin/library-coverage-ratchet`, `ruff check .`, `mypy`, `bin/library-mutation-smoke`.
Expected: all pass; ratchet must not drop (new extractor code is well-covered by Task 2's tests — if the ratchet still drops, add coverage for the uncovered branches rather than bumping the baseline).

- [ ] **Step 3: Diff review**

Run: `git diff main...HEAD --stat && git log --oneline main..HEAD`
Check: no stray files; `graphify_runner.py` only changed if Task 1's compat pass required it.

- [ ] **Step 4: Report**

State what was verified and paste the acceptance-run output summary. Do not merge — the human reviews the community quality first.
