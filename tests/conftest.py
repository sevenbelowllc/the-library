"""Shared test fixtures for the-library."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from library_server.config import LibraryConfig, load_config


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for test files."""
    return tmp_path


@pytest.fixture
def sample_config(tmp_dir: Path) -> LibraryConfig:
    """Create a sample library-config.yaml and return loaded config."""
    config_data = {
        "library": {"version": "1.0"},
        "reading_room": {
            "path": str(tmp_dir / "reading-room"),
            "type": "directory",
            "specs": "docs/specs",
            "plans": "docs/plans",
            "checkpoints": "docs/checkpoints",
        },
        "specs": {"path": str(tmp_dir / "specs"), "index": "INDEX.md", "format": "markdown"},
        "vault": {
            "path": str(tmp_dir / "vault"),
            "schema_version": "karpathy-v1",
            "compile_protocol": "CLAUDE.md",
            "compile_order": "kb.yaml",
        },
        "pm": {"provider": "none", "projects": []},
        "graphify": {
            "enabled": False,
            "graph_path": str(tmp_dir / "graphify-out" / "graph.json"),
            "source_path": "./raw",
            "mode": "deep",
            "mcp_port": 3001,
            "auto_rebuild": True,
        },
        "memory": {
            "path": str(tmp_dir / "memory"),
            "index": "MEMORY.md",
            "max_index_lines": 200,
            "stale_threshold_days": 30,
        },
        "checkpoints": {
            "path": str(tmp_dir / "checkpoints"),
            "format": "YYYY-MM-DD-HH-MM-SS-<topic>-checkpoint.md",
        },
    }
    config_path = tmp_dir / "library-config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config_data, f, default_flow_style=False)
    return load_config(config_path)


@pytest.fixture
def vault_dir(tmp_dir: Path) -> Path:
    """Create and return a temporary vault directory."""
    vault = tmp_dir / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    return vault


@pytest.fixture
def memory_dir(tmp_dir: Path) -> Path:
    """Create and return a temporary memory directory with sample files."""
    mem = tmp_dir / "memory"
    mem.mkdir(parents=True, exist_ok=True)

    # Create MEMORY.md index
    (mem / "MEMORY.md").write_text(
        "- [Sample Project](project_sample.md) — sample project memory\n"
    )

    # Create a sample memory file
    (mem / "project_sample.md").write_text(
        "---\n"
        "name: Sample Project\n"
        "description: A sample project memory for testing\n"
        "type: project\n"
        "---\n\n"
        "This is a sample project memory.\n"
    )

    return mem
