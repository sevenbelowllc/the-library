"""Specs extractor — Reading Room canonical spec files."""

from __future__ import annotations

import re
import time
from pathlib import Path

from library_server.vault_builder.extractors.base import BaseExtractor
from library_server.vault_builder.output import OutputWriter
from library_server.vault_builder.types import SurveyResult, PreviewResult, ExtractResult

_SPEC_DOMAIN_MAP: dict[str, str] = {
    "GLOSSARY": "glossary", "DOMAINS": "domains", "INVARIANTS": "invariants",
    "DECISIONS": "decisions", "LIFECYCLES": "lifecycles", "SCOPE": "scope",
    "DEPENDENCIES": "dependencies", "FRAMEWORKS": "compliance", "TENANCY": "tenancy",
    "AUDIT-RULES": "audit", "AI-AGENTS": "ai-agents", "INDEX": "index",
}

_WIKI_LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


class SpecsExtractor(BaseExtractor):
    name = "specs"
    display_name = "Reading Room Specs"
    source_description = "Canonical spec files from the Library Reading Room"
    output_subdir = "specs"

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
        last_mod = max((f.stat().st_mtime for f in files), default=0)
        from datetime import datetime, timezone
        last_modified = datetime.fromtimestamp(last_mod, tz=timezone.utc) if last_mod else None
        return SurveyResult(
            source_name=self.name, file_count=len(files), total_size_bytes=total_size,
            structure_summary=f"{len(files)} canonical spec files", health="connected",
            last_modified=last_modified,
        )

    async def preview(self) -> PreviewResult:
        source = Path(self.config["source_path"])
        files = list(source.glob("*.md")) if source.exists() else []
        return PreviewResult(
            source_name=self.name,
            files_to_create=[f"specs/{f.name}" for f in files],
            estimated_tokens=sum(f.stat().st_size // 4 for f in files),
        )

    async def extract(self, output_dir: Path) -> ExtractResult:
        source = Path(self.config["source_path"])
        writer = OutputWriter(base_dir=output_dir.parent)
        files_written: list[str] = []
        errors: list[str] = []
        start = time.monotonic()

        for spec_file in sorted(source.glob("*.md")):
            try:
                content = spec_file.read_text()
                stem = spec_file.stem
                domain = _SPEC_DOMAIN_MAP.get(stem, "general")

                related = []
                for match in _WIKI_LINK_RE.finditer(content):
                    target = match.group(1).split("#")[0]
                    if target != stem:
                        link = f"[[{match.group(1)}]]"
                        if link not in related:
                            related.append(link)

                tags = ["source/spec", f"domain/{domain}", "trust/high", "canonical"]

                writer.write_file(
                    subdir=output_dir.name, filename=spec_file.name, title=stem,
                    source_type="spec", source_path=f"library-reading-room/specs/{spec_file.name}",
                    extractor=self.name, trust=1.0, domain=domain, tags=tags,
                    related=related, body=content,
                )
                files_written.append(spec_file.name)
            except Exception as e:
                errors.append(f"Error extracting {spec_file.name}: {e}")

        duration = time.monotonic() - start
        return ExtractResult(
            source_name=self.name, files_written=files_written, files_skipped=[],
            errors=errors, duration_seconds=duration,
            success=len(files_written) > 0 and len(errors) == 0,
        )
