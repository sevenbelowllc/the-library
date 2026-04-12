"""Decision capture — extract and persist decision-signal messages from transcripts.

Reads a Claude Code ``.jsonl`` transcript, identifies messages that contain
decision-signal language (via :func:`extract_decision_patterns`), and writes
each matched message as a numbered decision file.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from textwrap import dedent

from library_server.hooks.transcript import extract_decision_patterns


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def capture_decisions_from_transcript(
    transcript_path: Path, decisions_dir: Path
) -> list[str]:
    """Extract decisions from *transcript_path* and write decision files.

    Parameters
    ----------
    transcript_path:
        Path to a Claude Code ``.jsonl`` transcript file.
    decisions_dir:
        Directory where decision ``.md`` files will be written.

    Returns
    -------
    list[str]
        File names (not full paths) of the decision files that were created.
        Returns an empty list when the transcript is absent or contains no
        decision-signal messages.
    """
    decisions = extract_decision_patterns(transcript_path)
    if not decisions:
        return []

    decisions_dir.mkdir(parents=True, exist_ok=True)

    next_id = _next_decision_id(decisions_dir)
    today = date.today().isoformat()
    created: list[str] = []

    for text in decisions:
        slug = _slugify(text, max_chars=50)
        filename = f"{next_id:03d}-{slug}.md"
        file_path = decisions_dir / filename

        file_path.write_text(
            _render_decision_file(next_id, text, today),
            encoding="utf-8",
        )
        created.append(filename)
        next_id += 1

    return created


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _next_decision_id(decisions_dir: Path) -> int:
    """Return the next available decision ID (1-based, continuing from existing files)."""
    existing = list(decisions_dir.glob("*.md"))
    if not existing:
        return 1

    max_id = 0
    for f in existing:
        # Expect filenames like 001-some-slug.md
        match = re.match(r"^(\d+)-", f.stem)
        if match:
            candidate = int(match.group(1))
            if candidate > max_id:
                max_id = candidate

    return max_id + 1


def _slugify(text: str, max_chars: int = 50) -> str:
    """Convert *text* to a URL-safe slug of at most *max_chars* characters."""
    slug = text.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    return slug[:max_chars].rstrip("-")


def _render_decision_file(decision_id: int, text: str, today: str) -> str:
    """Render the markdown content for a decision file."""
    title = text[:80] if len(text) <= 80 else text[:77] + "..."

    return dedent(f"""\
        ---
        id: {decision_id}
        title: {title}
        date: {today}
        status: draft
        domain:
        references: []
        ---

        ## Decision
        {text}

        ## Context
        Extracted from session transcript.

        ## Rationale
        (To be filled during maintenance pass)
    """)
