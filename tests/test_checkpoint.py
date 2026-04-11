"""Tests for the checkpoint module."""

from __future__ import annotations

from pathlib import Path

import pytest

from library_server.checkpoint.checkpoint import (
    write_checkpoint,
    read_checkpoint,
    list_checkpoints,
)
from library_server.types import CheckpointData


def test_write_checkpoint_creates_file(tmp_path: Path):
    """write_checkpoint should create a formatted markdown file."""
    data = CheckpointData(
        topic="test-feature",
        date="2026-04-10",
        status="In Progress",
        next_session="Continue with step 3",
        accomplished=["Completed step 1", "Completed step 2"],
        next_actions=["Do step 3", "Do step 4"],
        open_decisions=[{"question": "Use React or Vue?", "options": "React, Vue", "impact": "Frontend stack"}],
    )

    result = write_checkpoint(str(tmp_path), data)
    assert result["status"] == "written"
    assert Path(result["path"]).exists()

    content = Path(result["path"]).read_text()
    assert "test-feature" in content
    assert "Completed step 1" in content
    assert "Continue with step 3" in content


def test_write_checkpoint_filename_format(tmp_path: Path):
    """write_checkpoint should use YYYY-MM-DD-HH-MM-SS-<topic>-checkpoint.md format."""
    data = CheckpointData(
        topic="my-feature",
        date="2026-04-10",
        status="Done",
        next_session="N/A",
    )

    result = write_checkpoint(str(tmp_path), data)
    filename = Path(result["path"]).name
    assert filename == "2026-04-10-my-feature-checkpoint.md"


def test_read_checkpoint_roundtrip(tmp_path: Path):
    """read_checkpoint should parse what write_checkpoint wrote."""
    data = CheckpointData(
        topic="roundtrip-test",
        date="2026-04-10",
        status="Brainstorming",
        next_session="Resume at step 4",
        accomplished=["Did thing A"],
        next_actions=["Do thing B"],
        key_context=["Important: X depends on Y"],
    )

    write_result = write_checkpoint(str(tmp_path), data)
    read_result = read_checkpoint(write_result["path"])

    assert read_result["topic"] == "roundtrip-test"
    assert read_result["status"] == "Brainstorming"
    assert read_result["next_session"] == "Resume at step 4"
    assert "Did thing A" in read_result["accomplished"]


def test_list_checkpoints(tmp_path: Path):
    """list_checkpoints should return all checkpoint files sorted by date."""
    for topic in ["alpha", "beta"]:
        data = CheckpointData(topic=topic, date="2026-04-10", status="Done", next_session="N/A")
        write_checkpoint(str(tmp_path), data)

    result = list_checkpoints(str(tmp_path))
    assert len(result["checkpoints"]) == 2
    assert all("topic" in cp for cp in result["checkpoints"])


def test_list_checkpoints_empty(tmp_path: Path):
    """list_checkpoints on empty dir should return empty list."""
    result = list_checkpoints(str(tmp_path))
    assert result["checkpoints"] == []
