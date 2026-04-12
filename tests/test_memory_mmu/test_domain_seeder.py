"""Tests for domain_seeder module — TDD first pass."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from library_server.memory.domain_seeder import seed_domains_from_claude_md


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_claude_md(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _parse_frontmatter(md_text: str) -> dict:
    """Extract YAML frontmatter from a markdown file."""
    if not md_text.startswith("---"):
        return {}
    end = md_text.index("---", 3)
    return yaml.safe_load(md_text[3:end])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_missing_claude_md_returns_empty_list(tmp_path: Path):
    """seed_domains_from_claude_md returns [] when CLAUDE.md does not exist."""
    claude_md = tmp_path / "nonexistent" / "CLAUDE.md"
    domains_dir = tmp_path / "domains"

    result = seed_domains_from_claude_md(claude_md, domains_dir)

    assert result == []


def test_creates_auth_domain_when_clerk_mentioned(tmp_path: Path):
    """Mentioning 'clerk' in CLAUDE.md should create the auth domain file."""
    claude_md = tmp_path / "CLAUDE.md"
    domains_dir = tmp_path / "domains"
    _write_claude_md(claude_md, "Auth is handled via Clerk JWT verification.\n")

    result = seed_domains_from_claude_md(claude_md, domains_dir)

    assert "auth" in result
    auth_file = domains_dir / "auth.md"
    assert auth_file.exists()


def test_creates_database_domain_when_postgres_mentioned(tmp_path: Path):
    """Mentioning 'postgres' in CLAUDE.md should create the database domain file."""
    claude_md = tmp_path / "CLAUDE.md"
    domains_dir = tmp_path / "domains"
    _write_claude_md(claude_md, "Database: PostgreSQL via pg driver. Migrations in migrations/.\n")

    result = seed_domains_from_claude_md(claude_md, domains_dir)

    assert "database" in result
    assert (domains_dir / "database.md").exists()


def test_creates_multiple_domains_from_content(tmp_path: Path):
    """Content mentioning auth AND database keywords creates 2+ domain files."""
    claude_md = tmp_path / "CLAUDE.md"
    domains_dir = tmp_path / "domains"
    _write_claude_md(
        claude_md,
        "Auth via Clerk JWT. Database: PostgreSQL with sql migrations.\n",
    )

    result = seed_domains_from_claude_md(claude_md, domains_dir)

    assert len(result) >= 2
    assert "auth" in result
    assert "database" in result


def test_domain_file_has_valid_frontmatter(tmp_path: Path):
    """Created domain file should have required YAML frontmatter fields."""
    claude_md = tmp_path / "CLAUDE.md"
    domains_dir = tmp_path / "domains"
    _write_claude_md(claude_md, "Auth: Clerk JWT requireAuth guards.\n")

    seed_domains_from_claude_md(claude_md, domains_dir)

    auth_file = domains_dir / "auth.md"
    fm = _parse_frontmatter(auth_file.read_text(encoding="utf-8"))

    assert fm["domain"] == "auth"
    assert "keywords" in fm
    assert "starter" in fm["keywords"]
    assert isinstance(fm["keywords"]["starter"], list)
    assert len(fm["keywords"]["starter"]) > 0
    assert fm["keywords"]["learned"] == []
    assert "exclude" in fm
    assert "match_threshold" in fm
    assert "token_estimate" in fm


def test_domain_file_has_markdown_body(tmp_path: Path):
    """Created domain file should have a markdown body after the frontmatter."""
    claude_md = tmp_path / "CLAUDE.md"
    domains_dir = tmp_path / "domains"
    _write_claude_md(claude_md, "GraphQL resolvers typeDefs apollo server.\n")

    seed_domains_from_claude_md(claude_md, domains_dir)

    gql_file = domains_dir / "graphql.md"
    assert gql_file.exists()
    body = gql_file.read_text(encoding="utf-8")
    assert "## Graphql Domain" in body or "## GraphQL Domain" in body or "## Graphql" in body


def test_does_not_overwrite_existing_domain_file(tmp_path: Path):
    """seed_domains_from_claude_md should NOT overwrite existing domain files."""
    claude_md = tmp_path / "CLAUDE.md"
    domains_dir = tmp_path / "domains"
    domains_dir.mkdir(parents=True, exist_ok=True)
    _write_claude_md(claude_md, "Auth: requireAuth clerk jwt.\n")

    # Pre-write the auth domain file with custom content
    existing = domains_dir / "auth.md"
    existing.write_text("custom content", encoding="utf-8")

    seed_domains_from_claude_md(claude_md, domains_dir)

    # File should NOT be overwritten
    assert existing.read_text(encoding="utf-8") == "custom content"


def test_domains_dir_is_created_if_missing(tmp_path: Path):
    """domains_dir should be created automatically if it does not exist."""
    claude_md = tmp_path / "CLAUDE.md"
    domains_dir = tmp_path / "new" / "domains"
    _write_claude_md(claude_md, "Auth: Clerk JWT.\n")

    seed_domains_from_claude_md(claude_md, domains_dir)

    assert domains_dir.is_dir()


def test_no_match_returns_empty_list(tmp_path: Path):
    """Content with no recognizable patterns returns an empty list."""
    claude_md = tmp_path / "CLAUDE.md"
    domains_dir = tmp_path / "domains"
    _write_claude_md(claude_md, "This file talks about nothing relevant at all.\n")

    result = seed_domains_from_claude_md(claude_md, domains_dir)

    assert result == []


def test_returns_list_of_domain_names(tmp_path: Path):
    """Return value is a list of string domain names, not file paths."""
    claude_md = tmp_path / "CLAUDE.md"
    domains_dir = tmp_path / "domains"
    _write_claude_md(claude_md, "jest playwright test suite coverage.\n")

    result = seed_domains_from_claude_md(claude_md, domains_dir)

    assert isinstance(result, list)
    for item in result:
        assert isinstance(item, str)
        # Should be a name like "testing", not a file path
        assert "/" not in item
        assert item.endswith(".md") is False


def test_infrastructure_domain_matches_terraform(tmp_path: Path):
    """'terraform' keyword should create the infrastructure domain."""
    claude_md = tmp_path / "CLAUDE.md"
    domains_dir = tmp_path / "domains"
    _write_claude_md(claude_md, "Infrastructure managed via Terraform modules on GCP.\n")

    result = seed_domains_from_claude_md(claude_md, domains_dir)

    assert "infrastructure" in result


def test_frontend_domain_matches_nextjs(tmp_path: Path):
    """'next.js' or 'react' keyword should create the frontend domain."""
    claude_md = tmp_path / "CLAUDE.md"
    domains_dir = tmp_path / "domains"
    _write_claude_md(claude_md, "Frontend built with Next.js 15 and React 18.\n")

    result = seed_domains_from_claude_md(claude_md, domains_dir)

    assert "frontend" in result
