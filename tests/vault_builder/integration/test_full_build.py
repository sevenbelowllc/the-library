"""End-to-end vault build test with fixture data."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from library_server.vault_builder.extractors.specs import SpecsExtractor
from library_server.vault_builder.extractors.claude_memory import ClaudeMemoryExtractor
from library_server.vault_builder.graphify_runner import GraphifyRunner
from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
from library_server.vault_builder.registry import PluginRegistry


async def test_full_build_with_fixtures(sample_specs_dir: Path, sample_memory_dir: Path, tmp_path: Path):
    registry = PluginRegistry()
    registry.register(SpecsExtractor(config={"enabled": True, "source_path": str(sample_specs_dir)}))
    registry.register(ClaudeMemoryExtractor(config={"enabled": True, "memory_paths": [str(sample_memory_dir)]}))
    graphify = GraphifyRunner(config={"enabled": False})

    output_vault = tmp_path / "vault"
    orch = VaultBuildOrchestrator(
        registry=registry, graphify_runner=graphify,
        output_vault=output_vault, mode="create",
    )
    result = await orch.build()

    assert result.status == "completed"
    assert result.any_succeeded is True
    assert len(result.extract_results) == 2

    raw = output_vault / "raw"
    assert raw.exists()
    assert (raw / "_build-manifest.md").exists()
    assert (raw / "specs" / "GLOSSARY.md").exists()
    assert (raw / "memory" / "project_greenfield_reset.md").exists()


async def test_all_output_files_have_frontmatter(sample_specs_dir: Path, tmp_path: Path):
    registry = PluginRegistry()
    registry.register(SpecsExtractor(config={"enabled": True, "source_path": str(sample_specs_dir)}))
    graphify = GraphifyRunner(config={"enabled": False})

    output_vault = tmp_path / "vault"
    orch = VaultBuildOrchestrator(
        registry=registry, graphify_runner=graphify,
        output_vault=output_vault, mode="create",
    )
    await orch.build()

    raw = output_vault / "raw"
    for md in raw.rglob("*.md"):
        if md.name == "_build-manifest.md":
            continue
        content = md.read_text()
        assert content.startswith("---\n"), f"{md} missing frontmatter"
        parts = content.split("---\n", 2)
        assert len(parts) >= 3, f"{md} has malformed frontmatter"
        fm = yaml.safe_load(parts[1])
        assert "title" in fm, f"{md} missing title"
        assert "trust" in fm, f"{md} missing trust"
        assert "extractor" in fm, f"{md} missing extractor"
        assert "extracted_at" in fm, f"{md} missing extracted_at"


async def test_trust_hierarchy_enforced(sample_specs_dir: Path, sample_memory_dir: Path, tmp_path: Path):
    registry = PluginRegistry()
    registry.register(SpecsExtractor(config={"enabled": True, "source_path": str(sample_specs_dir)}))
    registry.register(ClaudeMemoryExtractor(config={"enabled": True, "memory_paths": [str(sample_memory_dir)]}))
    graphify = GraphifyRunner(config={"enabled": False})

    output_vault = tmp_path / "vault"
    orch = VaultBuildOrchestrator(
        registry=registry, graphify_runner=graphify,
        output_vault=output_vault, mode="create",
    )
    await orch.build()

    raw = output_vault / "raw"
    for md in raw.rglob("*.md"):
        if md.name == "_build-manifest.md":
            continue
        content = md.read_text()
        parts = content.split("---\n", 2)
        fm = yaml.safe_load(parts[1])
        if fm["extractor"] == "specs":
            assert fm["trust"] == 1.0
        elif fm["extractor"] == "claude_memory":
            assert fm["trust"] == 0.7
