# Jira Direct Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace MCP-mediated Jira calls with a standalone `JiraClient` HTTP client, add project management capabilities, consolidate all Jira HTTP into one class, and document the setup.

**Architecture:** `JiraClient` (HTTP layer) → `JiraAdapter` (type mapping) → MCP tools (server.py). Vault builder extractor and hooks client import `JiraClient` directly instead of rolling their own HTTP logic.

**Tech Stack:** Python 3.11+, httpx (async HTTP), pytest + pytest-asyncio, Jira REST API v3, Basic Auth

---

### Task 1: `JiraClient` — Core HTTP Client

**Files:**
- Create: `src/library_server/pm/jira_client.py`
- Create: `tests/test_jira_client.py`

- [ ] **Step 1: Write failing tests for JiraClient construction and auth**

```python
# tests/test_jira_client.py
"""Tests for JiraClient — direct Jira REST API client."""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from library_server.pm.jira_client import JiraClient, JiraApiError


class TestJiraClientInit:
    """Constructor and auth header tests."""

    def test_builds_auth_header_from_env(self, monkeypatch):
        monkeypatch.setenv("JIRA_EMAIL", "user@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "test-token")
        client = JiraClient(site_url="https://test.atlassian.net")
        expected = base64.b64encode(b"user@example.com:test-token").decode()
        assert client._headers["Authorization"] == f"Basic {expected}"

    def test_raises_without_env_vars(self, monkeypatch):
        monkeypatch.delenv("JIRA_EMAIL", raising=False)
        monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
        with pytest.raises(ValueError, match="JIRA_EMAIL"):
            JiraClient(site_url="https://test.atlassian.net")

    def test_strips_trailing_slash(self, monkeypatch):
        monkeypatch.setenv("JIRA_EMAIL", "user@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "test-token")
        client = JiraClient(site_url="https://test.atlassian.net/")
        assert client.base_url == "https://test.atlassian.net"


class TestJiraApiError:
    def test_error_includes_details(self):
        err = JiraApiError(404, "Not found", "/rest/api/3/issue/BAD-1")
        assert "404" in str(err)
        assert "Not found" in str(err)
        assert "/rest/api/3/issue/BAD-1" in str(err)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library && python -m pytest tests/test_jira_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'library_server.pm.jira_client'`

- [ ] **Step 3: Implement JiraClient skeleton with auth**

```python
# src/library_server/pm/jira_client.py
"""Standalone Jira REST API client using Basic Auth.

All Jira HTTP communication in The Library goes through this client:
PM adapter, vault builder extractor, and hooks client.
"""

from __future__ import annotations

import base64
import os
from typing import Any

import httpx


class JiraApiError(Exception):
    """Raised on non-2xx Jira API responses."""

    def __init__(self, status_code: int, message: str, endpoint: str):
        self.status_code = status_code
        self.endpoint = endpoint
        super().__init__(f"Jira API {status_code} on {endpoint}: {message}")


class JiraClient:
    """Async HTTP client for Jira REST API v3.

    Auth: Basic Auth using JIRA_EMAIL + JIRA_API_TOKEN env vars.
    """

    def __init__(self, site_url: str, timeout: float = 15.0):
        email = os.environ.get("JIRA_EMAIL", "")
        token = os.environ.get("JIRA_API_TOKEN", "")
        if not email or not token:
            raise ValueError(
                "JIRA_EMAIL and JIRA_API_TOKEN env vars are required. "
                "See docs/setup/jira-setup.md for configuration."
            )
        self.base_url = site_url.rstrip("/")
        credentials = base64.b64encode(f"{email}:{token}".encode()).decode()
        self._headers = {
            "Authorization": f"Basic {credentials}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self._timeout = timeout

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Make an authenticated request to the Jira REST API."""
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(
                method, url, headers=self._headers, params=params, json=json,
            )
        if response.status_code == 204:
            return None
        if response.status_code >= 400:
            try:
                body = response.json()
                msg = ", ".join(body.get("errorMessages", [])) or str(body.get("errors", {}))
            except Exception:
                msg = response.text
            raise JiraApiError(response.status_code, msg, path)
        return response.json()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library && python -m pytest tests/test_jira_client.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library
git add src/library_server/pm/jira_client.py tests/test_jira_client.py
git commit -m "feat: add JiraClient skeleton with auth and error handling"
```

---

### Task 2: `JiraClient` — Project Methods

**Files:**
- Modify: `src/library_server/pm/jira_client.py`
- Modify: `tests/test_jira_client.py`

- [ ] **Step 1: Write failing tests for project methods**

Append to `tests/test_jira_client.py`:

```python
class TestProjectMethods:
    """Tests for project CRUD methods."""

    @pytest.fixture(autouse=True)
    def setup_env(self, monkeypatch):
        monkeypatch.setenv("JIRA_EMAIL", "user@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "test-token")

    @pytest.fixture
    def client(self):
        return JiraClient(site_url="https://test.atlassian.net")

    @pytest.mark.asyncio
    async def test_create_project(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.return_value = {
                "id": 10001, "key": "COS", "self": "https://test.atlassian.net/rest/api/3/project/10001",
            }
            result = await client.create_project(
                name="COMPLIANCE-OS", key="COS",
                project_type_key="software", lead_account_id="abc-123",
                description="Product features",
            )
        assert result["key"] == "COS"
        mock.assert_called_once_with("POST", "/rest/api/3/project", json={
            "name": "COMPLIANCE-OS", "key": "COS", "projectTypeKey": "software",
            "leadAccountId": "abc-123", "description": "Product features",
        })

    @pytest.mark.asyncio
    async def test_list_projects(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.return_value = {
                "values": [
                    {"id": "10001", "key": "COS", "name": "COMPLIANCE-OS"},
                    {"id": "10002", "key": "PLT", "name": "PLATFORM"},
                ],
                "total": 2,
            }
            result = await client.list_projects()
        assert len(result["values"]) == 2
        mock.assert_called_once_with("GET", "/rest/api/3/project/search", params={"maxResults": 50, "startAt": 0})

    @pytest.mark.asyncio
    async def test_get_project(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.return_value = {"id": "10001", "key": "COS", "name": "COMPLIANCE-OS", "description": ""}
            result = await client.get_project("COS")
        assert result["key"] == "COS"
        mock.assert_called_once_with("GET", "/rest/api/3/project/COS")

    @pytest.mark.asyncio
    async def test_update_project(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.return_value = {"id": "10001", "key": "COS", "name": "Updated Name"}
            result = await client.update_project("COS", name="Updated Name", description="New desc")
        assert result["name"] == "Updated Name"
        mock.assert_called_once_with("PUT", "/rest/api/3/project/COS", json={
            "name": "Updated Name", "description": "New desc",
        })
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library && python -m pytest tests/test_jira_client.py::TestProjectMethods -v`
Expected: FAIL — `AttributeError: 'JiraClient' object has no attribute 'create_project'`

- [ ] **Step 3: Implement project methods**

Append to `JiraClient` class in `src/library_server/pm/jira_client.py`:

```python
    # --- Projects ---

    async def create_project(
        self,
        name: str,
        key: str,
        project_type_key: str = "software",
        lead_account_id: str = "",
        description: str = "",
    ) -> dict[str, Any]:
        """Create a Jira project."""
        payload: dict[str, Any] = {
            "name": name,
            "key": key,
            "projectTypeKey": project_type_key,
            "leadAccountId": lead_account_id,
            "description": description,
        }
        return await self._request("POST", "/rest/api/3/project", json=payload)

    async def list_projects(
        self, max_results: int = 50, start_at: int = 0,
    ) -> dict[str, Any]:
        """List all visible Jira projects."""
        return await self._request(
            "GET", "/rest/api/3/project/search",
            params={"maxResults": max_results, "startAt": start_at},
        )

    async def get_project(self, project_key: str) -> dict[str, Any]:
        """Get a single project by key."""
        return await self._request("GET", f"/rest/api/3/project/{project_key}")

    async def update_project(self, project_key: str, **fields: Any) -> dict[str, Any]:
        """Update project fields (name, description, leadAccountId)."""
        return await self._request(
            "PUT", f"/rest/api/3/project/{project_key}",
            json={k: v for k, v in fields.items() if v is not None},
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library && python -m pytest tests/test_jira_client.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library
git add src/library_server/pm/jira_client.py tests/test_jira_client.py
git commit -m "feat: add JiraClient project CRUD methods"
```

