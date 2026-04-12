"""Tests for the direct Jira REST API client."""
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch


class TestFetchIssueSummary:
    """Tests for fetch_issue_summary."""

    async def test_successful_fetch_returns_correct_dict(self):
        """A 200 response returns the expected normalized dict."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "key": "COS-42",
            "fields": {
                "summary": "Implement Jira REST client",
                "status": {"name": "In Progress"},
            },
        }

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "library_server.hooks.jira_client.httpx.AsyncClient",
            return_value=mock_client,
        ):
            from library_server.hooks.jira_client import fetch_issue_summary

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

    async def test_404_returns_none(self):
        """A 404 response returns None."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "library_server.hooks.jira_client.httpx.AsyncClient",
            return_value=mock_client,
        ):
            from library_server.hooks.jira_client import fetch_issue_summary

            result = await fetch_issue_summary(
                base_url="https://example.atlassian.net",
                api_token="secret-token",
                email="user@example.com",
                issue_key="COS-99",
            )

        assert result is None

    async def test_network_error_returns_none(self):
        """A network exception returns None rather than raising."""
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.RequestError(
            "connection failed", request=MagicMock()
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "library_server.hooks.jira_client.httpx.AsyncClient",
            return_value=mock_client,
        ):
            from library_server.hooks.jira_client import fetch_issue_summary

            result = await fetch_issue_summary(
                base_url="https://example.atlassian.net",
                api_token="secret-token",
                email="user@example.com",
                issue_key="COS-42",
            )

        assert result is None
