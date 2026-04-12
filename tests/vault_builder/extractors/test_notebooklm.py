"""Tests for NotebookLM extractor."""

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
def nlm_extractor(sample_notebooklm_dir: Path, tmp_path: Path):
    from library_server.vault_builder.extractors.notebooklm import NotebookLMExtractor
    return NotebookLMExtractor(config={
        "enabled": True,
        "source_path": str(sample_notebooklm_dir),
        "summaries_path": str(tmp_path / "notebooklm-summaries"),
    })


async def test_validate_config_valid(nlm_extractor):
    assert nlm_extractor.validate_config() == []


async def test_validate_config_missing_paths():
    from library_server.vault_builder.extractors.notebooklm import NotebookLMExtractor
    ext = NotebookLMExtractor(config={"enabled": True})
    errors = ext.validate_config()
    assert any("source_path" in e for e in errors)


async def test_survey_returns_correct_counts(nlm_extractor):
    result = await nlm_extractor.survey()
    assert result.file_count == 2  # 1 export + 1 summary


async def test_extract_writes_correct_files(nlm_extractor, output_dir: Path):
    result = await nlm_extractor.extract(output_dir / "notebooklm")
    assert result.success is True
    assert len(result.files_written) == 2


async def test_extract_trust_values(nlm_extractor, output_dir: Path):
    await nlm_extractor.extract(output_dir / "notebooklm")
    for md in (output_dir / "notebooklm").rglob("*.md"):
        fm = _parse_frontmatter(md.read_text())
        assert fm["trust"] == 0.4


async def test_extract_frontmatter_valid(nlm_extractor, output_dir: Path):
    await nlm_extractor.extract(output_dir / "notebooklm")
    files = list((output_dir / "notebooklm").rglob("*.md"))
    for f in files:
        fm = _parse_frontmatter(f.read_text())
        assert fm["extractor"] == "notebooklm"
        assert "source/notebooklm" in fm["tags"]
        assert "trust/low" in fm["tags"]
