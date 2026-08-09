"""Code Repo extractor — source code repos analyzed in-process via Graphify.

Replaces the axon_bridge extractor: no CLI subprocess, no separate index.
AST extraction, community detection, labeling, and cohesion scoring all run
through the graphify Python API (deterministic, offline, no LLM calls).
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from library_server.vault_builder.extractors.base import BaseExtractor
from library_server.vault_builder.output import OutputWriter
from library_server.vault_builder.types import SurveyResult, PreviewResult, ExtractResult

try:
    from graphify.build import build_from_json
    from graphify.cluster import cluster, label_communities_by_hub, score_all
    from graphify.extract import collect_files, extract
except ImportError:  # pragma: no cover
    build_from_json = None  # type: ignore[assignment]
    cluster = None  # type: ignore[assignment]
    label_communities_by_hub = None  # type: ignore[assignment]
    score_all = None  # type: ignore[assignment]
    collect_files = None  # type: ignore[assignment]
    extract = None  # type: ignore[assignment]

_GRAPHIFY_HINT = "Graphify is not installed. Run: pip install 'the-library[graphify]'"

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

_MEMBER_LIMIT = 50


class CodeRepoExtractor(BaseExtractor):
    name = "code_repo"
    display_name = "Source Code (Graphify)"
    source_description = "Source code repos analyzed in-process via Graphify"
    output_subdir = "repos"

    def validate_config(self) -> list[str]:
        errors: list[str] = []
        repos = self.config.get("repos")
        if not repos:
            errors.append("Missing required config: repos")
            return errors
        if extract is None:
            errors.append(_GRAPHIFY_HINT)
        for repo in repos:
            path = repo.get("path")
            if path and not Path(path).exists():
                errors.append(f"Repo path does not exist: {path}")
        return errors

    async def survey(self) -> SurveyResult:
        repos = self.config.get("repos", [])
        if extract is None:
            return SurveyResult(
                source_name=self.name, file_count=0, total_size_bytes=0,
                structure_summary=_GRAPHIFY_HINT, health="error",
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
        return PreviewResult(
            source_name=self.name,
            files_to_create=files,
            warnings=[
                "Community pages (repos/<name>/communities/*.md) are computed "
                "at extract time and are not listed in this preview."
            ],
        )

    async def extract(self, output_dir: Path) -> ExtractResult:
        writer = OutputWriter(base_dir=output_dir.parent)
        files_written: list[str] = []
        errors: list[str] = []
        start = time.monotonic()

        if extract is None:
            return ExtractResult(
                source_name=self.name, errors=[_GRAPHIFY_HINT],
                duration_seconds=time.monotonic() - start, success=False,
            )

        for repo in self.config.get("repos", []):
            repo_name = repo["name"]
            repo_path = Path(repo["path"])
            try:
                files_written.extend(
                    self._extract_repo(writer, output_dir, repo_name, repo_path, repo)
                )
            except Exception as e:
                errors.append(f"Error analyzing {repo_name}: {e}")

        return ExtractResult(
            source_name=self.name, files_written=files_written, files_skipped=[],
            errors=errors, duration_seconds=time.monotonic() - start,
            success=len(files_written) > 0,
        )

    def _extract_repo(
        self, writer: OutputWriter, output_dir: Path, repo_name: str,
        repo_path: Path, repo_cfg: dict,
    ) -> list[str]:
        files_written: list[str] = []

        code_files = collect_files(repo_path, root=repo_path)
        if not code_files:
            raise RuntimeError(f"no supported code files found under {repo_path}")

        extraction = extract(code_files, root=repo_path)
        graph = build_from_json(extraction, root=repo_path)
        communities = cluster(graph)
        labels = label_communities_by_hub(graph, communities)
        cohesion = score_all(graph, communities)

        # Community pages
        slug_counts: dict[str, int] = {}
        for cid, member_ids in communities.items():
            label = labels.get(cid, f"community-{cid}")
            base_slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or f"community-{cid}"
            count = slug_counts.get(base_slug, 0)
            slug_counts[base_slug] = count + 1
            slug = f"{base_slug}-{count + 1}" if count > 0 else base_slug

            members = [
                (
                    str(graph.nodes[nid].get("label", nid)),
                    str(graph.nodes[nid].get("source_file", "")),
                )
                for nid in member_ids[:_MEMBER_LIMIT]
            ]
            domain = self._detect_domain(" ".join(m[0] for m in members) + " " + label)

            body_parts = [
                f"# {label}",
                "",
                f"**Repo:** {repo_name}  ",
                f"**Symbols:** {len(member_ids)}  ",
                f"**Cohesion:** {cohesion.get(cid, 0.0)}  ",
                f"**Domain:** {domain}",
                "",
                "## Members",
                "",
            ]
            body_parts += [f"- `{sym}` — `{path}`" for sym, path in members]
            if len(member_ids) > _MEMBER_LIMIT:
                body_parts.append(f"- … {len(member_ids) - _MEMBER_LIMIT} more")

            writer.write_file(
                subdir=f"{output_dir.name}/{repo_name}/communities", filename=f"{slug}.md",
                title=label, source_type="code_repo",
                source_path=repo_name, extractor=self.name, trust=1.0,
                domain=domain, tags=["source/code", "trust/high", f"domain/{domain}"],
                related=[f"[[{repo_name}/repo-summary]]"],
                body="\n".join(body_parts),
            )
            files_written.append(f"{repo_name}/communities/{slug}.md")

        # Repo summary
        summary_body = (
            f"# {repo_name}\n\n"
            f"**Type:** {repo_cfg.get('type', 'unknown')}\n"
            f"**Language:** {repo_cfg.get('language', 'auto-detected')}\n"
            f"**Files:** {len(code_files)}\n"
            f"**Symbols:** {graph.number_of_nodes()}\n"
            f"**Relationships:** {graph.number_of_edges()}\n"
            f"**Communities:** {len(communities)}\n"
        )
        writer.write_file(
            subdir=f"{output_dir.name}/{repo_name}", filename="repo-summary.md",
            title=f"{repo_name} Repository", source_type="code_repo",
            source_path=str(repo_path), extractor=self.name, trust=1.0,
            domain=self._detect_domain(repo_name),
            tags=["source/code", "trust/high"], related=[], body=summary_body,
        )
        files_written.append(f"{repo_name}/repo-summary.md")
        return files_written

    @staticmethod
    def _detect_domain(text: str) -> str:
        for pattern, domain in _DOMAIN_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return domain
        return "general"
