"""PROJECT-STATE.md reader/writer for the MMU."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from library_server.types import ProjectStateData

_LIBRARY_VERSION = "1.0"


def render_project_state(data: ProjectStateData) -> str:
    """Render ProjectStateData to markdown with YAML frontmatter.

    Stays under 100 lines.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines: list[str] = []

    # YAML frontmatter
    lines += [
        "---",
        f"library_version: {_LIBRARY_VERSION}",
        f"updated: {now}",
        f"session_count: {data.session_count}",
        "---",
        "",
    ]

    # Active section
    lines += [
        "## Active",
        "",
        f"**Project:** {data.project}",
        f"**Focus:** {data.focus}",
        f"**Task:** {data.active_task}",
        "",
    ]

    if data.blockers:
        lines.append("**Blockers:**")
        lines += [f"- {b}" for b in data.blockers]
        lines.append("")

    # PM Projects (only if non-empty)
    if data.pm_projects:
        lines += ["## PM Projects", ""]
        lines.append("| Key | Name | Open | Blocked |")
        lines.append("|-----|------|------|---------|")
        for p in data.pm_projects:
            lines.append(
                f"| {p.get('key', '')} | {p.get('name', '')} | {p.get('open', 0)} | {p.get('blocked', 0)} |"
            )
        lines.append("")

    # Invariants
    lines += ["## Invariants", ""]
    if data.invariants:
        lines += [f"- {inv}" for inv in data.invariants]
    lines.append("")

    # Recent Decisions
    lines += ["## Recent Decisions", ""]
    if data.recent_decisions:
        for d in data.recent_decisions:
            lines.append(f"- **{d.get('id', '')}**: {d.get('decision', '')}")
    lines.append("")

    # Library Health
    lines += [
        "## Library Health",
        "",
        f"- vault_file_count: {data.vault_file_count}",
        f"- domain_count: {data.domain_count}",
        f"- decision_count: {data.decision_count}",
        f"- claude_md_lines: {data.claude_md_lines}",
        f"- keyword_accuracy: {data.keyword_accuracy}",
        f"- keyword_observations: {data.keyword_observations}",
        "",
    ]

    return "\n".join(lines)


def parse_project_state(path: Path) -> ProjectStateData:
    """Parse a PROJECT-STATE.md file into ProjectStateData."""
    content = path.read_text(encoding="utf-8")

    def _scalar(pattern: str, default: str = "") -> str:
        m = re.search(pattern, content, re.MULTILINE)
        return m.group(1).strip() if m else default

    def _int(pattern: str, default: int = 0) -> int:
        m = re.search(pattern, content, re.MULTILINE)
        return int(m.group(1).strip()) if m else default

    def _float(pattern: str, default: float = 0.0) -> float:
        m = re.search(pattern, content, re.MULTILINE)
        return float(m.group(1).strip()) if m else default

    def _list_section(heading: str) -> list[str]:
        pattern = rf"## {re.escape(heading)}\s*\n(.*?)(?=\n## |\Z)"
        m = re.search(pattern, content, re.DOTALL)
        if not m:
            return []
        items = []
        for line in m.group(1).splitlines():
            line = line.strip()
            if line.startswith("- "):
                items.append(line[2:])
        return items

    project = _scalar(r"\*\*Project:\*\*[ \t]*(.+)")
    focus = _scalar(r"\*\*Focus:\*\*[ \t]*(.+)")
    active_task = _scalar(r"\*\*Task:\*\*[ \t]*(.+)")
    session_count = _int(r"^session_count:\s*(\d+)")
    vault_file_count = _int(r"vault_file_count:\s*(\d+)")
    domain_count = _int(r"domain_count:\s*(\d+)")
    decision_count = _int(r"decision_count:\s*(\d+)")
    claude_md_lines = _int(r"claude_md_lines:\s*(\d+)")
    keyword_accuracy = _float(r"keyword_accuracy:\s*([\d.]+)")
    keyword_observations = _int(r"keyword_observations:\s*(\d+)")

    # Blockers: bullets under **Blockers:** until blank line or next section
    blockers: list[str] = []
    blockers_m = re.search(r"\*\*Blockers:\*\*\s*\n(.*?)(?=\n\n|\n## |\Z)", content, re.DOTALL)
    if blockers_m:
        for line in blockers_m.group(1).splitlines():
            line = line.strip()
            if line.startswith("- "):
                blockers.append(line[2:])

    invariants = _list_section("Invariants")

    # Recent Decisions: "- **ID**: text"
    recent_decisions: list[dict] = []
    decisions_m = re.search(r"## Recent Decisions\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
    if decisions_m:
        for line in decisions_m.group(1).splitlines():
            line = line.strip()
            dm = re.match(r"- \*\*(.+?)\*\*:\s*(.+)", line)
            if dm:
                recent_decisions.append({"id": dm.group(1), "decision": dm.group(2)})

    # PM Projects: table rows after header
    pm_projects: list[dict] = []
    pm_m = re.search(r"## PM Projects\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
    if pm_m:
        for line in pm_m.group(1).splitlines():
            line = line.strip()
            if line.startswith("|") and not line.startswith("| Key") and not line.startswith("|---"):
                parts = [p.strip() for p in line.strip("|").split("|")]
                if len(parts) >= 4:
                    try:
                        pm_projects.append({
                            "key": parts[0],
                            "name": parts[1],
                            "open": int(parts[2]),
                            "blocked": int(parts[3]),
                        })
                    except ValueError:
                        pass

    return ProjectStateData(
        project=project,
        focus=focus,
        active_task=active_task,
        blockers=blockers,
        invariants=invariants,
        pm_projects=pm_projects,
        recent_decisions=recent_decisions,
        session_count=session_count,
        vault_file_count=vault_file_count,
        domain_count=domain_count,
        decision_count=decision_count,
        claude_md_lines=claude_md_lines,
        keyword_accuracy=keyword_accuracy,
        keyword_observations=keyword_observations,
    )


def update_project_state_field(path: Path, field: str, value) -> None:
    """Parse PROJECT-STATE.md, update one field, re-render and write."""
    data = parse_project_state(path)
    setattr(data, field, value)
    path.write_text(render_project_state(data), encoding="utf-8")
