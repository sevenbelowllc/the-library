"""Memory aggregation — merge related memories, consolidate index."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import yaml


def aggregate_memories(memory_path: str, dry_run: bool = True) -> dict:
    """Analyze memory files for merge opportunities.

    Groups memories by type, then checks for overlapping names/descriptions.
    With dry_run=True, returns suggestions without modifying files.

    Returns:
        {
            "suggestions": [{"action": "merge", "files": [...], "reason": str}, ...],
            "applied": bool,
        }
    """
    path = Path(memory_path)
    suggestions: list[dict] = []

    # Group by type
    by_type: dict[str, list[dict]] = defaultdict(list)
    for md_file in sorted(path.glob("*.md")):
        if md_file.name == "MEMORY.md":
            continue
        frontmatter = _parse_frontmatter(md_file)
        if frontmatter:
            by_type[frontmatter.get("type", "unknown")].append({
                "file": md_file,
                "frontmatter": frontmatter,
                "content": md_file.read_text(encoding="utf-8"),
            })

    # Find merge candidates within each type
    for memory_type, entries in by_type.items():
        if len(entries) < 2:
            continue
        for i, a in enumerate(entries):
            for b in entries[i + 1:]:
                if _are_related(a["frontmatter"], b["frontmatter"]):
                    suggestions.append({
                        "action": "merge",
                        "files": [str(a["file"].name), str(b["file"].name)],
                        "reason": f"Same type ({memory_type}), related names: "
                                  f"'{a['frontmatter'].get('name', '')}' and "
                                  f"'{b['frontmatter'].get('name', '')}'",
                    })

    return {"suggestions": suggestions, "applied": not dry_run and len(suggestions) > 0}


def _are_related(a: dict, b: dict) -> bool:
    """Check if two memory frontmatters describe related content."""
    name_a = a.get("name", "").lower()
    name_b = b.get("name", "").lower()

    # Check if one name contains the other
    if name_a in name_b or name_b in name_a:
        return True

    # Check word overlap (>50% shared words)
    words_a = set(name_a.split())
    words_b = set(name_b.split())
    if words_a and words_b:
        overlap = len(words_a & words_b) / min(len(words_a), len(words_b))
        if overlap > 0.5:
            return True

    return False


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
