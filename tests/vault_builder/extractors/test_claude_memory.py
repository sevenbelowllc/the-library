"""Tests for Claude Memory extractor."""

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
def memory_extractor(sample_memory_dir: Path):
    from library_server.vault_builder.extractors.claude_memory import ClaudeMemoryExtractor
    return ClaudeMemoryExtractor(config={"enabled": True, "memory_paths": [str(sample_memory_dir)]})


async def test_validate_config_valid(memory_extractor):
    assert memory_extractor.validate_config() == []


async def test_validate_config_missing_paths():
    from library_server.vault_builder.extractors.claude_memory import ClaudeMemoryExtractor
    ext = ClaudeMemoryExtractor(config={"enabled": True})
    errors = ext.validate_config()
    assert any("memory_paths" in e for e in errors)


async def test_survey_returns_correct_counts(memory_extractor):
    result = await memory_extractor.survey()
    assert result.source_name == "claude_memory"
    assert result.file_count == 2


async def test_preview_shows_expected_files(memory_extractor):
    result = await memory_extractor.preview()
    assert len(result.files_to_create) == 2
    filenames = [f.split("/")[-1] for f in result.files_to_create]
    assert "project_greenfield_reset.md" in filenames


async def test_extract_writes_correct_files(memory_extractor, output_dir: Path):
    result = await memory_extractor.extract(output_dir / "memory")
    assert result.success is True
    assert len(result.files_written) == 2
    assert (output_dir / "memory" / "project_greenfield_reset.md").exists()


async def test_extract_frontmatter_valid(memory_extractor, output_dir: Path):
    await memory_extractor.extract(output_dir / "memory")
    content = (output_dir / "memory" / "project_greenfield_reset.md").read_text()
    fm = _parse_frontmatter(content)
    assert fm["trust"] == 0.7
    assert fm["extractor"] == "claude_memory"
    assert "source/memory" in fm["tags"]
    assert fm["source_type"] == "claude_memory"


async def test_extract_groups_by_type(memory_extractor, output_dir: Path):
    await memory_extractor.extract(output_dir / "memory")
    project = (output_dir / "memory" / "project_greenfield_reset.md").read_text()
    feedback = (output_dir / "memory" / "feedback_testing_required.md").read_text()
    assert "domain/project" in " ".join(_parse_frontmatter(project)["tags"])
    assert "domain/feedback" in " ".join(_parse_frontmatter(feedback)["tags"])


async def test_extract_idempotent(memory_extractor, output_dir: Path):
    result1 = await memory_extractor.extract(output_dir / "memory")
    result2 = await memory_extractor.extract(output_dir / "memory")
    assert result1.files_written == result2.files_written
