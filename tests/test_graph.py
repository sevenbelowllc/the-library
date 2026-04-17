"""Tests for the Graphify orchestrator module."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from library_server.graph.orchestrator import (
    rebuild_graph,
    query_graph,
    trace_path,
    is_graphify_available,
)


def test_is_graphify_available_when_missing():
    """is_graphify_available should return False when graphifyy not installed."""
    with patch("shutil.which", return_value=None):
        assert is_graphify_available() is False


def test_is_graphify_available_when_installed():
    """is_graphify_available should return True when graphify CLI exists."""
    with patch("shutil.which", return_value="/usr/local/bin/graphify"):
        assert is_graphify_available() is True


def test_rebuild_graph_disabled():
    """rebuild_graph should return graceful message when disabled."""
    result = rebuild_graph(
        vault_path="/fake/vault",
        graph_path="/fake/graph.json",
        mode="deep",
        enabled=False,
    )
    assert result["status"] == "disabled"
    assert "not enabled" in result["message"].lower()


def test_rebuild_graph_not_installed():
    """rebuild_graph should return error when graphify CLI not found."""
    with patch("shutil.which", return_value=None):
        result = rebuild_graph(
            vault_path="/fake/vault",
            graph_path="/fake/graph.json",
            mode="deep",
            enabled=True,
        )
    assert result["status"] == "error"
    assert "not installed" in result["message"].lower()


def test_query_graph_disabled():
    """query_graph should return graceful fallback when disabled."""
    result = query_graph(query="test query", graph_path="/fake/graph.json", enabled=False)
    assert result["status"] == "disabled"


def test_trace_path_disabled():
    """trace_path should return graceful fallback when disabled."""
    result = trace_path(
        node_a="NodeA", node_b="NodeB", graph_path="/fake/graph.json", enabled=False
    )
    assert result["status"] == "disabled"


# ---------------------------------------------------------------------------
# rebuild_graph — success, failure, timeout, FileNotFoundError
# ---------------------------------------------------------------------------


@patch("library_server.graph.orchestrator.subprocess.run")
@patch("library_server.graph.orchestrator.shutil.which", return_value="/usr/local/bin/graphify")
def test_rebuild_graph_success(mock_which, mock_run):
    """rebuild_graph should return 'rebuilt' on subprocess returncode 0."""
    mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
    result = rebuild_graph(
        vault_path="/my/vault",
        graph_path="/my/graph.json",
        mode="deep",
        enabled=True,
    )
    assert result["status"] == "rebuilt"
    assert "/my/graph.json" in result["message"]
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args[0] == "graphify"
    assert "/my/vault/sources" in args[1]


@patch("library_server.graph.orchestrator.subprocess.run")
@patch("library_server.graph.orchestrator.shutil.which", return_value="/usr/local/bin/graphify")
def test_rebuild_graph_failure(mock_which, mock_run):
    """rebuild_graph should return 'error' when subprocess exits non-zero."""
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="bad input")
    result = rebuild_graph(
        vault_path="/my/vault",
        graph_path="/my/graph.json",
        enabled=True,
    )
    assert result["status"] == "error"
    assert "bad input" in result["message"]


@patch("library_server.graph.orchestrator.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="graphify", timeout=300))
@patch("library_server.graph.orchestrator.shutil.which", return_value="/usr/local/bin/graphify")
def test_rebuild_graph_timeout(mock_which, mock_run):
    """rebuild_graph should handle TimeoutExpired."""
    result = rebuild_graph(
        vault_path="/my/vault",
        graph_path="/my/graph.json",
        enabled=True,
    )
    assert result["status"] == "error"
    assert "timed out" in result["message"].lower()


@patch("library_server.graph.orchestrator.subprocess.run", side_effect=FileNotFoundError("No such file"))
@patch("library_server.graph.orchestrator.shutil.which", return_value="/usr/local/bin/graphify")
def test_rebuild_graph_file_not_found(mock_which, mock_run):
    """rebuild_graph should handle FileNotFoundError from subprocess."""
    result = rebuild_graph(
        vault_path="/my/vault",
        graph_path="/my/graph.json",
        enabled=True,
    )
    assert result["status"] == "error"
    assert "not found" in result["message"].lower()


# ---------------------------------------------------------------------------
# query_graph — success, missing file, subprocess error, timeout
# ---------------------------------------------------------------------------


@patch("library_server.graph.orchestrator.subprocess.run")
def test_query_graph_success(mock_run, tmp_path):
    """query_graph should return 'result' on subprocess returncode 0."""
    graph_file = tmp_path / "graph.json"
    graph_file.write_text("{}")
    mock_run.return_value = MagicMock(returncode=0, stdout='{"nodes": []}', stderr="")
    result = query_graph(query="find controls", graph_path=str(graph_file), enabled=True)
    assert result["status"] == "result"
    assert result["data"] == '{"nodes": []}'


def test_query_graph_missing_file():
    """query_graph should return error when graph file does not exist."""
    result = query_graph(query="test", graph_path="/nonexistent/graph.json", enabled=True)
    assert result["status"] == "error"
    assert "not found" in result["message"].lower()


@patch("library_server.graph.orchestrator.subprocess.run")
def test_query_graph_subprocess_error(mock_run, tmp_path):
    """query_graph should return error on non-zero exit."""
    graph_file = tmp_path / "graph.json"
    graph_file.write_text("{}")
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="parse error")
    result = query_graph(query="test", graph_path=str(graph_file), enabled=True)
    assert result["status"] == "error"
    assert "parse error" in result["message"]


@patch("library_server.graph.orchestrator.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="graphify", timeout=60))
def test_query_graph_timeout(mock_run, tmp_path):
    """query_graph should handle TimeoutExpired."""
    graph_file = tmp_path / "graph.json"
    graph_file.write_text("{}")
    result = query_graph(query="test", graph_path=str(graph_file), enabled=True)
    assert result["status"] == "error"
    assert "timed out" in result["message"].lower() or "timeout" in result["message"].lower()


@patch("library_server.graph.orchestrator.subprocess.run", side_effect=FileNotFoundError("graphify not found"))
def test_query_graph_file_not_found_error(mock_run, tmp_path):
    """query_graph should handle FileNotFoundError from subprocess."""
    graph_file = tmp_path / "graph.json"
    graph_file.write_text("{}")
    result = query_graph(query="test", graph_path=str(graph_file), enabled=True)
    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# trace_path — success, missing file, subprocess error, timeout
# ---------------------------------------------------------------------------


@patch("library_server.graph.orchestrator.subprocess.run")
def test_trace_path_success(mock_run, tmp_path):
    """trace_path should return 'result' on subprocess returncode 0."""
    graph_file = tmp_path / "graph.json"
    graph_file.write_text("{}")
    mock_run.return_value = MagicMock(returncode=0, stdout="A -> B -> C", stderr="")
    result = trace_path(node_a="A", node_b="C", graph_path=str(graph_file), enabled=True)
    assert result["status"] == "result"
    assert result["path"] == "A -> B -> C"


def test_trace_path_missing_file():
    """trace_path should return error when graph file does not exist."""
    result = trace_path(node_a="A", node_b="B", graph_path="/nonexistent/graph.json", enabled=True)
    assert result["status"] == "error"
    assert "not found" in result["message"].lower()


@patch("library_server.graph.orchestrator.subprocess.run")
def test_trace_path_subprocess_error(mock_run, tmp_path):
    """trace_path should return error on non-zero exit."""
    graph_file = tmp_path / "graph.json"
    graph_file.write_text("{}")
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="no path exists")
    result = trace_path(node_a="A", node_b="Z", graph_path=str(graph_file), enabled=True)
    assert result["status"] == "error"
    assert "no path exists" in result["message"]


@patch("library_server.graph.orchestrator.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="graphify", timeout=60))
def test_trace_path_timeout(mock_run, tmp_path):
    """trace_path should handle TimeoutExpired."""
    graph_file = tmp_path / "graph.json"
    graph_file.write_text("{}")
    result = trace_path(node_a="A", node_b="Z", graph_path=str(graph_file), enabled=True)
    assert result["status"] == "error"


@patch("library_server.graph.orchestrator.subprocess.run", side_effect=FileNotFoundError("graphify not found"))
def test_trace_path_file_not_found_error(mock_run, tmp_path):
    """trace_path should handle FileNotFoundError from subprocess."""
    graph_file = tmp_path / "graph.json"
    graph_file.write_text("{}")
    result = trace_path(node_a="A", node_b="Z", graph_path=str(graph_file), enabled=True)
    assert result["status"] == "error"
