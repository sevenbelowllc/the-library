"""Tests for PM adapter module."""

from __future__ import annotations

from unittest.mock import MagicMock

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


# --- Extended Jira tests ---

class TestJiraAdapterExtended:
    """Extended Jira adapter tests for uncovered methods."""

    @pytest.mark.asyncio
    async def test_call_mcp_raises(self):
        """_call_mcp should raise NotImplementedError."""
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        with pytest.raises(NotImplementedError, match="MCP calls are made"):
            await adapter._call_mcp("test", {})

    @pytest.mark.asyncio
    async def test_create_epic(self, mocker):
        """create_epic should return an EpicResult."""
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        mocker.patch.object(
            adapter, "_call_mcp",
            return_value={
                "key": "PROJ-E1",
                "self": "https://test.atlassian.net/rest/api/3/issue/PROJ-E1",
            },
        )
        result = await adapter.create_epic("PROJ", "My Epic", "Epic desc")
        assert result.epic_id == "PROJ-E1"
        assert result.project_key == "PROJ"
        assert result.summary == "My Epic"
        adapter._call_mcp.assert_called_once_with("createJiraIssue", {
            "projectKey": "PROJ",
            "issueType": "Epic",
            "summary": "My Epic",
            "description": "Epic desc",
        })

    @pytest.mark.asyncio
    async def test_update_task_with_comment(self, mocker):
        """update_task should add a comment when provided."""
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        call_log = []

        async def mock_mcp(tool_name, params):
            call_log.append(tool_name)
            if tool_name == "getJiraIssue":
                return {"key": "PROJ-1", "fields": {"summary": "Task", "status": {"name": "Open"}}}
            return {}

        mocker.patch.object(adapter, "_call_mcp", side_effect=mock_mcp)
        result = await adapter.update_task("PROJ-1", comment="Progress note")
        assert "addCommentToJiraIssue" in call_log
        assert "getJiraIssue" in call_log
        assert result.task_id == "PROJ-1"

    @pytest.mark.asyncio
    async def test_update_task_with_status_transition(self, mocker):
        """update_task should find and execute the right transition."""
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        call_log = []

        async def mock_mcp(tool_name, params):
            call_log.append(tool_name)
            if tool_name == "getTransitionsForJiraIssue":
                return {"transitions": [
                    {"id": "11", "name": "To Do"},
                    {"id": "21", "name": "In Progress"},
                    {"id": "31", "name": "Done"},
                ]}
            if tool_name == "getJiraIssue":
                return {"key": "PROJ-1", "fields": {"summary": "Task", "status": {"name": "Done"}}}
            return {}

        mocker.patch.object(adapter, "_call_mcp", side_effect=mock_mcp)
        result = await adapter.update_task("PROJ-1", status="Done")
        assert "getTransitionsForJiraIssue" in call_log
        assert "transitionJiraIssue" in call_log
        assert result.status == TaskStatus.DONE

    @pytest.mark.asyncio
    async def test_update_task_status_not_found(self, mocker):
        """update_task should still return result when transition name doesn't match."""
        adapter = JiraAdapter(site_url="https://test.atlassian.net")

        async def mock_mcp(tool_name, params):
            if tool_name == "getTransitionsForJiraIssue":
                return {"transitions": [{"id": "11", "name": "To Do"}]}
            if tool_name == "getJiraIssue":
                return {"key": "PROJ-1", "fields": {"summary": "Task", "status": {"name": "To Do"}}}
            return {}

        mocker.patch.object(adapter, "_call_mcp", side_effect=mock_mcp)
        result = await adapter.update_task("PROJ-1", status="Nonexistent")
        assert result.task_id == "PROJ-1"

    @pytest.mark.asyncio
    async def test_query_tasks_with_filters(self, mocker):
        """query_tasks should build JQL with status and label filters."""
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        mocker.patch.object(
            adapter, "_call_mcp",
            return_value={"issues": [
                {"key": "PROJ-1", "fields": {"summary": "Bug", "status": {"name": "Open"}, "labels": ["bug"]}},
            ]},
        )
        results = await adapter.query_tasks("PROJ", {"status": "Open", "labels": ["bug", "urgent"]})
        assert len(results) == 1
        jql = adapter._call_mcp.call_args[0][1]["jql"]
        assert "status = 'Open'" in jql
        assert "labels in (bug,urgent)" in jql

    @pytest.mark.asyncio
    async def test_sync_state(self, mocker):
        """sync_state should categorize tasks by status."""
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        mocker.patch.object(
            adapter, "_call_mcp",
            return_value={"issues": [
                {"key": "PROJ-1", "fields": {"summary": "Open task", "status": {"name": "Open"}}},
                {"key": "PROJ-2", "fields": {"summary": "Done task", "status": {"name": "Done"}}},
                {"key": "PROJ-3", "fields": {"summary": "Blocked", "status": {"name": "Blocked"}}},
            ]},
        )
        state = await adapter.sync_state("PROJ")
        assert state.project_key == "PROJ"
        assert len(state.open_tasks) == 1
        assert len(state.recently_closed) == 1
        assert len(state.blocked_tasks) == 1

    @pytest.mark.asyncio
    async def test_get_transitions(self, mocker):
        """get_transitions should map Jira transitions to Transition objects."""
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        mocker.patch.object(
            adapter, "_call_mcp",
            return_value={"transitions": [
                {"id": "11", "name": "To Do", "to": {"name": "To Do"}},
                {"id": "21", "name": "In Progress", "to": {"name": "In Progress"}},
                {"id": "31", "name": "Done", "to": {"name": "Done"}},
            ]},
        )
        transitions = await adapter.get_transitions("PROJ-1")
        assert len(transitions) == 3
        assert transitions[0].transition_id == "11"
        assert transitions[0].to_status == TaskStatus.OPEN
        assert transitions[2].to_status == TaskStatus.DONE


