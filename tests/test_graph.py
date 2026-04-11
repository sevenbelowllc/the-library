"""Tests for the Graphify orchestrator module."""

from __future__ import annotations

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
