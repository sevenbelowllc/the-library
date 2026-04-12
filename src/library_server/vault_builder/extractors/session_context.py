"""Session Context extractor — session context migration files."""

from __future__ import annotations

import re
import time
from pathlib import Path

from library_server.vault_builder.extractors.base import BaseExtractor
from library_server.vault_builder.output import OutputWriter
from library_server.vault_builder.types import SurveyResult, PreviewResult, ExtractResult

_DECISION_RE = re.compile(r"(?:^|\n)##\s*Decision:\s*(.+)", re.IGNORECASE)


class SessionContextExtractor(BaseExtractor):
    name = "session_context"
    display_name = "Session Context"
    source_description = "Session context files from Claude Chat migration"
    output_subdir = "sessions"

    def validate_config(self) -> list[str]:
        errors: list[str] = []
        source_path = self.config.get("source_path")
        if not source_path:
            errors.append("Missing required config: source_path")
        elif not Path(source_path).exists():
            errors.append(f"source_path does not exist: {source_path}")
        return errors

    async def survey(self) -> SurveyResult:
        source = Path(self.config["source_path"])
        if not source.exists():
            return SurveyResult(source_name=self.name, file_count=0, total_size_bytes=0, health="missing")
        files = list(source.glob("*.md"))
        total_size = sum(f.stat().st_size for f in files)
        return SurveyResult(
            source_name=self.name, file_count=len(files), total_size_bytes=total_size,
            structure_summary=f"{len(files)} session context files",
            health="connected" if files else "empty",
        )

    async def preview(self) -> PreviewResult:
        source = Path(self.config["source_path"])
        files = list(source.glob("*.md")) if source.exists() else []
        return PreviewResult(
            source_name=self.name,
            files_to_create=[f"sessions/{f.name}" for f in files],
            estimated_tokens=sum(f.stat().st_size // 4 for f in files),
        )

    async def extract(self, output_dir: Path) -> ExtractResult:
        source = Path(self.config["source_path"])
        writer = OutputWriter(base_dir=output_dir.parent)
        files_written: list[str] = []
        errors: list[str] = []
        start = time.monotonic()

        for session_file in sorted(source.glob("*.md")):
            try:
                content = session_file.read_text()
                decisions = _DECISION_RE.findall(content)
                tags = ["source/session", "trust/medium"]
                if decisions:
                    tags.append("architecture-decision")

                writer.write_file(
                    subdir=output_dir.name, filename=session_file.name,
                    title=session_file.stem, source_type="session_context",
                    source_path=f"session-context/{session_file.name}",
                    extractor=self.name, trust=0.6, domain="architecture",
                    tags=tags, related=[], body=content,
                )
                files_written.append(session_file.name)
            except Exception as e:
                errors.append(f"Error extracting {session_file.name}: {e}")

        duration = time.monotonic() - start
        return ExtractResult(
            source_name=self.name, files_written=files_written, files_skipped=[],
            errors=errors, duration_seconds=duration,
            success=len(files_written) > 0 and len(errors) == 0,
        )
