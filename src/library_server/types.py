"""Shared types used across library-server modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class TaskStatus(Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"


class Verdict(Enum):
    VERIFIED = "verified"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass
class TaskResult:
    task_id: str
    project_key: str
    summary: str
    status: TaskStatus
    labels: list[str] = field(default_factory=list)
    url: str = ""


@dataclass
class EpicResult:
    epic_id: str
    project_key: str
    summary: str
    task_count: int = 0
    url: str = ""


@dataclass
class ProjectState:
    project_key: str
    project_name: str
    open_tasks: list[TaskResult] = field(default_factory=list)
    stale_tasks: list[TaskResult] = field(default_factory=list)
    blocked_tasks: list[TaskResult] = field(default_factory=list)
    recently_closed: list[TaskResult] = field(default_factory=list)


@dataclass
class Transition:
    transition_id: str
    name: str
    to_status: TaskStatus


@dataclass
class VaultTag:
    tag_type: str  # VERIFY, CONFLICT, PLANNED
    content: str
    source_file: str
    line_number: int


@dataclass
class MemoryEntry:
    name: str
    description: str
    memory_type: str  # user, feedback, project, reference
    file_path: str
    last_validated: datetime | None = None
    is_stale: bool = False
    conflicts_with: list[str] = field(default_factory=list)


@dataclass
class CheckpointData:
    topic: str
    date: str
    status: str
    next_session: str
    accomplished: list[str] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    open_decisions: list[dict] = field(default_factory=list)
    key_context: list[str] = field(default_factory=list)
    memory_updates: list[dict] = field(default_factory=list)