---

### Task 3: `JiraClient` — Issue Methods

**Files:**
- Modify: `src/library_server/pm/jira_client.py`
- Modify: `tests/test_jira_client.py`

- [ ] **Step 1: Write failing tests for issue methods**

Append to `tests/test_jira_client.py`:

```python
class TestIssueMethods:
    """Tests for issue CRUD and search methods."""

    @pytest.fixture(autouse=True)
    def setup_env(self, monkeypatch):
        monkeypatch.setenv("JIRA_EMAIL", "user@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "test-token")

    @pytest.fixture
    def client(self):
        return JiraClient(site_url="https://test.atlassian.net")

    @pytest.mark.asyncio
    async def test_create_issue(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.return_value = {
                "id": "10042", "key": "COS-42",
                "self": "https://test.atlassian.net/rest/api/3/issue/10042",
            }
            result = await client.create_issue(
                project_key="COS", issue_type="Task",
                summary="Build Jira client", description="Direct REST",
                labels=["core"], assignee_id="abc-123",
            )
        assert result["key"] == "COS-42"
        call_json = mock.call_args.kwargs["json"]
        assert call_json["fields"]["project"]["key"] == "COS"
        assert call_json["fields"]["issuetype"]["name"] == "Task"
        assert call_json["fields"]["labels"] == ["core"]

    @pytest.mark.asyncio
    async def test_create_issue_with_parent(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.return_value = {"id": "10043", "key": "COS-43"}
            await client.create_issue(
                project_key="COS", issue_type="Task",
                summary="Sub-task", description="Under epic",
                parent_key="COS-1",
            )
        call_json = mock.call_args.kwargs["json"]
        assert call_json["fields"]["parent"]["key"] == "COS-1"

    @pytest.mark.asyncio
    async def test_get_issue(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.return_value = {
                "key": "COS-42",
                "fields": {"summary": "Test", "status": {"name": "Open"}},
            }
            result = await client.get_issue("COS-42")
        assert result["key"] == "COS-42"
        mock.assert_called_once_with(
            "GET", "/rest/api/3/issue/COS-42",
            params={"fields": "summary,status,issuetype,priority,labels,assignee,description"},
        )

    @pytest.mark.asyncio
    async def test_get_issue_custom_fields(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.return_value = {"key": "COS-42", "fields": {"summary": "Test"}}
            await client.get_issue("COS-42", fields=["summary"])
        mock.assert_called_once_with("GET", "/rest/api/3/issue/COS-42", params={"fields": "summary"})

    @pytest.mark.asyncio
    async def test_update_issue(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.return_value = None  # 204 No Content
            await client.update_issue("COS-42", fields={"summary": "Updated"})
        mock.assert_called_once_with(
            "PUT", "/rest/api/3/issue/COS-42",
            json={"fields": {"summary": "Updated"}},
        )

    @pytest.mark.asyncio
    async def test_search_issues(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.return_value = {
                "issues": [{"key": "COS-1"}, {"key": "COS-2"}],
                "total": 2, "startAt": 0, "maxResults": 50,
            }
            result = await client.search_issues("project = COS")
        assert len(result["issues"]) == 2
        mock.assert_called_once_with(
            "GET", "/rest/api/3/search",
            params={"jql": "project = COS", "maxResults": 50, "startAt": 0,
                    "fields": "summary,status,issuetype,priority,labels,assignee"},
        )

    @pytest.mark.asyncio
    async def test_assign_issue(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.return_value = None
            await client.assign_issue("COS-42", "abc-123")
        mock.assert_called_once_with(
            "PUT", "/rest/api/3/issue/COS-42/assignee",
            json={"accountId": "abc-123"},
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library && python -m pytest tests/test_jira_client.py::TestIssueMethods -v`
Expected: FAIL — `AttributeError: 'JiraClient' object has no attribute 'create_issue'`

- [ ] **Step 3: Implement issue methods**

Append to `JiraClient` class in `src/library_server/pm/jira_client.py`:

