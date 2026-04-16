"""Tests for GraphifyRunner.

Tests cover the full pipeline: detect → AST extract → semantic cache → build → export.
The key invariant is that detect() is called (not collect_files alone), so that
documents, papers, and images are discovered — not just code files.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock, ANY

import pytest


@pytest.fixture
def runner():
    from library_server.vault_builder.graphify_runner import GraphifyRunner
    return GraphifyRunner(config={
        "enabled": True, "command": "graphify",
        "flags": ["--obsidian", "--wiki"], "incremental": False,
    })


@pytest.fixture
def disabled_runner():
    from library_server.vault_builder.graphify_runner import GraphifyRunner
    return GraphifyRunner(config={"enabled": False})


# --- is_available ---

def test_is_available_when_installed(runner):
    with patch("shutil.which", return_value="/usr/bin/graphify"):
        assert runner.is_available() is True


def test_is_available_when_not_installed(runner):
    with patch("shutil.which", return_value=None):
        assert runner.is_available() is False


def test_is_available_when_disabled(disabled_runner):
    assert disabled_runner.is_available() is False


def test_is_available_when_graphify_not_importable():
    from library_server.vault_builder.graphify_runner import GraphifyRunner
    runner = GraphifyRunner(config={"enabled": True, "command": "graphify"})
    with patch("library_server.vault_builder.graphify_runner.graphify_detect", None):
        assert runner.is_available() is False


# --- build: disabled / not installed ---

async def test_build_skipped_when_disabled(disabled_runner, tmp_path: Path):
    result = await disabled_runner.build(
        raw_dir=tmp_path / "raw", output_dir=tmp_path / "out", wiki_dir=tmp_path / "wiki",
    )
    assert result["status"] == "disabled"


async def test_build_error_when_graphify_not_installed(runner, tmp_path: Path):
    with patch("library_server.vault_builder.graphify_runner.graphify_detect", None):
        result = await runner.build(
            raw_dir=tmp_path / "raw", output_dir=tmp_path / "out", wiki_dir=tmp_path / "wiki",
        )
    assert result["status"] == "error"
    assert "not installed" in result["message"]


# --- build: detect is called ---

async def test_build_calls_detect_not_collect_files(runner, tmp_path: Path):
    """The core bug regression: detect() must be called to find docs, not just collect_files()."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "spec.md").write_text("# Architecture\n\nMulti-tenant compliance platform.")
    (raw_dir / "notes.md").write_text("# Notes\n\nDesign decisions.")

    mock_graph = MagicMock()
    mock_graph.number_of_nodes.return_value = 2
    mock_graph.number_of_edges.return_value = 1

    with patch("library_server.vault_builder.graphify_runner.graphify_detect") as mock_detect, \
         patch("library_server.vault_builder.graphify_runner.check_semantic_cache") as mock_cache, \
         patch("library_server.vault_builder.graphify_runner.build_from_json", return_value=mock_graph), \
         patch("library_server.vault_builder.graphify_runner.cluster", return_value={0: ["a", "b"]}), \
         patch("library_server.vault_builder.graphify_runner.score_all", return_value={0: 0.8}), \
         patch("library_server.vault_builder.graphify_runner.god_nodes", return_value=[]), \
         patch("library_server.vault_builder.graphify_runner.surprising_connections", return_value=[]), \
         patch("library_server.vault_builder.graphify_runner.generate", return_value="# Report"), \
         patch("library_server.vault_builder.graphify_runner.to_json"), \
         patch("library_server.vault_builder.graphify_runner.to_html"), \
         patch("library_server.vault_builder.graphify_runner.to_wiki", return_value=2):

        mock_detect.return_value = {
            "total_files": 2,
            "total_words": 50,
            "files": {
                "code": [],
                "document": [str(raw_dir / "spec.md"), str(raw_dir / "notes.md")],
                "paper": [],
                "image": [],
                "video": [],
            },
        }
        mock_cache.return_value = (
            [{"id": "spec_arch", "label": "Architecture"}],
            [{"source": "spec_arch", "target": "notes_design", "relation": "references"}],
            [],
            [],  # no uncached files
        )

        result = await runner.build(
            raw_dir=raw_dir, output_dir=tmp_path / "out", wiki_dir=tmp_path / "wiki",
        )

    # detect() MUST be called — this is the regression guard
    mock_detect.assert_called_once_with(raw_dir)
    # semantic cache should be checked for the document files
    mock_cache.assert_called_once()
    assert result["status"] == "success"


