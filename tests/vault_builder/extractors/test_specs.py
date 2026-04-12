"""Tests for Specs extractor."""

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
def specs_extractor(sample_specs_dir: Path):
    from library_server.vault_builder.extractors.specs import SpecsExtractor
    return SpecsExtractor(config={"enabled": True, "source_path": str(sample_specs_dir)})


async def test_validate_config_valid(specs_extractor):
    errors = specs_extractor.validate_config()
    assert errors == []


async def test_validate_config_missing_path():
    from library_server.vault_builder.extractors.specs import SpecsExtractor
    ext = SpecsExtractor(config={"enabled": True, "source_path": "/nonexistent"})
    errors = ext.validate_config()
    assert any("source_path" in e for e in errors)


async def test_survey_returns_correct_counts(specs_extractor):
    result = await specs_extractor.survey()
    assert result.source_name == "specs"
    assert result.file_count == 4
    assert result.total_size_bytes > 0


async def test_survey_empty_source(tmp_path: Path):
    from library_server.vault_builder.extractors.specs import SpecsExtractor
    empty = tmp_path / "empty"
    empty.mkdir()
    ext = SpecsExtractor(config={"enabled": True, "source_path": str(empty)})
    result = await ext.survey()
    assert result.file_count == 0


async def test_preview_shows_expected_files(specs_extractor):
    result = await specs_extractor.preview()
    assert result.source_name == "specs"
    assert len(result.files_to_create) == 4
    filenames = [f.split("/")[-1] for f in result.files_to_create]
    assert "GLOSSARY.md" in filenames


async def test_extract_writes_correct_files(specs_extractor, output_dir: Path):
    result = await specs_extractor.extract(output_dir / "specs")
    assert result.success is True
    assert len(result.files_written) == 4
    assert (output_dir / "specs" / "GLOSSARY.md").exists()


async def test_extract_frontmatter_valid(specs_extractor, output_dir: Path):
    await specs_extractor.extract(output_dir / "specs")
    content = (output_dir / "specs" / "GLOSSARY.md").read_text()
    fm = _parse_frontmatter(content)
    assert fm["title"] == "GLOSSARY"
    assert fm["source_type"] == "spec"
    assert fm["extractor"] == "specs"
    assert fm["trust"] == 1.0
    assert "source/spec" in fm["tags"]
    assert "canonical" in fm["tags"]
    assert "trust/high" in fm["tags"]
    assert "extracted_at" in fm


async def test_extract_trust_values(specs_extractor, output_dir: Path):
    await specs_extractor.extract(output_dir / "specs")
    for name in ["GLOSSARY.md", "INVARIANTS.md", "TENANCY.md"]:
        content = (output_dir / "specs" / name).read_text()
        fm = _parse_frontmatter(content)
        assert fm["trust"] == 1.0, f"{name} should have trust 1.0"


async def test_extract_preserves_content_verbatim(specs_extractor, output_dir: Path, sample_specs_dir: Path):
    await specs_extractor.extract(output_dir / "specs")
    original = (sample_specs_dir / "GLOSSARY.md").read_text()
    extracted = (output_dir / "specs" / "GLOSSARY.md").read_text()
    body = extracted.split("---\n", 2)[2].strip()
    assert original.strip() in body


async def test_extract_generates_cross_references(specs_extractor, output_dir: Path):
    await specs_extractor.extract(output_dir / "specs")
    content = (output_dir / "specs" / "TENANCY.md").read_text()
    fm = _parse_frontmatter(content)
    related_str = " ".join(fm.get("related", []))
    assert "GLOSSARY" in related_str or "INVARIANTS" in related_str


async def test_extract_tags_format(specs_extractor, output_dir: Path):
    await specs_extractor.extract(output_dir / "specs")
    content = (output_dir / "specs" / "GLOSSARY.md").read_text()
    fm = _parse_frontmatter(content)
    for tag in fm["tags"]:
        assert "/" in tag or tag == "canonical", f"Tag '{tag}' should use layer/value format"


async def test_extract_idempotent(specs_extractor, output_dir: Path):
    result1 = await specs_extractor.extract(output_dir / "specs")
    result2 = await specs_extractor.extract(output_dir / "specs")
    assert result1.files_written == result2.files_written
    assert result1.success == result2.success
