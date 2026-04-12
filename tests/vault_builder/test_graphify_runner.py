"""Tests for GraphifyRunner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def runner():
    from library_server.vault_builder.graphify_runner import GraphifyRunner
    return GraphifyRunner(config={
        "enabled": True, "command": "graphify",
        "flags": ["--obsidian", "--wiki"], "incremental": False,
    })


def test_is_available_when_installed(runner):
    with patch("shutil.which", return_value="/usr/bin/graphify"):
        assert runner.is_available() is True


def test_is_available_when_not_installed(runner):
    with patch("shutil.which", return_value=None):
        assert runner.is_available() is False


def test_is_available_when_disabled():
    from library_server.vault_builder.graphify_runner import GraphifyRunner
    runner = GraphifyRunner(config={"enabled": False})
    assert runner.is_available() is False


async def test_build_creates_output(runner, tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "test.md").write_text("---\ntitle: Test\n---\n\n# Test\n")

    graphify_out = tmp_path / "graphify-out"
    wiki_dir = tmp_path / "wiki"

    mock_graph = MagicMock()
    mock_graph.number_of_nodes.return_value = 5
    mock_graph.number_of_edges.return_value = 3

    with patch("library_server.vault_builder.graphify_runner.extract") as mock_extract, \
         patch("library_server.vault_builder.graphify_runner.build_from_json", return_value=mock_graph), \
         patch("library_server.vault_builder.graphify_runner.cluster", return_value={0: ["a", "b"]}), \
         patch("library_server.vault_builder.graphify_runner.score_all", return_value={0: 0.8}), \
         patch("library_server.vault_builder.graphify_runner.god_nodes", return_value=[]), \
         patch("library_server.vault_builder.graphify_runner.surprising_connections", return_value=[]), \
         patch("library_server.vault_builder.graphify_runner.generate", return_value="# Report"), \
         patch("library_server.vault_builder.graphify_runner.to_json") as mock_json, \
         patch("library_server.vault_builder.graphify_runner.to_html") as mock_html, \
         patch("library_server.vault_builder.graphify_runner.to_wiki", return_value=2) as mock_wiki:

        mock_extract.return_value = {"nodes": [{"id": "a"}, {"id": "b"}], "edges": []}

        result = await runner.build(raw_dir=raw_dir, output_dir=graphify_out, wiki_dir=wiki_dir)

    assert result["status"] == "success"
    assert result["nodes"] == 5
    assert result["edges"] == 3
    mock_extract.assert_called_once()
    mock_wiki.assert_called_once()


async def test_build_skipped_when_disabled(tmp_path: Path):
    from library_server.vault_builder.graphify_runner import GraphifyRunner
    runner = GraphifyRunner(config={"enabled": False})
    result = await runner.build(
        raw_dir=tmp_path / "raw", output_dir=tmp_path / "out", wiki_dir=tmp_path / "wiki",
    )
    assert result["status"] == "disabled"


async def test_build_returns_error_on_failure(runner, tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "test.md").write_text("# Test")

    with patch("library_server.vault_builder.graphify_runner.extract", side_effect=Exception("Graphify error")):
        result = await runner.build(
            raw_dir=raw_dir, output_dir=tmp_path / "out", wiki_dir=tmp_path / "wiki",
        )

    assert result["status"] == "error"
    assert "Graphify error" in result["message"]