async def test_build_with_only_docs_and_no_cache_reports_uncached(runner, tmp_path: Path):
    """When docs exist but have no semantic cache, report uncached count."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "doc.md").write_text("# Test doc")

    with patch("library_server.vault_builder.graphify_runner.graphify_detect") as mock_detect, \
         patch("library_server.vault_builder.graphify_runner.check_semantic_cache") as mock_cache:

        mock_detect.return_value = {
            "total_files": 1,
            "total_words": 10,
            "files": {
                "code": [],
                "document": [str(raw_dir / "doc.md")],
                "paper": [],
                "image": [],
                "video": [],
            },
        }
        # No cache — document needs semantic extraction
        mock_cache.return_value = ([], [], [], [str(raw_dir / "doc.md")])

        result = await runner.build(
            raw_dir=raw_dir, output_dir=tmp_path / "out", wiki_dir=tmp_path / "wiki",
        )

    assert result["status"] == "error"
    assert "semantic extraction" in result["message"]
    assert "1 document" in result["message"]


# --- build: code files go through AST extract ---

async def test_build_routes_code_through_ast_extract(runner, tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "app.py").write_text("def main(): pass")

    mock_graph = MagicMock()
    mock_graph.number_of_nodes.return_value = 3
    mock_graph.number_of_edges.return_value = 1

    with patch("library_server.vault_builder.graphify_runner.graphify_detect") as mock_detect, \
         patch("library_server.vault_builder.graphify_runner.collect_files", return_value=[raw_dir / "app.py"]) as mock_collect, \
         patch("library_server.vault_builder.graphify_runner.extract") as mock_extract, \
         patch("library_server.vault_builder.graphify_runner.build_from_json", return_value=mock_graph), \
         patch("library_server.vault_builder.graphify_runner.cluster", return_value={0: ["a"]}), \
         patch("library_server.vault_builder.graphify_runner.score_all", return_value={0: 0.9}), \
         patch("library_server.vault_builder.graphify_runner.god_nodes", return_value=[]), \
         patch("library_server.vault_builder.graphify_runner.surprising_connections", return_value=[]), \
         patch("library_server.vault_builder.graphify_runner.generate", return_value="# Report"), \
         patch("library_server.vault_builder.graphify_runner.to_json"), \
         patch("library_server.vault_builder.graphify_runner.to_html"), \
         patch("library_server.vault_builder.graphify_runner.to_wiki", return_value=1):

        mock_detect.return_value = {
            "total_files": 1,
            "total_words": 5,
            "files": {
                "code": [str(raw_dir / "app.py")],
                "document": [],
                "paper": [],
                "image": [],
                "video": [],
            },
        }
        mock_extract.return_value = {
            "nodes": [{"id": "app_main", "label": "main"}],
            "edges": [],
        }

        result = await runner.build(
            raw_dir=raw_dir, output_dir=tmp_path / "out", wiki_dir=tmp_path / "wiki",
        )

    mock_extract.assert_called_once()
    assert result["status"] == "success"
    assert result["detection"]["code_files"] == 1


# --- build: mixed code + docs ---

async def test_build_merges_code_and_cached_docs(runner, tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "app.py").write_text("def main(): pass")
    (raw_dir / "spec.md").write_text("# Spec\n\nArchitecture overview.")

    mock_graph = MagicMock()
    mock_graph.number_of_nodes.return_value = 3
    mock_graph.number_of_edges.return_value = 2

    with patch("library_server.vault_builder.graphify_runner.graphify_detect") as mock_detect, \
         patch("library_server.vault_builder.graphify_runner.collect_files", return_value=[raw_dir / "app.py"]), \
         patch("library_server.vault_builder.graphify_runner.extract") as mock_extract, \
         patch("library_server.vault_builder.graphify_runner.check_semantic_cache") as mock_cache, \
         patch("library_server.vault_builder.graphify_runner.build_from_json", return_value=mock_graph), \
         patch("library_server.vault_builder.graphify_runner.cluster", return_value={0: ["a", "b", "c"]}), \
         patch("library_server.vault_builder.graphify_runner.score_all", return_value={0: 0.7}), \
         patch("library_server.vault_builder.graphify_runner.god_nodes", return_value=[]), \
         patch("library_server.vault_builder.graphify_runner.surprising_connections", return_value=[]), \
         patch("library_server.vault_builder.graphify_runner.generate", return_value="# Report"), \
         patch("library_server.vault_builder.graphify_runner.to_json"), \
         patch("library_server.vault_builder.graphify_runner.to_html"), \
         patch("library_server.vault_builder.graphify_runner.to_wiki", return_value=1):

        mock_detect.return_value = {
            "total_files": 2,
            "total_words": 20,
            "files": {
                "code": [str(raw_dir / "app.py")],
                "document": [str(raw_dir / "spec.md")],
                "paper": [],
                "image": [],
                "video": [],
            },
        }
        mock_extract.return_value = {
            "nodes": [{"id": "app_main", "label": "main"}],
            "edges": [],
        }
        mock_cache.return_value = (
            [{"id": "spec_arch", "label": "Architecture"}],
            [{"source": "app_main", "target": "spec_arch", "relation": "implements"}],
            [],
            [],
        )

        result = await runner.build(
            raw_dir=raw_dir, output_dir=tmp_path / "out", wiki_dir=tmp_path / "wiki",
        )

    assert result["status"] == "success"
    assert result["detection"]["code_files"] == 1
    assert result["detection"]["doc_files"] == 1
    assert result["detection"]["uncached_docs"] == 0


# --- build: empty vault ---

async def test_build_error_on_empty_directory(runner, tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    with patch("library_server.vault_builder.graphify_runner.graphify_detect") as mock_detect:
        mock_detect.return_value = {
            "total_files": 0,
            "total_words": 0,
            "files": {"code": [], "document": [], "paper": [], "image": [], "video": []},
        }

        result = await runner.build(
            raw_dir=raw_dir, output_dir=tmp_path / "out", wiki_dir=tmp_path / "wiki",
        )

    assert result["status"] == "error"
    assert "No supported files" in result["message"]


# --- build: saves detection and extraction artifacts ---

async def test_build_saves_detect_and_extract_json(runner, tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "app.py").write_text("def main(): pass")
    output_dir = tmp_path / "out"

    mock_graph = MagicMock()
    mock_graph.number_of_nodes.return_value = 1
    mock_graph.number_of_edges.return_value = 0

    with patch("library_server.vault_builder.graphify_runner.graphify_detect") as mock_detect, \
         patch("library_server.vault_builder.graphify_runner.collect_files", return_value=[raw_dir / "app.py"]), \
         patch("library_server.vault_builder.graphify_runner.extract") as mock_extract, \
         patch("library_server.vault_builder.graphify_runner.build_from_json", return_value=mock_graph), \
         patch("library_server.vault_builder.graphify_runner.cluster", return_value={0: ["a"]}), \
         patch("library_server.vault_builder.graphify_runner.score_all", return_value={0: 1.0}), \
         patch("library_server.vault_builder.graphify_runner.god_nodes", return_value=[]), \
         patch("library_server.vault_builder.graphify_runner.surprising_connections", return_value=[]), \
         patch("library_server.vault_builder.graphify_runner.generate", return_value="# Report"), \
         patch("library_server.vault_builder.graphify_runner.to_json"), \
         patch("library_server.vault_builder.graphify_runner.to_html"), \
         patch("library_server.vault_builder.graphify_runner.to_wiki", return_value=1):

        detection = {
            "total_files": 1, "total_words": 5,
            "files": {"code": [str(raw_dir / "app.py")], "document": [], "paper": [], "image": [], "video": []},
        }
        mock_detect.return_value = detection
        mock_extract.return_value = {"nodes": [{"id": "a"}], "edges": []}

        await runner.build(raw_dir=raw_dir, output_dir=output_dir, wiki_dir=tmp_path / "wiki")

    # Verify intermediate artifacts are saved for /graphify skill compatibility
    assert (output_dir / ".graphify_detect.json").exists()
    assert (output_dir / ".graphify_extract.json").exists()
    assert (output_dir / ".graphify_analysis.json").exists()

    saved_detect = json.loads((output_dir / ".graphify_detect.json").read_text())
    assert saved_detect["total_files"] == 1


# --- build: exception handling ---

async def test_build_returns_error_on_exception(runner, tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "test.md").write_text("# Test")

    with patch(
        "library_server.vault_builder.graphify_runner.graphify_detect",
        side_effect=Exception("Graphify crashed"),
    ):
        result = await runner.build(
            raw_dir=raw_dir, output_dir=tmp_path / "out", wiki_dir=tmp_path / "wiki",
        )

    assert result["status"] == "error"
    assert "Graphify crashed" in result["message"]


# --- build: large graph skips HTML ---

async def test_build_skips_html_for_large_graphs(runner, tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "app.py").write_text("x = 1")

    mock_graph = MagicMock()
    mock_graph.number_of_nodes.return_value = 6000  # > 5000 threshold
    mock_graph.number_of_edges.return_value = 10000

    with patch("library_server.vault_builder.graphify_runner.graphify_detect") as mock_detect, \
         patch("library_server.vault_builder.graphify_runner.collect_files", return_value=[raw_dir / "app.py"]), \
         patch("library_server.vault_builder.graphify_runner.extract", return_value={"nodes": [{"id": "a"}], "edges": []}), \
         patch("library_server.vault_builder.graphify_runner.build_from_json", return_value=mock_graph), \
         patch("library_server.vault_builder.graphify_runner.cluster", return_value={0: ["a"]}), \
         patch("library_server.vault_builder.graphify_runner.score_all", return_value={0: 1.0}), \
         patch("library_server.vault_builder.graphify_runner.god_nodes", return_value=[]), \
         patch("library_server.vault_builder.graphify_runner.surprising_connections", return_value=[]), \
         patch("library_server.vault_builder.graphify_runner.generate", return_value="# Report"), \
         patch("library_server.vault_builder.graphify_runner.to_json"), \
         patch("library_server.vault_builder.graphify_runner.to_html") as mock_html, \
         patch("library_server.vault_builder.graphify_runner.to_wiki", return_value=1):

        mock_detect.return_value = {
            "total_files": 1, "total_words": 5,
            "files": {"code": [str(raw_dir / "app.py")], "document": [], "paper": [], "image": [], "video": []},
        }

        result = await runner.build(
            raw_dir=raw_dir, output_dir=tmp_path / "out", wiki_dir=tmp_path / "wiki",
        )

    mock_html.assert_not_called()
    assert result["status"] == "success"


# --- build: directory in code_file_paths triggers collect_files ---

async def test_build_calls_collect_files_for_directory_code_paths(runner, tmp_path: Path):
    """When detect() returns a directory path in code files, collect_files() must be called on it."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    src_dir = raw_dir / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text("def main(): pass")

    mock_graph = MagicMock()
    mock_graph.number_of_nodes.return_value = 1
    mock_graph.number_of_edges.return_value = 0

    with patch("library_server.vault_builder.graphify_runner.graphify_detect") as mock_detect, \
         patch("library_server.vault_builder.graphify_runner.collect_files") as mock_collect, \
         patch("library_server.vault_builder.graphify_runner.extract") as mock_extract, \
         patch("library_server.vault_builder.graphify_runner.build_from_json", return_value=mock_graph), \
         patch("library_server.vault_builder.graphify_runner.cluster", return_value={0: ["a"]}), \
         patch("library_server.vault_builder.graphify_runner.score_all", return_value={0: 1.0}), \
         patch("library_server.vault_builder.graphify_runner.god_nodes", return_value=[]), \
         patch("library_server.vault_builder.graphify_runner.surprising_connections", return_value=[]), \
         patch("library_server.vault_builder.graphify_runner.generate", return_value="# Report"), \
         patch("library_server.vault_builder.graphify_runner.to_json"), \
         patch("library_server.vault_builder.graphify_runner.to_html"), \
         patch("library_server.vault_builder.graphify_runner.to_wiki", return_value=1):

        # detect() returns the src/ directory (not a file) as a code entry
        mock_detect.return_value = {
            "total_files": 1, "total_words": 5,
            "files": {
                "code": [str(src_dir)],  # directory path, not a file
                "document": [], "paper": [], "image": [], "video": [],
            },
        }
        mock_collect.return_value = [src_dir / "app.py"]
        mock_extract.return_value = {"nodes": [{"id": "app_main", "label": "main"}], "edges": []}

        result = await runner.build(
            raw_dir=raw_dir, output_dir=tmp_path / "out", wiki_dir=tmp_path / "wiki",
        )

    # collect_files() must be called with the directory
    mock_collect.assert_called_once_with(src_dir)
    # extract() should receive the file returned by collect_files()
    mock_extract.assert_called_once_with([src_dir / "app.py"])
    assert result["status"] == "success"