```python
    # --- Issues ---

    async def create_issue(
        self,
        project_key: str,
        issue_type: str,
        summary: str,
        description: str = "",
        labels: list[str] | None = None,
        parent_key: str = "",
        assignee_id: str = "",
    ) -> dict[str, Any]:
        """Create an issue (Task, Epic, Bug, Story)."""
        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "issuetype": {"name": issue_type},
            "summary": summary,
        }
        if description:
            fields["description"] = {
                "type": "doc", "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}],
            }
        if labels:
            fields["labels"] = labels
        if parent_key:
            fields["parent"] = {"key": parent_key}
        if assignee_id:
            fields["assignee"] = {"accountId": assignee_id}
        return await self._request("POST", "/rest/api/3/issue", json={"fields": fields})

    async def get_issue(
        self, issue_key: str, fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get issue details."""
        default_fields = "summary,status,issuetype,priority,labels,assignee,description"
        field_str = ",".join(fields) if fields else default_fields
        return await self._request(
            "GET", f"/rest/api/3/issue/{issue_key}",
            params={"fields": field_str},
        )

    async def update_issue(
        self, issue_key: str, fields: dict[str, Any] | None = None,
    ) -> None:
        """Update issue fields."""
        await self._request(
            "PUT", f"/rest/api/3/issue/{issue_key}",
            json={"fields": fields or {}},
        )

    async def search_issues(
        self,
        jql: str,
        fields: list[str] | None = None,
        max_results: int = 50,
        start_at: int = 0,
    ) -> dict[str, Any]:
        """Search issues using JQL."""
        default_fields = "summary,status,issuetype,priority,labels,assignee"
        return await self._request(
            "GET", "/rest/api/3/search",
            params={
                "jql": jql, "maxResults": max_results, "startAt": start_at,
                "fields": ",".join(fields) if fields else default_fields,
            },
        )

    async def assign_issue(self, issue_key: str, account_id: str) -> None:
        """Assign an issue to a user."""
        await self._request(
            "PUT", f"/rest/api/3/issue/{issue_key}/assignee",
            json={"accountId": account_id},
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library && python -m pytest tests/test_jira_client.py -v`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library
git add src/library_server/pm/jira_client.py tests/test_jira_client.py
git commit -m "feat: add JiraClient issue CRUD and search methods"
```

---

### Task 4: `JiraClient` — Transitions, Comments, Links, Users

**Files:**
- Modify: `src/library_server/pm/jira_client.py`
- Modify: `tests/test_jira_client.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_jira_client.py`:

```python
class TestTransitionMethods:
    @pytest.fixture(autouse=True)
    def setup_env(self, monkeypatch):
        monkeypatch.setenv("JIRA_EMAIL", "user@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "test-token")

    @pytest.fixture
    def client(self):
        return JiraClient(site_url="https://test.atlassian.net")

    @pytest.mark.asyncio
    async def test_get_transitions(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.return_value = {"transitions": [
                {"id": "11", "name": "To Do", "to": {"name": "To Do"}},
                {"id": "21", "name": "In Progress", "to": {"name": "In Progress"}},
            ]}
            result = await client.get_transitions("COS-42")
        assert len(result["transitions"]) == 2
        mock.assert_called_once_with("GET", "/rest/api/3/issue/COS-42/transitions")

    @pytest.mark.asyncio
    async def test_transition_issue(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.return_value = None
            await client.transition_issue("COS-42", "21")
        mock.assert_called_once_with(
            "POST", "/rest/api/3/issue/COS-42/transitions",
            json={"transition": {"id": "21"}},
        )


class TestCommentMethods:
    @pytest.fixture(autouse=True)
    def setup_env(self, monkeypatch):
        monkeypatch.setenv("JIRA_EMAIL", "user@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "test-token")

    @pytest.fixture
    def client(self):
        return JiraClient(site_url="https://test.atlassian.net")

    @pytest.mark.asyncio
    async def test_add_comment(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.return_value = {"id": "10001", "body": {}}
            result = await client.add_comment("COS-42", "Progress update")
        assert result["id"] == "10001"
        call_json = mock.call_args.kwargs["json"]
        assert call_json["body"]["content"][0]["content"][0]["text"] == "Progress update"


class TestLinkMethods:
    @pytest.fixture(autouse=True)
    def setup_env(self, monkeypatch):
        monkeypatch.setenv("JIRA_EMAIL", "user@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "test-token")

    @pytest.fixture
    def client(self):
        return JiraClient(site_url="https://test.atlassian.net")

    @pytest.mark.asyncio
    async def test_create_issue_link(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.return_value = None
            await client.create_issue_link("Blocks", "COS-1", "COS-2")
        mock.assert_called_once_with("POST", "/rest/api/3/issueLink", json={
            "type": {"name": "Blocks"},
            "inwardIssue": {"key": "COS-1"},
            "outwardIssue": {"key": "COS-2"},
        })

    @pytest.mark.asyncio
    async def test_get_link_types(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.return_value = {"issueLinkTypes": [
                {"id": "1", "name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
            ]}
            result = await client.get_link_types()
        assert len(result["issueLinkTypes"]) == 1


class TestUserMethods:
    @pytest.fixture(autouse=True)
    def setup_env(self, monkeypatch):
        monkeypatch.setenv("JIRA_EMAIL", "user@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "test-token")

    @pytest.fixture
    def client(self):
        return JiraClient(site_url="https://test.atlassian.net")

    @pytest.mark.asyncio
    async def test_get_myself(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.return_value = {"accountId": "abc-123", "displayName": "David"}
            result = await client.get_myself()
        assert result["accountId"] == "abc-123"
        mock.assert_called_once_with("GET", "/rest/api/3/myself")

    @pytest.mark.asyncio
    async def test_find_users(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock) as mock:
            mock.return_value = [{"accountId": "abc-123", "displayName": "David"}]
            result = await client.find_users("david")
        assert len(result) == 1
        mock.assert_called_once_with("GET", "/rest/api/3/user/search", params={"query": "david"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library && python -m pytest tests/test_jira_client.py::TestTransitionMethods tests/test_jira_client.py::TestCommentMethods tests/test_jira_client.py::TestLinkMethods tests/test_jira_client.py::TestUserMethods -v`
Expected: FAIL — `AttributeError` for missing methods

- [ ] **Step 3: Implement remaining methods**

Append to `JiraClient` class in `src/library_server/pm/jira_client.py`:

```python
    # --- Transitions ---

    async def get_transitions(self, issue_key: str) -> dict[str, Any]:
        """Get available transitions for an issue."""
        return await self._request("GET", f"/rest/api/3/issue/{issue_key}/transitions")

    async def transition_issue(self, issue_key: str, transition_id: str) -> None:
        """Execute a status transition."""
        await self._request(
            "POST", f"/rest/api/3/issue/{issue_key}/transitions",
            json={"transition": {"id": transition_id}},
        )

    # --- Comments ---

    async def add_comment(self, issue_key: str, body: str) -> dict[str, Any]:
        """Add a comment to an issue."""
        return await self._request(
            "POST", f"/rest/api/3/issue/{issue_key}/comment",
            json={"body": {
                "type": "doc", "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": body}]}],
            }},
        )

    # --- Links ---

    async def create_issue_link(
        self, type_name: str, inward_key: str, outward_key: str,
    ) -> None:
        """Create a link between two issues."""
        await self._request("POST", "/rest/api/3/issueLink", json={
            "type": {"name": type_name},
            "inwardIssue": {"key": inward_key},
            "outwardIssue": {"key": outward_key},
        })

    async def get_link_types(self) -> dict[str, Any]:
        """List available issue link types."""
        return await self._request("GET", "/rest/api/3/issueLinkType")

    # --- Users ---

    async def get_myself(self) -> dict[str, Any]:
        """Get the authenticated user's account info."""
        return await self._request("GET", "/rest/api/3/myself")

    async def find_users(self, query: str) -> list[dict[str, Any]]:
        """Search for users by name or email."""
        return await self._request("GET", "/rest/api/3/user/search", params={"query": query})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library && python -m pytest tests/test_jira_client.py -v`
Expected: 21 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library
git add src/library_server/pm/jira_client.py tests/test_jira_client.py
git commit -m "feat: add JiraClient transition, comment, link, and user methods"
```

---

### Task 5: Add `ProjectResult` Type + Extend `PMAdapter` Interface

**Files:**
- Modify: `src/library_server/types.py`
- Modify: `src/library_server/pm/adapter.py`

- [ ] **Step 1: Add ProjectResult to types.py**

Add after the `EpicResult` dataclass in `src/library_server/types.py`:

```python
@dataclass
class ProjectResult:
    project_id: str
    project_key: str
    name: str
    description: str = ""
    lead: str = ""
    url: str = ""
```

- [ ] **Step 2: Extend PMAdapter with new abstract methods**

Replace `src/library_server/pm/adapter.py` with:

```python
"""Abstract PM adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from library_server.types import (
    EpicResult,
    ProjectResult,
    ProjectState,
    TaskResult,
    Transition,
)


class PMAdapter(ABC):
    """Abstract interface for project management tools.

    Jira and Linear implement this. User sets pm.provider in config.
    """

    @abstractmethod
    async def create_task(
        self,
        project_key: str,
        summary: str,
        description: str,
        labels: list[str] | None = None,
    ) -> TaskResult:
        ...

    @abstractmethod
    async def create_epic(
        self,
        project_key: str,
        summary: str,
        description: str,
    ) -> EpicResult:
        ...

    @abstractmethod
    async def update_task(
        self,
        task_id: str,
        status: str | None = None,
        comment: str | None = None,
    ) -> TaskResult:
        ...

    @abstractmethod
    async def query_tasks(
        self,
        project_key: str,
        filters: dict | None = None,
    ) -> list[TaskResult]:
        ...

    @abstractmethod
    async def sync_state(
        self,
        project_key: str,
    ) -> ProjectState:
        ...

    @abstractmethod
    async def get_transitions(
        self,
        task_id: str,
    ) -> list[Transition]:
        ...

    # --- Project management ---

    @abstractmethod
    async def create_project(
        self,
        name: str,
        key: str,
        description: str = "",
        lead_account_id: str = "",
    ) -> ProjectResult:
        ...

    @abstractmethod
    async def list_projects(self) -> list[ProjectResult]:
        ...

    @abstractmethod
    async def get_project(self, project_key: str) -> ProjectResult:
        ...

    @abstractmethod
    async def update_project(
        self,
        project_key: str,
        name: str = "",
        description: str = "",
    ) -> ProjectResult:
        ...

    # --- Assignment and linking ---

    @abstractmethod
    async def assign_task(self, task_id: str, account_id: str) -> TaskResult:
        ...

    @abstractmethod
    async def link_issues(
        self,
        type_name: str,
        inward_key: str,
        outward_key: str,
    ) -> None:
        ...

    @abstractmethod
    async def get_link_types(self) -> list[dict]:
        ...
```

- [ ] **Step 3: Run existing tests to check nothing breaks**

Run: `cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library && python -m pytest tests/test_jira_client.py -v`
Expected: 21 passed (JiraClient tests still pass, adapter tests will fail because JiraAdapter and LinearAdapter need updating — that's expected, we fix them next)

- [ ] **Step 4: Commit**

```bash
cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library
git add src/library_server/types.py src/library_server/pm/adapter.py
git commit -m "feat: add ProjectResult type and extend PMAdapter interface"
```

---

### Task 6: Rewrite `JiraAdapter` to Use `JiraClient`

**Files:**
- Rewrite: `src/library_server/pm/jira.py`
- Rewrite: `tests/test_pm_adapter.py` (Jira tests only)

- [ ] **Step 1: Write failing tests for new JiraAdapter**

Replace the `TestJiraAdapter`, `TestJiraAdapterExtended` classes in `tests/test_pm_adapter.py` with:

```python
"""Tests for PM adapter module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from library_server.pm.adapter import PMAdapter
from library_server.pm.jira import JiraAdapter
from library_server.pm.linear import LinearAdapter
from library_server.types import TaskStatus


class TestJiraAdapter:
    """Tests for Jira adapter — uses mocked JiraClient."""

    @pytest.fixture(autouse=True)
    def setup_env(self, monkeypatch):
        monkeypatch.setenv("JIRA_EMAIL", "user@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "test-token")

    @pytest.fixture
    def adapter(self):
        return JiraAdapter(site_url="https://test.atlassian.net")

    def test_implements_interface(self, adapter):
        assert isinstance(adapter, PMAdapter)

    @pytest.mark.asyncio
    async def test_create_task(self, adapter):
        adapter.client.create_issue = AsyncMock(return_value={
            "key": "COS-42",
            "fields": {"summary": "Test task", "status": {"name": "To Do"}, "labels": ["core"]},
        })
        result = await adapter.create_task("COS", "Test task", "Description", ["core"])
        assert result.task_id == "COS-42"
        assert result.summary == "Test task"
        assert result.project_key == "COS"
        adapter.client.create_issue.assert_called_once_with(
            project_key="COS", issue_type="Task",
            summary="Test task", description="Description", labels=["core"],
        )

    @pytest.mark.asyncio
    async def test_create_epic(self, adapter):
        adapter.client.create_issue = AsyncMock(return_value={
            "key": "COS-E1",
            "self": "https://test.atlassian.net/rest/api/3/issue/COS-E1",
        })
        result = await adapter.create_epic("COS", "My Epic", "Epic desc")
        assert result.epic_id == "COS-E1"
        assert result.project_key == "COS"
        adapter.client.create_issue.assert_called_once_with(
            project_key="COS", issue_type="Epic",
            summary="My Epic", description="Epic desc",
        )

    @pytest.mark.asyncio
    async def test_update_task_with_comment(self, adapter):
        adapter.client.add_comment = AsyncMock(return_value={"id": "1"})
        adapter.client.get_issue = AsyncMock(return_value={
            "key": "COS-1",
            "fields": {"summary": "Task", "status": {"name": "Open"}, "labels": []},
        })
        result = await adapter.update_task("COS-1", comment="Progress note")
        adapter.client.add_comment.assert_called_once_with("COS-1", "Progress note")
        assert result.task_id == "COS-1"

    @pytest.mark.asyncio
    async def test_update_task_with_transition(self, adapter):
        adapter.client.get_transitions = AsyncMock(return_value={"transitions": [
            {"id": "11", "name": "To Do", "to": {"name": "To Do"}},
            {"id": "21", "name": "In Progress", "to": {"name": "In Progress"}},
            {"id": "31", "name": "Done", "to": {"name": "Done"}},
        ]})
        adapter.client.transition_issue = AsyncMock()
        adapter.client.get_issue = AsyncMock(return_value={
            "key": "COS-1",
            "fields": {"summary": "Task", "status": {"name": "Done"}, "labels": []},
        })
        result = await adapter.update_task("COS-1", status="Done")
        adapter.client.transition_issue.assert_called_once_with("COS-1", "31")
        assert result.status == TaskStatus.DONE

    @pytest.mark.asyncio
    async def test_update_task_transition_not_found(self, adapter):
        adapter.client.get_transitions = AsyncMock(return_value={"transitions": [
            {"id": "11", "name": "To Do", "to": {"name": "To Do"}},
        ]})
        adapter.client.get_issue = AsyncMock(return_value={
            "key": "COS-1",
            "fields": {"summary": "Task", "status": {"name": "To Do"}, "labels": []},
        })
        result = await adapter.update_task("COS-1", status="Nonexistent")
        assert result.task_id == "COS-1"

    @pytest.mark.asyncio
    async def test_query_tasks(self, adapter):
        adapter.client.search_issues = AsyncMock(return_value={"issues": [
            {"key": "COS-1", "fields": {"summary": "Task 1", "status": {"name": "To Do"}, "labels": []}},
            {"key": "COS-2", "fields": {"summary": "Task 2", "status": {"name": "In Progress"}, "labels": []}},
        ]})
        results = await adapter.query_tasks("COS")
        assert len(results) == 2
        assert results[0].task_id == "COS-1"

    @pytest.mark.asyncio
    async def test_query_tasks_with_filters(self, adapter):
        adapter.client.search_issues = AsyncMock(return_value={"issues": [
            {"key": "COS-1", "fields": {"summary": "Bug", "status": {"name": "Open"}, "labels": ["bug"]}},
        ]})
        results = await adapter.query_tasks("COS", {"status": "Open", "labels": ["bug"]})
        assert len(results) == 1
        jql = adapter.client.search_issues.call_args.args[0]
        assert "status = 'Open'" in jql
        assert "labels in (bug)" in jql

    @pytest.mark.asyncio
    async def test_sync_state(self, adapter):
        adapter.client.search_issues = AsyncMock(return_value={"issues": [
            {"key": "COS-1", "fields": {"summary": "Open", "status": {"name": "Open"}, "labels": []}},
            {"key": "COS-2", "fields": {"summary": "Done", "status": {"name": "Done"}, "labels": []}},
            {"key": "COS-3", "fields": {"summary": "Blocked", "status": {"name": "Blocked"}, "labels": []}},
        ]})
        state = await adapter.sync_state("COS")
        assert len(state.open_tasks) == 1
        assert len(state.recently_closed) == 1
        assert len(state.blocked_tasks) == 1

    @pytest.mark.asyncio
    async def test_get_transitions(self, adapter):
        adapter.client.get_transitions = AsyncMock(return_value={"transitions": [
            {"id": "11", "name": "To Do", "to": {"name": "To Do"}},
            {"id": "21", "name": "In Progress", "to": {"name": "In Progress"}},
            {"id": "31", "name": "Done", "to": {"name": "Done"}},
        ]})
        transitions = await adapter.get_transitions("COS-1")
        assert len(transitions) == 3
        assert transitions[0].transition_id == "11"
        assert transitions[2].to_status == TaskStatus.DONE

    @pytest.mark.asyncio
    async def test_create_project(self, adapter):
        adapter.client.get_myself = AsyncMock(return_value={"accountId": "abc-123"})
        adapter.client.create_project = AsyncMock(return_value={
            "id": 10001, "key": "COS",
            "self": "https://test.atlassian.net/rest/api/3/project/10001",
        })
        result = await adapter.create_project("COMPLIANCE-OS", "COS", "Product features")
        assert result.project_key == "COS"
        assert result.name == "COMPLIANCE-OS"

    @pytest.mark.asyncio
    async def test_list_projects(self, adapter):
        adapter.client.list_projects = AsyncMock(return_value={"values": [
            {"id": "10001", "key": "COS", "name": "COMPLIANCE-OS", "description": ""},
            {"id": "10002", "key": "PLT", "name": "PLATFORM", "description": ""},
        ]})
        results = await adapter.list_projects()
        assert len(results) == 2
        assert results[0].project_key == "COS"

    @pytest.mark.asyncio
    async def test_get_project(self, adapter):
        adapter.client.get_project = AsyncMock(return_value={
            "id": "10001", "key": "COS", "name": "COMPLIANCE-OS",
            "description": "Product features", "lead": {"displayName": "David"},
        })
        result = await adapter.get_project("COS")
        assert result.project_key == "COS"
        assert result.lead == "David"

    @pytest.mark.asyncio
    async def test_assign_task(self, adapter):
        adapter.client.assign_issue = AsyncMock()
        adapter.client.get_issue = AsyncMock(return_value={
            "key": "COS-42",
            "fields": {"summary": "Task", "status": {"name": "Open"}, "labels": []},
        })
        result = await adapter.assign_task("COS-42", "abc-123")
        adapter.client.assign_issue.assert_called_once_with("COS-42", "abc-123")
        assert result.task_id == "COS-42"

    @pytest.mark.asyncio
    async def test_link_issues(self, adapter):
        adapter.client.create_issue_link = AsyncMock()
        await adapter.link_issues("Blocks", "COS-1", "COS-2")
        adapter.client.create_issue_link.assert_called_once_with("Blocks", "COS-1", "COS-2")

    @pytest.mark.asyncio
    async def test_get_link_types(self, adapter):
        adapter.client.get_link_types = AsyncMock(return_value={"issueLinkTypes": [
            {"id": "1", "name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
        ]})
        result = await adapter.get_link_types()
        assert len(result) == 1
        assert result[0]["name"] == "Blocks"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library && python -m pytest tests/test_pm_adapter.py::TestJiraAdapter -v`
Expected: FAIL — adapter still uses `_call_mcp`

- [ ] **Step 3: Rewrite JiraAdapter**

Replace `src/library_server/pm/jira.py` with:

```python
"""Jira PM adapter — wraps JiraClient with Library types."""

from __future__ import annotations

from library_server.pm.adapter import PMAdapter
from library_server.pm.jira_client import JiraClient
from library_server.types import (
    EpicResult,
    ProjectResult,
    ProjectState,
    TaskResult,
    TaskStatus,
    Transition,
)

STATUS_MAP = {
    "to do": TaskStatus.OPEN,
    "open": TaskStatus.OPEN,
    "in progress": TaskStatus.IN_PROGRESS,
    "done": TaskStatus.DONE,
    "closed": TaskStatus.DONE,
    "blocked": TaskStatus.BLOCKED,
}


class JiraAdapter(PMAdapter):
    """Jira implementation using direct REST API via JiraClient."""

    def __init__(self, site_url: str = ""):
        self.site_url = site_url
        self.client = JiraClient(site_url=site_url)

    # --- Tasks ---

    async def create_task(
        self,
        project_key: str,
        summary: str,
        description: str,
        labels: list[str] | None = None,
    ) -> TaskResult:
        result = await self.client.create_issue(
            project_key=project_key, issue_type="Task",
            summary=summary, description=description, labels=labels or [],
        )
        return _parse_issue(result, project_key)

    async def create_epic(
        self,
        project_key: str,
        summary: str,
        description: str,
    ) -> EpicResult:
        result = await self.client.create_issue(
            project_key=project_key, issue_type="Epic",
            summary=summary, description=description,
        )
        return EpicResult(
            epic_id=result["key"],
            project_key=project_key,
            summary=summary,
            url=result.get("self", ""),
        )

    async def update_task(
        self,
        task_id: str,
        status: str | None = None,
        comment: str | None = None,
    ) -> TaskResult:
        if comment:
            await self.client.add_comment(task_id, comment)
        if status:
            transitions = await self.client.get_transitions(task_id)
            for t in transitions.get("transitions", []):
                if t["name"].lower() == status.lower():
                    await self.client.transition_issue(task_id, t["id"])
                    break
        issue = await self.client.get_issue(task_id)
        project_key = task_id.split("-")[0]
        return _parse_issue(issue, project_key)

    async def query_tasks(
        self,
        project_key: str,
        filters: dict | None = None,
    ) -> list[TaskResult]:
        jql = f"project = {project_key}"
        if filters:
            if filters.get("status"):
                jql += f" AND status = '{filters['status']}'"
            if filters.get("labels"):
                jql += f" AND labels in ({','.join(filters['labels'])})"
        result = await self.client.search_issues(jql)
        return [_parse_issue(issue, project_key) for issue in result.get("issues", [])]

    async def sync_state(self, project_key: str) -> ProjectState:
        all_tasks = await self.query_tasks(project_key)
        return ProjectState(
            project_key=project_key,
            project_name=project_key,
            open_tasks=[t for t in all_tasks if t.status == TaskStatus.OPEN],
            stale_tasks=[],
            blocked_tasks=[t for t in all_tasks if t.status == TaskStatus.BLOCKED],
            recently_closed=[t for t in all_tasks if t.status == TaskStatus.DONE],
        )

    async def get_transitions(self, task_id: str) -> list[Transition]:
        result = await self.client.get_transitions(task_id)
        return [
            Transition(
                transition_id=t["id"],
                name=t["name"],
                to_status=STATUS_MAP.get(t["to"]["name"].lower(), TaskStatus.OPEN),
            )
            for t in result.get("transitions", [])
        ]

    # --- Projects ---

    async def create_project(
        self,
        name: str,
        key: str,
        description: str = "",
        lead_account_id: str = "",
    ) -> ProjectResult:
        if not lead_account_id:
            me = await self.client.get_myself()
            lead_account_id = me["accountId"]
        result = await self.client.create_project(
            name=name, key=key, lead_account_id=lead_account_id, description=description,
        )
        return ProjectResult(
            project_id=str(result.get("id", "")),
            project_key=result.get("key", key),
            name=name,
            description=description,
            url=result.get("self", ""),
        )

    async def list_projects(self) -> list[ProjectResult]:
        result = await self.client.list_projects()
        return [
            ProjectResult(
                project_id=str(p.get("id", "")),
                project_key=p.get("key", ""),
                name=p.get("name", ""),
                description=p.get("description", ""),
                lead=p.get("lead", {}).get("displayName", "") if isinstance(p.get("lead"), dict) else "",
                url=p.get("self", ""),
            )
            for p in result.get("values", [])
        ]

    async def get_project(self, project_key: str) -> ProjectResult:
        p = await self.client.get_project(project_key)
        return ProjectResult(
            project_id=str(p.get("id", "")),
            project_key=p.get("key", ""),
            name=p.get("name", ""),
            description=p.get("description", ""),
            lead=p.get("lead", {}).get("displayName", "") if isinstance(p.get("lead"), dict) else "",
            url=p.get("self", ""),
        )

    async def update_project(
        self,
        project_key: str,
        name: str = "",
        description: str = "",
    ) -> ProjectResult:
        fields = {}
        if name:
            fields["name"] = name
        if description:
            fields["description"] = description
        await self.client.update_project(project_key, **fields)
        return await self.get_project(project_key)

    # --- Assignment and linking ---

    async def assign_task(self, task_id: str, account_id: str) -> TaskResult:
        await self.client.assign_issue(task_id, account_id)
        issue = await self.client.get_issue(task_id)
        project_key = task_id.split("-")[0]
        return _parse_issue(issue, project_key)

    async def link_issues(
        self,
        type_name: str,
        inward_key: str,
        outward_key: str,
    ) -> None:
        await self.client.create_issue_link(type_name, inward_key, outward_key)

    async def get_link_types(self) -> list[dict]:
        result = await self.client.get_link_types()
        return result.get("issueLinkTypes", [])


def _parse_issue(data: dict, project_key: str) -> TaskResult:
    """Parse a Jira issue response into TaskResult."""
    fields = data.get("fields", {})
    status_name = fields.get("status", {}).get("name", "Open").lower()
    return TaskResult(
        task_id=data.get("key", ""),
        project_key=project_key,
        summary=fields.get("summary", ""),
        status=STATUS_MAP.get(status_name, TaskStatus.OPEN),
        labels=fields.get("labels", []),
        url=data.get("self", ""),
    )
```

- [ ] **Step 4: Run Jira adapter tests to verify they pass**

Run: `cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library && python -m pytest tests/test_pm_adapter.py::TestJiraAdapter -v`
Expected: All Jira tests pass

- [ ] **Step 5: Commit**

```bash
cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library
git add src/library_server/pm/jira.py tests/test_pm_adapter.py
git commit -m "feat: rewrite JiraAdapter to use JiraClient direct REST API"
```

---

### Task 7: Stub Linear Adapter for New Methods

**Files:**
- Modify: `src/library_server/pm/linear.py`
- Modify: `tests/test_pm_adapter.py` (Linear tests)

- [ ] **Step 1: Add stubs to LinearAdapter**

Add the following methods to `LinearAdapter` in `src/library_server/pm/linear.py`, after the existing `get_transitions` method. Also add the `ProjectResult` import:

```python
# Add to imports at top:
from library_server.types import (
    EpicResult,
    ProjectResult,
    ProjectState,
    TaskResult,
    TaskStatus,
    Transition,
)

# Add after get_transitions method:

    async def create_project(
        self, name: str, key: str, description: str = "", lead_account_id: str = "",
    ) -> ProjectResult:
        raise NotImplementedError("Not supported by Linear adapter")

    async def list_projects(self) -> list[ProjectResult]:
        raise NotImplementedError("Not supported by Linear adapter")

    async def get_project(self, project_key: str) -> ProjectResult:
        raise NotImplementedError("Not supported by Linear adapter")

    async def update_project(
        self, project_key: str, name: str = "", description: str = "",
    ) -> ProjectResult:
        raise NotImplementedError("Not supported by Linear adapter")

    async def assign_task(self, task_id: str, account_id: str) -> TaskResult:
        raise NotImplementedError("Not supported by Linear adapter")

    async def link_issues(
        self, type_name: str, inward_key: str, outward_key: str,
    ) -> None:
        raise NotImplementedError("Not supported by Linear adapter")

    async def get_link_types(self) -> list[dict]:
        raise NotImplementedError("Not supported by Linear adapter")
```

- [ ] **Step 2: Add Linear stub tests**

Add to `TestLinearAdapterExtended` in `tests/test_pm_adapter.py`:

```python
    @pytest.mark.asyncio
    async def test_create_project_not_supported(self):
        adapter = LinearAdapter(api_key="test-key")
        with pytest.raises(NotImplementedError, match="Not supported"):
            await adapter.create_project("Test", "TST")

    @pytest.mark.asyncio
    async def test_list_projects_not_supported(self):
        adapter = LinearAdapter(api_key="test-key")
        with pytest.raises(NotImplementedError, match="Not supported"):
            await adapter.list_projects()

    @pytest.mark.asyncio
    async def test_assign_task_not_supported(self):
        adapter = LinearAdapter(api_key="test-key")
        with pytest.raises(NotImplementedError, match="Not supported"):
            await adapter.assign_task("TST-1", "abc")

    @pytest.mark.asyncio
    async def test_link_issues_not_supported(self):
        adapter = LinearAdapter(api_key="test-key")
        with pytest.raises(NotImplementedError, match="Not supported"):
            await adapter.link_issues("Blocks", "A-1", "A-2")
```

- [ ] **Step 3: Run all adapter tests**

Run: `cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library && python -m pytest tests/test_pm_adapter.py -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library
git add src/library_server/pm/linear.py tests/test_pm_adapter.py
git commit -m "feat: stub Linear adapter for new PMAdapter interface methods"
```

---

### Task 8: Add New MCP Tools to server.py

**Files:**
- Modify: `src/library_server/server.py`

- [ ] **Step 1: Add project management MCP tools**

Add the following after the existing `library_pm_query` tool in `src/library_server/server.py`:

```python
@mcp.tool(name="library_pm_create_project")
async def library_pm_create_project(
    name: str, key: str, description: str = "", project_type_key: str = "software",
) -> dict:
    """Create a Jira project. Requires admin access."""
    adapter = _get_pm_adapter()
    result = await adapter.create_project(name, key, description)
    return {"project_key": result.project_key, "name": result.name, "url": result.url}


@mcp.tool(name="library_pm_list_projects")
async def library_pm_list_projects() -> dict:
    """List all visible projects."""
    adapter = _get_pm_adapter()
    results = await adapter.list_projects()
    return {
        "count": len(results),
        "projects": [
            {"key": p.project_key, "name": p.name, "description": p.description}
            for p in results
        ],
    }


@mcp.tool(name="library_pm_get_project")
async def library_pm_get_project(project_key: str) -> dict:
    """Get project details."""
    adapter = _get_pm_adapter()
    result = await adapter.get_project(project_key)
    return {
        "project_key": result.project_key, "name": result.name,
        "description": result.description, "lead": result.lead, "url": result.url,
    }


@mcp.tool(name="library_pm_update_project")
async def library_pm_update_project(
    project_key: str, name: str = "", description: str = "",
) -> dict:
    """Update project name or description."""
    adapter = _get_pm_adapter()
    result = await adapter.update_project(project_key, name, description)
    return {"project_key": result.project_key, "name": result.name, "url": result.url}


@mcp.tool(name="library_pm_assign_task")
async def library_pm_assign_task(task_id: str, account_id: str) -> dict:
    """Assign a task to a user by account ID."""
    adapter = _get_pm_adapter()
    result = await adapter.assign_task(task_id, account_id)
    return {"task_id": result.task_id, "status": result.status.value}


@mcp.tool(name="library_pm_link_issues")
async def library_pm_link_issues(
    type_name: str, inward_key: str, outward_key: str,
) -> dict:
    """Link two issues (e.g., 'Blocks', 'Relates')."""
    adapter = _get_pm_adapter()
    await adapter.link_issues(type_name, inward_key, outward_key)
    return {"status": "linked", "type": type_name, "inward": inward_key, "outward": outward_key}


@mcp.tool(name="library_pm_get_link_types")
async def library_pm_get_link_types() -> dict:
    """List available issue link types."""
    adapter = _get_pm_adapter()
    types = await adapter.get_link_types()
    return {"types": types}
```

- [ ] **Step 2: Run server module to verify no import errors**

Run: `cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library && python -c "from library_server.server import mcp; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library
git add src/library_server/server.py
git commit -m "feat: add 7 new MCP tools for project management, assignment, and linking"
```

---

### Task 9: Consolidate Vault Builder Jira Extractor

**Files:**
- Modify: `src/library_server/vault_builder/extractors/jira.py`
- Modify: `tests/vault_builder/extractors/test_jira.py`

- [ ] **Step 1: Refactor extractor to use JiraClient**

Replace the `_build_auth_headers` and `_fetch_issues` methods in `src/library_server/vault_builder/extractors/jira.py`. Remove the `import base64` and `import os` at the top (os still needed for validate_config). Replace with:

```python
"""Jira extractor — Atlassian issues via JiraClient."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from library_server.pm.jira_client import JiraClient
from library_server.vault_builder.extractors.base import BaseExtractor
from library_server.vault_builder.output import OutputWriter
from library_server.vault_builder.types import SurveyResult, PreviewResult, ExtractResult

_STATUS_TRUST: dict[str, float] = {
    "done": 0.8, "closed": 0.8, "in progress": 0.6, "in review": 0.6,
    "to do": 0.5, "backlog": 0.5, "open": 0.5,
}

_STATUS_TAG_MAP: dict[str, str] = {
    "done": "done", "closed": "done", "in progress": "in-progress",
    "in review": "in-progress", "to do": "backlog", "backlog": "backlog", "open": "backlog",
}


class JiraExtractor(BaseExtractor):
    name = "jira"
    display_name = "Jira Issues"
    source_description = "Jira issues via Atlassian API"
    output_subdir = "jira"

    def validate_config(self) -> list[str]:
        errors: list[str] = []
        if not self.config.get("projects"):
            errors.append("Missing required config: projects")
        if not os.environ.get("JIRA_API_TOKEN"):
            errors.append("Missing env var: JIRA_API_TOKEN")
        if not os.environ.get("JIRA_EMAIL"):
            errors.append("Missing env var: JIRA_EMAIL")
        return errors

    def _get_client(self) -> JiraClient:
        """Get a JiraClient for the configured instance."""
        site_url = f"https://{self.config.get('instance', '')}"
        return JiraClient(site_url=site_url)

    async def _fetch_issues(self, project: str) -> list[dict[str, Any]]:
        """Fetch all issues for a project via JiraClient."""
        client = self._get_client()
        result = await client.search_issues(
            jql=f"project = {project}",
            fields=["summary", "description", "issuetype", "status", "assignee", "labels", "issuelinks", "comment"],
            max_results=100,
        )
        return result.get("issues", [])
```

The `survey`, `preview`, and `extract` methods remain unchanged — they call `_fetch_issues` which now goes through `JiraClient`.

- [ ] **Step 2: Update tests to mock JiraClient instead of _fetch_issues directly**

The existing tests in `tests/vault_builder/extractors/test_jira.py` mock `_fetch_issues` via `patch.object(jira_extractor, "_fetch_issues", ...)` which still works because we kept the method signature. But update the fixture to ensure env vars are set (already done).

Run the existing tests to verify nothing broke:

Run: `cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library && python -m pytest tests/vault_builder/extractors/test_jira.py -v`
Expected: All tests pass (mocking `_fetch_issues` still works)

- [ ] **Step 3: Commit**

```bash
cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library
git add src/library_server/vault_builder/extractors/jira.py
git commit -m "refactor: consolidate vault builder Jira extractor to use JiraClient"
```

---

### Task 10: Consolidate Hooks Jira Client

**Files:**
- Modify: `src/library_server/hooks/jira_client.py`
- Modify: `tests/test_hooks/test_jira_client.py`

- [ ] **Step 1: Rewrite hooks jira_client to use JiraClient**

Replace `src/library_server/hooks/jira_client.py` with:

```python
"""Direct Jira REST API client for zero-token task fetching.

Uses the shared JiraClient for HTTP. Preserves the fetch_issue_summary
function signature for backward compatibility with hook callers.
"""

from library_server.pm.jira_client import JiraClient, JiraApiError


async def fetch_issue_summary(
    base_url: str,
    api_token: str,
    email: str,
    issue_key: str,
) -> dict | None:
    """Fetch a Jira issue's summary and status.

    Args:
        base_url: The Jira instance base URL, e.g. "https://example.atlassian.net".
        api_token: Jira API token (unused — reads from env, kept for backward compat).
        email: Email address (unused — reads from env, kept for backward compat).
        issue_key: The issue key, e.g. "COS-42".

    Returns:
        A dict with keys ``key``, ``summary``, and ``status``, or ``None`` if
        the issue is not found or a network error occurs.
    """
    try:
        client = JiraClient(site_url=base_url)
        data = await client.get_issue(issue_key, fields=["summary", "status"])
        return {
            "key": data["key"],
            "summary": data["fields"]["summary"],
            "status": data["fields"]["status"]["name"],
        }
    except (JiraApiError, ValueError, KeyError):
        return None
    except Exception:
        return None
```

- [ ] **Step 2: Update tests**

Replace `tests/test_hooks/test_jira_client.py` with:

```python
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
```

- [ ] **Step 3: Run tests**

Run: `cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library && python -m pytest tests/test_hooks/test_jira_client.py -v`
Expected: 3 passed

- [ ] **Step 4: Commit**

```bash
cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library
git add src/library_server/hooks/jira_client.py tests/test_hooks/test_jira_client.py
git commit -m "refactor: consolidate hooks Jira client to use shared JiraClient"
```

---

### Task 11: Full Test Suite Pass

**Files:**
- No new files — verification only

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library && python -m pytest --tb=short -q`
Expected: All tests pass, no regressions

- [ ] **Step 2: Fix any failures**

If any tests fail, fix them. Common issues:
- Import paths changed
- Mock targets moved
- Missing env vars in test fixtures

- [ ] **Step 3: Commit any fixes**

```bash
cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library
git add -A
git commit -m "fix: resolve test regressions from Jira integration rewrite"
```

---

### Task 12: Documentation — Jira Setup Guide

**Files:**
- Create: `docs/setup/jira-setup.md`

- [ ] **Step 1: Write the Jira setup guide**

```markdown
# Jira Setup Guide

## Prerequisites

- A Jira Cloud instance (e.g., `yoursite.atlassian.net`)
- Admin access for project creation
- An Atlassian account with API token access

## 1. Create an API Token

1. Go to [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Click **Create API token**
3. Give it a label (e.g., "The Library")
4. Copy the token — you won't see it again

## 2. Configure Environment Variables

Add to your shell profile (`~/.zshrc`, `~/.bashrc`, etc.):

\`\`\`bash
export JIRA_EMAIL="your-email@example.com"
export JIRA_API_TOKEN="your-api-token"
\`\`\`

Reload your shell: `source ~/.zshrc`

These env vars are used by The Library's `JiraClient` for Basic Auth against the Jira REST API v3. They're passed to the MCP server via `.mcp.json`:

\`\`\`json
{
  "library": {
    "command": "library",
    "env": {
      "JIRA_EMAIL": "${JIRA_EMAIL}",
      "JIRA_API_TOKEN": "${JIRA_API_TOKEN}"
    }
  }
}
\`\`\`

## 3. Configure The Library

In your `library-config.yaml`:

\`\`\`yaml
pm:
  provider: jira
  site_url: https://yoursite.atlassian.net
  projects:
    - key: PROJ
      name: My Project
\`\`\`

Or use the config skill:

\`\`\`
library:config
\`\`\`

## 4. Create Projects

Use the `library_pm_create_project` MCP tool:

\`\`\`
Create project COMPLIANCE-OS with key COS
\`\`\`

Or verify existing projects:

\`\`\`
List all Jira projects
\`\`\`

## 5. Verify

\`\`\`
library_pm_list_projects
\`\`\`

Should return all your configured projects.

## Vault Builder Integration

The vault builder's Jira extractor uses the same `JiraClient` and credentials. Configure in `library-config.yaml`:

\`\`\`yaml
vault_builder:
  sources:
    jira:
      enabled: true
      instance: yoursite.atlassian.net
      projects: [PROJ]
      auth: api_token
\`\`\`

## Why Not the Atlassian MCP?

The Library uses direct Jira REST API calls instead of the Atlassian MCP server. Here's why:

**OAuth scope limitations.** The Atlassian MCP's OAuth scopes (`read:jira-work`, `write:jira-work`) don't include project administration. You can't create projects, manage workflows, or perform admin operations through it.

**Agent-in-the-loop requirement.** Every MCP tool call requires the LLM to mediate — the adapter can't make Jira calls on its own. This consumes tokens and prevents background automation like hooks, scheduled syncs, or vault builds from accessing Jira data.

**No consolidation.** With the MCP approach, each consumer (PM adapter, vault builder, hooks) needs separate wiring to route through MCP tool calls. With a shared `JiraClient`, all three import one class.

**Basic Auth is sufficient.** Jira Cloud's REST API v3 works with email + API token, providing full access to every endpoint The Library needs — including project creation, issue management, and search — without OAuth complexity.

The Atlassian MCP remains useful for ad-hoc Jira/Confluence exploration in Claude Code, but The Library doesn't depend on it for any functionality.
```

- [ ] **Step 2: Commit**

```bash
cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library
mkdir -p docs/setup
git add docs/setup/jira-setup.md
git commit -m "docs: add Jira setup guide with API token, config, and MCP rationale"
```

---

### Task 13: Documentation — Quickstart, Linear Placeholder, PM Guide, API Reference

**Files:**
- Create: `docs/setup/quickstart.md`
- Create: `docs/setup/linear-setup.md`
- Create: `docs/guides/pm-integration.md`
- Create: `docs/reference/jira-api.md`

- [ ] **Step 1: Write quickstart.md**

```markdown
# Quickstart

## Install

\`\`\`bash
pip install the-library
\`\`\`

## Initialize

\`\`\`bash
cd your-project
library init
\`\`\`

This creates: config file, Reading Room, vault structure, runtime directories, SESSION.md, PROJECT-STATE.md, domain manifests, hooks, and validation.

## Optional: Claude Code Plugin

\`\`\`bash
claude plugins install sevenbelowllc/the-library
\`\`\`

## Configure PM Integration

\`\`\`bash
library:config
\`\`\`

Or edit `library-config.yaml` directly. See:
- [Jira Setup](jira-setup.md)
- [Linear Setup](linear-setup.md)

## Verify

\`\`\`bash
library validate
library doctor    # auto-fix common issues
\`\`\`
```

- [ ] **Step 2: Write linear-setup.md**

```markdown
# Linear Setup

> **Status:** Linear adapter supports issue and epic management. Project management features (create/list/update projects, assignment, issue linking) are not yet supported.

## Prerequisites

- A Linear workspace
- A Linear API key

## 1. Create an API Key

1. Go to Linear → Settings → API → Personal API keys
2. Create a new key
3. Copy the key

## 2. Configure The Library

In `library-config.yaml`:

\`\`\`yaml
pm:
  provider: linear
  api_key: lin_api_xxxxxxxxxxxx
\`\`\`

## Supported Operations

- Create tasks
- Create epics (mapped to Linear Projects)
- Query tasks
- Update task status and comments
- Sync project state
- Get workflow transitions

## Not Yet Supported

- Project creation / management
- Task assignment
- Issue linking
```

- [ ] **Step 3: Write pm-integration.md**

```markdown
# Project Management Integration

The Library provides a unified PM adapter that works with Jira and Linear. All PM operations go through the adapter, which maps provider-specific responses to Library types.

## Architecture

\`\`\`
MCP Tools (server.py)
    ↓
PMAdapter (abstract interface)
    ├── JiraAdapter → JiraClient → Jira REST API v3
    └── LinearAdapter → Linear GraphQL API
\`\`\`

## Capabilities

| Feature | Jira | Linear |
|---------|------|--------|
| Create project | Yes | No |
| List projects | Yes | No |
| Update project | Yes | No |
| Create task | Yes | Yes |
| Create epic | Yes | Yes |
| Update task | Yes | Yes |
| Query (JQL/filter) | Yes | Yes |
| Sync state | Yes | Yes |
| Transitions | Yes | Yes |
| Assign task | Yes | No |
| Link issues | Yes | No |
| Comments | Yes | Yes |

## MCP Tools

### Project Management
- `library_pm_create_project` — Create a project (Jira only)
- `library_pm_list_projects` — List all visible projects
- `library_pm_get_project` — Get project details
- `library_pm_update_project` — Update name/description

### Ticket Management
- `library_pm_create_task` — Create a task with labels
- `library_pm_create_epic` — Create an epic
- `library_pm_update` — Update status or add comment
- `library_pm_query` — Search by project, status, labels
- `library_pm_sync` — Pull full project state

### Assignment and Linking
- `library_pm_assign_task` — Assign to user by account ID
- `library_pm_link_issues` — Link two issues (Blocks, Relates, etc.)
- `library_pm_get_link_types` — List available link types

## Configuration

Set provider in `library-config.yaml`:

\`\`\`yaml
pm:
  provider: jira          # jira | linear | none
  site_url: https://yoursite.atlassian.net   # Jira only
  projects:               # tracked projects
    - key: COS
      name: COMPLIANCE-OS
\`\`\`

## Vault Builder Integration

The vault builder's Jira extractor uses the same `JiraClient` to ingest issues into the knowledge vault. This means PM operations and vault builds share one HTTP client — auth configured once, no duplication.
```

- [ ] **Step 4: Write jira-api.md**

```markdown
# Jira REST API Reference

The Library's `JiraClient` uses the following Jira Cloud REST API v3 endpoints.

## Authentication

Basic Auth: `base64(email:api_token)` in the `Authorization` header.

Base URL: `https://{site}.atlassian.net/rest/api/3`

## Endpoints

### Projects

| Method | Endpoint | Library Method |
|--------|----------|---------------|
| `POST /project` | Create project | `JiraClient.create_project()` |
| `GET /project/search` | List projects | `JiraClient.list_projects()` |
| `GET /project/{key}` | Get project | `JiraClient.get_project()` |
| `PUT /project/{key}` | Update project | `JiraClient.update_project()` |

### Issues

| Method | Endpoint | Library Method |
|--------|----------|---------------|
| `POST /issue` | Create issue | `JiraClient.create_issue()` |
| `GET /issue/{key}` | Get issue | `JiraClient.get_issue()` |
| `PUT /issue/{key}` | Update fields | `JiraClient.update_issue()` |
| `GET /search` | JQL search | `JiraClient.search_issues()` |
| `PUT /issue/{key}/assignee` | Assign issue | `JiraClient.assign_issue()` |

### Transitions

| Method | Endpoint | Library Method |
|--------|----------|---------------|
| `GET /issue/{key}/transitions` | List transitions | `JiraClient.get_transitions()` |
| `POST /issue/{key}/transitions` | Execute transition | `JiraClient.transition_issue()` |

### Comments

| Method | Endpoint | Library Method |
|--------|----------|---------------|
| `POST /issue/{key}/comment` | Add comment | `JiraClient.add_comment()` |

### Links

| Method | Endpoint | Library Method |
|--------|----------|---------------|
| `POST /issueLink` | Create link | `JiraClient.create_issue_link()` |
| `GET /issueLinkType` | List link types | `JiraClient.get_link_types()` |

### Users

| Method | Endpoint | Library Method |
|--------|----------|---------------|
| `GET /myself` | Current user | `JiraClient.get_myself()` |
| `GET /user/search` | Find users | `JiraClient.find_users()` |

## Description Format

Jira REST API v3 uses Atlassian Document Format (ADF) for descriptions and comments, not plain text. The `JiraClient` wraps plain text strings in ADF automatically:

\`\`\`json
{
  "type": "doc",
  "version": 1,
  "content": [
    {
      "type": "paragraph",
      "content": [{"type": "text", "text": "Your text here"}]
    }
  ]
}
\`\`\`

## Error Handling

All non-2xx responses raise `JiraApiError` with:
- `status_code` — HTTP status
- `message` — Jira error message
- `endpoint` — The API path that failed

Common errors:
- `401` — Invalid or expired API token
- `403` — Insufficient permissions (e.g., project creation requires admin)
- `404` — Issue or project not found
- `400` — Invalid JQL, missing required fields
```

- [ ] **Step 5: Commit**

```bash
cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library
mkdir -p docs/setup docs/guides docs/reference
git add docs/setup/quickstart.md docs/setup/linear-setup.md docs/guides/pm-integration.md docs/reference/jira-api.md
git commit -m "docs: add quickstart, Linear placeholder, PM guide, and Jira API reference"
```

---

### Task 14: Update README to Link to Docs

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add docs section to README**

Add after the "MCP Server" section (before "Configuration") in `README.md`:

```markdown
## Documentation

| Guide | Purpose |
|-------|---------|
| [Quickstart](docs/setup/quickstart.md) | Install, init, first run |
| [Jira Setup](docs/setup/jira-setup.md) | API token, env vars, project setup |
| [Linear Setup](docs/setup/linear-setup.md) | Linear integration (partial) |
| [PM Integration](docs/guides/pm-integration.md) | End-to-end project & ticket management |
| [Jira API Reference](docs/reference/jira-api.md) | REST endpoints, field mappings |
```

- [ ] **Step 2: Update MCP server tool count**

Update the line that says "20 tools across 6 modules" to reflect the 7 new tools (27 total). Update the PM row in the tool table:

```markdown
| PM | `library:pm:create_task`, `library:pm:create_epic`, `library:pm:sync`, `library:pm:update`, `library:pm:query`, `library:pm:create_project`, `library:pm:list_projects`, `library:pm:get_project`, `library:pm:update_project`, `library:pm:assign_task`, `library:pm:link_issues`, `library:pm:get_link_types` |
```

- [ ] **Step 3: Commit**

```bash
cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library
git add README.md
git commit -m "docs: update README with docs links and new PM tool count"
```

---

### Task 15: Update Config + Final Verification

**Files:**
- Modify: `library-config.yaml`
- Modify: `library-config.example.yaml`

- [ ] **Step 1: Update library-config.yaml with projects list**

Add projects list to the `pm:` section in `library-config.yaml`:

```yaml
pm:
  provider: jira
  site_url: https://sevenbelow.atlassian.net
  projects:
    - key: LIBRARY
      name: THE LIBRARY
    - key: COS
      name: COMPLIANCE-OS
    - key: PLT
      name: PLATFORM
    - key: SEC
      name: SECURITY
    - key: SB
      name: SEVENBELOW
    - key: DEIOCAP
      name: DEIO-CAPSTONE
```

- [ ] **Step 2: Update example config with Jira section**

Update `pm:` section in `library-config.example.yaml` to show Jira example:

```yaml
pm:
  provider: "none"                      # jira | linear | none
  # site_url: "https://yoursite.atlassian.net"  # Jira only
  projects: []                          # list of {key, name} objects
  # Example:
  # projects:
  #   - key: "PROJ"
  #     name: "My Project"
  #
  # Jira requires JIRA_EMAIL and JIRA_API_TOKEN env vars.
  # See docs/setup/jira-setup.md for full setup instructions.
```

- [ ] **Step 3: Run full test suite one final time**

Run: `cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library && python -m pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
cd /Users/pollucts/workdir/sevenbelow/compliance-os-project/the-library
git add library-config.yaml library-config.example.yaml
git commit -m "chore: update config with Jira projects list and example docs reference"
```
