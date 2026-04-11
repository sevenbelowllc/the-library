"""Abstract PM adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from library_server.types import (
    EpicResult,
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
