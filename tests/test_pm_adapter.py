"""Tests for PM adapter module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from library_server.pm.adapter import PMAdapter
from library_server.pm.jira import JiraAdapter
from library_server.pm.linear import LinearAdapter


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
            "self": "https://test.atlassian.net/rest/api/3/issue/PROJ-123",
        })
        adapter.client.get_issue = AsyncMock(return_value={
            "key": "PROJ-123",
            "fields": {"status": {"name": "To Do"}},
        })

        result = await adapter.create_task("PROJ", "Test task", "desc", labels=["core"])
        assert result.task_id == "PROJ-123"
        assert result.summary == "Test task"
        assert result.project_key == "PROJ"
        assert result.status == "To Do"
        adapter.client.create_issue.assert_called_once()
        adapter.client.get_issue.assert_called_once_with("PROJ-123", fields="status")
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
        adapter.client.get_issue = AsyncMock(return_value={
            "key": "PROJ-124",
            "fields": {"status": {"name": "To Do"}},
        })

        result = await adapter.create_task(
            "PROJ", "Child task", "desc", labels=[], epic_id="PROJ-E1"
        )
        assert result.task_id == "PROJ-124"
        assert result.summary == "Child task"
        assert result.status == "To Do"
        call_kwargs = adapter.client.create_issue.call_args.kwargs
        assert call_kwargs["parent_key"] == "PROJ-E1"

    @pytest.mark.asyncio
    async def test_create_task_survives_status_fetch_failure(self, monkeypatch, caplog):
        """If the post-create status fetch fails, create_task must still return
        the TaskResult (with empty status) so the caller doesn't lose reference
        to the newly-created task_id. Warning is logged per TESTING-STANDARD §3
        (no silent swallowing)."""
        import logging

        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        adapter.client.create_issue = AsyncMock(return_value={
            "key": "PROJ-999",
            "self": "https://test.atlassian.net/rest/api/3/issue/PROJ-999",
        })
        adapter.client.get_issue = AsyncMock(side_effect=RuntimeError("boom"))

        with caplog.at_level(logging.WARNING, logger="library_server.pm.jira"):
            result = await adapter.create_task("PROJ", "Task", "desc")

        assert result.task_id == "PROJ-999"
        assert result.status == ""
        assert "status fetch failed" in caplog.text
        assert "PROJ-999" in caplog.text

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
        """update_task should match on target status name (to.name), not transition name.

        Real Jira workflows often name every transition "Any" (or similar) and distinguish
        them only by their ``to`` status. The adapter must match the requested status
        against ``transition.to.name`` and call transition_issue with the matched id.
        """
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        adapter.client.get_transitions = AsyncMock(return_value={
            "transitions": [
                {"id": "2", "name": "Any", "to": {"name": "In Progress"}},
                {"id": "3", "name": "Any", "to": {"name": "To Do"}},
                {"id": "4", "name": "Any", "to": {"name": "In Review"}},
                {"id": "5", "name": "Any", "to": {"name": "Done"}},
            ],
        })
        adapter.client.transition_issue = AsyncMock(return_value=None)
        adapter.client.get_issue = AsyncMock(return_value={
            "key": "PROJ-1",
            "fields": {"summary": "Task", "status": {"name": "Done"}, "labels": []},
        })

        result = await adapter.update_task("PROJ-1", status="Done")
        adapter.client.transition_issue.assert_called_once_with("PROJ-1", "5")
        assert result.status == "Done"

    @pytest.mark.asyncio
    async def test_update_task_matches_named_transition(self, monkeypatch):
        """update_task should also match when requested status equals transition.name
        (covers Jira workflows where transitions have semantic names)."""
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        adapter.client.get_transitions = AsyncMock(return_value={
            "transitions": [
                {"id": "11", "name": "To Do", "to": {"name": "To Do"}},
                {"id": "21", "name": "Start Progress", "to": {"name": "In Progress"}},
            ],
        })
        adapter.client.transition_issue = AsyncMock(return_value=None)
        adapter.client.get_issue = AsyncMock(return_value={
            "key": "PROJ-1",
            "fields": {"summary": "Task", "status": {"name": "In Progress"}, "labels": []},
        })

        result = await adapter.update_task("PROJ-1", status="Start Progress")
        adapter.client.transition_issue.assert_called_once_with("PROJ-1", "21")
        assert result.status == "In Progress"

    @pytest.mark.asyncio
    async def test_update_task_transition_not_found_raises(self, monkeypatch):
        """update_task MUST raise TransitionNotAvailableError when no transition matches,
        listing the available transitions and current status. Silent no-op is a bug
        (see 2026-04-17 audit failure)."""
        from library_server.pm.adapter import TransitionNotAvailableError

        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        adapter.client.get_transitions = AsyncMock(return_value={
            "transitions": [
                {"id": "11", "name": "Any", "to": {"name": "To Do"}},
                {"id": "21", "name": "Any", "to": {"name": "In Progress"}},
            ],
        })
        adapter.client.transition_issue = AsyncMock()
        adapter.client.get_issue = AsyncMock(return_value={
            "key": "PROJ-1",
            "fields": {"summary": "Task", "status": {"name": "To Do"}, "labels": []},
        })

        with pytest.raises(TransitionNotAvailableError) as exc_info:
            await adapter.update_task("PROJ-1", status="Nonexistent")

        err = exc_info.value
        assert err.task_id == "PROJ-1"
        assert err.requested_status == "Nonexistent"
        # Available transitions should list both transition.name and to.name options
        assert any("To Do" in t for t in err.available_transitions)
        assert any("In Progress" in t for t in err.available_transitions)
        # Message must mention the available options for debuggability
        assert "To Do" in str(err) or "In Progress" in str(err)
        adapter.client.transition_issue.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_task_no_status_does_not_raise(self, monkeypatch):
        """update_task with no status must not call get_transitions or raise."""
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        adapter.client.get_transitions = AsyncMock()
        adapter.client.transition_issue = AsyncMock()
        adapter.client.get_issue = AsyncMock(return_value={
            "key": "PROJ-1",
            "fields": {"summary": "Task", "status": {"name": "To Do"}, "labels": []},
        })

        result = await adapter.update_task("PROJ-1")
        adapter.client.get_transitions.assert_not_called()
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
    async def test_sync_state_classifies_by_workflow_state(self, monkeypatch):
        """sync_state must bucket by raw status using the adapter's configured
        closed/blocked lists — not by a hardcoded 4-state enum. Workflows like
        Jira's default ("To Do" / "In Progress" / "In Review" / "Done") must
        route correctly: In Review is OPEN, not silently collapsed to closed."""
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        adapter.client.search_issues = AsyncMock(return_value={
            "issues": [
                {"key": "P-1", "fields": {"summary": "Todo", "status": {"name": "To Do"}, "labels": []}},
                {"key": "P-2", "fields": {"summary": "WIP", "status": {"name": "In Progress"}, "labels": []}},
                {"key": "P-3", "fields": {"summary": "Review", "status": {"name": "In Review"}, "labels": []}},
                {"key": "P-4", "fields": {"summary": "Done", "status": {"name": "Done"}, "labels": []}},
                {"key": "P-5", "fields": {"summary": "Blocked", "status": {"name": "Blocked"}, "labels": []}},
            ],
        })

        state = await adapter.sync_state("PROJ")
        assert state.project_key == "PROJ"
        # Raw statuses are preserved on TaskResult — no enum collapse
        all_statuses = {t.status for t in state.open_tasks + state.recently_closed + state.blocked_tasks}
        assert all_statuses == {"To Do", "In Progress", "In Review", "Done", "Blocked"}
        # Bucketing: To Do, In Progress, In Review are all "open" (not closed, not blocked)
        open_statuses = {t.status for t in state.open_tasks}
        assert open_statuses == {"To Do", "In Progress", "In Review"}
        assert [t.status for t in state.recently_closed] == ["Done"]
        assert [t.status for t in state.blocked_tasks] == ["Blocked"]

    @pytest.mark.asyncio
    async def test_sync_state_honors_custom_closed_statuses(self, monkeypatch):
        """When a caller configures pm.workflow.closed to a non-default name
        (e.g. ``Shipped``), sync_state must classify by that name."""
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(
            site_url="https://test.atlassian.net",
            closed_statuses=("Shipped",),
        )
        adapter.client.search_issues = AsyncMock(return_value={
            "issues": [
                {"key": "P-1", "fields": {"summary": "S", "status": {"name": "Shipped"}, "labels": []}},
                {"key": "P-2", "fields": {"summary": "D", "status": {"name": "Done"}, "labels": []}},
            ],
        })

        state = await adapter.sync_state("PROJ")
        # With Shipped as the closed name, Done is no longer closed — it's open.
        assert [t.status for t in state.recently_closed] == ["Shipped"]
        assert [t.status for t in state.open_tasks] == ["Done"]

    @pytest.mark.asyncio
    async def test_get_transitions(self, monkeypatch):
        """get_transitions should preserve Jira's raw target-status names verbatim."""
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(site_url="https://test.atlassian.net")
        adapter.client.get_transitions = AsyncMock(return_value={
            "transitions": [
                {"id": "11", "name": "Any", "to": {"name": "To Do"}},
                {"id": "21", "name": "Any", "to": {"name": "In Progress"}},
                {"id": "25", "name": "Any", "to": {"name": "In Review"}},
                {"id": "31", "name": "Any", "to": {"name": "Done"}},
            ],
        })

        transitions = await adapter.get_transitions("PROJ-1")
        assert len(transitions) == 4
        assert transitions[0].transition_id == "11"
        assert transitions[0].to_status == "To Do"
        assert transitions[2].to_status == "In Review"
        assert transitions[3].to_status == "Done"

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
    async def test_get_issue_parses_all_fields(self, monkeypatch):
        """get_issue returns an IssueDetail with all fields populated and most-recent
        20 comments, rendering ADF description to plain text."""
        from library_server.types import IssueDetail

        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(site_url="https://test.atlassian.net")

        # Fabricate 25 comments to verify trimming to 20.
        comments_payload = [
            {
                "author": {"displayName": f"User {i}"},
                "created": f"2026-04-17T00:00:{i:02d}.000Z",
                "body": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": f"c{i}"}]},
                    ],
                },
            }
            for i in range(25)
        ]
        adapter.client.get_issue = AsyncMock(return_value={
            "key": "LIBRARY-99",
            "self": "https://test.atlassian.net/rest/api/3/issue/LIBRARY-99",
            "fields": {
                "summary": "A thing",
                "status": {"name": "In Progress"},
                "labels": ["infra", "bug"],
                "assignee": {"displayName": "Alice", "accountId": "a1"},
                "parent": {"key": "LIBRARY-1"},
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": "Hello"}]},
                        {"type": "paragraph", "content": [{"type": "text", "text": "World"}]},
                    ],
                },
                "comment": {"comments": comments_payload, "total": 25},
            },
        })
        adapter.client.get_transitions = AsyncMock(return_value={
            "transitions": [
                {"id": "2", "name": "Any", "to": {"name": "In Progress"}},
                {"id": "5", "name": "Any", "to": {"name": "Done"}},
            ],
        })

        detail = await adapter.get_issue("LIBRARY-99")
        assert isinstance(detail, IssueDetail)
        assert detail.id == "LIBRARY-99"
        assert detail.summary == "A thing"
        assert detail.status == "In Progress"
        assert detail.labels == ["infra", "bug"]
        assert detail.parent == "LIBRARY-1"
        assert detail.assignee == "Alice"
        assert detail.description == "Hello\nWorld"
        # Most-recent 20, chronological order preserved (c5..c24)
        assert len(detail.comments) == 20
        assert detail.comments[0].body == "c5"
        assert detail.comments[-1].body == "c24"
        assert detail.comments[-1].author == "User 24"
        assert [t.to_status for t in detail.available_transitions] == [
            "In Progress",
            "Done",
        ]

    @pytest.mark.asyncio
    async def test_get_issue_handles_missing_fields(self, monkeypatch):
        """get_issue tolerates missing assignee/parent/description/comments."""
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        adapter = JiraAdapter(site_url="https://test.atlassian.net")

        adapter.client.get_issue = AsyncMock(return_value={
            "key": "LIBRARY-1",
            "self": "",
            "fields": {
                "summary": "minimal",
                "status": {"name": "To Do"},
                "labels": [],
                "assignee": None,
                "description": None,
            },
        })
        adapter.client.get_transitions = AsyncMock(return_value={"transitions": []})

        detail = await adapter.get_issue("LIBRARY-1")
        assert detail.assignee is None
        assert detail.parent is None
        assert detail.description == ""
        assert detail.comments == []
        assert detail.available_transitions == []

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
        assert result.status == "In Progress"
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
        assert result.status == "Done"
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
        assert results[1].status == "In Progress"

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
        assert transitions[0].to_status == "Backlog"
        assert transitions[1].to_status == "In Progress"
        assert transitions[2].to_status == "Done"

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