# --- Extended Linear tests ---

class TestLinearAdapterExtended:
    """Extended Linear adapter tests for uncovered methods."""

    @pytest.mark.asyncio
    async def test_create_epic(self, mocker):
        """create_epic should return an EpicResult."""
        adapter = LinearAdapter(api_key="test-key")
        mocker.patch.object(
            adapter, "_graphql",
            return_value={
                "data": {
                    "projectCreate": {
                        "project": {
                            "id": "proj-123",
                            "name": "My Epic",
                            "url": "https://linear.app/proj-123",
                        }
                    }
                }
            },
        )
        result = await adapter.create_epic("TEAM-1", "My Epic", "Epic desc")
        assert result.epic_id == "proj-123"
        assert result.summary == "My Epic"
        assert result.url == "https://linear.app/proj-123"

    @pytest.mark.asyncio
    async def test_update_task_with_comment(self, mocker):
        """update_task with comment should call commentCreate mutation."""
        adapter = LinearAdapter(api_key="test-key")
        calls = []

        async def mock_graphql(query, variables=None):
            calls.append(query.strip()[:20])
            if "commentCreate" in query:
                return {"data": {"commentCreate": {"comment": {"id": "c1"}}}}
            return {
                "data": {
                    "issue": {
                        "id": "abc", "identifier": "PROJ-42",
                        "title": "Task", "state": {"name": "In Progress"},
                        "url": "https://linear.app/PROJ-42",
                    }
                }
            }

        mocker.patch.object(adapter, "_graphql", side_effect=mock_graphql)
        result = await adapter.update_task("abc", comment="Progress note")
        assert result.task_id == "PROJ-42"
        assert result.status == TaskStatus.IN_PROGRESS
        assert len(calls) == 2  # comment + fetch

    @pytest.mark.asyncio
    async def test_update_task_no_comment(self, mocker):
        """update_task without comment should only fetch issue."""
        adapter = LinearAdapter(api_key="test-key")
        mocker.patch.object(
            adapter, "_graphql",
            return_value={
                "data": {
                    "issue": {
                        "id": "abc", "identifier": "PROJ-42",
                        "title": "Task", "state": {"name": "Done"},
                        "url": "",
                    }
                }
            },
        )
        result = await adapter.update_task("abc")
        assert result.status == TaskStatus.DONE
        adapter._graphql.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_tasks(self, mocker):
        """query_tasks should return list of TaskResults."""
        adapter = LinearAdapter(api_key="test-key")
        mocker.patch.object(
            adapter, "_graphql",
            return_value={
                "data": {
                    "team": {
                        "issues": {
                            "nodes": [
                                {
                                    "id": "i1", "identifier": "PROJ-1",
                                    "title": "Bug fix", "state": {"name": "Todo"},
                                    "url": "https://linear.app/PROJ-1",
                                    "labels": {"nodes": [{"name": "bug"}]},
                                },
                                {
                                    "id": "i2", "identifier": "PROJ-2",
                                    "title": "Feature", "state": {"name": "In Progress"},
                                    "url": "https://linear.app/PROJ-2",
                                },
                            ]
                        }
                    }
                }
            },
        )
        results = await adapter.query_tasks("TEAM-1")
        assert len(results) == 2
        assert results[0].labels == ["bug"]
        assert results[1].status == TaskStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_sync_state(self, mocker):
        """sync_state should categorize tasks by status."""
        adapter = LinearAdapter(api_key="test-key")
        mocker.patch.object(
            adapter, "_graphql",
            return_value={
                "data": {
                    "team": {
                        "issues": {
                            "nodes": [
                                {"id": "1", "identifier": "P-1", "title": "Open",
                                 "state": {"name": "Todo"}, "url": ""},
                                {"id": "2", "identifier": "P-2", "title": "Closed",
                                 "state": {"name": "Done"}, "url": ""},
                            ]
                        }
                    }
                }
            },
        )
        state = await adapter.sync_state("TEAM-1")
        assert len(state.open_tasks) == 1
        assert len(state.recently_closed) == 1

    @pytest.mark.asyncio
    async def test_get_transitions(self, mocker):
        """get_transitions should return workflow states as Transitions."""
        adapter = LinearAdapter(api_key="test-key")
        mocker.patch.object(
            adapter, "_graphql",
            return_value={
                "data": {
                    "workflowStates": {
                        "nodes": [
                            {"id": "s1", "name": "Backlog"},
                            {"id": "s2", "name": "In Progress"},
                            {"id": "s3", "name": "Done"},
                        ]
                    }
                }
            },
        )
        transitions = await adapter.get_transitions("PROJ-1")
        assert len(transitions) == 3
        assert transitions[0].to_status == TaskStatus.OPEN
        assert transitions[1].to_status == TaskStatus.IN_PROGRESS
        assert transitions[2].to_status == TaskStatus.DONE

    def test_import_error_handling(self, mocker):
        """LinearAdapter should raise ImportError when httpx is not available."""
        import library_server.pm.linear as linear_mod
        original = linear_mod.httpx
        try:
            linear_mod.httpx = None
            with pytest.raises(ImportError, match="httpx is required"):
                LinearAdapter(api_key="test-key")
        finally:
            linear_mod.httpx = original

    @pytest.mark.asyncio
    async def test_graphql_method(self, mocker):
        """_graphql should POST to Linear API."""
        adapter = LinearAdapter(api_key="test-key")
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"test": True}}
        mock_response.raise_for_status = MagicMock()

        async def mock_post(*args, **kwargs):
            return mock_response

        mocker.patch.object(adapter._client, "post", side_effect=mock_post)

        result = await adapter._graphql("query { test }", {"key": "val"})
        assert result == {"data": {"test": True}}
        adapter._client.post.assert_called_once_with("", json={"query": "query { test }", "variables": {"key": "val"}})

    @pytest.mark.asyncio
    async def test_graphql_no_variables(self, mocker):
        """_graphql without variables should omit them from payload."""
        adapter = LinearAdapter(api_key="test-key")
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {}}
        mock_response.raise_for_status = MagicMock()

        async def mock_post(*args, **kwargs):
            return mock_response

        mocker.patch.object(adapter._client, "post", side_effect=mock_post)

        await adapter._graphql("query { test }")
        adapter._client.post.assert_called_once_with("", json={"query": "query { test }"})