# --- build: success with uncached docs includes warning message ---

async def test_build_success_with_uncached_docs_includes_warning(runner, tmp_path: Path):
    """A successful build (code nodes extracted) with uncached docs must include a warning message."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "app.py").write_text("def main(): pass")
    (raw_dir / "doc.pdf").write_text("PDF content")

    mock_graph = MagicMock()
    mock_graph.number_of_nodes.return_value = 2
    mock_graph.number_of_edges.return_value = 1

    with patch("library_server.vault_builder.graphify_runner.graphify_detect") as mock_detect, \
         patch("library_server.vault_builder.graphify_runner.collect_files", return_value=[raw_dir / "app.py"]), \
         patch("library_server.vault_builder.graphify_runner.extract") as mock_extract, \
         patch("library_server.vault_builder.graphify_runner.check_semantic_cache") as mock_cache, \
         patch("library_server.vault_builder.graphify_runner.build_from_json", return_value=mock_graph), \
         patch("library_server.vault_builder.graphify_runner.cluster", return_value={0: ["a"]}), \
         patch("library_server.vault_builder.graphify_runner.score_all", return_value={0: 0.9}), \
         patch("library_server.vault_builder.graphify_runner.god_nodes", return_value=[]), \
         patch("library_server.vault_builder.graphify_runner.surprising_connections", return_value=[]), \
         patch("library_server.vault_builder.graphify_runner.generate", return_value="# Report"), \
         patch("library_server.vault_builder.graphify_runner.to_json"), \
         patch("library_server.vault_builder.graphify_runner.to_html"), \
         patch("library_server.vault_builder.graphify_runner.to_wiki", return_value=1):

        mock_detect.return_value = {
            "total_files": 2, "total_words": 10,
            "files": {
                "code": [str(raw_dir / "app.py")],
                "document": [str(raw_dir / "doc.pdf")],
                "paper": [], "image": [], "video": [],
            },
        }
        mock_extract.return_value = {"nodes": [{"id": "app_main", "label": "main"}], "edges": []}
        # One doc has no cache — uncached_count = 1
        mock_cache.return_value = ([], [], [], [str(raw_dir / "doc.pdf")])

        result = await runner.build(
            raw_dir=raw_dir, output_dir=tmp_path / "out", wiki_dir=tmp_path / "wiki",
        )

    # Build succeeds (code nodes present) but warns about uncached doc
    assert result["status"] == "success"
    assert result["detection"]["uncached_docs"] == 1
    assert "message" in result
    assert "1 document" in result["message"]
    assert "/graphify" in result["message"]


# --- build_from_vault: frontmatter-based graph building ---


async def test_build_from_vault_disabled(disabled_runner, tmp_path: Path):
    result = await disabled_runner.build_from_vault(
        raw_dir=tmp_path / "raw", output_dir=tmp_path / "out", wiki_dir=tmp_path / "wiki",
    )
    assert result["status"] == "disabled"


async def test_build_from_vault_not_installed(runner, tmp_path: Path):
    with patch("library_server.vault_builder.graphify_runner.build_from_json", None):
        result = await runner.build_from_vault(
            raw_dir=tmp_path / "raw", output_dir=tmp_path / "out", wiki_dir=tmp_path / "wiki",
        )
    assert result["status"] == "error"
    assert "not installed" in result["message"]


async def test_build_from_vault_parses_frontmatter(runner, tmp_path: Path):
    """build_from_vault reads YAML frontmatter to create nodes and edges."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "glossary.md").write_text(
        "---\ntitle: Glossary\nsource_type: spec\ndomain: compliance\n"
        "trust: 1.0\ntags: [source/spec]\nrelated:\n  - '[[Domains]]'\n---\n\n# Glossary\n"
    )
    (raw_dir / "domains.md").write_text(
        "---\ntitle: Domains\nsource_type: spec\ndomain: compliance\n"
        "trust: 1.0\ntags: [source/spec]\nrelated: []\n---\n\n# Domains\n"
    )

    mock_graph = MagicMock()
    mock_graph.number_of_nodes.return_value = 4  # 2 content + 1 domain node (shared)
    mock_graph.number_of_edges.return_value = 3

    with patch("library_server.vault_builder.graphify_runner.build_from_json", return_value=mock_graph) as mock_build, \
         patch("library_server.vault_builder.graphify_runner.cluster", return_value={0: ["a", "b"]}), \
         patch("library_server.vault_builder.graphify_runner.score_all", return_value={0: 0.8}), \
         patch("library_server.vault_builder.graphify_runner.god_nodes", return_value=[]), \
         patch("library_server.vault_builder.graphify_runner.surprising_connections", return_value=[]), \
         patch("library_server.vault_builder.graphify_runner.generate", return_value="# Report"), \
         patch("library_server.vault_builder.graphify_runner.to_json"), \
         patch("library_server.vault_builder.graphify_runner.to_html"), \
         patch("library_server.vault_builder.graphify_runner.to_wiki", return_value=2):

        result = await runner.build_from_vault(
            raw_dir=raw_dir, output_dir=tmp_path / "out", wiki_dir=tmp_path / "wiki",
        )

    assert result["status"] == "success"
    # build_from_json should receive the parsed extraction
    extraction = mock_build.call_args[0][0]
    node_ids = {n["id"] for n in extraction["nodes"]}
    assert "Glossary" in node_ids
    assert "Domains" in node_ids
    assert "domain:compliance" in node_ids
    # Glossary should have a related_to edge to Domains
    edge_targets = {(e["source"], e["target"], e["type"]) for e in extraction["edges"]}
    assert ("Glossary", "Domains", "related_to") in edge_targets


