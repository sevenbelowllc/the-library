"""Tests for PM adapter module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from library_server.pm.adapter import PMAdapter
from library_server.pm.jira import JiraAdapter
from library_server.pm.linear import LinearAdapter
from library_server.types import TaskStatus


# ---------------------------------------------------------------------------
# Jira adapter tests — mock JiraClient methods directly
# ---------------------------------------------------------------------------


class TestJiraAdapter:
    """Tests for Jira adapter — mocks JiraClient methods."""

    def test_implements_interface(self, monkeypatch):
        """JiraAdapter should implement PMAdapter."""
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        assert isinstance(adapter, PMAdapter)

    @pytest.mark.asyncio
    async def test_create_task(self, monkeypatch):
        """create_task should call client.create_issue and return TaskResult."""
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        adapter.client.create_issue = AsyncMock(return_value={
            "key": "PROJ-123",
            "fields": {"summary": "Test task", "status": {"name": "To Do"}, "labels": ["core"]},
            "self": "https://test.atlassian.net/rest/api/3/issue/PROJ-123",
        })

        result = await adapter.create_task("PROJ", "Test task", "desc", labels=["core"])
        assert result.task_id == "PROJ-123"
        assert result.summary == "Test task"
        assert result.project_key == "PROJ"
        adapter.client.create_issue.assert_called_once()
        call_kwargs = adapter.client.create_issue.call_args.kwargs
        assert call_kwargs["parent_key"] == ""

    @pytest.mark.asyncio
    async def test_create_task_with_epic(self, monkeypatch):
        """create_task should pass epic_id as parent_key to the Jira client."""
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        adapter.client.create_issue = AsyncMock(return_value={
            "key": "PROJ-124",
            "self": "https://test.atlassian.net/rest/api/3/issue/PROJ-124",
        })

        result = await adapter.create_task(
            "PROJ", "Child task", "desc", labels=[], epic_id="PROJ-E1"
        )
        assert result.task_id == "PROJ-124"
        assert result.summary == "Child task"
        call_kwargs = adapter.client.create_issue.call_args.kwargs
        assert call_kwargs["parent_key"] == "PROJ-E1"

    @pytest.mark.asyncio
    async def test_create_epic(self, monkeypatch):
        """create_epic should return an EpicResult."""
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        adapter.client.create_issue = AsyncMock(return_value={
            "key": "PROJ-E1",
            "self": "https://test.atlassian.net/rest/api/3/issue/PROJ-E1",
        })

        result = await adapter.create_epic("PROJ", "My Epic", "Epic desc")
        assert result.epic_id == "PROJ-E1"
        assert result.project_key == "PROJ"
        assert result.summary == "My Epic"

    @pytest.mark.asyncio
    async def test_update_task_with_comment(self, monkeypatch):
        """update_task should add a comment when provided."""
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        adapter.client.add_comment = AsyncMock(return_value={})
        adapter.client.get_issue = AsyncMock(return_value={
            "key": "PROJ-1",
            "fields": {"summary": "Task", "status": {"name": "Open"}, "labels": []},
        })

        result = await adapter.update_task("PROJ-1", comment="Progress note")
        adapter.client.add_comment.assert_called_once_with("PROJ-1", "Progress note")
        assert result.task_id == "PROJ-1"

    @pytest.mark.asyncio
    async def test_update_task_with_transition(self, monkeypatch):
        """update_task should find and execute the right transition."""
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        adapter.client.get_transitions = AsyncMock(return_value={
            "transitions": [
                {"id": "11", "name": "To Do"},
                {"id": "21", "name": "In Progress"},
                {"id": "31", "name": "Done"},
            ],
        })
        adapter.client.transition_issue = AsyncMock(return_value=None)
        adapter.client.get_issue = AsyncMock(return_value={
            "key": "PROJ-1",
            "fields": {"summary": "Task", "status": {"name": "Done"}, "labels": []},
        })

        result = await adapter.update_task("PROJ-1", status="Done")
        adapter.client.transition_issue.assert_called_once_with("PROJ-1", "31")
        assert result.status == TaskStatus.DONE

    @pytest.mark.asyncio
    async def test_update_task_transition_not_found(self, monkeypatch):
        """update_task should still return result when transition name doesn't match."""
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        adapter.client.get_transitions = AsyncMock(return_value={
            "transitions": [{"id": "11", "name": "To Do"}],
        })
        adapter.client.transition_issue = AsyncMock()
        adapter.client.get_issue = AsyncMock(return_value={
            "key": "PROJ-1",
            "fields": {"summary": "Task", "status": {"name": "To Do"}, "labels": []},
        })

        result = await adapter.update_task("PROJ-1", status="Nonexistent")
        adapter.client.transition_issue.assert_not_called()
        assert result.task_id == "PROJ-1"

    @pytest.mark.asyncio
    async def test_query_tasks(self, monkeypatch):
        """query_tasks should return a list of TaskResults."""
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        adapter.client.search_issues = AsyncMock(return_value={
            "issues": [
                {"key": "PROJ-1", "fields": {"summary": "Task 1", "status": {"name": "To Do"}, "labels": []}},
                {"key": "PROJ-2", "fields": {"summary": "Task 2", "status": {"name": "In Progress"}, "labels": []}},
            ],
        })

        results = await adapter.query_tasks("PROJ")
        assert len(results) == 2
        assert results[0].task_id == "PROJ-1"

    @pytest.mark.asyncio
    async def test_query_tasks_with_filters(self, monkeypatch):
        """query_tasks should build JQL with status and label filters."""
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        adapter.client.search_issues = AsyncMock(return_value={
            "issues": [
                {"key": "PROJ-1", "fields": {"summary": "Bug", "status": {"name": "Open"}, "labels": ["bug"]}},
            ],
        })

        results = await adapter.query_tasks("PROJ", {"status": "Open", "labels": ["bug", "urgent"]})
        assert len(results) == 1
        jql = adapter.client.search_issues.call_args[0][0]
        assert "status = 'Open'" in jql
        assert "labels in (bug,urgent)" in jql

    @pytest.mark.asyncio
    async def test_sync_state(self, monkeypatch):
        """sync_state should categorize tasks by status."""
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        adapter.client.search_issues = AsyncMock(return_value={
            "issues": [
                {"key": "PROJ-1", "fields": {"summary": "Open task", "status": {"name": "Open"}, "labels": []}},
                {"key": "PROJ-2", "fields": {"summary": "Done task", "status": {"name": "Done"}, "labels": []}},
                {"key": "PROJ-3", "fields": {"summary": "Blocked", "status": {"name": "Blocked"}, "labels": []}},
            ],
        })

        state = await adapter.sync_state("PROJ")
        assert state.project_key == "PROJ"
        assert len(state.open_tasks) == 1
        assert len(state.recently_closed) == 1
        assert len(state.blocked_tasks) == 1

    @pytest.mark.asyncio
    async def test_get_transitions(self, monkeypatch):
        """get_transitions should map Jira transitions to Transition objects."""
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        adapter.client.get_transitions = AsyncMock(return_value={
            "transitions": [
                {"id": "11", "name": "To Do", "to": {"name": "To Do"}},
                {"id": "21", "name": "In Progress", "to": {"name": "In Progress"}},
                {"id": "31", "name": "Done", "to": {"name": "Done"}},
            ],
        })

        transitions = await adapter.get_transitions("PROJ-1")
        assert len(transitions) == 3
        assert transitions[0].transition_id == "11"
        assert transitions[0].to_status == TaskStatus.OPEN
        assert transitions[2].to_status == TaskStatus.DONE

    @pytest.mark.asyncio
    async def test_create_project_auto_lead(self, monkeypatch):
        """create_project should auto-fetch lead_account_id via get_myself."""
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        adapter.client.get_myself = AsyncMock(return_value={"accountId": "abc-123"})
        adapter.client.create_project = AsyncMock(return_value={
            "id": "10001",
            "key": "NEW",
            "self": "https://test.atlassian.net/rest/api/3/project/10001",
        })

        result = await adapter.create_project("New Project", "NEW", description="desc")
        adapter.client.get_myself.assert_called_once()
        adapter.client.create_project.assert_called_once_with(
            name="New Project",
            key="NEW",
            description="desc",
            lead_account_id="abc-123",
        )
        assert result.project_key == "NEW"
        assert result.lead == "abc-123"
        assert result.name == "New Project"

    @pytest.mark.asyncio
    async def test_list_projects(self, monkeypatch):
        """list_projects should return list of ProjectResult."""
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        adapter.client.list_projects = AsyncMock(return_value={
            "values": [
                {"id": "1", "key": "PROJ", "name": "Project", "description": "", "lead": {"accountId": "lead-1"}, "self": ""},
                {"id": "2", "key": "OTH", "name": "Other", "description": "desc", "lead": None, "self": ""},
            ],
        })

        results = await adapter.list_projects()
        assert len(results) == 2
        assert results[0].project_key == "PROJ"
        assert results[0].lead == "lead-1"
        assert results[1].lead == ""

    @pytest.mark.asyncio
    async def test_get_project(self, monkeypatch):
        """get_project should return a ProjectResult."""
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        adapter.client.get_project = AsyncMock(return_value={
            "id": "1", "key": "PROJ", "name": "Project", "description": "desc",
            "lead": {"accountId": "lead-1"}, "self": "https://test.atlassian.net/rest/api/3/project/1",
        })

        result = await adapter.get_project("PROJ")
        assert result.project_key == "PROJ"
        assert result.name == "Project"
        assert result.lead == "lead-1"

    @pytest.mark.asyncio
    async def test_assign_task(self, monkeypatch):
        """assign_task should call assign_issue and return updated TaskResult."""
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        adapter.client.assign_issue = AsyncMock(return_value=None)
        adapter.client.get_issue = AsyncMock(return_value={
            "key": "PROJ-1",
            "fields": {"summary": "Task", "status": {"name": "Open"}, "labels": []},
        })

        result = await adapter.assign_task("PROJ-1", "user-abc")
        adapter.client.assign_issue.assert_called_once_with("PROJ-1", "user-abc")
        assert result.task_id == "PROJ-1"

    @pytest.mark.asyncio
    async def test_link_issues(self, monkeypatch):
        """link_issues should call create_issue_link."""
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        adapter.client.create_issue_link = AsyncMock(return_value=None)

        await adapter.link_issues("Blocks", "PROJ-1", "PROJ-2")
        adapter.client.create_issue_link.assert_called_once_with("Blocks", "PROJ-1", "PROJ-2")

    @pytest.mark.asyncio
    async def test_get_link_types(self, monkeypatch):
        """get_link_types should return list of dicts."""
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        adapter.client.get_link_types = AsyncMock(return_value={
            "issueLinkTypes": [
                {"id": "1", "name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
            ],
        })

        result = await adapter.get_link_types()
        assert len(result) == 1
        assert result[0]["name"] == "Blocks"


# ---------------------------------------------------------------------------
# Linear adapter tests — uses mocked HTTP calls
# ---------------------------------------------------------------------------


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

    @pytest.mark.asyncio
    async def test_create_project_not_supported(self):
        """create_project should raise NotImplementedError."""
        adapter = LinearAdapter(api_key="test-key")
        with pytest.raises(NotImplementedError, match="Not supported by Linear adapter"):
            await adapter.create_project("Proj", "PRJ")

    @pytest.mark.asyncio
    async def test_list_projects_not_supported(self):
        """list_projects should raise NotImplementedError."""
        adapter = LinearAdapter(api_key="test-key")
        with pytest.raises(NotImplementedError, match="Not supported by Linear adapter"):
            await adapter.list_projects()

    @pytest.mark.asyncio
    async def test_assign_task_not_supported(self):
        """assign_task should raise NotImplementedError."""
        adapter = LinearAdapter(api_key="test-key")
        with pytest.raises(NotImplementedError, match="Not supported by Linear adapter"):
            await adapter.assign_task("PROJ-1", "user-123")

    @pytest.mark.asyncio
    async def test_link_issues_not_supported(self):
        """link_issues should raise NotImplementedError."""
        adapter = LinearAdapter(api_key="test-key")
        with pytest.raises(NotImplementedError, match="Not supported by Linear adapter"):
            await adapter.link_issues("Blocks", "PROJ-1", "PROJ-2")
