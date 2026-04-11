"""Tests for PM adapter module."""

from __future__ import annotations

import pytest

from library_server.pm.adapter import PMAdapter
from library_server.pm.jira import JiraAdapter
from library_server.pm.linear import LinearAdapter
from library_server.types import TaskStatus


class TestJiraAdapter:
    """Tests for Jira adapter — uses mocked MCP calls."""

    def test_implements_interface(self):
        """JiraAdapter should implement PMAdapter."""
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        assert isinstance(adapter, PMAdapter)

    @pytest.mark.asyncio
    async def test_create_task_returns_task_result(self, mocker):
        """create_task should return a TaskResult with correct fields."""
        adapter = JiraAdapter(site_url="https://test.atlassian.net")

        # Mock the MCP call
        mocker.patch.object(
            adapter, "_call_mcp",
            return_value={
                "key": "PROJ-123",
                "fields": {"summary": "Test task", "status": {"name": "To Do"}},
                "self": "https://test.atlassian.net/rest/api/3/issue/PROJ-123",
            },
        )

        result = await adapter.create_task(
            project_key="PROJ",
            summary="Test task",
            description="Test description",
            labels=["core"],
        )

        assert result.task_id == "PROJ-123"
        assert result.summary == "Test task"
        assert result.project_key == "PROJ"

    @pytest.mark.asyncio
    async def test_query_tasks_returns_list(self, mocker):
        """query_tasks should return a list of TaskResults."""
        adapter = JiraAdapter(site_url="https://test.atlassian.net")

        mocker.patch.object(
            adapter, "_call_mcp",
            return_value={
                "issues": [
                    {"key": "PROJ-1", "fields": {"summary": "Task 1", "status": {"name": "To Do"}}},
                    {"key": "PROJ-2", "fields": {"summary": "Task 2", "status": {"name": "In Progress"}}},
                ],
            },
        )

        results = await adapter.query_tasks("PROJ")
        assert len(results) == 2
        assert results[0].task_id == "PROJ-1"


class TestLinearAdapter:
    """Tests for Linear adapter — uses mocked HTTP calls."""

    def test_implements_interface(self):
        """LinearAdapter should implement PMAdapter."""
        adapter = LinearAdapter(api_key="test-key")
        assert isinstance(adapter, PMAdapter)

    @pytest.mark.asyncio
    async def test_create_task_returns_task_result(self, mocker):
        """create_task should return a TaskResult with correct fields."""
        adapter = LinearAdapter(api_key="test-key")

        mocker.patch.object(
            adapter, "_graphql",
            return_value={
                "data": {
                    "issueCreate": {
                        "issue": {
                            "id": "abc-123",
                            "identifier": "PROJ-42",
                            "title": "Test task",
                            "state": {"name": "Todo"},
                            "url": "https://linear.app/team/PROJ-42",
                        }
                    }
                }
            },
        )

        result = await adapter.create_task(
            project_key="PROJ",
            summary="Test task",
            description="Test description",
        )

        assert result.task_id == "PROJ-42"
        assert result.summary == "Test task"