async def test_build_from_vault_empty_dir(runner, tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    result = await runner.build_from_vault(
        raw_dir=raw_dir, output_dir=tmp_path / "out", wiki_dir=tmp_path / "wiki",
    )
    assert result["status"] == "error"
    assert "No frontmatter" in result["message"]


async def test_build_from_vault_skips_manifest(runner, tmp_path: Path):
    """Files starting with _ (like _build-manifest.md) should be skipped."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "_build-manifest.md").write_text(
        "---\ntitle: Build Manifest\n---\n\n# Manifest\n"
    )

    result = await runner.build_from_vault(
        raw_dir=raw_dir, output_dir=tmp_path / "out", wiki_dir=tmp_path / "wiki",
    )
    assert result["status"] == "error"  # No valid nodes found


async def test_build_from_vault_saves_artifacts(runner, tmp_path: Path):
    """build_from_vault must save .graphify_extract.json and .graphify_analysis.json."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "test.md").write_text(
        "---\ntitle: Test\nsource_type: spec\ndomain: general\ntrust: 1.0\n"
        "tags: []\nrelated: []\n---\n\n# Test\n"
    )
    out_dir = tmp_path / "out"

    mock_graph = MagicMock()
    mock_graph.number_of_nodes.return_value = 2
    mock_graph.number_of_edges.return_value = 1

    with patch("library_server.vault_builder.graphify_runner.build_from_json", return_value=mock_graph), \
         patch("library_server.vault_builder.graphify_runner.cluster", return_value={0: ["a"]}), \
         patch("library_server.vault_builder.graphify_runner.score_all", return_value={0: 1.0}), \
         patch("library_server.vault_builder.graphify_runner.god_nodes", return_value=[]), \
         patch("library_server.vault_builder.graphify_runner.surprising_connections", return_value=[]), \
         patch("library_server.vault_builder.graphify_runner.generate", return_value="# Report"), \
         patch("library_server.vault_builder.graphify_runner.to_json"), \
         patch("library_server.vault_builder.graphify_runner.to_html"), \
         patch("library_server.vault_builder.graphify_runner.to_wiki", return_value=1):

        await runner.build_from_vault(raw_dir=raw_dir, output_dir=out_dir, wiki_dir=tmp_path / "wiki")

    assert (out_dir / ".graphify_extract.json").exists()
    assert (out_dir / ".graphify_analysis.json").exists()
    assert (out_dir / "GRAPH_REPORT.md").exists()


