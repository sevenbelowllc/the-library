"""SessionEnd hook script — archive SESSION.md and increment session_count.

Reads stdin JSON from Claude Code's stop/session-end hook, archives
SESSION.md to vault_sessions_dir, and increments session_count in
PROJECT-STATE.md. Emits no stdout output (zero tokens back to Claude).
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from library_server.state.project_state import parse_project_state, update_project_state_field
from library_server.state.session_state import parse_session_state


def process_session_end(
    reading_room: Path,
    sessions_dir: Path,
    vault_sessions_dir: Path,
    session_id: str,
) -> dict:
    """Archive SESSION.md and update PROJECT-STATE.md at session end.

    Parameters
    ----------
    reading_room:
        Directory containing SESSION.md and PROJECT-STATE.md.
    sessions_dir:
        Directory where runtime session state files live (unused directly
        here, kept for API symmetry).
    vault_sessions_dir:
        Destination directory for archived session files.
    session_id:
        Unique identifier for this session, used in the archive filename.

    Returns
    -------
    dict
        ``{"archived": True}`` on success,
        ``{"archived": False}`` if SESSION.md does not exist.
    """
    session_file = reading_room / "SESSION.md"

    if not session_file.exists():
        return {"archived": False}

    # Determine date prefix — prefer the `started` field from SESSION.md
    try:
        session_data = parse_session_state(session_file)
        started = session_data.started
        # started is ISO-8601 like "2026-04-11T10:00:00Z"; take the date part
        date_prefix = started[:10] if started and len(started) >= 10 else None
    except Exception:
        date_prefix = None

    if not date_prefix:
        date_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    vault_sessions_dir.mkdir(parents=True, exist_ok=True)

    dest_name = f"{date_prefix}-{session_id}-session.md"
    dest = vault_sessions_dir / dest_name
    shutil.copy2(session_file, dest)

    # Increment session_count in PROJECT-STATE.md (if it exists)
    project_state_file = reading_room / "PROJECT-STATE.md"
    if project_state_file.exists():
        try:
            state = parse_project_state(project_state_file)
            update_project_state_field(
                project_state_file, "session_count", state.session_count + 1
            )
        except Exception:
            pass  # Non-fatal — archiving is the primary goal

    return {"archived": True}


def main() -> None:
    """Entry point — reads stdin JSON, archives session, emits no stdout."""
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        payload = {}

    reading_room = Path(payload.get("reading_room", ".")).expanduser()
    sessions_dir = Path(
        payload.get("sessions_dir", "~/.library/sessions")
    ).expanduser()
    vault_sessions_dir = Path(
        payload.get("vault_sessions_dir", "~/.library/vault/sessions")
    ).expanduser()
    session_id = payload.get("session_id", "unknown")

    process_session_end(
        reading_room=reading_room,
        sessions_dir=sessions_dir,
        vault_sessions_dir=vault_sessions_dir,
        session_id=session_id,
    )
    # No stdout — zero tokens returned to Claude


if __name__ == "__main__":
    main()
