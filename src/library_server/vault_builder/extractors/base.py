"""BaseExtractor ABC — contract for all vault builder extractors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from library_server.vault_builder.types import SurveyResult, PreviewResult, ExtractResult


class BaseExtractor(ABC):
    """Abstract base for all vault builder extractors."""

    name: str
    display_name: str
    source_description: str
    output_subdir: str

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    @property
    def is_enabled(self) -> bool:
        return self.config.get("enabled", True)

    @abstractmethod
    async def survey(self) -> SurveyResult:
        """What's in the source? File counts, structure, staleness."""

    @abstractmethod
    async def preview(self) -> PreviewResult:
        """What would be extracted? Dry run — no writes."""

    @abstractmethod
    async def extract(self, output_dir: Path) -> ExtractResult:
        """Extract and write structured MD to output_dir."""

    @abstractmethod
    def validate_config(self) -> list[str]:
        """Return list of config errors, empty if valid."""
