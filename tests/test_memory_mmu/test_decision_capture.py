"""Tests for decision_capture module — TDD first pass."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml


from library_server.memory.decision_capture import capture_decisions_from_transcript


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, entries: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(e) for e in entries) + "\n",
        encoding="utf-8",
    )


def _parse_frontmatter(md_text: str) -> dict:
    if not md_text.startswith("---"):
        return {}
    end = md_text.index("---", 3)
    return yaml.safe_load(md_text[3:end])


def _user_message(content: str) -> dict:
    return {"type": "message", "role": "user", "content": content}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_missing_transcript_returns_empty_list(tmp_path: Path):
    """capture_decisions_from_transcript returns [] when transcript does not exist."""
    transcript = tmp_path / "nonexistent.jsonl"
    decisions_dir = tmp_path / "decisions"

    result = capture_decisions_from_transcript(transcript, decisions_dir)

    assert result == []


def test_no_decision_patterns_returns_empty_list(tmp_path: Path):
    """Transcript with no decision-signal messages returns []."""
    transcript = tmp_path / "session.jsonl"
    decisions_dir = tmp_path / "decisions"

    _write_jsonl(transcript, [
        _user_message("Can you help me fix this bug?"),
        _user_message("What does this function do?"),
    ])

    result = capture_decisions_from_transcript(transcript, decisions_dir)

    assert result == []


def test_lets_go_with_creates_decision_file(tmp_path: Path):
    """\"let's go with X\" pattern creates a decision file."""
    transcript = tmp_path / "session.jsonl"
    decisions_dir = tmp_path / "decisions"

    _write_jsonl(transcript, [
        _user_message("Let's go with PostgreSQL for the database."),
    ])

    result = capture_decisions_from_transcript(transcript, decisions_dir)

    assert len(result) >= 1
    assert decisions_dir.is_dir()
    # At least one decision file should exist
    decision_files = list(decisions_dir.glob("*.md"))
    assert len(decision_files) >= 1


def test_confirmed_creates_decision_file(tmp_path: Path):
    """\"confirmed Y\" pattern creates a decision file."""
    transcript = tmp_path / "session.jsonl"
    decisions_dir = tmp_path / "decisions"

    _write_jsonl(transcript, [
        _user_message("confirmed we'll use Clerk for authentication"),
    ])

    result = capture_decisions_from_transcript(transcript, decisions_dir)

    assert len(result) >= 1


def test_two_decision_messages_create_two_files(tmp_path: Path):
    """Two decision-signal messages produce 2 decision files."""
    transcript = tmp_path / "session.jsonl"
    decisions_dir = tmp_path / "decisions"

    _write_jsonl(transcript, [
        _user_message("Let's go with Express for the server."),
        _user_message("confirmed we'll use PostgreSQL for storage"),
    ])

    result = capture_decisions_from_transcript(transcript, decisions_dir)

    assert len(result) >= 2
    decision_files = list(decisions_dir.glob("*.md"))
    assert len(decision_files) >= 2


def test_decision_file_has_valid_frontmatter(tmp_path: Path):
    """Decision file should have required YAML frontmatter fields."""
    transcript = tmp_path / "session.jsonl"
    decisions_dir = tmp_path / "decisions"

    _write_jsonl(transcript, [
        _user_message("Let's go with TypeScript for all modules."),
    ])

    capture_decisions_from_transcript(transcript, decisions_dir)

    files = sorted(decisions_dir.glob("*.md"))
    assert len(files) >= 1

    fm = _parse_frontmatter(files[0].read_text(encoding="utf-8"))
    assert "id" in fm
    assert "title" in fm
    assert "date" in fm
    assert fm["status"] == "draft"
    assert "domain" in fm
    assert "references" in fm