async def test_build_from_vault_exception_handling(runner, tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "test.md").write_text(
        "---\ntitle: Test\nsource_type: spec\ndomain: general\ntrust: 1.0\n"
        "tags: []\nrelated: []\n---\n\n# Test\n"
    )

    with patch("library_server.vault_builder.graphify_runner.build_from_json", side_effect=Exception("boom")):
        result = await runner.build_from_vault(
            raw_dir=raw_dir, output_dir=tmp_path / "out", wiki_dir=tmp_path / "wiki",
        )
    assert result["status"] == "error"
    assert "boom" in result["message"]


# --- _parse_vault_frontmatter ---


def test_parse_vault_frontmatter_deduplicates_titles(runner, tmp_path: Path):
    """Nodes with duplicate titles get disambiguated with parent dir prefix."""
    raw_dir = tmp_path / "raw"
    (raw_dir / "a").mkdir(parents=True)
    (raw_dir / "b").mkdir(parents=True)
    (raw_dir / "a" / "summary.md").write_text(
        "---\ntitle: Summary\nsource_type: spec\ndomain: general\n"
        "trust: 1.0\ntags: []\nrelated: []\n---\n\n# Summary A\n"
    )
    (raw_dir / "b" / "summary.md").write_text(
        "---\ntitle: Summary\nsource_type: spec\ndomain: general\n"
        "trust: 1.0\ntags: []\nrelated: []\n---\n\n# Summary B\n"
    )

    nodes, edges = runner._parse_vault_frontmatter(raw_dir)
    node_ids = {n["id"] for n in nodes if n["type"] != "domain"}
    # One should be "Summary", the other disambiguated
    assert len(node_ids) == 2
    assert "Summary" in node_ids


def test_parse_vault_frontmatter_skips_no_frontmatter(runner, tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "plain.md").write_text("# No frontmatter here\n\nJust body text.")

    nodes, edges = runner._parse_vault_frontmatter(raw_dir)
    content_nodes = [n for n in nodes if n["type"] != "domain"]
    assert len(content_nodes) == 0
