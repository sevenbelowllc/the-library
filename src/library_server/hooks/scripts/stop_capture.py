"""Stop hook script for the MMU.

Invoked by Claude Code at session stop (Stop hook event).
Updates SESSION.md with files touched and decisions made, checks context
usage, and returns a checkpoint warning if usage is approaching limits.

Usage (Claude Code hook):
    python -m library_server.hooks.scripts.stop_capture

Stdin JSON fields:
    session_id          -- opaque session identifier
    sessions_dir        -- path to the sessions directory containing SESSION.md
    transcript_path     -- path to the Claude Code JSONL transcript file
    context_usage_path  -- path to a JSON file with {"context_usage": <float>}
    journal_path        -- path to the routing JSONL journal

Stdout JSON (when warning exists):
    {"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": <str>}}

Stdout (no warning):
    <empty>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from library_server.hooks.transcript import (
    extract_files_from_transcript,
    extract_decision_patterns,
)
from library_server.state.session_state import update_session_turn


def _read_context_usage(context_usage_path: Path) -> float:
    """Read context_usage float from a state file.

    Accepts either a bare float (e.g. ``23.0``) or a JSON object
    (e.g. ``{"context_usage": 23.0}``). Returns 0.0 if the file is
    missing or unreadable.
    """
    if not context_usage_path.is_file():
        return 0.0
    try:
        raw = context_usage_path.read_text(encoding="utf-8").strip()
        data = json.loads(raw)
        if isinstance(data, (int, float)):
            # Bare float written by status_line.py
            return float(data) / 100.0  # stored as percentage, normalize to 0-1
        return float(data.get("context_usage", 0.0))
    except (json.JSONDecodeError, ValueError, TypeError):
        return 0.0


def _build_warning(context_usage: float, warn_pct: int, checkpoint_pct: int) -> str | None:
    """Return a warning string based on context usage thresholds.

    Parameters
    ----------
    context_usage:
        Fractional context usage (0.0–1.0).
    warn_pct:
        Percentage threshold (0–100) at which to start warning.
    checkpoint_pct:
        Percentage threshold (0–100) at which to warn about auto-checkpoint.

    Returns
    -------
    str | None
        Warning string if threshold exceeded, else None.
    """
    pct = context_usage * 100.0
    if pct >= checkpoint_pct:
        return (
            f"Context usage is at {pct:.0f}% — approaching auto-checkpoint threshold. "
            "Consider running /checkpoint now to capture session state before compaction."
        )
    if pct >= warn_pct:
        return (
            f"Context usage is at {pct:.0f}%. "
            "Consider checkpointing soon to preserve session state."
        )
    return None


def process_stop(
    sessions_dir: Path,
    transcript_path: Path,
    context_usage_path: Path,
    journal_path: Path,
    warn_pct: int = 50,
    checkpoint_pct: int = 60,
) -> dict:
    """Process the Stop hook: update SESSION.md and optionally emit a warning.

    Parameters
    ----------
    sessions_dir:
        Directory containing SESSION.md.
    transcript_path:
        Path to the JSONL transcript file.
    context_usage_path:
        Path to JSON file with ``{"context_usage": <float>}``.
    journal_path:
        Path to the JSONL routing journal (reserved for future use).
    warn_pct:
        Percentage at which to emit a warning (default 50).
    checkpoint_pct:
        Percentage at which to emit an auto-checkpoint warning (default 60).

    Returns
    -------
    dict
        ``{"warning": <str | None>}``
    """
    session_md = sessions_dir / "SESSION.md"
    context_usage = _read_context_usage(context_usage_path)

    # Extract data from transcript
    new_files = extract_files_from_transcript(transcript_path)
    decision_messages = extract_decision_patterns(transcript_path)
    new_decision = decision_messages[0] if decision_messages else None

    # Update SESSION.md if it exists
    if session_md.is_file():
        try:
            update_session_turn(
                path=session_md,
                context_usage=context_usage,
                doing="",  # empty string preserves existing value in update_session_turn
                new_files=new_files,
                new_decision=new_decision,
                new_domain=None,
            )
        except Exception as exc:
            print(f"[library] stop_capture: failed to update SESSION.md: {exc}", file=sys.stderr)

    warning = _build_warning(context_usage, warn_pct, checkpoint_pct)
    return {"warning": warning}


def main() -> None:
    """Entry point: read JSON from stdin, write JSON to stdout or stay silent."""
    raw = sys.stdin.read()
    data = json.loads(raw) if raw.strip() else {}

    sessions_dir = Path(data["sessions_dir"]) if "sessions_dir" in data else Path(".")
    transcript_path = Path(data["transcript_path"]) if "transcript_path" in data else Path("/dev/null")
    context_usage_path = Path(data["context_usage_path"]) if "context_usage_path" in data else Path("/dev/null")
    journal_path = Path(data.get("journal_path", "/tmp/routing.jsonl"))

    result = process_stop(
        sessions_dir=sessions_dir,
        transcript_path=transcript_path,
        context_usage_path=context_usage_path,
        journal_path=journal_path,
    )

    if result["warning"] is None:
        # Silent exit — no output
        return

    output = {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": result["warning"],
        }
    }
    sys.stdout.write(json.dumps(output) + "\n")


if __name__ == "__main__":
    main()
