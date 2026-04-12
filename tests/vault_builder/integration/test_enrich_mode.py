"""Tests for enrich mode — user content preservation."""

from __future__ import annotations

from pathlib import Path

import pytest

from library_server.vault_builder.extractors.specs import SpecsExtractor
from library_server.vault_builder.graphify_runner import GraphifyRunner
from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
from library_server.vault_builder.registry import PluginRegistry


async def test_enrich_mode_preserves_user_content(sample_specs_dir: Path, tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / ".obsidian").mkdir()
    (vault / ".obsidian" / "app.json").write_text('{"theme": "dark"}')

    user_notes = vault / "my-notes"
    user_notes.mkdir()
    (user_notes / "important.md").write_text("# My Important Note\n\nDon't touch this!")

    registry = PluginRegistry()
    registry.register(SpecsExtractor(config={"enabled": True, "source_path": str(sample_specs_dir)}))
    graphify = GraphifyRunner(config={"enabled": False})

    orch = VaultBuildOrchestrator(
        registry=registry, graphify_runner=graphify,
        output_vault=vault, mode="enrich",
    )
    await orch.build()

    assert (user_notes / "important.md").read_text() == "# My Important Note\n\nDon't touch this!"
    assert (vault / ".obsidian" / "app.json").read_text() == '{"theme": "dark"}'
    assert (vault / "raw" / "specs" / "GLOSSARY.md").exists()


async def test_enrich_mode_preserves_obsidian_config(sample_specs_dir: Path, tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / ".obsidian").mkdir()
    original_config = '{"baseFontSize": 16, "theme": "dark"}'
    (vault / ".obsidian" / "app.json").write_text(original_config)

    registry = PluginRegistry()
    registry.register(SpecsExtractor(config={"enabled": True, "source_path": str(sample_specs_dir)}))
    graphify = GraphifyRunner(config={"enabled": False})

    orch = VaultBuildOrchestrator(
        registry=registry, graphify_runner=graphify,
        output_vault=vault, mode="enrich",
    )
    await orch.build()

    assert (vault / ".obsidian" / "app.json").read_text() == original_config
