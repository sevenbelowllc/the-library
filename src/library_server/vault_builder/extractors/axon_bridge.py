"""Axon Bridge extractor — source code repos via Axon CLI."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from library_server.vault_builder.extractors.base import BaseExtractor
from library_server.vault_builder.output import OutputWriter
from library_server.vault_builder.types import SurveyResult, PreviewResult, ExtractResult

_DOMAIN_PATTERNS: list[tuple[str, str]] = [
    (r"auth|clerk|jwt|requireAuth", "auth"),
    (r"tenant|org_id|current_tenant|rls", "tenancy"),
    (r"graphql|resolver|typeDef", "api"),
    (r"migration|schema|sql|entity", "database"),
    (r"terraform|gcp|cloudflare", "infra"),
    (r"stripe|billing|subscription", "integration"),
    (r"audit|log|immutable", "audit"),
    (r"compliance|framework|control|evidence", "compliance"),
    (r"encrypt|decrypt|vault|secret", "encryption"),
]

_TF_RESOURCE_RE = re.compile(r'^resource\s+"([^"]+)"\s+"([^"]+)"', re.MULTILINE)
_TF_MODULE_RE = re.compile(r'^module\s+"([^"]+)"', re.MULTILINE)
_TF_VARIABLE_RE = re.compile(r'^variable\s+"([^"]+)"', re.MULTILINE)


class AxonBridgeExtractor(BaseExtractor):
    name = "axon_bridge"
    display_name = "Source Code (Axon)"
    source_description = "Source code repos analyzed via Axon"
    output_subdir = "repos"

    def validate_config(self) -> list[str]:
        errors: list[str] = []
        repos = self.config.get("repos")
        if not repos:
            errors.append("Missing required config: repos")
            return errors
        if not shutil.which("axon"):
            errors.append("Axon CLI not found. Install with: pip install axoniq")
        for repo in repos:
            path = repo.get("path")
            if path and not Path(path).exists():
                errors.append(f"Repo path does not exist: {path}")
        return errors

    async def survey(self) -> SurveyResult:
        repos = self.config.get("repos", [])
        return SurveyResult(
            source_name=self.name, file_count=len(repos), total_size_bytes=0,
            structure_summary=f"{len(repos)} source code repos", health="connected",
        )

    async def preview(self) -> PreviewResult:
        repos = self.config.get("repos", [])
        files = [f"repos/{r['name']}/repo-summary.md" for r in repos]
        return PreviewResult(source_name=self.name, files_to_create=files)

    async def extract(self, output_dir: Path) -> ExtractResult:
        writer = OutputWriter(base_dir=output_dir.parent)
        files_written: list[str] = []
        errors: list[str] = []
        start = time.monotonic()

        for repo in self.config.get("repos", []):
            repo_name = repo["name"]
            repo_path = repo["path"]
            language = repo.get("language", "unknown")

            try:
                if language == "terraform":
                    written = self._extract_terraform(writer, output_dir, repo_name, repo_path)
                else:
                    written = self._extract_with_axon(writer, output_dir, repo_name, repo_path, repo)
                files_written.extend(written)
            except Exception as e:
                errors.append(f"Error analyzing {repo_name}: {e}")

        duration = time.monotonic() - start
        return ExtractResult(
            source_name=self.name, files_written=files_written, files_skipped=[],
            errors=errors, duration_seconds=duration,
            success=len(files_written) > 0,
        )

    def _extract_with_axon(
        self, writer: OutputWriter, output_dir: Path, repo_name: str, repo_path: str, repo_cfg: dict,
    ) -> list[str]:
        files_written: list[str] = []

        try:
            subprocess.run(
                ["axon", "analyze", repo_path, "--no-embeddings"],
                capture_output=True, text=True, timeout=120,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        try:
            result = subprocess.run(
                ["axon", "query", "list all modules and communities", "--limit", "100"],
                capture_output=True, text=True, timeout=60, cwd=repo_path,
            )
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                results = data.get("results", [])
                if results:
                    files_written.extend(
                        self._write_axon_results(writer, output_dir, repo_name, results)
                    )
        except Exception:
            pass

        repo_dir = Path(repo_path)
        file_count = sum(1 for _ in repo_dir.rglob("*") if _.is_file() and not str(_).startswith(str(repo_dir / ".git")))
        summary_body = f"# {repo_name}\n\n**Type:** {repo_cfg.get('type', 'unknown')}\n**Language:** {repo_cfg.get('language', 'unknown')}\n**Files:** {file_count}\n"

        writer.write_file(
            subdir=f"{output_dir.name}/{repo_name}", filename="repo-summary.md",
            title=f"{repo_name} Repository", source_type="code_repo",
            source_path=repo_path, extractor=self.name, trust=1.0,
            domain=self._detect_domain(repo_name),
            tags=["source/code", "trust/high"], related=[], body=summary_body,
        )
        files_written.append(f"{repo_name}/repo-summary.md")
        return files_written

    def _write_axon_results(
        self, writer: OutputWriter, output_dir: Path, repo_name: str, results: list[dict],
    ) -> list[str]:
        files_written: list[str] = []
        communities: dict[str, list[dict]] = {}

        for item in results:
            community = item.get("community", "uncategorized")
            communities.setdefault(community, []).append(item)

        for community_name, members in communities.items():
            slug = community_name.lower().replace(" ", "-")
            symbols = []
            for m in members:
                for sym in m.get("symbols", []):
                    symbols.append(sym)

            body_parts = [f"# {community_name}", "", "## Members", ""]
            for m in members:
                body_parts.append(f"- **{m.get('id', '?')}** ({m.get('type', '?')})")
                for sym in m.get("symbols", []):
                    body_parts.append(f"  - `{sym}`")

            domain = self._detect_domain(" ".join(symbols))
            related = [f"[[{repo_name}/repo-summary]]"]

            writer.write_file(
                subdir=f"{output_dir.name}/{repo_name}/communities", filename=f"{slug}.md",
                title=f"{community_name} Community", source_type="code_repo",
                source_path=repo_name, extractor=self.name, trust=1.0,
                domain=domain, tags=["source/code", "trust/high", f"domain/{domain}"],
                related=related, body="\n".join(body_parts),
            )
            files_written.append(f"{repo_name}/communities/{slug}.md")

        return files_written

    def _extract_terraform(
        self, writer: OutputWriter, output_dir: Path, repo_name: str, repo_path: str,
    ) -> list[str]:
        files_written: list[str] = []
        repo_dir = Path(repo_path)
        resources: list[str] = []
        modules: list[str] = []
        variables: list[str] = []

        for tf_file in repo_dir.rglob("*.tf"):
            content = tf_file.read_text()
            resources.extend(f"{t}.{n}" for t, n in _TF_RESOURCE_RE.findall(content))
            modules.extend(_TF_MODULE_RE.findall(content))
            variables.extend(_TF_VARIABLE_RE.findall(content))

        body_parts = [f"# {repo_name}", "", "**Type:** infrastructure", "**Language:** terraform", ""]
        if resources:
            body_parts.extend(["## Resources", ""] + [f"- `{r}`" for r in resources] + [""])
        if modules:
            body_parts.extend(["## Modules", ""] + [f"- `{m}`" for m in modules] + [""])
        if variables:
            body_parts.extend(["## Variables", ""] + [f"- `{v}`" for v in variables] + [""])

        writer.write_file(
            subdir=f"{output_dir.name}/{repo_name}", filename="repo-summary.md",
            title=f"{repo_name} Infrastructure", source_type="code_repo",
            source_path=repo_path, extractor=self.name, trust=1.0,
            domain="infra", tags=["source/code", "trust/high", "domain/infra"],
            related=[], body="\n".join(body_parts),
        )
        files_written.append(f"{repo_name}/repo-summary.md")
        return files_written

    @staticmethod
    def _detect_domain(text: str) -> str:
        for pattern, domain in _DOMAIN_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return domain
        return "general"
