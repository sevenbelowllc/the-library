"""Hook infrastructure: Claude Code JSONL transcript parser.

Provides utilities for reading and analysing transcript files produced by
Claude Code hooks (one JSON object per line).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Tools whose ``input.file_path`` we care about
_FILE_TOOLS = frozenset({"Read", "Write", "Edit"})

# Decision-signal patterns (matched against user message text)
_DECISION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"let\s*'?s\s+go\s+with", re.IGNORECASE),
    re.compile(r"\bagreed\b", re.IGNORECASE),
    re.compile(r"\bconfirmed\b", re.IGNORECASE),
    re.compile(r"\blocked\b", re.IGNORECASE),
    re.compile(r"the\s+decision\s+is", re.IGNORECASE),
    re.compile(r"\bno,\s+use\b.+instead", re.IGNORECASE),
]


def _iter_entries(path: Path):
    """Yield parsed JSON objects from a JSONL file, skipping blank lines.

    Returns an empty iterator if the file does not exist.
    """
    if not path.is_file():
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    pass


def read_transcript_tail(path: Path, n: int = 10) -> list[dict]:
    """Return the last *n* entries from a JSONL transcript.

    Parameters
    ----------
    path:
        Path to the ``.jsonl`` transcript file.
    n:
        Number of tail entries to return (default 10).

    Returns
    -------
    list[dict]
        Up to *n* most-recent entries; empty list if the file is absent or empty.
    """
    entries = list(_iter_entries(path))
    return entries[-n:] if entries else []


def extract_files_from_transcript(path: Path) -> list[str]:
    """Extract unique file paths touched by Read/Write/Edit tool calls.

    Parameters
    ----------
    path:
        Path to the ``.jsonl`` transcript file.

    Returns
    -------
    list[str]
        Deduplicated file paths in the order first encountered.
    """
    seen: dict[str, None] = {}  # insertion-ordered set
    for entry in _iter_entries(path):
        if entry.get("type") != "tool_use":
            continue
        if entry.get("name") not in _FILE_TOOLS:
            continue
        file_path = entry.get("input", {}).get("file_path")
        if file_path and file_path not in seen:
            seen[file_path] = None
    return list(seen)


def extract_decision_patterns(path: Path) -> list[str]:
    """Return user messages that contain decision-signal language.

    Scans user-role messages only; ignores assistant messages and other
    entry types.  Case-insensitive matching.

    Parameters
    ----------
    path:
        Path to the ``.jsonl`` transcript file.

    Returns
    -------
    list[str]
        Message texts that matched one or more decision patterns.
    """
    results: list[str] = []
    for entry in _iter_entries(path):
        if entry.get("type") != "message":
            continue
        if entry.get("role") != "user":
            continue
        content = entry.get("content", "")
        if not isinstance(content, str):
            continue
        for pattern in _DECISION_PATTERNS:
            if pattern.search(content):
                results.append(content)
                break  # only add message once even if multiple patterns match
    return results
