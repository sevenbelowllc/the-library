"""NotebookLM extractor — NotebookLM exports and summaries."""

from __future__ import annotations

import time
from pathlib import Path

from library_server.vault_builder.extractors.base import BaseExtractor
from library_server.vault_builder.output import OutputWriter
from library_server.vault_builder.types import SurveyResult, PreviewResult, ExtractResult


class NotebookLMExtractor(BaseExtractor):
    name = "notebooklm"
    display_name = "NotebookLM Exports"
    source_description = "NotebookLM exports and AI-generated summaries"
    output_subdir = "notebooklm"

    def validate_config(self) -> list[str]:
        errors: list[str] = []
        if not self.config.get("source_path"):
            errors.append("Missing required config: source_path")
        elif not Path(self.config["source_path"]).exists():
            errors.append(f"source_path does not exist: {self.config['source_path']}")
        return errors

    def _get_files(self) -> list[Path]:
        files: list[Path] = []
        source = Path(self.config["source_path"])
        if source.exists():
            files.extend(source.glob("*.md"))
        summaries = self.config.get("summaries_path")
        if summaries and Path(summaries).exists():
            files.extend(Path(summaries).glob("*.md"))
        return sorted(files)

    async def survey(self) -> SurveyResult:
        files = self._get_files()
        total_size = sum(f.stat().st_size for f in files)
        return SurveyResult(
            source_name=self.name, file_count=len(files), total_size_bytes=total_size,
            structure_summary=f"{len(files)} NotebookLM files",
            health="connected" if files else "empty",
        )

    async def preview(self) -> PreviewResult:
        files = self._get_files()
        return PreviewResult(
            source_name=self.name,
            files_to_create=[f"notebooklm/{f.name}" for f in files],
            estimated_tokens=sum(f.stat().st_size // 4 for f in files),
        )

    async def extract(self, output_dir: Path) -> ExtractResult:
        writer = OutputWriter(base_dir=output_dir.parent)
        files_written: list[str] = []
        errors: list[str] = []
        start = time.monotonic()

        for nlm_file in self._get_files():
            try:
                content = nlm_file.read_text()
                writer.write_file(
                    subdir=output_dir.name, filename=nlm_file.name,
                    title=nlm_file.stem, source_type="notebooklm",
                    source_path=str(nlm_file), extractor=self.name,
                    trust=0.4, domain="general",
                    tags=["source/notebooklm", "trust/low"],
                    related=[], body=content,
                )
                files_written.append(nlm_file.name)
            except Exception as e:
                errors.append(f"Error extracting {nlm_file.name}: {e}")

        duration = time.monotonic() - start
        return ExtractResult(
            source_name=self.name, files_written=files_written, files_skipped=[],
            errors=errors, duration_seconds=duration,
            success=len(files_written) > 0 and len(errors) == 0,
        )
