"""Tests for JiraClient — standalone Jira REST API client."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from library_server.pm.jira_client import JiraApiError, JiraClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def _env_vars(monkeypatch: pytest.MonkeyPatch):
    """Set required Jira env vars."""
    monkeypatch.setenv("ATLASSIAN_EMAIL", "test@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "tok-abc123")


@pytest.fixture()
def client(_env_vars) -> JiraClient:
    """Return a JiraClient with mocked env vars."""
    return JiraClient(site_url="https://test.atlassian.net")


# ---------------------------------------------------------------------------
# TestJiraClientInit
# ---------------------------------------------------------------------------

class TestJiraClientInit:
    """Initialisation, auth header, URL normalisation."""

    def test_builds_auth_header_from_env(self, _env_vars):
        c = JiraClient(site_url="https://x.atlassian.net")
        # Basic Auth = base64(email:token)
        import base64
        expected = base64.b64encode(b"test@example.com:tok-abc123").decode()
        assert c._auth_header == f"Basic {expected}"

    def test_raises_without_email(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("ATLASSIAN_EMAIL", raising=False)
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        with pytest.raises(ValueError, match="ATLASSIAN_EMAIL"):
            JiraClient(site_url="https://x.atlassian.net")

    def test_raises_without_token(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ATLASSIAN_EMAIL", "a@b.com")
        monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
        with pytest.raises(ValueError, match="JIRA_API_TOKEN"):
            JiraClient(site_url="https://x.atlassian.net")

    def test_strips_trailing_slash(self, _env_vars):
        c = JiraClient(site_url="https://x.atlassian.net/")
        assert c._site_url == "https://x.atlassian.net"

    def test_stores_timeout(self, _env_vars):
        c = JiraClient(site_url="https://x.atlassian.net", timeout=30.0)
        assert c._timeout == 30.0


# ---------------------------------------------------------------------------
# TestJiraApiError
# ---------------------------------------------------------------------------

class TestJiraApiError:
    """Error class carries status, message, endpoint."""

    def test_error_includes_all_details(self):
        err = JiraApiError(status_code=404, message="Not Found", endpoint="/rest/api/3/issue/X")
        assert err.status_code == 404
        assert err.message == "Not Found"
        assert err.endpoint == "/rest/api/3/issue/X"
        assert "404" in str(err)
        assert "Not Found" in str(err)
        assert "/rest/api/3/issue/X" in str(err)


# ---------------------------------------------------------------------------
# TestProjectMethods
# ---------------------------------------------------------------------------

class TestProjectMethods:
    """Project CRUD — mocks _request."""

    @pytest.mark.asyncio
    async def test_create_project(self, client: JiraClient):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"id": "10001", "key": "NEW"}
            result = await client.create_project(
                name="New Project",
                key="NEW",
                project_type_key="software",
                lead_account_id="abc",
                description="desc",
            )
            mock_req.assert_called_once_with(
                "POST",
                "/rest/api/3/project",
                json={
                    "name": "New Project",
                    "key": "NEW",
                    "projectTypeKey": "software",
                    "projectTemplateKey": "com.pyxis.greenhopper.jira:gh-simplified-scrum-classic",
                    "description": "desc",
                    "assigneeType": "PROJECT_LEAD",
                    "leadAccountId": "abc",
                },
            )
            assert result["key"] == "NEW"

    @pytest.mark.asyncio
    async def test_list_projects(self, client: JiraClient):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"values": [{"key": "A"}], "total": 1}
            result = await client.list_projects(max_results=10, start_at=5)
            mock_req.assert_called_once_with(
                "GET",
                "/rest/api/3/project/search",
                params={"maxResults": 10, "startAt": 5},
            )
            assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_get_project(self, client: JiraClient):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"key": "COS", "name": "Compliance OS"}
            result = await client.get_project("COS")
            mock_req.assert_called_once_with("GET", "/rest/api/3/project/COS")
            assert result["name"] == "Compliance OS"

    @pytest.mark.asyncio
    async def test_update_project(self, client: JiraClient):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"key": "COS"}
            result = await client.update_project("COS", name="Updated", description=None)
            # None values should be filtered out
            mock_req.assert_called_once_with(
                "PUT",
                "/rest/api/3/project/COS",
                json={"name": "Updated"},
            )
            assert result["key"] == "COS"


# ---------------------------------------------------------------------------
# TestIssueMethods
# ---------------------------------------------------------------------------

class TestIssueMethods:
    """Issue CRUD — mocks _request."""

    @pytest.mark.asyncio
    async def test_create_issue_basic(self, client: JiraClient):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"id": "1", "key": "COS-1"}
            result = await client.create_issue(
                project_key="COS",
                issue_type="Task",
                summary="Do something",
                description="Details here",
            )
            call_args = mock_req.call_args
            assert call_args[0] == ("POST", "/rest/api/3/issue")
            body = call_args[1]["json"]
            assert body["fields"]["project"]["key"] == "COS"
            assert body["fields"]["issuetype"]["name"] == "Task"
            assert body["fields"]["summary"] == "Do something"
            # Description should be ADF
            assert body["fields"]["description"]["type"] == "doc"
            assert result["key"] == "COS-1"

    @pytest.mark.asyncio
    async def test_create_issue_with_labels(self, client: JiraClient):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"key": "COS-2"}
            await client.create_issue(
                project_key="COS",
                issue_type="Task",
                summary="Labelled",
                labels=["core", "urgent"],
            )
            body = mock_req.call_args[1]["json"]
            assert body["fields"]["labels"] == ["core", "urgent"]

    @pytest.mark.asyncio
    async def test_create_issue_with_parent(self, client: JiraClient):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"key": "COS-3"}
            await client.create_issue(
                project_key="COS",
                issue_type="Subtask",
                summary="Sub",
                parent_key="COS-1",
            )
            body = mock_req.call_args[1]["json"]
            assert body["fields"]["parent"] == {"key": "COS-1"}

    @pytest.mark.asyncio
    async def test_create_issue_with_assignee(self, client: JiraClient):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"key": "COS-4"}
            await client.create_issue(
                project_key="COS",
                issue_type="Task",
                summary="Assigned",
                assignee_id="user-abc",
            )
            body = mock_req.call_args[1]["json"]
            assert body["fields"]["assignee"] == {"accountId": "user-abc"}

    @pytest.mark.asyncio
    async def test_get_issue_default_fields(self, client: JiraClient):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"key": "COS-1", "fields": {"summary": "X"}}
            await client.get_issue("COS-1")
            call_args = mock_req.call_args
            assert call_args[0] == ("GET", "/rest/api/3/issue/COS-1")
            params = call_args[1]["params"]
            assert "summary" in params["fields"]

    @pytest.mark.asyncio
    async def test_get_issue_custom_fields(self, client: JiraClient):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"key": "COS-1"}
            await client.get_issue("COS-1", fields="summary,status")
            params = mock_req.call_args[1]["params"]
            assert params["fields"] == "summary,status"

    @pytest.mark.asyncio
    async def test_update_issue(self, client: JiraClient):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = None
            await client.update_issue("COS-1", fields={"summary": "Updated"})
            mock_req.assert_called_once_with(
                "PUT",
                "/rest/api/3/issue/COS-1",
                json={"fields": {"summary": "Updated"}},
            )

    @pytest.mark.asyncio
    async def test_delete_issue_default_subtasks_true(self, client: JiraClient):
        """delete_issue() hits DELETE /rest/api/3/issue/{key} with deleteSubtasks=true."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = None
            result = await client.delete_issue("COS-42")
            mock_req.assert_called_once_with(
                "DELETE",
                "/rest/api/3/issue/COS-42",
                params={"deleteSubtasks": "true"},
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_delete_issue_subtasks_false(self, client: JiraClient):
        """delete_issue(delete_subtasks=False) passes deleteSubtasks=false."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = None
            await client.delete_issue("COS-42", delete_subtasks=False)
            params = mock_req.call_args[1]["params"]
            assert params["deleteSubtasks"] == "false"

    @pytest.mark.asyncio
    async def test_delete_project(self, client: JiraClient):
        """delete_project() hits DELETE /rest/api/3/project/{key}."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = None
            result = await client.delete_project("ZZTABCD")
            mock_req.assert_called_once_with(
                "DELETE",
                "/rest/api/3/project/ZZTABCD",
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_search_issues(self, client: JiraClient):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"issues": [], "total": 0}
            result = await client.search_issues("project = COS", max_results=20)
            mock_req.assert_called_once_with(
                "POST",
                "/rest/api/3/search/jql",
                json={
                    "jql": "project = COS",
                    "fields": ["summary", "status", "issuetype", "priority", "labels", "assignee"],
                    "maxResults": 20,
                },
            )
            assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_search_issues_with_page_token(self, client: JiraClient):
        """nextPageToken is included when provided."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"issues": []}
            await client.search_issues("project = COS", next_page_token="abc123")
            body = mock_req.call_args[1]["json"]
            assert body["nextPageToken"] == "abc123"

    @pytest.mark.asyncio
    async def test_search_issues_custom_fields_string(self, client: JiraClient):
        """Comma-separated string fields are normalised to a list."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"issues": []}
            await client.search_issues("project = COS", fields="summary,status")
            body = mock_req.call_args[1]["json"]
            assert body["fields"] == ["summary", "status"]

    @pytest.mark.asyncio
    async def test_search_issues_custom_fields_list(self, client: JiraClient):
        """List fields are passed through unchanged."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"issues": []}
            await client.search_issues("project = COS", fields=["summary"])
            body = mock_req.call_args[1]["json"]
            assert body["fields"] == ["summary"]

    @pytest.mark.asyncio
    async def test_assign_issue(self, client: JiraClient):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = None
            await client.assign_issue("COS-1", "user-abc")
            mock_req.assert_called_once_with(
                "PUT",
                "/rest/api/3/issue/COS-1/assignee",
                json={"accountId": "user-abc"},
            )


# ---------------------------------------------------------------------------
# TestTransitionMethods
# ---------------------------------------------------------------------------

class TestTransitionMethods:
    """Transition read/execute."""

    @pytest.mark.asyncio
    async def test_get_transitions(self, client: JiraClient):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"transitions": [{"id": "31", "name": "Done"}]}
            result = await client.get_transitions("COS-1")
            mock_req.assert_called_once_with("GET", "/rest/api/3/issue/COS-1/transitions")
            assert result["transitions"][0]["name"] == "Done"

    @pytest.mark.asyncio
    async def test_transition_issue(self, client: JiraClient):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = None
            await client.transition_issue("COS-1", "31")
            mock_req.assert_called_once_with(
                "POST",
                "/rest/api/3/issue/COS-1/transitions",
                json={"transition": {"id": "31"}},
            )


# ---------------------------------------------------------------------------
# TestCommentMethods
# ---------------------------------------------------------------------------

class TestCommentMethods:
    """Comment creation with ADF body."""

    @pytest.mark.asyncio
    async def test_add_comment(self, client: JiraClient):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"id": "100"}
            result = await client.add_comment("COS-1", "This is a comment")
            call_args = mock_req.call_args
            assert call_args[0] == ("POST", "/rest/api/3/issue/COS-1/comment")
            body = call_args[1]["json"]["body"]
            # Verify ADF format
            assert body["type"] == "doc"
            assert body["version"] == 1
            content = body["content"][0]
            assert content["type"] == "paragraph"
            assert content["content"][0]["text"] == "This is a comment"
            assert result["id"] == "100"


# ---------------------------------------------------------------------------
# TestLinkMethods
# ---------------------------------------------------------------------------

class TestLinkMethods:
    """Issue linking."""

    @pytest.mark.asyncio
    async def test_create_issue_link(self, client: JiraClient):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = None
            await client.create_issue_link("Blocks", "COS-1", "COS-2")
            mock_req.assert_called_once_with(
                "POST",
                "/rest/api/3/issueLink",
                json={
                    "type": {"name": "Blocks"},
                    "inwardIssue": {"key": "COS-1"},
                    "outwardIssue": {"key": "COS-2"},
                },
            )

    @pytest.mark.asyncio
    async def test_get_link_types(self, client: JiraClient):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"issueLinkTypes": [{"name": "Blocks"}]}
            result = await client.get_link_types()
            mock_req.assert_called_once_with("GET", "/rest/api/3/issueLinkType")
            assert result["issueLinkTypes"][0]["name"] == "Blocks"


# ---------------------------------------------------------------------------
# TestUserMethods
# ---------------------------------------------------------------------------

class TestUserMethods:
    """User lookup."""

    @pytest.mark.asyncio
    async def test_get_myself(self, client: JiraClient):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"accountId": "abc", "displayName": "Test User"}
            result = await client.get_myself()
            mock_req.assert_called_once_with("GET", "/rest/api/3/myself")
            assert result["accountId"] == "abc"

    @pytest.mark.asyncio
    async def test_find_users(self, client: JiraClient):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [{"accountId": "abc", "displayName": "Test"}]
            result = await client.find_users("test")
            mock_req.assert_called_once_with(
                "GET",
                "/rest/api/3/user/search",
                params={"query": "test"},
            )
            assert len(result) == 1


class TestAssignWorkflowScheme:
    """assign_workflow_scheme looks up the scheme by name and assigns it."""

    @pytest.mark.asyncio
    async def test_assigns_matching_scheme(self, client: JiraClient):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = [
                {"values": [{"id": "10", "name": "Other"}, {"id": "42", "name": "SevenBelow Standard SDLC Workflow"}]},
                {},  # PUT response
            ]
            await client.assign_workflow_scheme("12345", "SevenBelow Standard SDLC Workflow")

            assert mock_req.call_count == 2
            # Second call must use the matched scheme id (42), not the first (10)
            put_call = mock_req.call_args_list[1]
            assert put_call.kwargs["json"] == {"workflowSchemeId": "42", "projectId": "12345"}

    @pytest.mark.asyncio
    async def test_is_case_insensitive(self, client: JiraClient):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = [
                {"values": [{"id": "99", "name": "My Scheme"}]},
                {},
            ]
            await client.assign_workflow_scheme("p1", "MY SCHEME")
            put_call = mock_req.call_args_list[1]
            assert put_call.kwargs["json"] == {"workflowSchemeId": "99", "projectId": "p1"}

    @pytest.mark.asyncio
    async def test_raises_when_scheme_not_found(self, client: JiraClient):
        """Missing scheme must raise ValueError listing available schemes — silent
        no-op would leave the project on the default workflow without warning."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"values": [{"id": "1", "name": "Alpha"}, {"id": "2", "name": "Beta"}]}
            with pytest.raises(ValueError) as exc_info:
                await client.assign_workflow_scheme("p1", "Gamma")
            msg = str(exc_info.value)
            assert "Gamma" in msg
            assert "Alpha" in msg and "Beta" in msg


class TestGetEpicNameFieldId:
    """get_epic_name_field_id resolves the custom field via case-insensitive match."""

    @pytest.mark.asyncio
    async def test_matches_epic_name_case_insensitive(self, client: JiraClient):
        client.get_fields = AsyncMock(return_value=[
            {"id": "customfield_1", "name": "Other"},
            {"id": "customfield_99", "name": "Epic Name"},
        ])
        result = await client.get_epic_name_field_id()
        assert result == "customfield_99"

    @pytest.mark.asyncio
    async def test_does_not_match_unrelated_name(self, client: JiraClient):
        """The filter must be the literal 'epic name' — nothing else. If it
        flipped to `!=`, this test fails because 'Epic Link' would match."""
        client.get_fields = AsyncMock(return_value=[
            {"id": "customfield_50", "name": "Epic Link"},
            {"id": "customfield_51", "name": "Story Points"},
        ])
        result = await client.get_epic_name_field_id()
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_cached_value(self, client: JiraClient):
        """Second call must use the cached value, not re-fetch fields."""
        client.get_fields = AsyncMock(return_value=[{"id": "cf_1", "name": "Epic Name"}])
        first = await client.get_epic_name_field_id()
        second = await client.get_epic_name_field_id()
        assert first == second == "cf_1"
        client.get_fields.assert_called_once()
