"""Checkpoint read/write — structured session state capture."""

from __future__ import annotations

import re
from pathlib import Path

from library_server.types import CheckpointData


def write_checkpoint(checkpoint_dir: str, data: CheckpointData) -> dict:
    """Write a structured checkpoint file.

    Creates YYYY-MM-DD-HH-MM-SS-<topic>-checkpoint.md in checkpoint_dir.

    Returns:
        {"status": "written", "path": str}
    """
    path = Path(checkpoint_dir)
    path.mkdir(parents=True, exist_ok=True)

    filename = f"{data.date}-{data.topic}-checkpoint.md"
    filepath = path / filename

    content = _render_checkpoint(data)
    filepath.write_text(content, encoding="utf-8")

    return {"status": "written", "path": str(filepath)}


def read_checkpoint(checkpoint_path: str) -> dict:
    """Read and parse a checkpoint file.

    Returns parsed checkpoint data as a dict.
    """
    path = Path(checkpoint_path)
    if not path.exists():
        return {"error": f"Checkpoint not found: {checkpoint_path}"}

    content = path.read_text(encoding="utf-8")
    return _parse_checkpoint(content)


def list_checkpoints(checkpoint_dir: str) -> dict:
    """List all checkpoint files in a directory.

    Returns:
        {"checkpoints": [{"topic", "date", "status", "path"}, ...]}
    """
    path = Path(checkpoint_dir)
    checkpoints: list[dict] = []

    if not path.is_dir():
        return {"checkpoints": []}

    for f in sorted(path.glob("*-checkpoint.md")):
        parsed = _parse_checkpoint(f.read_text(encoding="utf-8"))
        checkpoints.append({
            "topic": parsed.get("topic", f.stem),
            "date": parsed.get("date", ""),
            "status": parsed.get("status", ""),
            "path": str(f),
        })

    return {"checkpoints": checkpoints}


def _render_checkpoint(data: CheckpointData) -> str:
    """Render CheckpointData to markdown."""
    lines = [
        f"# {data.topic} — Session Checkpoint",
        "",
        f"> **Session Date:** {data.date}",
        f"> **Status:** {data.status}",
        f"> **Next Session:** {data.next_session}",
        "",
        "---",
        "",
    ]

    if data.accomplished:
        lines.append("## 1. What Was Accomplished")
        lines.append("")
        for item in data.accomplished:
            lines.append(f"- {item}")
        lines.append("")

    if data.changes:
        lines.append("## 2. What Changed")
        lines.append("")
        for item in data.changes:
            lines.append(f"- {item}")
        lines.append("")

    if data.next_actions:
        lines.append("## 3. What's Next")
        lines.append("")
        for i, item in enumerate(data.next_actions, 1):
            lines.append(f"{i}. {item}")
        lines.append("")

    if data.open_decisions:
        lines.append("## 4. Open Decisions")
        lines.append("")
        lines.append("| # | Question | Options | Impact |")
        lines.append("|---|----------|---------|--------|")
        for i, d in enumerate(data.open_decisions, 1):
            lines.append(f"| {i} | {d.get('question', '')} | {d.get('options', '')} | {d.get('impact', '')} |")
        lines.append("")

    if data.key_context:
        lines.append("## 5. Key Context")
        lines.append("")
        for item in data.key_context:
            lines.append(f"- {item}")
        lines.append("")

    if data.memory_updates:
        lines.append("## 6. Memory Updates")
        lines.append("")
        lines.append("| Memory File | Type | What Was Saved |")
        lines.append("|------------|------|---------------|")
        for m in data.memory_updates:
            lines.append(f"| {m.get('file', '')} | {m.get('type', '')} | {m.get('content', '')} |")
        lines.append("")

    return "\n".join(lines)


def _parse_checkpoint(content: str) -> dict:
    """Parse a checkpoint markdown file into structured data."""
    result: dict = {}

    # Extract header metadata
    title_match = re.search(r"^# (.+?) — Session Checkpoint", content, re.MULTILINE)
    if title_match:
        result["topic"] = title_match.group(1)

    date_match = re.search(r"\*\*Session Date:\*\*\s*(.+)", content)
    if date_match:
        result["date"] = date_match.group(1).strip()

    status_match = re.search(r"\*\*Status:\*\*\s*(.+)", content)
    if status_match:
        result["status"] = status_match.group(1).strip()

    next_match = re.search(r"\*\*Next Session:\*\*\s*(.+)", content)
    if next_match:
        result["next_session"] = next_match.group(1).strip()

    # Extract list sections
    result["accomplished"] = _extract_list_section(content, "What Was Accomplished")
    result["changes"] = _extract_list_section(content, "What Changed")
    result["next_actions"] = _extract_list_section(content, "What's Next")
    result["key_context"] = _extract_list_section(content, "Key Context")

    return result


def _extract_list_section(content: str, heading: str) -> list[str]:
    """Extract bullet/numbered items from a markdown section."""
    pattern = rf"## \d+\. {re.escape(heading)}\s*\n(.*?)(?=\n## |\n---|\Z)"
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return []

    items = []
    for line in match.group(1).strip().split("\n"):
        line = line.strip()
        cleaned = re.sub(r"^[\d]+\.\s*", "", line)
        cleaned = re.sub(r"^-\s*", "", cleaned)
        if cleaned:
            items.append(cleaned)
    return items
