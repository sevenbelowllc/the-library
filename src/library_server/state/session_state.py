"""SESSION.md reader/writer for the MMU."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from library_server.types import SessionStateData


def render_session_state(data: SessionStateData) -> str:
    """Render SessionStateData to markdown with YAML frontmatter."""
    lines: list[str] = []

    # YAML frontmatter
    lines += [
        "---",
        f"session_id: {data.session_id}",
        f"started: {data.started}",
        f"last_updated: {data.last_updated}",
        f"context_usage: {data.context_usage}",
        f"turns: {data.turns}",
        "---",
        "",
    ]

    # Current section
    lines += [
        "## Current",
        "",
        f"**Task:** {data.task}",
        f"**Doing:** {data.doing}",
        f"**Branch:** {data.branch}",
        "",
    ]

    # Resume section
    lines += ["## Resume", ""]
    if data.resume_instructions:
        lines += [f"- {r}" for r in data.resume_instructions]
    lines.append("")

    # Files Touched
    lines += ["## Files Touched", ""]
    if data.files_touched:
        lines += [f"- {f}" for f in data.files_touched]
    lines.append("")

    # Decisions This Session
    lines += ["## Decisions This Session", ""]
    if data.decisions:
        lines += [f"- {d}" for d in data.decisions]
    lines.append("")

    # Domains Loaded
    lines += ["## Domains Loaded", ""]
    if data.domains_loaded:
        lines += [f"- {d}" for d in data.domains_loaded]
    lines.append("")

    return "\n".join(lines)


def parse_session_state(path: Path) -> SessionStateData:
    """Parse a SESSION.md file into SessionStateData."""
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

    session_id = _scalar(r"^session_id:\s*(.+)")
    started = _scalar(r"^started:\s*(.+)")
    last_updated = _scalar(r"^last_updated:\s*(.+)")
    context_usage = _float(r"^context_usage:\s*([\d.]+)")
    turns = _int(r"^turns:\s*(\d+)")
    task = _scalar(r"\*\*Task:\*\*[ \t]*(.+)")
    doing = _scalar(r"\*\*Doing:\*\*[ \t]*(.+)")
    branch = _scalar(r"\*\*Branch:\*\*[ \t]*(.+)", default="main")

    resume_instructions = _list_section("Resume")
    files_touched = _list_section("Files Touched")
    decisions = _list_section("Decisions This Session")
    domains_loaded = _list_section("Domains Loaded")

    return SessionStateData(
        session_id=session_id,
        task=task,
        doing=doing,
        branch=branch,
        resume_instructions=resume_instructions,
        decisions=decisions,
        files_touched=files_touched,
        domains_loaded=domains_loaded,
        turns=turns,
        context_usage=context_usage,
        started=started,
        last_updated=last_updated,
    )


def update_session_turn(
    path: Path,
    context_usage: float,
    doing: str,
    new_files: list[str],
    new_decision: str | None,
    new_domain: str | None,
) -> None:
    """Increment turns, update last_updated, and append new data."""
    data = parse_session_state(path)

    data.turns += 1
    data.last_updated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data.context_usage = context_usage
    if doing:
        data.doing = doing

    for f in new_files:
        if f not in data.files_touched:
            data.files_touched.append(f)

    if new_decision and new_decision not in data.decisions:
        data.decisions.append(new_decision)

    if new_domain and new_domain not in data.domains_loaded:
        data.domains_loaded.append(new_domain)

    path.write_text(render_session_state(data), encoding="utf-8")
