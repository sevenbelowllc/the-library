"""Linear PM adapter — wraps Linear GraphQL API via httpx."""

from __future__ import annotations

from typing import Any

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

from library_server.pm.adapter import PMAdapter
from library_server.types import (
    EpicResult,
    ProjectResult,
    ProjectState,
    TaskResult,
    TaskStatus,
    Transition,
)

LINEAR_API = "https://api.linear.app/graphql"

STATUS_MAP = {
    "todo": TaskStatus.OPEN,
    "backlog": TaskStatus.OPEN,
    "in progress": TaskStatus.IN_PROGRESS,
    "done": TaskStatus.DONE,
    "canceled": TaskStatus.DONE,
}


class LinearAdapter(PMAdapter):
    """Linear implementation using GraphQL API."""

    def __init__(self, api_key: str = ""):
        if httpx is None:
            raise ImportError("httpx is required for Linear adapter: pip install the-library[linear]")
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=LINEAR_API,
            headers={
                "Authorization": api_key,
                "Content-Type": "application/json",
            },
        )

    async def _graphql(self, query: str, variables: dict | None = None) -> dict:
        """Execute a GraphQL query against Linear API."""
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        response = await self._client.post("", json=payload)
        response.raise_for_status()
        return response.json()

    async def create_task(
        self,
        project_key: str,
        summary: str,
        description: str,
        labels: list[str] | None = None,
        epic_id: str = "",
    ) -> TaskResult:
        input_payload: dict = {"title": summary, "description": description, "teamId": project_key}
        if epic_id:
            input_payload["parentId"] = epic_id
        result = await self._graphql(
            """
            mutation($input: IssueCreateInput!) {
                issueCreate(input: $input) {
                    issue {
                        id
                        identifier
                        title
                        state { name }
                        url
                    }
                }
            }
            """,
            {"input": input_payload},
        )
        issue = result["data"]["issueCreate"]["issue"]
        return TaskResult(
            task_id=issue["identifier"],
            project_key=project_key,
            summary=issue["title"],
            status=STATUS_MAP.get(issue["state"]["name"].lower(), TaskStatus.OPEN),
            labels=labels or [],
            url=issue.get("url", ""),
        )

    async def create_epic(
        self,
        project_key: str,
        summary: str,
        description: str,
    ) -> EpicResult:
        result = await self._graphql(
            """
            mutation($input: ProjectCreateInput!) {
                projectCreate(input: $input) {
                    project {
                        id
                        name
                        url
                    }
                }
            }
            """,
            {"input": {"name": summary, "description": description, "teamIds": [project_key]}},
        )
        project = result["data"]["projectCreate"]["project"]
        return EpicResult(
            epic_id=project["id"],
            project_key=project_key,
            summary=summary,
            url=project.get("url", ""),
        )

    async def update_task(
        self,
        task_id: str,
        status: str | None = None,
        comment: str | None = None,
    ) -> TaskResult:
        if comment:
            await self._graphql(
                """
                mutation($input: CommentCreateInput!) {
                    commentCreate(input: $input) { comment { id } }
                }
                """,
                {"input": {"issueId": task_id, "body": comment}},
            )
        # Fetch current state
        result = await self._graphql(
            """
            query($id: String!) {
                issue(id: $id) {
                    id identifier title state { name } url
                }
            }
            """,
            {"id": task_id},
        )
        issue = result["data"]["issue"]
        return TaskResult(
            task_id=issue["identifier"],
            project_key="",
            summary=issue["title"],
            status=STATUS_MAP.get(issue["state"]["name"].lower(), TaskStatus.OPEN),
            url=issue.get("url", ""),
        )

    async def query_tasks(
        self,
        project_key: str,
        filters: dict | None = None,
    ) -> list[TaskResult]:
        result = await self._graphql(
            """
            query($teamId: String!) {
                team(id: $teamId) {
                    issues { nodes { id identifier title state { name } url labels { nodes { name } } } }
                }
            }
            """,
            {"teamId": project_key},
        )
        issues = result["data"]["team"]["issues"]["nodes"]
        return [
            TaskResult(
                task_id=i["identifier"],
                project_key=project_key,
                summary=i["title"],
                status=STATUS_MAP.get(i["state"]["name"].lower(), TaskStatus.OPEN),
                labels=[l["name"] for l in i.get("labels", {}).get("nodes", [])],
                url=i.get("url", ""),
            )
            for i in issues
        ]

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
        result = await self._graphql(
            """
            query {
                workflowStates { nodes { id name } }
            }
            """,
        )
        return [
            Transition(
                transition_id=s["id"],
                name=s["name"],
                to_status=STATUS_MAP.get(s["name"].lower(), TaskStatus.OPEN),
            )
            for s in result["data"]["workflowStates"]["nodes"]
        ]

    async def create_project(
        self,
        name: str,
        key: str,
        description: str = "",
        lead_account_id: str = "",
        workflow_scheme: str = "",
    ) -> ProjectResult:
        raise NotImplementedError("Not supported by Linear adapter")

    async def list_projects(self) -> list[ProjectResult]:
        raise NotImplementedError("Not supported by Linear adapter")

    async def get_project(self, project_key: str) -> ProjectResult:
        raise NotImplementedError("Not supported by Linear adapter")

    async def update_project(
        self,
        project_key: str,
        name: str = "",
        description: str = "",
    ) -> ProjectResult:
        raise NotImplementedError("Not supported by Linear adapter")

    async def assign_task(self, task_id: str, account_id: str) -> TaskResult:
        raise NotImplementedError("Not supported by Linear adapter")

    async def link_issues(
        self,
        type_name: str,
        inward_key: str,
        outward_key: str,
    ) -> None:
        raise NotImplementedError("Not supported by Linear adapter")

    async def get_link_types(self) -> list[dict]:
        raise NotImplementedError("Not supported by Linear adapter")
