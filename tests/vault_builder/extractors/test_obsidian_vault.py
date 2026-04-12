"""Tests for Obsidian Vault extractor."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


def _parse_frontmatter(content: str) -> dict:
    parts = content.split("---\n", 2)
    if len(parts) < 3:
        return {}
    return yaml.safe_load(parts[1]) or {}


@pytest.fixture
def vault_extractor(sample_obsidian_vault: Path):
    from library_server.vault_builder.extractors.obsidian_vault import ObsidianVaultExtractor
    return ObsidianVaultExtractor(config={
        "enabled": True,
        "source_path": str(sample_obsidian_vault),
        "exclude_dirs": ["raw/jira-tickets", ".obsidian", ".git"],
        "include_extensions": [".md"],
        "stale_markers": ["Supabase", "Auth0"],
    })


async def test_validate_config_valid(vault_extractor):
    assert vault_extractor.validate_config() == []


async def test_validate_config_missing_path():
    from library_server.vault_builder.extractors.obsidian_vault import ObsidianVaultExtractor
    ext = ObsidianVaultExtractor(config={"enabled": True, "source_path": "/nonexistent"})
    errors = ext.validate_config()
    assert any("source_path" in e for e in errors)


async def test_survey_returns_correct_counts(vault_extractor):
    result = await vault_extractor.survey()
    assert result.source_name == "obsidian_vault"
    # Should count: wiki/auth-system.md and raw/paul-gsd-phases/phase-01.md
    # Should NOT count: raw/jira-tickets/ticket.md, .obsidian/*, .git/*
    assert result.file_count == 2


async def test_excluded_directories_are_skipped(vault_extractor, output_dir: Path):
    result = await vault_extractor.extract(output_dir / "vault")
    written_names = [f.split("/")[-1] for f in result.files_written]
    assert "ticket.md" not in written_names
    assert "app.json" not in written_names


async def test_stale_markers_detected(vault_extractor, output_dir: Path):
    await vault_extractor.extract(output_dir / "vault")
    # phase-01.md contains "Supabase" — a stale marker
    phase_file = None
    for md in (output_dir / "vault").rglob("phase-01.md"):
        phase_file = md
    assert phase_file is not None
    fm = _parse_frontmatter(phase_file.read_text())
    assert "stale-reference" in fm["tags"]


async def test_stale_marker_downgrades_trust(vault_extractor, output_dir: Path):
    await vault_extractor.extract(output_dir / "vault")
    for md in (output_dir / "vault").rglob("phase-01.md"):
        fm = _parse_frontmatter(md.read_text())
        # Base trust for raw docs is 0.3, stale marker downgrades by 0.1 → 0.2
        assert fm["trust"] <= 0.3


async def test_wiki_articles_higher_trust(vault_extractor, output_dir: Path):
    await vault_extractor.extract(output_dir / "vault")
    for md in (output_dir / "vault").rglob("auth-system.md"):
        fm = _parse_frontmatter(md.read_text())
        assert fm["trust"] == 0.5


async def test_existing_wiki_links_preserved(vault_extractor, output_dir: Path):
    await vault_extractor.extract(output_dir / "vault")
    for md in (output_dir / "vault").rglob("auth-system.md"):
        content = md.read_text()
        body = content.split("---\n", 2)[2]
        assert "[[Clerk]]" in body
        assert "[[INVARIANTS#INV-001]]" in body


async def test_extract_frontmatter_valid(vault_extractor, output_dir: Path):
    await vault_extractor.extract(output_dir / "vault")
    for md in (output_dir / "vault").rglob("*.md"):
        fm = _parse_frontmatter(md.read_text())
        assert fm["extractor"] == "obsidian_vault"
        assert "source/vault" in fm["tags"]
        assert "extracted_at" in fm


async def test_extract_idempotent(vault_extractor, output_dir: Path):
    result1 = await vault_extractor.extract(output_dir / "vault")
    result2 = await vault_extractor.extract(output_dir / "vault")
    assert sorted(result1.files_written) == sorted(result2.files_written)
