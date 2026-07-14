"""JiraClient — standalone Jira REST API client using Basic Auth.

Replaces MCP-mediated Atlassian integration with direct HTTP calls.
All other layers (adapter, MCP tools, vault builder) import from here.
"""

from __future__ import annotations

import asyncio
import base64
import os
from typing import Any

import httpx

from library_server.pm.md_to_adf import md_to_adf

# Statuses worth retrying: rate limiting and transient gateway failures.
_RETRYABLE_STATUSES = {429, 502, 503, 504}
# Total attempts per request (initial + retries).
_MAX_ATTEMPTS = 3
# Exponential backoff base in seconds (0.5, 1.0, ...) when Jira sends no
# Retry-After header.
_BACKOFF_BASE = 0.5


class JiraApiError(Exception):
    """Raised when the Jira API returns a non-2xx status code."""

    def __init__(self, status_code: int, message: str, endpoint: str) -> None:
        self.status_code = status_code
        self.message = message
        self.endpoint = endpoint
        super().__init__(f"Jira API {status_code} on {endpoint}: {message}")


class JiraClient:
    """Async Jira REST API v3 client with Basic Auth."""

    def __init__(
        self,
        site_url: str,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        email = os.environ.get("ATLASSIAN_EMAIL")
        token = os.environ.get("JIRA_API_TOKEN")
        if not email:
            raise ValueError("ATLASSIAN_EMAIL environment variable is required")
        if not token:
            raise ValueError("JIRA_API_TOKEN environment variable is required")

        self._site_url = site_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport
        self._http: httpx.AsyncClient | None = None
        creds = base64.b64encode(f"{email}:{token}".encode()).decode()
        self._auth_header = f"Basic {creds}"
        self._epic_name_field_id: str | None = None

    def _get_http(self) -> httpx.AsyncClient:
        """Return the shared AsyncClient, creating it on first use.

        One client per JiraClient instance keeps the TCP/TLS connection
        alive across requests instead of handshaking on every call.
        """
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=self._timeout, transport=self._transport)
        return self._http

    async def aclose(self) -> None:
        """Close the underlying HTTP client (reopened lazily if used again)."""
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def __aenter__(self) -> "JiraClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    # ------------------------------------------------------------------
    # Internal request helper
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Make an authenticated request to the Jira REST API.

        Rate-limit (429), transient gateway (502/503/504), and transport
        errors are retried with backoff, honoring Retry-After when sent.
        """
        url = f"{self._site_url}{path}"
        headers = {
            "Authorization": self._auth_header,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        http = self._get_http()
        for attempt in range(_MAX_ATTEMPTS):
            last_attempt = attempt == _MAX_ATTEMPTS - 1
            try:
                resp = await http.request(method, url, headers=headers, params=params, json=json)
            except httpx.TransportError:
                if last_attempt:
                    raise
                await asyncio.sleep(_BACKOFF_BASE * (2**attempt))
                continue
            if resp.status_code in _RETRYABLE_STATUSES and not last_attempt:
                retry_after = resp.headers.get("Retry-After")
                if retry_after is not None and retry_after.isdigit():
                    delay = float(retry_after)
                else:
                    delay = _BACKOFF_BASE * (2**attempt)
                await asyncio.sleep(delay)
                continue
            break

        if resp.status_code == 204:
            return None
        if not (200 <= resp.status_code < 300):
            try:
                body = resp.json()
                msg = body.get("errorMessages", [])
                if not isinstance(msg, list):
                    msg = [str(msg)]
                errs = body.get("errors", {})
                if errs:
                    msg.extend(f"{k}: {v}" for k, v in errs.items())
                if not msg:
                    msg = [resp.text]
                message = "; ".join(msg)
            except Exception:
                message = resp.text
            raise JiraApiError(
                status_code=resp.status_code,
                message=message,
                endpoint=path,
            )
        # Some endpoints (e.g. POST /issueLink) return 201 with no body
        if not resp.content:
            return None
        return resp.json()

    # ------------------------------------------------------------------
    # Project methods
    # ------------------------------------------------------------------

    async def create_project(
        self,
        name: str,
        key: str,
        project_type_key: str = "software",
        lead_account_id: str = "",
        description: str = "",
        template_key: str = "com.pyxis.greenhopper.jira:gh-simplified-scrum-classic",
    ) -> dict[str, Any]:
        """POST /rest/api/3/project"""
        payload = {
            "name": name,
            "key": key,
            "projectTypeKey": project_type_key,
            "projectTemplateKey": template_key,
            "description": description,
            "assigneeType": "PROJECT_LEAD",
        }
        if lead_account_id:
            payload["leadAccountId"] = lead_account_id
            
        return await self._request(
            "POST",
            "/rest/api/3/project",
            json=payload,
        )

    async def list_projects(
        self,
        max_results: int = 50,
        start_at: int = 0,
    ) -> dict[str, Any]:
        """GET /rest/api/3/project/search"""
        return await self._request(
            "GET",
            "/rest/api/3/project/search",
            params={"maxResults": max_results, "startAt": start_at},
        )

    async def get_project(self, project_key: str) -> dict[str, Any]:
        """GET /rest/api/3/project/{key}"""
        return await self._request("GET", f"/rest/api/3/project/{project_key}")

    async def update_project(self, project_key: str, **fields: Any) -> dict[str, Any]:
        """PUT /rest/api/3/project/{key} — filters out None values."""
        payload = {k: v for k, v in fields.items() if v is not None}
        return await self._request(
            "PUT",
            f"/rest/api/3/project/{project_key}",
            json=payload,
        )

    async def assign_workflow_scheme(self, project_id: str, workflow_scheme_name: str) -> None:
        """Assign an existing workflow scheme to a project."""
        # 1. Look up the scheme ID by name
        schemes_response = await self._request("GET", "/rest/api/3/workflowscheme")
        scheme_id = None
        available_schemes = [s.get("name") for s in schemes_response.get("values", [])]
        for scheme in schemes_response.get("values", []):
            if scheme.get("name", "").lower() == workflow_scheme_name.lower():
                scheme_id = scheme.get("id")
                break
                
        if not scheme_id:
            raise ValueError(f"Workflow scheme '{workflow_scheme_name}' not found. Available schemes from Atlassian: {', '.join(str(s) for s in available_schemes)}")
            
        # 2. Assign the scheme to the project
        payload = {"workflowSchemeId": scheme_id, "projectId": project_id}
        await self._request("PUT", "/rest/api/3/workflowscheme/project", json=payload)

    # ------------------------------------------------------------------
    # Issue methods
    # ------------------------------------------------------------------

    async def create_issue(
        self,
        project_key: str,
        issue_type: str,
        summary: str,
        description: str = "",
        labels: list[str] | None = None,
        parent_key: str = "",
        assignee_id: str = "",
        custom_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST /rest/api/3/issue — description uses ADF format."""
        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "issuetype": {"name": issue_type},
            "summary": summary,
            "description": _to_adf(description),
        }
        if custom_fields:
            fields.update(custom_fields)
        if labels:
            fields["labels"] = labels
        if parent_key:
            fields["parent"] = {"key": parent_key}
        if assignee_id:
            fields["assignee"] = {"accountId": assignee_id}
        return await self._request("POST", "/rest/api/3/issue", json={"fields": fields})

    async def get_issue(
        self,
        issue_key: str,
        fields: str | None = None,
    ) -> dict[str, Any]:
        """GET /rest/api/3/issue/{key}"""
        if fields is None:
            fields = "summary,status,issuetype,priority,labels,assignee,description"
        return await self._request(
            "GET",
            f"/rest/api/3/issue/{issue_key}",
            params={"fields": fields},
        )

    async def update_issue(
        self,
        issue_key: str,
        fields: dict[str, Any] | None = None,
    ) -> Any:
        """PUT /rest/api/3/issue/{key}"""
        return await self._request(
            "PUT",
            f"/rest/api/3/issue/{issue_key}",
            json={"fields": fields or {}},
        )

    async def delete_issue(
        self,
        issue_key: str,
        delete_subtasks: bool = True,
    ) -> Any:
        """DELETE /rest/api/3/issue/{key} — permanently removes the issue.

        Used for test cleanup. Returns None on 204.
        """
        return await self._request(
            "DELETE",
            f"/rest/api/3/issue/{issue_key}",
            params={"deleteSubtasks": "true" if delete_subtasks else "false"},
        )

    async def delete_project(self, project_key: str) -> Any:
        """DELETE /rest/api/3/project/{key} — permanently removes the project.

        Used for test cleanup. Returns None on 204.
        """
        return await self._request(
            "DELETE",
            f"/rest/api/3/project/{project_key}",
        )

    async def search_issues(
        self,
        jql: str,
        fields: str | list[str] | None = None,
        max_results: int = 50,
        start_at: int = 0,
        next_page_token: str | None = None,
    ) -> dict[str, Any]:
        """POST /rest/api/3/search/jql — replaces deprecated GET /rest/api/3/search.

        Pagination uses ``nextPageToken`` (returned in each response) rather
        than the legacy ``startAt`` offset.  The ``start_at`` parameter is
        kept for backward-compatibility but is ignored by this endpoint.
        """
        if fields is None:
            fields_list = ["summary", "status", "issuetype", "priority", "labels", "assignee"]
        elif isinstance(fields, str):
            fields_list = [f.strip() for f in fields.split(",")]
        else:
            fields_list = fields
        body: dict[str, Any] = {
            "jql": jql,
            "fields": fields_list,
            "maxResults": max_results,
        }
        if next_page_token:
            body["nextPageToken"] = next_page_token
        return await self._request(
            "POST",
            "/rest/api/3/search/jql",
            json=body,
        )

    async def assign_issue(self, issue_key: str, account_id: str) -> Any:
        """PUT /rest/api/3/issue/{key}/assignee"""
        return await self._request(
            "PUT",
            f"/rest/api/3/issue/{issue_key}/assignee",
            json={"accountId": account_id},
        )

    # ------------------------------------------------------------------
    # Transition methods
    # ------------------------------------------------------------------

    async def get_transitions(self, issue_key: str) -> dict[str, Any]:
        """GET /rest/api/3/issue/{key}/transitions"""
        return await self._request("GET", f"/rest/api/3/issue/{issue_key}/transitions")

    async def transition_issue(self, issue_key: str, transition_id: str) -> Any:
        """POST /rest/api/3/issue/{key}/transitions"""
        return await self._request(
            "POST",
            f"/rest/api/3/issue/{issue_key}/transitions",
            json={"transition": {"id": transition_id}},
        )

    # ------------------------------------------------------------------
    # Comment methods
    # ------------------------------------------------------------------

    async def add_comment(self, issue_key: str, body: str) -> dict[str, Any]:
        """POST /rest/api/3/issue/{key}/comment — body uses ADF format."""
        return await self._request(
            "POST",
            f"/rest/api/3/issue/{issue_key}/comment",
            json={"body": _to_adf(body)},
        )

    # ------------------------------------------------------------------
    # Link methods
    # ------------------------------------------------------------------

    async def create_issue_link(
        self,
        type_name: str,
        inward_key: str,
        outward_key: str,
    ) -> Any:
        """POST /rest/api/3/issueLink"""
        return await self._request(
            "POST",
            "/rest/api/3/issueLink",
            json={
                "type": {"name": type_name},
                "inwardIssue": {"key": inward_key},
                "outwardIssue": {"key": outward_key},
            },
        )

    async def get_link_types(self) -> dict[str, Any]:
        """GET /rest/api/3/issueLinkType"""
        return await self._request("GET", "/rest/api/3/issueLinkType")

    # ------------------------------------------------------------------
    # User methods
    # ------------------------------------------------------------------

    async def get_myself(self) -> dict[str, Any]:
        """GET /rest/api/3/myself"""
        return await self._request("GET", "/rest/api/3/myself")

    async def find_users(self, query: str) -> list[dict[str, Any]]:
        """GET /rest/api/3/user/search"""
        return await self._request(
            "GET",
            "/rest/api/3/user/search",
            params={"query": query},
        )

    async def get_fields(self) -> list[dict[str, Any]]:
        """GET /rest/api/3/field"""
        return await self._request("GET", "/rest/api/3/field")

    async def get_epic_name_field_id(self) -> str | None:
        """Fetch and cache the custom field ID for 'Epic Name'."""
        if self._epic_name_field_id is not None:
            return self._epic_name_field_id

        fields = await self.get_fields()
        for f in fields:
            if f.get("name", "").lower() == "epic name":
                self._epic_name_field_id = f["id"]
                return self._epic_name_field_id

        return None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_adf(text: str) -> dict[str, Any]:
    """Convert a markdown string to Atlassian Document Format (ADF).

    Delegates to library_server.pm.md_to_adf.md_to_adf so descriptions and
    comment bodies render rich text instead of literal markdown chars.
    """
    return md_to_adf(text)
