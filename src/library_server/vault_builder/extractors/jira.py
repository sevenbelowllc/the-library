"""Jira extractor — Atlassian issues via REST API."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from library_server.pm.jira_client import JiraClient
from library_server.vault_builder.extractors.base import BaseExtractor
from library_server.vault_builder.output import OutputWriter
from library_server.vault_builder.types import SurveyResult, PreviewResult, ExtractResult

_STATUS_TRUST: dict[str, float] = {
    "done": 0.8, "closed": 0.8, "in progress": 0.6, "in review": 0.6,
    "to do": 0.5, "backlog": 0.5, "open": 0.5,
}

_STATUS_TAG_MAP: dict[str, str] = {
    "done": "done", "closed": "done", "in progress": "in-progress",
    "in review": "in-progress", "to do": "backlog", "backlog": "backlog", "open": "backlog",
}


class JiraExtractor(BaseExtractor):
    name = "jira"
    display_name = "Jira Issues"
    source_description = "Jira issues via Atlassian API"
    output_subdir = "jira"

    def validate_config(self) -> list[str]:
        errors: list[str] = []
        if not self.config.get("projects"):
            errors.append("Missing required config: projects")
        if not os.environ.get("JIRA_API_TOKEN"):
            errors.append("Missing env var: JIRA_API_TOKEN")
        if not os.environ.get("JIRA_EMAIL"):
            errors.append("Missing env var: JIRA_EMAIL")
        return errors

    def _get_client(self) -> JiraClient:
        """Get a JiraClient for the configured instance."""
        site_url = f"https://{self.config.get('instance', '')}"
        return JiraClient(site_url=site_url)

    async def _fetch_issues(self, project: str) -> list[dict[str, Any]]:
        """Fetch all issues for a project via JiraClient."""
        client = self._get_client()
        result = await client.search_issues(
            jql=f"project = {project}",
            fields=["summary", "description", "issuetype", "status", "assignee", "labels", "issuelinks", "comment"],
            max_results=100,
        )
        return result.get("issues", [])

    async def survey(self) -> SurveyResult:
        total_count = 0
        project_keys = self.config.get("projects", [])
        project_counts: dict[str, int] = {}
        failed_projects: list[str] = []
        for project in project_keys:
            try:
                issues = await self._fetch_issues(project)
                project_counts[project] = len(issues)
                total_count += len(issues)
            except Exception as e:
                project_counts[project] = 0
                failed_projects.append(f"{project}: {e}")
        project_detail = ", ".join(f"{k}({v})" for k, v in project_counts.items())
        if failed_projects and len(failed_projects) == len(project_keys):
            health = "error"
            summary = f"All {len(project_keys)} project(s) unreachable — {failed_projects[0]}"
        elif failed_projects:
            health = "degraded"
            summary = (
                f"{total_count} issues from {len(project_keys) - len(failed_projects)} project(s); "
                f"{len(failed_projects)} failed: {project_detail}"
            )
        elif total_count == 0:
            health = "empty"
            summary = f"0 issues across {len(project_keys)} projects: {project_detail}"
        else:
            health = "connected"
            summary = f"{total_count} issues across {len(project_keys)} projects: {project_detail}"
        return SurveyResult(
            source_name=self.name, file_count=total_count, total_size_bytes=0,
            structure_summary=summary, health=health,
        )

    async def preview(self) -> PreviewResult:
        files: list[str] = []
        for project in self.config.get("projects", []):
            try:
                issues = await self._fetch_issues(project)
                for issue in issues:
                    key = issue.get("key", "UNKNOWN")
                    files.append(f"jira/{project}/{key}.md")
            except Exception:
                pass
        return PreviewResult(source_name=self.name, files_to_create=files)

    async def extract(self, output_dir: Path) -> ExtractResult:
        writer = OutputWriter(base_dir=output_dir.parent)
        files_written: list[str] = []
        errors: list[str] = []
        start = time.monotonic()

        for project in self.config.get("projects", []):
            try:
                issues = await self._fetch_issues(project)
                for issue in issues:
                    try:
                        key = issue.get("key", "UNKNOWN")
                        fields = issue.get("fields", {})
                        summary = fields.get("summary", "Untitled")
                        description = fields.get("description") or "No description."
                        issue_type = fields.get("issuetype", {}).get("name", "Task")
                        status_name = fields.get("status", {}).get("name", "Unknown")
                        status_lower = status_name.lower()
                        assignee = fields.get("assignee")
                        assignee_name = assignee.get("displayName", "Unassigned") if assignee else "Unassigned"
                        labels = fields.get("labels", [])

                        trust = _STATUS_TRUST.get(status_lower, 0.5)
                        status_tag = _STATUS_TAG_MAP.get(status_lower, "backlog")
                        trust_tag = "trust/high" if trust >= 0.8 else "trust/medium" if trust >= 0.5 else "trust/low"

                        related: list[str] = []
                        for link in fields.get("issuelinks", []):
                            outward = link.get("outwardIssue", {})
                            inward = link.get("inwardIssue", {})
                            linked_key = outward.get("key") or inward.get("key")
                            if linked_key:
                                related.append(f"[[{linked_key}]]")

                        body_parts = [
                            f"# {key}: {summary}", "",
                            f"**Type:** {issue_type}", f"**Status:** {status_name}",
                            f"**Assignee:** {assignee_name}",
                        ]
                        if labels:
                            body_parts.append(f"**Labels:** {', '.join(labels)}")
                        body_parts.extend(["", "## Description", "", str(description)])

                        comments = fields.get("comment", {}).get("comments", [])
                        if comments:
                            body_parts.extend(["", "## Comments", ""])
                            for c in comments:
                                body_parts.append(f"- {c.get('body', '')}")

                        tags = ["source/jira", trust_tag, status_tag]

                        writer.write_file(
                            subdir=f"{output_dir.name}/{project}", filename=f"{key}.md",
                            title=f"{key}: {summary}", source_type="jira_issue",
                            source_path=f"{self.config.get('instance', '')}/browse/{key}",
                            extractor=self.name, trust=trust,
                            domain="project-management", tags=tags, related=related,
                            body="\n".join(body_parts),
                        )
                        files_written.append(f"{project}/{key}.md")
                    except Exception as e:
                        errors.append(f"Error extracting {issue.get('key', '?')}: {e}")
            except Exception as e:
                errors.append(f"Error fetching project {project}: {e}")

        duration = time.monotonic() - start
        projects = self.config.get("projects", [])
        # Treat as failure if every project errored (auth failure, network, etc.)
        project_errors = [e for e in errors if e.startswith("Error fetching project")]
        all_projects_failed = bool(projects) and len(project_errors) >= len(projects)
        return ExtractResult(
            source_name=self.name, files_written=files_written, files_skipped=[],
            errors=errors, duration_seconds=duration,
            success=len(files_written) > 0 and not all_projects_failed,
        )
