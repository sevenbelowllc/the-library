"""Jira PM adapter — wraps JiraClient for direct REST API calls."""

from __future__ import annotations

import logging

from library_server.pm.adapter import PMAdapter, TransitionNotAvailableError

logger = logging.getLogger(__name__)
from library_server.pm.jira_client import JiraClient
from library_server.types import (
    EpicResult,
    IssueComment,
    IssueDetail,
    IssueTransitionOption,
    ProjectResult,
    ProjectState,
    TaskResult,
    Transition,
)

# Sensible defaults when the caller hasn't configured pm.workflow.closed /
# pm.workflow.blocked. Match case-insensitively so "Done" / "done" / "DONE"
# all classify the same way. These are only used for sync_state bucketing —
# raw status strings from Jira are preserved verbatim on TaskResult.status.
DEFAULT_CLOSED_STATUSES: tuple[str, ...] = ("done", "closed", "resolved", "completed")
DEFAULT_BLOCKED_STATUSES: tuple[str, ...] = ("blocked",)


class JiraAdapter(PMAdapter):
    """Jira implementation using JiraClient direct REST API calls."""

    def __init__(
        self,
        site_url: str = "",
        closed_statuses: tuple[str, ...] | None = None,
        blocked_statuses: tuple[str, ...] | None = None,
    ):
        self.site_url = site_url
        self.client = JiraClient(site_url=site_url)
        self._closed = tuple(s.lower() for s in (closed_statuses or DEFAULT_CLOSED_STATUSES))
        self._blocked = tuple(s.lower() for s in (blocked_statuses or DEFAULT_BLOCKED_STATUSES))

    def _is_closed(self, status: str) -> bool:
        return status.lower() in self._closed

    def _is_blocked(self, status: str) -> bool:
        return status.lower() in self._blocked

    async def create_task(
        self,
        project_key: str,
        summary: str,
        description: str,
        labels: list[str] | None = None,
        epic_id: str = "",
    ) -> TaskResult:
        result = await self.client.create_issue(
            project_key=project_key,
            issue_type="Task",
            summary=summary,
            description=description,
            labels=labels,
            parent_key=epic_id,
        )
        task_id = result.get("key", "")
        # Jira's create response doesn't include status. Fetch it so the caller
        # sees the real initial state (usually "To Do", but workflow schemes
        # can override). Cheap — single REST call — and avoids returning
        # stale/guessed values.
        status = ""
        if task_id:
            try:
                issue = await self.client.get_issue(task_id, fields="status")
                status = issue.get("fields", {}).get("status", {}).get("name", "")
            except Exception as e:
                # The task was created; only the status fetch failed. Log so the
                # caller can see why the returned status is blank, but don't
                # raise — losing reference to the newly-created task_id would
                # be worse than a missing status field.
                logger.warning(
                    "created task %s but status fetch failed: %s", task_id, e
                )
        return TaskResult(
            task_id=task_id,
            project_key=project_key,
            summary=summary,
            status=status,
            labels=labels or [],
            url=result.get("self", ""),
        )

    async def create_epic(
        self,
        project_key: str,
        summary: str,
        description: str,
    ) -> EpicResult:
        epic_name_field_id = await self.client.get_epic_name_field_id()
        custom_fields = {}
        if epic_name_field_id:
            custom_fields[epic_name_field_id] = summary

        result = await self.client.create_issue(
            project_key=project_key,
            issue_type="Epic",
            summary=summary,
            description=description,
            custom_fields=custom_fields,
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
            trans_data = await self.client.get_transitions(task_id)
            transitions = trans_data.get("transitions", [])
            wanted = status.lower()
            chosen_id: str | None = None
            for t in transitions:
                # Match either the transition name (semantic workflows) OR the
                # target status name (numeric/"Any"-named workflows). Jira
                # Cloud's default software workflow uses the latter, which is
                # why the old name-only match silently no-op'd.
                to_name = t.get("to", {}).get("name", "")
                if t.get("name", "").lower() == wanted or to_name.lower() == wanted:
                    chosen_id = t["id"]
                    break
            if chosen_id is None:
                current_status = ""
                try:
                    current = await self.client.get_issue(task_id)
                    current_status = (
                        current.get("fields", {}).get("status", {}).get("name", "")
                    )
                except Exception:
                    pass
                available = [
                    f"{t.get('name', '?')} -> {t.get('to', {}).get('name', '?')}"
                    for t in transitions
                ]
                raise TransitionNotAvailableError(
                    task_id=task_id,
                    requested_status=status,
                    current_status=current_status,
                    available_transitions=available,
                )
            await self.client.transition_issue(task_id, chosen_id)
        issue = await self.client.get_issue(task_id)
        project_key = task_id.split("-")[0]
        return _parse_issue(issue, project_key)

    async def get_issue(self, task_id: str) -> IssueDetail:
        """Fetch an issue with expanded fields plus available transitions.

        Returns an ``IssueDetail`` with description, labels, parent epic,
        assignee, most-recent 20 comments, and the transitions reachable from
        the current state. Clients (MCP tool ``library_pm_get_issue``) use
        ``available_transitions[].to_status`` to decide the next legal move.
        """
        fields = (
            "summary,status,labels,assignee,description,parent,comment,issuetype"
        )
        issue = await self.client.get_issue(task_id, fields=fields)
        trans = await self.client.get_transitions(task_id)
        return _parse_issue_detail(issue, trans)

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
            open_tasks=[t for t in all_tasks if not self._is_closed(t.status) and not self._is_blocked(t.status)],
            stale_tasks=[],
            blocked_tasks=[t for t in all_tasks if self._is_blocked(t.status)],
            recently_closed=[t for t in all_tasks if self._is_closed(t.status)],
        )

    async def get_transitions(self, task_id: str) -> list[Transition]:
        result = await self.client.get_transitions(task_id)
        return [
            Transition(
                transition_id=t["id"],
                name=t["name"],
                to_status=t.get("to", {}).get("name", ""),
            )
            for t in result.get("transitions", [])
        ]

    async def create_project(
        self,
        name: str,
        key: str,
        description: str = "",
        lead_account_id: str = "",
        workflow_scheme: str = "",
    ) -> ProjectResult:
        if not lead_account_id:
            me = await self.client.get_myself()
            lead_account_id = me["accountId"]
        result = await self.client.create_project(
            name=name,
            key=key,
            description=description,
            lead_account_id=lead_account_id,
        )
        
        project_id = str(result.get("id", ""))
        
        if workflow_scheme and project_id:
            await self.client.assign_workflow_scheme(project_id, workflow_scheme)

        return ProjectResult(
            project_id=str(result.get("id", "")),
            project_key=result.get("key", key),
            name=name,
            description=description,
            lead=lead_account_id,
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
                lead=p.get("lead", {}).get("accountId", "") if p.get("lead") else "",
                url=p.get("self", ""),
            )
            for p in result.get("values", [])
        ]

    async def get_project(self, project_key: str) -> ProjectResult:
        p = await self.client.get_project(project_key)
        return ProjectResult(
            project_id=str(p.get("id", "")),
            project_key=p.get("key", project_key),
            name=p.get("name", ""),
            description=p.get("description", ""),
            lead=p.get("lead", {}).get("accountId", "") if p.get("lead") else "",
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
    """Parse a Jira issue response into TaskResult.

    Returns the raw Jira ``status.name`` verbatim (e.g. "To Do", "In Review",
    "Done"). Callers that need bucketing should use ``JiraAdapter.sync_state``
    or consult ``library-config.yaml#pm.workflow``.
    """
    fields = data.get("fields", {})
    return TaskResult(
        task_id=data.get("key", ""),
        project_key=project_key,
        summary=fields.get("summary", ""),
        status=fields.get("status", {}).get("name", ""),
        labels=fields.get("labels", []),
        url=data.get("self", ""),
    )


def _adf_to_text(node: dict | str | None) -> str:
    """Flatten Atlassian Document Format to plain text. Tolerates str input."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return node.get("text", "")
    parts: list[str] = []
    for child in node.get("content", []) or []:
        parts.append(_adf_to_text(child))
    text = "".join(parts)
    if node.get("type") in ("paragraph", "heading"):
        return text + "\n"
    return text


def _parse_issue_detail(data: dict, transitions_data: dict) -> IssueDetail:
    """Parse a Jira issue + transitions response into IssueDetail.

    Takes the most-recent 20 comments, renders description from ADF to plain
    text, and lists each available transition's target status so clients can
    pick a legal next move without re-querying.
    """
    fields = data.get("fields", {})
    assignee_obj = fields.get("assignee")
    assignee = (
        assignee_obj.get("displayName") or assignee_obj.get("accountId")
        if isinstance(assignee_obj, dict)
        else None
    )
    parent_obj = fields.get("parent")
    parent = parent_obj.get("key") if isinstance(parent_obj, dict) else None

    raw_comments = (fields.get("comment") or {}).get("comments", []) or []
    recent = raw_comments[-20:]
    comments = [
        IssueComment(
            author=(c.get("author") or {}).get("displayName", ""),
            created=c.get("created", ""),
            body=_adf_to_text(c.get("body")).rstrip("\n"),
        )
        for c in recent
    ]

    available = [
        IssueTransitionOption(
            name=t.get("name", ""),
            to_status=t.get("to", {}).get("name", ""),
        )
        for t in transitions_data.get("transitions", [])
    ]

    return IssueDetail(
        id=data.get("key", ""),
        summary=fields.get("summary", ""),
        description=_adf_to_text(fields.get("description")).rstrip("\n"),
        status=fields.get("status", {}).get("name", ""),
        labels=fields.get("labels", []) or [],
        parent=parent,
        assignee=assignee,
        comments=comments,
        available_transitions=available,
        url=data.get("self", ""),
    )