def test_decision_file_numbered_sequentially(tmp_path: Path):
    """Files should be named NNN-slug.md with sequential numbering."""
    transcript = tmp_path / "session.jsonl"
    decisions_dir = tmp_path / "decisions"

    _write_jsonl(transcript, [
        _user_message("Let's go with option A."),
        _user_message("confirmed option B is better"),
    ])

    capture_decisions_from_transcript(transcript, decisions_dir)

    files = sorted(decisions_dir.glob("*.md"))
    assert len(files) >= 2

    # Each filename should start with digits
    for f in files:
        parts = f.stem.split("-", 1)
        assert parts[0].isdigit(), f"Expected numeric prefix, got: {f.name}"


def test_decision_file_numbering_continues_from_existing(tmp_path: Path):
    """If decisions already exist, numbering continues from max ID + 1."""
    transcript = tmp_path / "session.jsonl"
    decisions_dir = tmp_path / "decisions"
    decisions_dir.mkdir(parents=True, exist_ok=True)

    # Pre-create two decision files
    (decisions_dir / "001-first-decision.md").write_text(
        "---\nid: 1\ntitle: First\ndate: 2026-01-01\nstatus: draft\ndomain: \nreferences: []\n---\n",
        encoding="utf-8",
    )
    (decisions_dir / "002-second-decision.md").write_text(
        "---\nid: 2\ntitle: Second\ndate: 2026-01-01\nstatus: draft\ndomain: \nreferences: []\n---\n",
        encoding="utf-8",
    )

    _write_jsonl(transcript, [
        _user_message("Let's go with the third approach."),
    ])

    capture_decisions_from_transcript(transcript, decisions_dir)

    files = sorted(decisions_dir.glob("*.md"))
    assert len(files) == 3

    # The new file should be 003-...
    new_files = [f for f in files if not f.name.startswith("001") and not f.name.startswith("002")]
    assert len(new_files) == 1
    assert new_files[0].name.startswith("003")


def test_decision_file_has_markdown_body(tmp_path: Path):
    """Decision file should have ## Decision and ## Context sections."""
    transcript = tmp_path / "session.jsonl"
    decisions_dir = tmp_path / "decisions"

    _write_jsonl(transcript, [
        _user_message("Let's go with GraphQL over REST."),
    ])

    capture_decisions_from_transcript(transcript, decisions_dir)

    files = sorted(decisions_dir.glob("*.md"))
    body = files[0].read_text(encoding="utf-8")

    assert "## Decision" in body
    assert "## Context" in body
    assert "## Rationale" in body


def test_title_truncated_to_80_chars(tmp_path: Path):
    """Title in frontmatter should be at most 80 characters."""
    transcript = tmp_path / "session.jsonl"
    decisions_dir = tmp_path / "decisions"

    long_decision = "Let's go with " + "a" * 100 + " as our approach for everything"
    _write_jsonl(transcript, [_user_message(long_decision)])

    capture_decisions_from_transcript(transcript, decisions_dir)

    files = sorted(decisions_dir.glob("*.md"))
    fm = _parse_frontmatter(files[0].read_text(encoding="utf-8"))
    assert len(fm["title"]) <= 80


def test_decisions_dir_created_if_missing(tmp_path: Path):
    """decisions_dir should be created automatically if it does not exist."""
    transcript = tmp_path / "session.jsonl"
    decisions_dir = tmp_path / "new" / "nested" / "decisions"

    _write_jsonl(transcript, [
        _user_message("Let's go with option Z."),
    ])

    capture_decisions_from_transcript(transcript, decisions_dir)

    assert decisions_dir.is_dir()


def test_returns_list_of_file_name_strings(tmp_path: Path):
    """Return value should be a list of created file name strings."""
    transcript = tmp_path / "session.jsonl"
    decisions_dir = tmp_path / "decisions"

    _write_jsonl(transcript, [
        _user_message("Let's go with the agreed approach."),
    ])

    result = capture_decisions_from_transcript(transcript, decisions_dir)

    assert isinstance(result, list)
    for item in result:
        assert isinstance(item, str)
        assert item.endswith(".md")
