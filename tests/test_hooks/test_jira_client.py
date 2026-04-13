"""Tests for the hooks Jira client wrapper."""

import pytest
from unittest.mock import AsyncMock, patch

from library_server.hooks.jira_client import fetch_issue_summary
from library_server.pm.jira_client import JiraApiError


class TestFetchIssueSummary:
    """Tests for fetch_issue_summary."""

    @pytest.fixture(autouse=True)
    def setup_env(self, monkeypatch):
        monkeypatch.setenv("JIRA_EMAIL", "user@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "test-token")

    @pytest.mark.asyncio
    async def test_successful_fetch_returns_correct_dict(self):
        with patch("library_server.hooks.jira_client.JiraClient") as MockClient:
            instance = MockClient.return_value
            instance.get_issue = AsyncMock(return_value={
                "key": "COS-42",
                "fields": {
                    "summary": "Implement Jira REST client",
                    "status": {"name": "In Progress"},
                },
            })
            result = await fetch_issue_summary(
                base_url="https://example.atlassian.net",
                api_token="secret-token",
                email="user@example.com",
                issue_key="COS-42",
            )
        assert result == {
            "key": "COS-42",
            "summary": "Implement Jira REST client",
            "status": "In Progress",
        }

    @pytest.mark.asyncio
    async def test_api_error_returns_none(self):
        with patch("library_server.hooks.jira_client.JiraClient") as MockClient:
            instance = MockClient.return_value
            instance.get_issue = AsyncMock(
                side_effect=JiraApiError(404, "Not found", "/rest/api/3/issue/COS-99"),
            )
            result = await fetch_issue_summary(
                base_url="https://example.atlassian.net",
                api_token="secret-token",
                email="user@example.com",
                issue_key="COS-99",
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_env_vars_returns_none(self, monkeypatch):
        monkeypatch.delenv("JIRA_EMAIL", raising=False)
        monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
        result = await fetch_issue_summary(
            base_url="https://example.atlassian.net",
            api_token="secret-token",
            email="user@example.com",
            issue_key="COS-42",
        )
        assert result is None
