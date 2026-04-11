"""Memory pruning — remove stale entries, update index."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

import yaml


def prune_stale(
    memory_path: str,
    stale_threshold_days: int = 30,
    dry_run: bool = True,
) -> dict:
    """Remove memory files older than stale_threshold_days.

    Updates MEMORY.md index to remove references to pruned files.

    Args:
        memory_path: Path to memory directory.
        stale_threshold_days: Files not modified in this many days are candidates.
        dry_run: If True, report candidates without deleting.

    Returns:
        {"pruned_count": int, "candidates": [str, ...]}
    """
    path = Path(memory_path)
    threshold = datetime.now() - timedelta(days=stale_threshold_days)
    candidates: list[str] = []
    pruned_count = 0

    for md_file in sorted(path.glob("*.md")):
        if md_file.name == "MEMORY.md":
            continue

        modified = datetime.fromtimestamp(os.path.getmtime(md_file))
        if modified < threshold:
            candidates.append(md_file.name)
            if not dry_run:
                md_file.unlink()
                pruned_count += 1

    if not dry_run and pruned_count > 0:
        _update_index(path, candidates)

    return {"pruned_count": pruned_count, "candidates": candidates}


def _update_index(memory_path: Path, removed_files: list[str]) -> None:
    """Remove entries for deleted files from MEMORY.md."""
    index_path = memory_path / "MEMORY.md"
    if not index_path.exists():
        return

    lines = index_path.read_text(encoding="utf-8").split("\n")
    filtered = [
        line for line in lines
        if not any(f"({fname})" in line for fname in removed_files)
    ]
    index_path.write_text("\n".join(filtered), encoding="utf-8")
