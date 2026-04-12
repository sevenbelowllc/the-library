"""OutputWriter — writes MD files with YAML frontmatter to raw/."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from library_server.vault_builder.types import ExtractResult


class OutputWriter:
    """Writes structured Markdown files with YAML frontmatter."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def write_file(
        self,
        subdir: str,
        filename: str,
        title: str,
        source_type: str,
        source_path: str,
        extractor: str,
        trust: float,
        domain: str,
        tags: list[str],
        related: list[str],
        body: str,
    ) -> Path:
        """Write a single MD file with YAML frontmatter. Returns the path to the written file."""
        out_dir = self.base_dir / subdir
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / filename

        frontmatter = {
            "title": title,
            "source_type": source_type,
            "source_path": source_path,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "extractor": extractor,
            "trust": trust,
            "domain": domain,
            "tags": tags,
            "related": related,
        }

        content = "---\n"
        content += yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)
        content += "---\n\n"
        content += body
        if not body.endswith("\n"):
            content += "\n"

        out_file.write_text(content)
        return out_file

    def write_manifest(
        self,
        results: list[ExtractResult],
        total_duration: float,
    ) -> Path:
        """Write build manifest summarizing what ran."""
        now = datetime.now(timezone.utc).isoformat()
        any_failed = any(not r.success for r in results)
        all_failed = all(not r.success for r in results)

        if all_failed:
            status = "failed"
        elif any_failed:
            status = "completed_with_warnings"
        else:
            status = "completed"

        lines = [
            "---",
            "title: Build Manifest",
            f"build_id: {now}",
            f"duration: {total_duration:.1f}s",
            f"status: {status}",
            "---",
            "",
            "| Extractor | Status | Files Written | Duration | Trust |",
            "|-----------|--------|---------------|----------|-------|",
        ]

        for r in results:
            s = "success" if r.success else "failed"
            lines.append(f"| {r.source_name} | {s} | {len(r.files_written)} | {r.duration_seconds:.1f}s | — |")

        if any(not r.success for r in results):
            lines.append("")
            lines.append("## Errors")
            lines.append("")
            for r in results:
                if r.errors:
                    for err in r.errors:
                        lines.append(f"- **{r.source_name}:** {err}")

        manifest_path = self.base_dir / "_build-manifest.md"
        manifest_path.write_text("\n".join(lines) + "\n")
        return manifest_path
