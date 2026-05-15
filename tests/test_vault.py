"""Tests for the vault module."""

from pathlib import Path

import pytest
import yaml

from library_server.vault.init import init_vault, VAULT_DIRS
from library_server.vault.validate import validate_vault
from library_server.vault.parse import parse_vault
from library_server.vault.ingest import ingest_source


# --- init tests ---


def test_init_vault_creates_karpathy_structure(tmp_path: Path):
    """init_vault should create _schema/, sources/, wiki/, archive/ directories."""
    vault_path = tmp_path / "test-vault"
    result = init_vault(str(vault_path))

    assert (vault_path / "_schema").is_dir()
    assert (vault_path / "sources").is_dir()
    assert (vault_path / "wiki").is_dir()
    assert (vault_path / "archive").is_dir()
    assert result["status"] == "created"
    assert result["path"] == str(vault_path)


def test_init_vault_creates_compile_protocol(tmp_path: Path):
    """init_vault should create CLAUDE.md compile protocol in vault root."""
    vault_path = tmp_path / "test-vault"
    init_vault(str(vault_path))

    claude_md = vault_path / "CLAUDE.md"
    assert claude_md.exists()
    content = claude_md.read_text()
    assert "compile" in content.lower()


def test_init_vault_creates_kb_yaml(tmp_path: Path):
    """init_vault should create kb.yaml compile order definition."""
    vault_path = tmp_path / "test-vault"
    init_vault(str(vault_path))

    kb_yaml = vault_path / "kb.yaml"
    assert kb_yaml.exists()


def test_init_vault_creates_obsidian_settings(tmp_path: Path):
    """init_vault should create .obsidian/app.json with wikilinks and excluded folders."""
    import json

    vault_path = tmp_path / "test-vault"
    init_vault(str(vault_path))

    app_json = vault_path / ".obsidian" / "app.json"
    assert app_json.exists()

    settings = json.loads(app_json.read_text())
    assert settings["useMarkdownLinks"] is False  # wikilinks enabled
    assert "sources/raw" in settings["userIgnoreFilters"]


def test_init_vault_idempotent(tmp_path: Path):
    """init_vault on existing vault should not destroy content."""
    vault_path = tmp_path / "test-vault"
    init_vault(str(vault_path))

    # Add a file to wiki/
    (vault_path / "wiki" / "existing.md").write_text("# Existing")

    result = init_vault(str(vault_path))
    assert result["status"] == "exists"
    assert (vault_path / "wiki" / "existing.md").exists()


# --- validate tests ---


def test_validate_vault_valid(tmp_path: Path):
    """validate_vault should return valid=True for a correctly structured vault."""
    vault_path = tmp_path / "valid-vault"
    init_vault(str(vault_path))
    result = validate_vault(str(vault_path))
    assert result["valid"] is True
    assert result["issues"] == []


def test_validate_vault_missing_dirs(tmp_path: Path):
    """validate_vault should flag missing directories."""
    vault_path = tmp_path / "bad-vault"
    vault_path.mkdir()
    (vault_path / "sources").mkdir()
    # Missing: _schema, wiki, archive

    result = validate_vault(str(vault_path))
    assert result["valid"] is False
    assert len(result["issues"]) == 5  # 3 missing dirs + 2 missing files (CLAUDE.md, kb.yaml)


def test_validate_vault_missing_compile_protocol(tmp_path: Path):
    """validate_vault should flag missing CLAUDE.md."""
    vault_path = tmp_path / "no-protocol"
    for d in VAULT_DIRS:
        (vault_path / d).mkdir(parents=True)

    result = validate_vault(str(vault_path))
    assert result["valid"] is False
    assert any("CLAUDE.md" in issue for issue in result["issues"])


def test_validate_vault_nonexistent(tmp_path: Path):
    """validate_vault should handle nonexistent paths."""
    result = validate_vault(str(tmp_path / "nope"))
    assert result["valid"] is False
    assert any("does not exist" in issue for issue in result["issues"])


# --- parse tests ---


def test_parse_vault_extracts_verify_tags(tmp_path: Path):
    """parse_vault should find [VERIFY] tags in wiki articles."""
    vault_path = tmp_path / "parse-vault"
    init_vault(str(vault_path))

    (vault_path / "wiki" / "security.md").write_text(
        "# Security\n\n"
        "The auth middleware is complete. [VERIFY] — need to confirm JWT validation works\n\n"
        "Rate limiting is in place. [VERIFY] — untested under load\n"
    )

    result = parse_vault(str(vault_path))
    verify_tags = [t for t in result["tags"] if t["tag_type"] == "VERIFY"]
    assert len(verify_tags) == 2
    assert all(t["source_file"].endswith("security.md") for t in verify_tags)


