"""Jira PM adapter — wraps Atlassian MCP tools."""

from __future__ import annotations

from typing import Any

from library_server.pm.adapter import PMAdapter
from library_server.types import (
    EpicResult,
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
    """Jira implementation using Atlassian MCP tools.

    In Claude Code, MCP tools are called by the LLM agent.
    This adapter structures the calls and parses responses.
    """

    def __init__(self, site_url: str = ""):
        self.site_url = site_url

    async def _call_mcp(self, tool_name: str, params: dict) -> dict:
        """Placeholder for MCP tool invocation.

        In production, this is called by the Claude Code agent via MCP.
        For testing, this method is mocked.
        """
        raise NotImplementedError(
            "MCP calls are made by the Claude Code agent. "
            "This adapter structures requests and parses responses."
        )

    async def create_task(
        self,
        project_key: str,
        summary: str,
        description: str,
        labels: list[str] | None = None,
    ) -> TaskResult:
        result = await self._call_mcp("createJiraIssue", {
            "projectKey": project_key,
            "issueType": "Task",
            "summary": summary,
            "description": description,
            "labels": labels or [],
        })
        return _parse_issue(result, project_key)

    async def create_epic(
        self,
        project_key: str,
        summary: str,
        description: str,
    ) -> EpicResult:
        result = await self._call_mcp("createJiraIssue", {
            "projectKey": project_key,
            "issueType": "Epic",
            "summary": summary,
            "description": description,
        })
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
            await self._call_mcp("addCommentToJiraIssue", {
                "issueIdOrKey": task_id,
                "body": comment,
            })
        if status:
            transitions = await self._call_mcp("getTransitionsForJiraIssue", {
                "issueIdOrKey": task_id,
            })
            for t in transitions.get("transitions", []):
                if t["name"].lower() == status.lower():
                    await self._call_mcp("transitionJiraIssue", {
                        "issueIdOrKey": task_id,
                        "transitionId": t["id"],
                    })
                    break
        issue = await self._call_mcp("getJiraIssue", {"issueIdOrKey": task_id})
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
        result = await self._call_mcp("searchJiraIssuesUsingJql", {"jql": jql})
        return [_parse_issue(issue, project_key) for issue in result.get("issues", [])]

    async def sync_state(self, project_key: str) -> ProjectState:
        all_tasks = await self.query_tasks(project_key)
        return ProjectState(
            project_key=project_key,
            project_name=project_key,
            open_tasks=[t for t in all_tasks if t.status == TaskStatus.OPEN],
            stale_tasks=[],  # Would need date comparison
            blocked_tasks=[t for t in all_tasks if t.status == TaskStatus.BLOCKED],
            recently_closed=[t for t in all_tasks if t.status == TaskStatus.DONE],
        )

    async def get_transitions(self, task_id: str) -> list[Transition]:
        result = await self._call_mcp("getTransitionsForJiraIssue", {
            "issueIdOrKey": task_id,
        })
        return [
            Transition(
                transition_id=t["id"],
                name=t["name"],
                to_status=STATUS_MAP.get(t["to"]["name"].lower(), TaskStatus.OPEN),
            )
            for t in result.get("transitions", [])
        ]


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
