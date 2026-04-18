"""Abstract PM adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from library_server.types import (
    EpicResult,
    IssueDetail,
    ProjectResult,
    ProjectState,
    TaskResult,
    Transition,
)


class TransitionNotAvailableError(Exception):
    """Raised when a requested status transition is not reachable from the current state.

    Surfaced when update_task is called with a ``status`` that does not match any
    available transition for the issue. Previously these were silent no-ops — a
    bug that caused the 2026-04-17 audit failure where ``status="Done"`` was
    accepted but ignored.

    Attributes:
        task_id: The issue key that could not be transitioned.
        requested_status: The status name the caller asked for.
        current_status: The issue's current status name (may be empty if unknown).
        available_transitions: Human-readable names of transitions that ARE available
            (format: ``"<transition.name> -> <to.name>"``).
    """

    def __init__(
        self,
        task_id: str,
        requested_status: str,
        current_status: str,
        available_transitions: list[str],
    ) -> None:
        self.task_id = task_id
        self.requested_status = requested_status
        self.current_status = current_status
        self.available_transitions = available_transitions
        avail = ", ".join(available_transitions) if available_transitions else "(none)"
        super().__init__(
            f"Cannot transition {task_id} from '{current_status}' to "
            f"'{requested_status}'. Available transitions: {avail}"
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
        epic_id: str = "",
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

    @abstractmethod
    async def create_project(
        self,
        name: str,
        key: str,
        description: str = "",
        lead_account_id: str = "",
        workflow_scheme: str = "",
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

    @abstractmethod
    async def get_issue(self, task_id: str) -> IssueDetail:
        """Return full detail for an issue — fields, comments, available transitions."""
        ...
