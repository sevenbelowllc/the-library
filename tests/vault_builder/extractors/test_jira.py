"""Tests for Jira extractor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml

SAMPLE_ISSUES = [
    {
        "key": "DEIOCAP-1",
        "fields": {
            "summary": "AI Agent Architecture", "description": "Design the AI agent system.",
            "issuetype": {"name": "Epic"}, "status": {"name": "Done"},
            "assignee": {"displayName": "Paul"}, "labels": ["ai-agents"],
            "issuelinks": [], "comment": {"comments": []},
        },
    },
    {
        "key": "DEIOCAP-10",
        "fields": {
            "summary": "Data Pipeline Design", "description": "Design the data ingestion pipeline.",
            "issuetype": {"name": "Story"}, "status": {"name": "In Progress"},
            "assignee": None, "labels": ["data-pipeline"],
            "issuelinks": [{"type": {"name": "is child of"}, "outwardIssue": {"key": "DEIOCAP-1"}}],
            "comment": {"comments": [{"body": "Started work on this."}]},
        },
    },
    {
        "key": "DEIOCAP-20",
        "fields": {
            "summary": "Fix login bug", "description": None,
            "issuetype": {"name": "Bug"}, "status": {"name": "To Do"},
            "assignee": None, "labels": [],
            "issuelinks": [], "comment": {"comments": []},
        },
    },
]


def _parse_frontmatter(content: str) -> dict:
    parts = content.split("---\n", 2)
    if len(parts) < 3:
        return {}
    return yaml.safe_load(parts[1]) or {}


@pytest.fixture
def jira_extractor(monkeypatch):
    monkeypatch.setenv("JIRA_API_TOKEN", "test-token")
    monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
    from library_server.vault_builder.extractors.jira import JiraExtractor
    return JiraExtractor(config={
        "enabled": True, "instance": "sevenbelow.atlassian.net",
        "cloud_id": "test-cloud-id", "projects": ["DEIOCAP"], "auth": "api_token",
    })


async def test_validate_config_valid(jira_extractor):
    assert jira_extractor.validate_config() == []


async def test_validate_config_missing_projects(monkeypatch):
    monkeypatch.setenv("JIRA_API_TOKEN", "test-token")
    monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
    from library_server.vault_builder.extractors.jira import JiraExtractor
    ext = JiraExtractor(config={"enabled": True})
    errors = ext.validate_config()
    assert any("projects" in e for e in errors)


async def test_validate_config_missing_env_vars(monkeypatch):
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    from library_server.vault_builder.extractors.jira import JiraExtractor
    ext = JiraExtractor(config={"enabled": True, "projects": ["DEIOCAP"]})
    errors = ext.validate_config()
    assert any("JIRA_API_TOKEN" in e for e in errors)
    assert any("JIRA_EMAIL" in e for e in errors)


async def test_extract_writes_correct_files(jira_extractor, output_dir: Path):
    with patch.object(jira_extractor, "_fetch_issues", new_callable=AsyncMock, return_value=SAMPLE_ISSUES):
        result = await jira_extractor.extract(output_dir / "jira")
    assert result.success is True
    assert len(result.files_written) == 3


async def test_extract_trust_varies_by_status(jira_extractor, output_dir: Path):
    with patch.object(jira_extractor, "_fetch_issues", new_callable=AsyncMock, return_value=SAMPLE_ISSUES):
        await jira_extractor.extract(output_dir / "jira")
    done_file = output_dir / "jira" / "DEIOCAP" / "DEIOCAP-1.md"
    assert _parse_frontmatter(done_file.read_text())["trust"] == 0.8
    ip_file = output_dir / "jira" / "DEIOCAP" / "DEIOCAP-10.md"
    assert _parse_frontmatter(ip_file.read_text())["trust"] == 0.6
    todo_file = output_dir / "jira" / "DEIOCAP" / "DEIOCAP-20.md"
    assert _parse_frontmatter(todo_file.read_text())["trust"] == 0.5


async def test_extract_handles_missing_fields(jira_extractor, output_dir: Path):
    with patch.object(jira_extractor, "_fetch_issues", new_callable=AsyncMock, return_value=SAMPLE_ISSUES):
        result = await jira_extractor.extract(output_dir / "jira")
    assert result.success is True
    todo_file = output_dir / "jira" / "DEIOCAP" / "DEIOCAP-20.md"
    assert todo_file.exists()


async def test_extract_generates_issue_links(jira_extractor, output_dir: Path):
    with patch.object(jira_extractor, "_fetch_issues", new_callable=AsyncMock, return_value=SAMPLE_ISSUES):
        await jira_extractor.extract(output_dir / "jira")
    story_file = output_dir / "jira" / "DEIOCAP" / "DEIOCAP-10.md"
    fm = _parse_frontmatter(story_file.read_text())
    related_str = " ".join(fm.get("related", []))
    assert "DEIOCAP-1" in related_str


async def test_extract_frontmatter_valid(jira_extractor, output_dir: Path):
    with patch.object(jira_extractor, "_fetch_issues", new_callable=AsyncMock, return_value=SAMPLE_ISSUES):
        await jira_extractor.extract(output_dir / "jira")
    for md in (output_dir / "jira").rglob("*.md"):
        fm = _parse_frontmatter(md.read_text())
        assert fm["extractor"] == "jira"
        assert "source/jira" in fm["tags"]
        assert "extracted_at" in fm


async def test_extract_status_tags(jira_extractor, output_dir: Path):
    with patch.object(jira_extractor, "_fetch_issues", new_callable=AsyncMock, return_value=SAMPLE_ISSUES):
        await jira_extractor.extract(output_dir / "jira")
    done = _parse_frontmatter((output_dir / "jira" / "DEIOCAP" / "DEIOCAP-1.md").read_text())
    assert "done" in done["tags"]
    ip = _parse_frontmatter((output_dir / "jira" / "DEIOCAP" / "DEIOCAP-10.md").read_text())
    assert "in-progress" in ip["tags"]


# ---------------------------------------------------------------------------
# survey() tests
# ---------------------------------------------------------------------------

async def test_survey_returns_correct_counts(jira_extractor):
    with patch.object(jira_extractor, "_fetch_issues", new_callable=AsyncMock, return_value=SAMPLE_ISSUES):
        result = await jira_extractor.survey()
    assert result.source_name == "jira"
    assert result.file_count == 3
    assert result.health == "connected"


async def test_survey_handles_fetch_error(jira_extractor):
    with patch.object(jira_extractor, "_fetch_issues", new_callable=AsyncMock, side_effect=Exception("Network error")):
        result = await jira_extractor.survey()
    assert result.file_count == 0


# ---------------------------------------------------------------------------
# preview() tests
# ---------------------------------------------------------------------------

async def test_preview_shows_expected_files(jira_extractor):
    with patch.object(jira_extractor, "_fetch_issues", new_callable=AsyncMock, return_value=SAMPLE_ISSUES):
        result = await jira_extractor.preview()
    assert len(result.files_to_create) == 3
    assert any("DEIOCAP-1" in f for f in result.files_to_create)


async def test_preview_handles_fetch_error(jira_extractor):
    with patch.object(jira_extractor, "_fetch_issues", new_callable=AsyncMock, side_effect=Exception("Network error")):
        result = await jira_extractor.preview()
    assert result.files_to_create == []
