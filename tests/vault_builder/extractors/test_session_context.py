"""Tests for Session Context extractor."""

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
def session_extractor(sample_session_dir: Path):
    from library_server.vault_builder.extractors.session_context import SessionContextExtractor
    return SessionContextExtractor(config={"enabled": True, "source_path": str(sample_session_dir)})


async def test_validate_config_valid(session_extractor):
    assert session_extractor.validate_config() == []


async def test_validate_config_missing_path():
    from library_server.vault_builder.extractors.session_context import SessionContextExtractor
    ext = SessionContextExtractor(config={"enabled": True, "source_path": "/nonexistent"})
    errors = ext.validate_config()
    assert any("source_path" in e for e in errors)


async def test_survey_returns_correct_counts(session_extractor):
    result = await session_extractor.survey()
    assert result.file_count == 2


async def test_preview_shows_expected_files(session_extractor):
    result = await session_extractor.preview()
    assert len(result.files_to_create) == 2


async def test_extract_writes_correct_files(session_extractor, output_dir: Path):
    result = await session_extractor.extract(output_dir / "sessions")
    assert result.success is True
    assert len(result.files_written) == 2


async def test_extract_frontmatter_valid(session_extractor, output_dir: Path):
    await session_extractor.extract(output_dir / "sessions")
    content = (output_dir / "sessions" / "01-architecture.md").read_text()
    fm = _parse_frontmatter(content)
    assert fm["trust"] == 0.6
    assert fm["extractor"] == "session_context"
    assert "source/session" in fm["tags"]


async def test_extract_idempotent(session_extractor, output_dir: Path):
    result1 = await session_extractor.extract(output_dir / "sessions")
    result2 = await session_extractor.extract(output_dir / "sessions")
    assert result1.files_written == result2.files_written
