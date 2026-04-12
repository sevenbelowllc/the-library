"""SessionStart hook script for the MMU.

Invoked by Claude Code on session start (SessionStart hook event).
Reads PROJECT-STATE.md and SESSION.md, combines them into a compact
context string, and outputs it as additionalContext JSON.

Usage (Claude Code hook):
    python -m library_server.hooks.scripts.session_start

Stdin JSON fields:
    session_id   -- opaque session identifier
    mode         -- "startup" | "resume" | "compact" | "clear"
    reading_room -- path to the Reading Room directory containing PROJECT-STATE.md
    sessions_dir -- path to the sessions directory containing SESSION.md

Stdout JSON:
    {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": <str>}}
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from library_server.state.project_state import parse_project_state
from library_server.state.session_state import parse_session_state

# Character budget: ~4000 chars / ~800 tokens
_BUDGET = 4000


def _read_project_state(reading_room: Path) -> str:
    """Return a compact CRITICAL-tier string from PROJECT-STATE.md."""
    path = reading_room / "PROJECT-STATE.md"
    if not path.is_file():
        return ""

    try:
        data = parse_project_state(path)
    except Exception:
        return ""

    parts: list[str] = ["## PROJECT STATE"]
    parts.append(f"Project: {data.project}")
    if data.focus:
        parts.append(f"Focus: {data.focus}")
    if data.active_task:
        parts.append(f"Task: {data.active_task}")
    if data.blockers:
        parts.append("Blockers:")
        for b in data.blockers:
            parts.append(f"  - {b}")
    if data.invariants:
        parts.append("Invariants:")
        for inv in data.invariants[:5]:  # cap at 5
            parts.append(f"  - {inv}")
    if data.recent_decisions:
        parts.append("Recent Decisions:")
        for d in data.recent_decisions[:3]:
            parts.append(f"  - {d.get('id', '')}: {d.get('decision', '')}")
    return "\n".join(parts)


def _read_session_state(sessions_dir: Path) -> str:
    """Return a compact FRESH-tier string from SESSION.md."""
    path = sessions_dir / "SESSION.md"
    if not path.is_file():
        return ""

    try:
        data = parse_session_state(path)
    except Exception:
        return ""

    parts: list[str] = ["## SESSION STATE"]
    if data.task:
        parts.append(f"Task: {data.task}")
    if data.doing:
        parts.append(f"Doing: {data.doing}")
    if data.branch and data.branch != "main":
        parts.append(f"Branch: {data.branch}")
    if data.turns:
        parts.append(f"Turns: {data.turns}")
    if data.resume_instructions:
        parts.append("Resume:")
        for r in data.resume_instructions[:5]:
            parts.append(f"  - {r}")
    if data.decisions:
        parts.append("Decisions:")
        for d in data.decisions[:3]:
            parts.append(f"  - {d}")
    if data.files_touched:
        parts.append("Files Touched:")
        for f in data.files_touched[:5]:
            parts.append(f"  - {f}")
    return "\n".join(parts)


def _archive_session(sessions_dir: Path) -> None:
    """Move SESSION.md to SESSION-<timestamp>.md for archival."""
    path = sessions_dir / "SESSION.md"
    if not path.is_file():
        return
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = sessions_dir / f"SESSION-{timestamp}.md"
    shutil.copy2(str(path), str(archive_path))


def build_session_context(mode: str, reading_room: Path, sessions_dir: Path) -> str:
    """Build a combined session context string for Claude Code injection.

    Parameters
    ----------
    mode:
        One of "startup", "resume", "compact", or "clear".
    reading_room:
        Directory containing PROJECT-STATE.md.
    sessions_dir:
        Directory containing SESSION.md.

    Returns
    -------
    str
        Combined context string, guaranteed to be under ~4000 chars.
    """
    if mode == "clear":
        _archive_session(sessions_dir)

    project_section = _read_project_state(reading_room)
    session_section = _read_session_state(sessions_dir)

    sections: list[str] = []
    if project_section:
        sections.append(project_section)
    if session_section:
        sections.append(session_section)

    context = "\n\n".join(sections)

    # Truncate to budget if needed (rare but defensive)
    if len(context) > _BUDGET:
        context = context[:_BUDGET - 3] + "..."

    return context


def main() -> None:
    """Entry point: read JSON from stdin, write JSON to stdout."""
    raw = sys.stdin.read()
    data = json.loads(raw) if raw.strip() else {}

    mode = data.get("mode", "startup")
    reading_room = Path(data["reading_room"]) if "reading_room" in data else Path(".")
    sessions_dir = Path(data["sessions_dir"]) if "sessions_dir" in data else Path(".")

    context = build_session_context(mode, reading_room, sessions_dir)

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }
    sys.stdout.write(json.dumps(output) + "\n")


if __name__ == "__main__":
    main()
