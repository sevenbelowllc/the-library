"""Data types for the Vault Builder Toolkit."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class VaultState(Enum):
    """Detected state of the target vault directory."""
    NEW_VAULT = "new_vault"
    EXISTING_VAULT_NO_RAW = "existing_vault_no_raw"
    EXISTING_VAULT_WITH_RAW = "existing_vault_with_raw"
    PREVIOUS_BUILD = "previous_build"
    NON_VAULT_DIRECTORY = "non_vault_directory"


@dataclass
class SurveyResult:
    """What's in the source? File counts, structure, staleness."""
    source_name: str
    file_count: int
    total_size_bytes: int
    structure_summary: str = ""
    health: str = "unknown"
    last_modified: datetime | None = None


@dataclass
class PreviewResult:
    """What would be extracted? Dry run — no writes."""
    source_name: str
    files_to_create: list[str] = field(default_factory=list)
    estimated_tokens: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class ExtractResult:
    """Result from running an extractor."""
    source_name: str
    files_written: list[str] = field(default_factory=list)
    files_skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    success: bool = False


@dataclass
class BuildResult:
    """Result from a full vault build."""
    status: str
    extract_results: list[ExtractResult] = field(default_factory=list)
    graphify_status: str = "skipped"
    graphify_message: str = ""
    duration_seconds: float = 0.0
    manifest_path: str = ""
    config_warnings: dict[str, list[str]] = field(default_factory=dict)

    @property
    def any_succeeded(self) -> bool:
        return any(r.success for r in self.extract_results)
