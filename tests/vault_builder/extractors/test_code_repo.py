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
