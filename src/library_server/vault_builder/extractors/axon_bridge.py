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

        if not shutil.which("axon"):
            return SurveyResult(
                source_name=self.name, file_count=0, total_size_bytes=0,
                structure_summary="Axon CLI not found",
                health="error",
            )

        missing = [r["path"] for r in repos if r.get("path") and not Path(r["path"]).exists()]
        if missing:
            return SurveyResult(
                source_name=self.name, file_count=0, total_size_bytes=0,
                structure_summary=f"{len(missing)} repo path(s) not found: {', '.join(missing)}",
                health="error",
            )

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
        repo_dir = Path(repo_path)

        # Step 1: Index the repo (run from repo dir so axon stores index locally)
        analyze = subprocess.run(
            ["axon", "analyze", ".", "--no-embeddings"],
            capture_output=True, text=True, timeout=180, cwd=repo_path,
        )
        if analyze.returncode != 0:
            raise RuntimeError(f"axon analyze failed: {analyze.stderr.strip()}")

        # Step 2: Get all communities via cypher
        communities = self._cypher_communities(repo_path)

        # Step 3: Get members per community via cypher
        if communities:
            files_written.extend(
                self._write_axon_results(writer, output_dir, repo_name, communities, repo_path)
            )

        # Step 4: Always write a repo summary with real stats from axon status
        status = self._axon_status(repo_path)
        file_count = status.get("files") or sum(
            1 for _ in repo_dir.rglob("*")
            if _.is_file() and not str(_).startswith(str(repo_dir / ".git"))
        )
        summary_body = (
            f"# {repo_name}\n\n"
            f"**Type:** {repo_cfg.get('type', 'unknown')}\n"
            f"**Language:** {repo_cfg.get('language', 'unknown')}\n"
            f"**Files:** {file_count}\n"
            f"**Symbols:** {status.get('symbols', '?')}\n"
            f"**Relationships:** {status.get('relationships', '?')}\n"
            f"**Clusters:** {status.get('clusters', '?')}\n"
        )
        writer.write_file(
            subdir=f"{output_dir.name}/{repo_name}", filename="repo-summary.md",
            title=f"{repo_name} Repository", source_type="code_repo",
            source_path=repo_path, extractor=self.name, trust=1.0,
            domain=self._detect_domain(repo_name),
            tags=["source/code", "trust/high"], related=[], body=summary_body,
        )
        files_written.append(f"{repo_name}/repo-summary.md")
        return files_written

    def _axon_status(self, repo_path: str) -> dict:
        """Run `axon status` and parse the key metrics."""
        result = subprocess.run(
            ["axon", "status"], capture_output=True, text=True, timeout=30, cwd=repo_path,
        )
        stats: dict = {}
        if result.returncode != 0:
            return stats
        for line in result.stdout.splitlines():
            line = line.strip()
            for key in ("Files", "Symbols", "Relationships", "Clusters", "Flows"):
                if line.startswith(key + ":"):
                    try:
                        stats[key.lower()] = int(line.split(":", 1)[1].strip())
                    except ValueError:
                        pass
        return stats

    def _cypher_communities(self, repo_path: str) -> list[dict]:
        """Query all communities from the axon graph via cypher."""
        result = subprocess.run(
            ["axon", "cypher",
             "MATCH (c:Community) RETURN c.name, c.cohesion, c.properties_json"],
            capture_output=True, text=True, timeout=60, cwd=repo_path,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []

        communities = []
        for line in result.stdout.splitlines():
            line = line.strip()
            # Lines look like: "  1. Services+graphql | 0.01 | {"symbol_count": 125}"
            if not line or not line[0].isdigit():
                continue
            parts = line.split(". ", 1)
            if len(parts) < 2:
                continue
            cols = parts[1].split(" | ")
            if len(cols) < 1:
                continue
            name = cols[0].strip()
            try:
                symbol_count = json.loads(cols[2].strip()).get("symbol_count", 0) if len(cols) > 2 else 0
            except (json.JSONDecodeError, IndexError):
                symbol_count = 0
            communities.append({"name": name, "symbol_count": symbol_count})
        return communities

    def _cypher_members(self, repo_path: str, community_name: str) -> list[tuple[str, str]]:
        """Query members of a community: returns list of (symbol_name, file_path)."""
        # Escape single quotes in community name
        safe_name = community_name.replace("'", "\\'")
        result = subprocess.run(
            ["axon", "cypher",
             f"MATCH (n:Method)-[r]->(c:Community) WHERE c.name = '{safe_name}' "
             f"RETURN n.name, n.file_path LIMIT 50"],
            capture_output=True, text=True, timeout=60, cwd=repo_path,
        )
        members = []
        if result.returncode != 0:
            return members
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or not line[0].isdigit():
                continue
            parts = line.split(". ", 1)
            if len(parts) < 2:
                continue
            cols = parts[1].split(" | ")
            if len(cols) >= 2:
                members.append((cols[0].strip(), cols[1].strip()))
        return members

    def _write_axon_results(
        self, writer: OutputWriter, output_dir: Path, repo_name: str,
        communities: list[dict], repo_path: str,
    ) -> list[str]:
        files_written: list[str] = []

        for community in communities:
            community_name = community["name"]
            symbol_count = community.get("symbol_count", 0)
            slug = re.sub(r"[^a-z0-9]+", "-", community_name.lower()).strip("-")

            members = self._cypher_members(repo_path, community_name)

            all_symbols = [name for name, _ in members]
            domain = self._detect_domain(" ".join(all_symbols) + " " + community_name)
            related = [f"[[{repo_name}/repo-summary]]"]

            body_parts = [
                f"# {community_name}",
                "",
                f"**Repo:** {repo_name}  ",
                f"**Symbols:** {symbol_count}  ",
                f"**Domain:** {domain}",
                "",
                "## Members",
                "",
            ]
            for sym_name, file_path in members:
                body_parts.append(f"- `{sym_name}` — `{file_path}`")

            writer.write_file(
                subdir=f"{output_dir.name}/{repo_name}/communities", filename=f"{slug}.md",
                title=f"{community_name}", source_type="code_repo",
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