def test_parse_vault_extracts_conflict_tags(tmp_path: Path):
    """parse_vault should find [CONFLICT] tags."""
    vault_path = tmp_path / "conflict-vault"
    init_vault(str(vault_path))

    (vault_path / "wiki" / "frameworks.md").write_text(
        "# Frameworks\n\n"
        "Schema status: [CONFLICT] — Feb says PARTIAL, March says Implemented\n"
    )

    result = parse_vault(str(vault_path))
    conflict_tags = [t for t in result["tags"] if t["tag_type"] == "CONFLICT"]
    assert len(conflict_tags) == 1


def test_parse_vault_extracts_planned_tags(tmp_path: Path):
    """parse_vault should find [PLANNED] tags."""
    vault_path = tmp_path / "planned-vault"
    init_vault(str(vault_path))

    (vault_path / "wiki" / "features.md").write_text(
        "# Features\n\n"
        "Notification system [PLANNED] — scheduled for Q3\n"
    )

    result = parse_vault(str(vault_path))
    planned_tags = [t for t in result["tags"] if t["tag_type"] == "PLANNED"]
    assert len(planned_tags) == 1


def test_parse_vault_extracts_frontmatter(tmp_path: Path):
    """parse_vault should extract YAML frontmatter from wiki articles."""
    vault_path = tmp_path / "fm-vault"
    init_vault(str(vault_path))

    (vault_path / "wiki" / "domains.md").write_text(
        "---\n"
        "title: Domain Objects\n"
        "domain: core\n"
        "---\n\n"
        "# Domain Objects\n"
    )

    result = parse_vault(str(vault_path))
    assert len(result["articles"]) >= 1
    article = next(a for a in result["articles"] if a["filename"] == "domains.md")
    assert article["frontmatter"]["title"] == "Domain Objects"


def test_parse_vault_empty_wiki(tmp_path: Path):
    """parse_vault with no wiki articles should return empty lists."""
    vault_path = tmp_path / "empty-vault"
    init_vault(str(vault_path))

    result = parse_vault(str(vault_path))
    assert result["tags"] == []
    assert result["articles"] == []


# --- ingest tests ---


def test_ingest_source_file(tmp_path: Path):
    """ingest_source should copy a file into the correct tier/category bucket."""
    vault_path = tmp_path / "ingest-vault"
    init_vault(str(vault_path))

    # Create a source file
    source = tmp_path / "my-prd.md"
    source.write_text("# Product Requirements\n\nThis is a PRD.")

    result = ingest_source(
        vault_path=str(vault_path),
        source_path=str(source),
        tier="raw",
        category="prds",
    )

    assert result["status"] == "ingested"
    dest = vault_path / "sources" / "raw" / "prds" / "my-prd.md"
    assert dest.exists()
    assert dest.read_text() == source.read_text()


def test_ingest_source_directory(tmp_path: Path):
    """ingest_source should copy all files from a directory."""
    vault_path = tmp_path / "ingest-dir-vault"
    init_vault(str(vault_path))

    # Create source directory with files
    src_dir = tmp_path / "session-notes"
    src_dir.mkdir()
    (src_dir / "note1.md").write_text("# Note 1")
    (src_dir / "note2.md").write_text("# Note 2")

    result = ingest_source(
        vault_path=str(vault_path),
        source_path=str(src_dir),
        tier="llm-generated",
        category="session-notes",
    )

    assert result["status"] == "ingested"
    assert result["file_count"] == 2
    dest_dir = vault_path / "sources" / "llm-generated" / "session-notes"
    assert (dest_dir / "note1.md").exists()
    assert (dest_dir / "note2.md").exists()


def test_ingest_source_updates_kb_yaml(tmp_path: Path):
    """ingest_source should add new category to kb.yaml."""
    vault_path = tmp_path / "kb-update-vault"
    init_vault(str(vault_path))

    source = tmp_path / "doc.md"
    source.write_text("# Doc")

    ingest_source(
        vault_path=str(vault_path),
        source_path=str(source),
        tier="raw",
        category="new-category",
    )

    with open(vault_path / "kb.yaml") as f:
        kb = yaml.safe_load(f)
    assert "new-category" in kb["categories"]
