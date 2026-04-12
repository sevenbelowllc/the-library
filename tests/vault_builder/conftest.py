"""Shared fixtures for vault_builder tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from library_server.vault_builder.output import OutputWriter


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Provide a temporary output directory for extractors."""
    out = tmp_path / "raw"
    out.mkdir()
    return out


@pytest.fixture
def output_writer(output_dir: Path) -> OutputWriter:
    """Provide an OutputWriter pointed at temp dir."""
    return OutputWriter(base_dir=output_dir)


@pytest.fixture
def sample_specs_dir(tmp_path: Path) -> Path:
    """Create a minimal specs directory with 3 sample spec files."""
    specs = tmp_path / "specs"
    specs.mkdir()

    (specs / "GLOSSARY.md").write_text(
        "# GLOSSARY\n\n"
        "## Tenant\n\n"
        "An organization using the platform. Maps to Clerk organization.\n\n"
        "## Control\n\n"
        "A compliance requirement from a framework.\n"
    )
    (specs / "INVARIANTS.md").write_text(
        "# INVARIANTS\n\n"
        "## INV-001: Tenant Isolation\n\n"
        "Every database query MUST include tenant_id in WHERE clause.\n\n"
        "## INV-002: Audit Immutability\n\n"
        "Audit log entries MUST never be modified or deleted.\n"
    )
    (specs / "TENANCY.md").write_text(
        "# TENANCY\n\n"
        "## Multi-Org Model\n\n"
        "Uses Clerk organizations as tenant boundary.\n"
        "See [[GLOSSARY#Tenant]] for canonical definition.\n"
        "See [[INVARIANTS#INV-001]] for isolation rules.\n"
    )
    (specs / "INDEX.md").write_text(
        "# INDEX\n\n"
        "| File | Purpose |\n"
        "|------|---------|\n"
        "| GLOSSARY.md | Canonical terms |\n"
        "| INVARIANTS.md | Non-negotiable constraints |\n"
        "| TENANCY.md | Multi-org model |\n"
    )
    return specs


@pytest.fixture
def sample_memory_dir(tmp_path: Path) -> Path:
    """Create a minimal memory directory with sample files."""
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "MEMORY.md").write_text(
        "- [Greenfield Reset](project_greenfield_reset.md) — Project reset\n"
        "- [Testing Required](feedback_testing_required.md) — Hard requirement\n"
    )
    (mem / "project_greenfield_reset.md").write_text(
        "---\n"
        "name: Greenfield Reset\n"
        "description: Project reset to greenfield state\n"
        "type: project\n"
        "---\n\n"
        "Project was reset. 11 spec files are canonical.\n"
    )
    (mem / "feedback_testing_required.md").write_text(
        "---\n"
        "name: Automated Testing Required\n"
        "description: All code must have automated tests at 90%+ coverage\n"
        "type: feedback\n"
        "---\n\n"
        "HARD REQUIREMENT: All code must have automated tests.\n"
    )
    return mem


@pytest.fixture
def sample_session_dir(tmp_path: Path) -> Path:
    """Create a minimal session context directory."""
    sessions = tmp_path / "session-context"
    sessions.mkdir()
    (sessions / "01-architecture.md").write_text(
        "# Architecture Decisions\n\n"
        "## Decision: PostgreSQL over MongoDB\n\n"
        "Chose PostgreSQL for relational data model and RLS support.\n"
    )
    (sessions / "02-auth-migration.md").write_text(
        "# Auth Migration\n\n"
        "Migrated from Auth0 to Clerk for organization management.\n"
        "This supersedes all Auth0 references in older documents.\n"
    )
    return sessions


@pytest.fixture
def sample_notebooklm_dir(tmp_path: Path) -> Path:
    """Create a minimal NotebookLM export directory."""
    nlm = tmp_path / "notebooklm-exports"
    nlm.mkdir()
    (nlm / "compliance-overview.md").write_text(
        "# Compliance Overview\n\n"
        "Summary of the compliance management platform.\n"
    )
    summaries = tmp_path / "notebooklm-summaries"
    summaries.mkdir()
    (summaries / "architecture-summary.md").write_text(
        "# Architecture Summary\n\n"
        "AI-generated summary of the system architecture.\n"
    )
    return nlm


@pytest.fixture
def sample_obsidian_vault(tmp_path: Path) -> Path:
    """Create a minimal Obsidian vault structure."""
    vault = tmp_path / "compliance-os-kb"
    vault.mkdir()
    (vault / ".obsidian").mkdir()
    (vault / ".obsidian" / "app.json").write_text("{}")

    # Wiki articles
    wiki = vault / "wiki"
    wiki.mkdir()
    (wiki / "auth-system.md").write_text(
        "---\ntitle: Auth System\n---\n\n"
        "# Auth System\n\n"
        "Uses [[Clerk]] for authentication. See [[INVARIANTS#INV-001]].\n"
    )

    # Raw docs
    raw = vault / "raw"
    raw.mkdir()
    paul = raw / "paul-gsd-phases"
    paul.mkdir()
    (paul / "phase-01.md").write_text(
        "# Phase 01: Understanding\n\n"
        "Initial exploration of the compliance domain.\n"
        "We used Supabase for database hosting.\n"
    )

    # Excluded directories
    jira_dir = raw / "jira-tickets"
    jira_dir.mkdir()
    (jira_dir / "ticket.md").write_text("Should be excluded")

    (vault / ".git").mkdir()

    return vault


def parse_frontmatter(content: str) -> dict:
    """Parse YAML frontmatter from MD content."""
    parts = content.split("---\n", 2)
    if len(parts) < 3:
        return {}
    return yaml.safe_load(parts[1]) or {}
