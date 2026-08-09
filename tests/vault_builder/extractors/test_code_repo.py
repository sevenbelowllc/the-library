"""Tests for CodeRepoExtractor — graphify-powered source code extraction.

Mocks in this file reflect the REAL return shapes of graphify 0.9.x
(pinned by tests/vault_builder/test_graphify_compat.py).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

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

    def __init__(self, nodes, edge_count=0):
        self.nodes = nodes  # dict: node_id -> attr dict
        self._edge_count = edge_count

    def number_of_nodes(self):
        return len(self.nodes)

    def number_of_edges(self):
        return self._edge_count


FAKE_GRAPH = _FakeGraph(
    {
        "auth.py::login": {"label": "login", "source_file": "auth.py"},
        "auth.py::check_token": {"label": "check_token", "source_file": "auth.py"},
        "db.py::connect": {"label": "connect", "source_file": "db.py"},
    },
    edge_count=len(FAKE_EXTRACTION["edges"]),
)


def _parse_frontmatter(content: str) -> dict:
    parts = content.split("---\n", 2)
    if len(parts) < 3:
        return {}
    return yaml.safe_load(parts[1]) or {}


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

    def test_reports_missing_graphify(self, extractor):
        with patch("library_server.vault_builder.extractors.code_repo.extract", None):
            errors = extractor.validate_config()
        assert any("Graphify is not installed" in e for e in errors)


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

    async def test_survey_reports_missing_graphify(self, extractor):
        with patch("library_server.vault_builder.extractors.code_repo.extract", None):
            result = await extractor.survey()
        assert result.health == "error"
        assert "Graphify is not installed" in result.structure_summary


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
        assert "# login" in c0
        assert "Cohesion:** 0.42" in c0
        assert "`check_token` — `auth.py`" in c0
        assert "[[myrepo/repo-summary]]" in c0
        assert sorted(result.files_written) == [
            "myrepo/communities/connect.md",
            "myrepo/communities/login.md",
            "myrepo/repo-summary.md",
        ]

    async def test_extract_reports_missing_graphify(self, extractor, tmp_path):
        with patch("library_server.vault_builder.extractors.code_repo.extract", None):
            result = await extractor.extract(tmp_path / "repos")
        assert not result.success
        assert any("Graphify is not installed" in e for e in result.errors)

    async def test_extract_repo_error_is_isolated(self, repo_dir, tmp_path):
        """Only the FIRST repo's extraction raises; the second must still succeed."""
        ext = CodeRepoExtractor(config={"repos": [
            {"name": "bad", "path": str(repo_dir)},
            {"name": "myrepo", "path": str(repo_dir)},
        ]})

        call_count = {"n": 0}

        def flaky_extract(paths, **kw):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("parse explosion")
            return FAKE_EXTRACTION

        with _patch_pipeline(), patch(
            "library_server.vault_builder.extractors.code_repo.extract", flaky_extract
        ):
            result = await ext.extract(tmp_path / "repos")

        assert result.success
        assert any("bad" in e and "parse explosion" in e for e in result.errors)
        assert not any(f.startswith("bad/") for f in result.files_written)
        assert any(f == "myrepo/repo-summary.md" for f in result.files_written)

    async def test_no_code_files_is_isolated_error(self, extractor, tmp_path):
        with patch.multiple(
            "library_server.vault_builder.extractors.code_repo",
            collect_files=lambda target, **kw: [],
            extract=lambda paths, **kw: FAKE_EXTRACTION,
            build_from_json=lambda extraction, **kw: FAKE_GRAPH,
            cluster=lambda g, **kw: FAKE_COMMUNITIES,
            label_communities_by_hub=lambda g, c: FAKE_LABELS,
            score_all=lambda g, c: FAKE_COHESION,
        ):
            result = await extractor.extract(tmp_path / "repos")
        assert not result.success
        assert any("no supported code files" in e for e in result.errors)

    async def test_member_limit_truncation(self, extractor, tmp_path):
        member_ids = [f"m{i}.py::sym{i}" for i in range(60)]
        big_extraction = {
            "nodes": [
                {"id": mid, "label": f"sym{i}", "source_file": f"m{i}.py"}
                for i, mid in enumerate(member_ids)
            ],
            "edges": [],
        }
        big_graph = _FakeGraph(
            {
                mid: {"label": f"sym{i}", "source_file": f"m{i}.py"}
                for i, mid in enumerate(member_ids)
            },
            edge_count=0,
        )

        with patch.multiple(
            "library_server.vault_builder.extractors.code_repo",
            collect_files=lambda target, **kw: [Path("m0.py")],
            extract=lambda paths, **kw: big_extraction,
            build_from_json=lambda extraction, **kw: big_graph,
            cluster=lambda g, **kw: {0: member_ids},
            label_communities_by_hub=lambda g, c: {0: "big"},
            score_all=lambda g, c: {0: 0.5},
        ):
            result = await extractor.extract(tmp_path / "repos")

        body = (tmp_path / "repos" / "myrepo" / "communities" / "big.md").read_text()
        assert "… 10 more" in body
        assert result.success

    async def test_slug_collision_deduped(self, extractor, tmp_path):
        with _patch_pipeline(), patch(
            "library_server.vault_builder.extractors.code_repo.label_communities_by_hub",
            lambda g, c: {0: "Same Name", 1: "Same Name"},
        ):
            result = await extractor.extract(tmp_path / "repos")
        names = sorted(f for f in result.files_written if "communities" in f)
        assert names == ["myrepo/communities/same-name-2.md", "myrepo/communities/same-name.md"]


class TestFrontmatter:
    async def test_all_output_files_have_valid_frontmatter(self, extractor, tmp_path):
        with _patch_pipeline():
            await extractor.extract(tmp_path / "repos")

        md_files = list((tmp_path / "repos").rglob("*.md"))
        assert md_files, "no output files written"
        for md in md_files:
            fm = _parse_frontmatter(md.read_text())
            assert fm.get("source_type") == "code_repo", f"Wrong source_type in {md}"
            assert fm.get("extractor") == "code_repo", f"Wrong extractor in {md}"
            assert fm.get("trust") == 1.0, f"Wrong trust in {md}"
            assert "source/code" in fm.get("tags", []), f"Missing tag in {md}"
            assert "trust/high" in fm.get("tags", []), f"Missing trust tag in {md}"
            assert fm.get("domain"), f"Missing domain in {md}"


class TestDomainDetection:
    def test_auth_pattern(self):
        assert CodeRepoExtractor._detect_domain("requireAuth verifyJWT clerk") == "auth"

    def test_tenancy_pattern(self):
        assert CodeRepoExtractor._detect_domain("setTenantContext org_id rls") == "tenancy"

    def test_fallback_general(self):
        assert CodeRepoExtractor._detect_domain("some random unmatched text") == "general"
