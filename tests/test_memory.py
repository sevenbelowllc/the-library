"""Tests for the memory module."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from library_server.memory.scan import scan_memories
from library_server.memory.aggregate import aggregate_memories
from library_server.memory.prune import prune_stale


def test_scan_finds_all_memory_files(memory_dir: Path):
    """scan_memories should find all .md files except MEMORY.md index."""
    result = scan_memories(str(memory_dir), stale_threshold_days=30)
    assert len(result["entries"]) == 1
    assert result["entries"][0]["name"] == "Sample Project"


def test_scan_detects_stale_memories(tmp_path: Path):
    """scan_memories should flag memories with old modification dates."""
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "MEMORY.md").write_text("- [Old](old.md) — old memory\n")

    old_file = mem / "old.md"
    old_file.write_text(
        "---\nname: Old Memory\ndescription: Very old\ntype: project\n---\n\nOld content.\n"
    )
    # Touch with old timestamp (60 days ago)
    import os
    old_time = (datetime.now() - timedelta(days=60)).timestamp()
    os.utime(old_file, (old_time, old_time))

    result = scan_memories(str(mem), stale_threshold_days=30)
    assert result["entries"][0]["is_stale"] is True
    assert result["stale_count"] == 1


def test_scan_parses_frontmatter(memory_dir: Path):
    """scan_memories should extract frontmatter fields."""
    result = scan_memories(str(memory_dir), stale_threshold_days=30)
    entry = result["entries"][0]
    assert entry["memory_type"] == "project"
    assert entry["description"] == "A sample project memory for testing"


def test_scan_empty_directory(tmp_path: Path):
    """scan_memories on empty dir should return empty results."""
    mem = tmp_path / "empty"
    mem.mkdir()
    (mem / "MEMORY.md").write_text("")

    result = scan_memories(str(mem), stale_threshold_days=30)
    assert result["entries"] == []
    assert result["stale_count"] == 0


def test_aggregate_merges_related_memories(tmp_path: Path):
    """aggregate_memories should merge memories with same type and overlapping names."""
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "MEMORY.md").write_text(
        "- [Project A](project_a.md) — first note\n"
        "- [Project A Update](project_a_update.md) — second note\n"
    )
    (mem / "project_a.md").write_text(
        "---\nname: Project A\ndescription: First note about project A\ntype: project\n---\n\n"
        "Project A started on Monday.\n"
    )
    (mem / "project_a_update.md").write_text(
        "---\nname: Project A Update\ndescription: Update about project A\ntype: project\n---\n\n"
        "Project A now uses React.\n"
    )

    result = aggregate_memories(str(mem), dry_run=True)
    assert len(result["suggestions"]) >= 1
    assert result["suggestions"][0]["action"] == "merge"


def test_aggregate_dry_run_no_changes(tmp_path: Path):
    """aggregate_memories with dry_run=True should not modify files."""
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "MEMORY.md").write_text("- [A](a.md) — note\n- [B](b.md) — note\n")
    (mem / "a.md").write_text("---\nname: A\ndescription: About A\ntype: project\n---\n\nContent A.\n")
    (mem / "b.md").write_text("---\nname: B\ndescription: About B\ntype: feedback\n---\n\nContent B.\n")

    aggregate_memories(str(mem), dry_run=True)

    # Files should be unchanged
    assert (mem / "a.md").exists()
    assert (mem / "b.md").exists()


def test_prune_removes_stale_memories(tmp_path: Path):
    """prune_stale should remove memories flagged as stale."""
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "MEMORY.md").write_text("- [Stale](stale.md) — old stuff\n")

    stale_file = mem / "stale.md"
    stale_file.write_text(
        "---\nname: Stale Memory\ndescription: Old\ntype: project\n---\n\nOld content.\n"
    )
    import os
    old_time = (datetime.now() - timedelta(days=60)).timestamp()
    os.utime(stale_file, (old_time, old_time))

    result = prune_stale(str(mem), stale_threshold_days=30, dry_run=False)
    assert result["pruned_count"] == 1
    assert not stale_file.exists()


def test_prune_updates_index(tmp_path: Path):
    """prune_stale should remove entries from MEMORY.md index."""
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "MEMORY.md").write_text(
        "- [Keep](keep.md) — keep this\n"
        "- [Stale](stale.md) — remove this\n"
    )
    (mem / "keep.md").write_text(
        "---\nname: Keep\ndescription: Fresh\ntype: project\n---\n\nFresh.\n"
    )
    stale_file = mem / "stale.md"
    stale_file.write_text(
        "---\nname: Stale\ndescription: Old\ntype: project\n---\n\nOld.\n"
    )
    import os
    old_time = (datetime.now() - timedelta(days=60)).timestamp()
    os.utime(stale_file, (old_time, old_time))

    prune_stale(str(mem), stale_threshold_days=30, dry_run=False)

    index = (mem / "MEMORY.md").read_text()
    assert "keep.md" in index
    assert "stale.md" not in index


def test_prune_dry_run_no_changes(tmp_path: Path):
    """prune_stale with dry_run=True should not delete files."""
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "MEMORY.md").write_text("- [Stale](stale.md) — old\n")

    stale_file = mem / "stale.md"
    stale_file.write_text(
        "---\nname: Stale\ndescription: Old\ntype: project\n---\n\nOld.\n"
    )
    import os
    old_time = (datetime.now() - timedelta(days=60)).timestamp()
    os.utime(stale_file, (old_time, old_time))

    result = prune_stale(str(mem), stale_threshold_days=30, dry_run=True)
    assert result["pruned_count"] == 0
    assert len(result["candidates"]) == 1
    assert stale_file.exists()
