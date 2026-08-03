"""PreCompact hook script — archive transcript to vault before context compaction.

Reads stdin JSON from Claude Code's PreCompact hook, copies the current
transcript to vault_transcripts_dir, and exits with no stdout output
(zero tokens emitted back to Claude).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from library_server.redaction import redact


def process_pre_compact(
    transcript_path: Path,
    vault_transcripts_dir: Path,
    sessions_dir: Path,
    session_id: str,
) -> dict:
    """Archive the transcript file to vault before compaction.

    Parameters
    ----------
    transcript_path:
        Path to the current JSONL transcript file.
    vault_transcripts_dir:
        Destination directory for archived transcripts.
    sessions_dir:
        Directory where session state files live (unused directly here,
        kept for API symmetry with other hook scripts).
    session_id:
        Unique identifier for this session, used in the archive filename.

    Returns
    -------
    dict
        ``{"saved": True, "archive_path": str}`` on success,
        ``{"saved": False}`` if the transcript does not exist.
    """
    if not transcript_path.exists():
        return {"saved": False}

    vault_transcripts_dir.mkdir(parents=True, exist_ok=True)

    date_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dest_name = f"{date_prefix}-{session_id}.jsonl"
    dest = vault_transcripts_dir / dest_name

    # Redact line-by-line: transcripts may contain pasted secrets, and the
    # vault is a long-lived, ingested store. redact() preserves line structure
    # (JSONL stays one object per line) since patterns never match newlines.
    with open(transcript_path, encoding="utf-8", errors="replace") as src, \
            open(dest, "w", encoding="utf-8") as out:
        for line in src:
            out.write(redact(line))

    return {"saved": True, "archive_path": str(dest)}


def main() -> None:
    """Entry point — reads stdin JSON, archives transcript, emits no stdout."""
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        payload = {}

    transcript_path = Path(payload.get("transcript_path", ""))
    vault_transcripts_dir = Path(
        payload.get("vault_transcripts_dir", "~/.library/vault/transcripts")
    ).expanduser()
    sessions_dir = Path(
        payload.get("sessions_dir", "~/.library/sessions")
    ).expanduser()
    session_id = payload.get("session_id", "unknown")

    process_pre_compact(
        transcript_path=transcript_path,
        vault_transcripts_dir=vault_transcripts_dir,
        sessions_dir=sessions_dir,
        session_id=session_id,
    )
    # No stdout — zero tokens returned to Claude


if __name__ == "__main__":
    main()
