"""Graphify orchestrator — CLI trigger and MCP proxy with graceful degradation."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def is_graphify_available() -> bool:
    """Check if the graphify CLI is installed."""
    return shutil.which("graphify") is not None


def rebuild_graph(
    vault_path: str,
    graph_path: str,
    mode: str = "deep",
    enabled: bool = True,
) -> dict:
    """Trigger Graphify to rebuild the knowledge graph from vault sources.

    Shells out to `graphify <vault_path>/sources --update --mode <mode>`.

    Args:
        vault_path: Root path to the vault.
        graph_path: Where to write graph.json.
        mode: 'deep' or 'shallow'.
        enabled: If False, return graceful disabled message.

    Returns:
        {"status": "rebuilt" | "disabled" | "error", "message": str}
    """
    if not enabled:
        return {"status": "disabled", "message": "Graphify is not enabled in config."}

    if not is_graphify_available():
        return {
            "status": "error",
            "message": "Graphify CLI not installed. Run: pip install the-library[graphify]",
        }

    source_path = str(Path(vault_path) / "sources")
    try:
        result = subprocess.run(
            ["graphify", source_path, "--update", "--mode", mode, "--output", graph_path],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            return {"status": "rebuilt", "message": f"Graph rebuilt at {graph_path}"}
        else:
            return {"status": "error", "message": f"Graphify failed: {result.stderr}"}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Graphify rebuild timed out (300s)"}
    except FileNotFoundError:
        return {"status": "error", "message": "Graphify CLI not found on PATH"}


def query_graph(
    query: str,
    graph_path: str,
    enabled: bool = True,
) -> dict:
    """Query the knowledge graph.

    Proxies to Graphify MCP `query_graph` tool, or falls back to disabled message.

    Args:
        query: Natural language query.
        graph_path: Path to graph.json.
        enabled: If False, return graceful disabled message.

    Returns:
        {"status": "result" | "disabled" | "error", "data": dict | str}
    """
    if not enabled:
        return {
            "status": "disabled",
            "message": "Graphify is not enabled. Graph queries unavailable. Falling back to direct vault parsing.",
        }

    graph_file = Path(graph_path)
    if not graph_file.exists():
        return {"status": "error", "message": f"Graph file not found: {graph_path}. Run rebuild first."}

    try:
        result = subprocess.run(
            ["graphify", "query", query, "--graph", graph_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            return {"status": "result", "data": result.stdout}
        else:
            return {"status": "error", "message": result.stderr}
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return {"status": "error", "message": str(e)}


def trace_path(
    node_a: str,
    node_b: str,
    graph_path: str,
    enabled: bool = True,
) -> dict:
    """Trace shortest path between two nodes in the knowledge graph.

    Args:
        node_a: Start node name.
        node_b: End node name.
        graph_path: Path to graph.json.
        enabled: If False, return graceful disabled message.

    Returns:
        {"status": "result" | "disabled" | "error", "path": list | str}
    """
    if not enabled:
        return {
            "status": "disabled",
            "message": "Graphify is not enabled. Path tracing unavailable.",
        }

    graph_file = Path(graph_path)
    if not graph_file.exists():
        return {"status": "error", "message": f"Graph file not found: {graph_path}"}

    try:
        result = subprocess.run(
            ["graphify", "path", node_a, node_b, "--graph", graph_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            return {"status": "result", "path": result.stdout}
        else:
            return {"status": "error", "message": result.stderr}
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return {"status": "error", "message": str(e)}
