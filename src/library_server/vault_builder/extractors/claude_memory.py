"""Claude Memory extractor — Claude Code auto-memory files."""

from __future__ import annotations

import time
from pathlib import Path

import yaml

from library_server.vault_builder.extractors.base import BaseExtractor
from library_server.vault_builder.output import OutputWriter
from library_server.vault_builder.types import SurveyResult, PreviewResult, ExtractResult

_TYPE_DOMAIN_MAP: dict[str, str] = {
    "user": "user", "feedback": "feedback", "project": "project", "reference": "reference",
}


class ClaudeMemoryExtractor(BaseExtractor):
    name = "claude_memory"
    display_name = "Claude Code Memory"
    source_description = "Claude Code auto-memory files"
    output_subdir = "memory"

    def validate_config(self) -> list[str]:
        errors: list[str] = []
        paths = self.config.get("memory_paths")
        if not paths:
            errors.append("Missing required config: memory_paths")
            return errors
        for p in paths:
            expanded = Path(p).expanduser()
            if not expanded.exists():
                errors.append(f"Memory path does not exist: {p}")
        return errors

    def _get_memory_files(self) -> list[Path]:
        files: list[Path] = []
        for p in self.config.get("memory_paths", []):
            mem_dir = Path(p).expanduser()
            if mem_dir.exists():
                for f in mem_dir.glob("*.md"):
                    if f.name != "MEMORY.md":
                        files.append(f)
        return sorted(files)

    async def survey(self) -> SurveyResult:
        files = self._get_memory_files()
        total_size = sum(f.stat().st_size for f in files)
        return SurveyResult(
            source_name=self.name, file_count=len(files), total_size_bytes=total_size,
            structure_summary=f"{len(files)} memory files",
            health="connected" if files else "empty",
        )

    async def preview(self) -> PreviewResult:
        files = self._get_memory_files()
        return PreviewResult(
            source_name=self.name,
            files_to_create=[f"memory/{f.name}" for f in files],
            estimated_tokens=sum(f.stat().st_size // 4 for f in files),
        )

    async def extract(self, output_dir: Path) -> ExtractResult:
        writer = OutputWriter(base_dir=output_dir.parent)
        files_written: list[str] = []
        errors: list[str] = []
        start = time.monotonic()

        for mem_file in self._get_memory_files():
            try:
                content = mem_file.read_text()
                frontmatter, body = self._parse_memory_file(content)
                mem_type = frontmatter.get("type", "unknown")
                domain = _TYPE_DOMAIN_MAP.get(mem_type, "general")

                tags = ["source/memory", f"domain/{domain}", "trust/medium"]

                writer.write_file(
                    subdir=output_dir.name, filename=mem_file.name,
                    title=frontmatter.get("name", mem_file.stem),
                    source_type="claude_memory", source_path=str(mem_file),
                    extractor=self.name, trust=0.7, domain=domain,
                    tags=tags, related=[], body=body,
                )
                files_written.append(mem_file.name)
            except Exception as e:
                errors.append(f"Error extracting {mem_file.name}: {e}")

        duration = time.monotonic() - start
        return ExtractResult(
            source_name=self.name, files_written=files_written, files_skipped=[],
            errors=errors, duration_seconds=duration,
            success=len(files_written) > 0 and len(errors) == 0,
        )

    @staticmethod
    def _parse_memory_file(content: str) -> tuple[dict, str]:
        if content.startswith("---\n"):
            parts = content.split("---\n", 2)
            if len(parts) >= 3:
                fm = yaml.safe_load(parts[1]) or {}
                return fm, parts[2].strip()
        return {}, content.strip()
