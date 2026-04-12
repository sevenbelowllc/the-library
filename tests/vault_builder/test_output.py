"""Tests for OutputWriter — MD generation with YAML frontmatter."""

from __future__ import annotations

from pathlib import Path

import yaml


def test_write_file_creates_md_with_frontmatter(tmp_path: Path):
    from library_server.vault_builder.output import OutputWriter

    writer = OutputWriter(base_dir=tmp_path)
    writer.write_file(
        subdir="specs",
        filename="GLOSSARY.md",
        title="Glossary",
        source_type="spec",
        source_path="library-reading-room/specs/GLOSSARY.md",
        extractor="specs",
        trust=1.0,
        domain="glossary",
        tags=["source/spec", "domain/glossary", "trust/high"],
        related=[],
        body="# Glossary\n\nTerms and definitions.",
    )
    outfile = tmp_path / "specs" / "GLOSSARY.md"
    assert outfile.exists()
    content = outfile.read_text()
    assert content.startswith("---\n")
    parts = content.split("---\n", 2)
    fm = yaml.safe_load(parts[1])
    assert fm["title"] == "Glossary"
    assert fm["trust"] == 1.0
    assert fm["extractor"] == "specs"
    assert "source/spec" in fm["tags"]
    assert "# Glossary" in parts[2]


def test_write_file_creates_subdirectories(tmp_path: Path):
    from library_server.vault_builder.output import OutputWriter

    writer = OutputWriter(base_dir=tmp_path)
    writer.write_file(
        subdir="repos/compliance-core/communities",
        filename="auth-middleware.md",
        title="Auth Middleware Community",
        source_type="code_repo",
        source_path="compliance-core",
        extractor="axon_bridge",
        trust=1.0,
        domain="auth",
        tags=["source/code", "domain/auth"],
        related=["[[clerk-jwt-verification]]"],
        body="# Auth Middleware\n\nCommunity details.",
    )
    outfile = tmp_path / "repos" / "compliance-core" / "communities" / "auth-middleware.md"
    assert outfile.exists()


def test_write_file_includes_related_links(tmp_path: Path):
    from library_server.vault_builder.output import OutputWriter

    writer = OutputWriter(base_dir=tmp_path)
    writer.write_file(
        subdir="specs", filename="test.md", title="Test", source_type="spec",
        source_path="specs/test", extractor="specs", trust=1.0, domain="test",
        tags=[], related=["[[GLOSSARY]]", "[[INVARIANTS#tenant-isolation]]"], body="Content here.",
    )
    content = (tmp_path / "specs" / "test.md").read_text()
    parts = content.split("---\n", 2)
    fm = yaml.safe_load(parts[1])
    assert "[[GLOSSARY]]" in fm["related"]
    assert "[[INVARIANTS#tenant-isolation]]" in fm["related"]


def test_write_file_extracted_at_present(tmp_path: Path):
    from library_server.vault_builder.output import OutputWriter

    writer = OutputWriter(base_dir=tmp_path)
    writer.write_file(
        subdir="test", filename="file.md", title="File", source_type="test",
        source_path="test/file", extractor="test", trust=0.5, domain="test",
        tags=[], related=[], body="Body.",
    )
    content = (tmp_path / "test" / "file.md").read_text()
    parts = content.split("---\n", 2)
    fm = yaml.safe_load(parts[1])
    assert "extracted_at" in fm


def test_write_file_idempotent(tmp_path: Path):
    from library_server.vault_builder.output import OutputWriter

    writer = OutputWriter(base_dir=tmp_path)
    kwargs = dict(
        subdir="test", filename="same.md", title="Same", source_type="test",
        source_path="test/same", extractor="test", trust=0.5, domain="test",
        tags=[], related=[], body="Same body.",
    )
    writer.write_file(**kwargs)
    content1 = (tmp_path / "test" / "same.md").read_text()
    writer.write_file(**kwargs)
    content2 = (tmp_path / "test" / "same.md").read_text()
    parts1 = content1.split("---\n", 2)
    parts2 = content2.split("---\n", 2)
    fm1 = yaml.safe_load(parts1[1])
    fm2 = yaml.safe_load(parts2[1])
    assert fm1["title"] == fm2["title"]
    assert fm1["trust"] == fm2["trust"]
    assert parts1[2] == parts2[2]


def test_write_manifest(tmp_path: Path):
    from library_server.vault_builder.output import OutputWriter
    from library_server.vault_builder.types import ExtractResult

    writer = OutputWriter(base_dir=tmp_path)
    results = [
        ExtractResult(source_name="specs", files_written=["a.md", "b.md"], files_skipped=[], errors=[], duration_seconds=2.0, success=True),
        ExtractResult(source_name="jira", files_written=[], files_skipped=[], errors=["Connection refused"], duration_seconds=3.0, success=False),
    ]
    writer.write_manifest(results, total_duration=5.0)
    manifest = tmp_path / "_build-manifest.md"
    assert manifest.exists()
    content = manifest.read_text()
    assert "specs" in content
    assert "success" in content
    assert "jira" in content
    assert "failed" in content
