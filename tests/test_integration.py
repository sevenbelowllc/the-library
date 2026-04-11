"""Integration test: config → vault-init → ingest → parse → checkpoint."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from library_server.config import load_config, validate_config
from library_server.vault.init import init_vault
from library_server.vault.validate import validate_vault
from library_server.vault.ingest import ingest_source
from library_server.vault.parse import parse_vault
from library_server.checkpoint.checkpoint import write_checkpoint, read_checkpoint, list_checkpoints
from library_server.memory.scan import scan_memories
from library_server.types import CheckpointData


def test_full_lifecycle(tmp_path: Path):
    """End-to-end: config → vault init → ingest → parse → checkpoint → read."""

    # 1. Create config
    config_data = {
        "library": {"version": "1.0"},
        "reading_room": {
            "path": str(tmp_path / "reading-room"),
            "type": "directory",
            "specs": "docs/specs",
            "plans": "docs/plans",
            "checkpoints": "docs/checkpoints",
        },
        "vault": {"path": str(tmp_path / "vault"), "schema_version": "karpathy-v1",
                   "compile_protocol": "CLAUDE.md", "compile_order": "kb.yaml"},
        "pm": {"provider": "none", "projects": []},
        "graphify": {"enabled": False},
        "memory": {"path": str(tmp_path / "memory"), "index": "MEMORY.md",
                    "max_index_lines": 200, "stale_threshold_days": 30},
        "checkpoints": {"path": str(tmp_path / "checkpoints")},
    }
    config_path = tmp_path / "library-config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)
    config = load_config(config_path)
    validation = validate_config(config)
    # vault doesn't exist yet, so warnings are expected
    assert "warnings" in validation

    # 2. Init vault
    vault_path = str(tmp_path / "vault")
    init_result = init_vault(vault_path)
    assert init_result["status"] == "created"

    # 3. Validate vault
    validate_result = validate_vault(vault_path)
    assert validate_result["valid"] is True

    # 4. Ingest a source
    source = tmp_path / "my-prd.md"
    source.write_text("# Product Requirements\n\nBuild the library.\n")
    ingest_result = ingest_source(vault_path, str(source), "raw", "prds")
    assert ingest_result["status"] == "ingested"

    # 5. Create a wiki article with tags
    wiki_dir = tmp_path / "vault" / "wiki"
    (wiki_dir / "overview.md").write_text(
        "---\ntitle: Overview\ndomain: core\n---\n\n"
        "# Overview\n\n"
        "The library is partially complete. [VERIFY] — need to test MCP tools\n"
    )

    # 6. Parse vault
    parse_result = parse_vault(vault_path)
    assert len(parse_result["tags"]) == 1
    assert parse_result["tags"][0]["tag_type"] == "VERIFY"
    assert len(parse_result["articles"]) == 1

    # 7. Write checkpoint
    checkpoint_data = CheckpointData(
        topic="integration-test",
        date="2026-04-10",
        status="Testing",
        next_session="Verify results",
        accomplished=["Built vault", "Ingested source", "Parsed tags"],
        next_actions=["Run full test suite"],
    )
    checkpoint_dir = str(tmp_path / "checkpoints")
    cp_result = write_checkpoint(checkpoint_dir, checkpoint_data)
    assert cp_result["status"] == "written"

    # 8. Read checkpoint
    read_result = read_checkpoint(cp_result["path"])
    assert read_result["topic"] == "integration-test"
    assert "Built vault" in read_result["accomplished"]

    # 9. List checkpoints
    list_result = list_checkpoints(checkpoint_dir)
    assert len(list_result["checkpoints"]) == 1

    # 10. Memory scan (empty dir)
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir()
    (mem_dir / "MEMORY.md").write_text("")
    scan_result = scan_memories(str(mem_dir))
    assert scan_result["total_count"] == 0
