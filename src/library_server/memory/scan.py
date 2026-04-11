"""Memory scanning — staleness detection, frontmatter parsing."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

import yaml


def scan_memories(memory_path: str, stale_threshold_days: int = 30) -> dict:
    """Scan memory files for staleness and extract metadata.

    Reads all .md files except the index (MEMORY.md).
    Flags files not modified within stale_threshold_days.

    Returns:
        {
            "entries": [{"name", "description", "memory_type", "file_path", "is_stale", "modified"}, ...],
            "stale_count": int,
            "total_count": int,
        }
    """
    path = Path(memory_path)
    entries: list[dict] = []
    stale_count = 0
    threshold = datetime.now() - timedelta(days=stale_threshold_days)

    for md_file in sorted(path.glob("*.md")):
        if md_file.name == "MEMORY.md":
            continue

        frontmatter = _parse_frontmatter(md_file)
        if not frontmatter:
            continue

        modified = datetime.fromtimestamp(os.path.getmtime(md_file))
        is_stale = modified < threshold

        if is_stale:
            stale_count += 1

        entries.append({
            "name": frontmatter.get("name", md_file.stem),
            "description": frontmatter.get("description", ""),
            "memory_type": frontmatter.get("type", "unknown"),
            "file_path": str(md_file),
            "is_stale": is_stale,
            "modified": modified.isoformat(),
        })

    return {
        "entries": entries,
        "stale_count": stale_count,
        "total_count": len(entries),
    }


def _parse_frontmatter(file_path: Path) -> dict:
    """Extract YAML frontmatter from a memory file."""
    content = file_path.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}
