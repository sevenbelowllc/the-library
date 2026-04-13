"""Obsidian Vault extractor — existing vault content with stale detection."""

from __future__ import annotations

import re
import time
from pathlib import Path

import yaml

from library_server.vault_builder.extractors.base import BaseExtractor
from library_server.vault_builder.output import OutputWriter
from library_server.vault_builder.types import SurveyResult, PreviewResult, ExtractResult

_WIKI_LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")

_TRUST_MAP: dict[str, float] = {"wiki": 0.5, "raw": 0.3}
_PRD_TRUST = 0.2
_STALE_PENALTY = 0.1


class ObsidianVaultExtractor(BaseExtractor):
    name = "obsidian_vault"
    display_name = "Existing Obsidian Vault"
    source_description = "Existing Obsidian vault (compliance-os-kb, READ ONLY)"
    output_subdir = "vault"

    def validate_config(self) -> list[str]:
        errors: list[str] = []
        source_path = self.config.get("source_path")
        if not source_path:
            errors.append("Missing required config: source_path")
        elif not Path(source_path).exists():
            errors.append(f"source_path does not exist: {source_path}")
        return errors

    def _is_excluded(self, file_path: Path, source_root: Path) -> bool:
        rel = file_path.relative_to(source_root)
        exclude_dirs = self.config.get("exclude_dirs", [])
        for excl in exclude_dirs:
            if str(rel).startswith(excl):
                return True
        return False

    def _get_included_files(self) -> list[Path]:
        source = Path(self.config["source_path"])
        extensions = self.config.get("include_extensions", [".md"])
        files: list[Path] = []
        for ext in extensions:
            for f in source.rglob(f"*{ext}"):
                if not self._is_excluded(f, source):
                    files.append(f)
        return sorted(files)

    def _compute_trust(self, file_path: Path, source_root: Path, is_stale: bool) -> float:
        rel = str(file_path.relative_to(source_root))
        if "prd" in rel.lower():
            trust = _PRD_TRUST
        elif rel.startswith("wiki"):
            trust = _TRUST_MAP["wiki"]
        else:
            trust = _TRUST_MAP.get("raw", 0.3)
        if is_stale:
            trust = max(0.1, trust - _STALE_PENALTY)
        return round(trust, 1)

    def _detect_stale(self, content: str) -> bool:
        markers = self.config.get("stale_markers", [])
        for marker in markers:
            if marker in content:
                return True
        return False

    async def survey(self) -> SurveyResult:
        source = Path(self.config["source_path"])
        if not source.exists():
            return SurveyResult(source_name=self.name, file_count=0, total_size_bytes=0, health="missing")
        files = self._get_included_files()
        total_size = sum(f.stat().st_size for f in files)
        return SurveyResult(
            source_name=self.name, file_count=len(files), total_size_bytes=total_size,
            structure_summary=f"{len(files)} files from existing vault",
            health="connected" if files else "empty",
        )

    async def preview(self) -> PreviewResult:
        source = Path(self.config["source_path"])
        files = self._get_included_files()
        return PreviewResult(
            source_name=self.name,
            files_to_create=[f"vault/{f.relative_to(source)}" for f in files],
            estimated_tokens=sum(f.stat().st_size // 4 for f in files),
        )

    async def extract(self, output_dir: Path) -> ExtractResult:
        source = Path(self.config["source_path"])
        writer = OutputWriter(base_dir=output_dir.parent)
        files_written: list[str] = []
        errors: list[str] = []
        start = time.monotonic()

        for vault_file in self._get_included_files():
            try:
                content = vault_file.read_text()
                rel_path = vault_file.relative_to(source)
                is_stale = self._detect_stale(content)
                trust = self._compute_trust(vault_file, source, is_stale)

                related = []
                for match in _WIKI_LINK_RE.finditer(content):
                    link = f"[[{match.group(1)}]]"
                    if link not in related:
                        related.append(link)

                trust_tag = "trust/high" if trust >= 0.8 else "trust/medium" if trust >= 0.5 else "trust/low"
                tags = ["source/vault", trust_tag]
                if is_stale:
                    tags.append("stale-reference")

                out_subdir = str(rel_path.parent)
                if out_subdir == ".":
                    out_subdir = ""
                full_subdir = f"{output_dir.name}/{out_subdir}".rstrip("/")

                writer.write_file(
                    subdir=full_subdir, filename=vault_file.name,
                    title=vault_file.stem, source_type="vault_archive",
                    source_path=str(rel_path), extractor=self.name,
                    trust=trust, domain="archive", tags=tags,
                    related=related, body=content,
                )
                files_written.append(str(rel_path))
            except Exception as e:
                errors.append(f"Error extracting {vault_file}: {e}")

        duration = time.monotonic() - start
        return ExtractResult(
            source_name=self.name, files_written=files_written, files_skipped=[],
            errors=errors, duration_seconds=duration,
            success=len(files_written) > 0 and len(errors) == 0,
        )
