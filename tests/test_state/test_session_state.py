"""Tests for session_state.py — TDD first pass."""

from __future__ import annotations

from pathlib import Path

import pytest

from library_server.state.session_state import (
    render_session_state,
    parse_session_state,
    update_session_turn,
)
from library_server.types import SessionStateData


@pytest.fixture
def empty_session() -> SessionStateData:
    return SessionStateData(
        session_id="sess-001",
        started="2026-04-11T09:00:00Z",
        last_updated="2026-04-11T09:00:00Z",
    )


@pytest.fixture
def full_session() -> SessionStateData:
    return SessionStateData(
        session_id="sess-042",
        task="CLO-42 — MMU state file management",
        doing="Writing tests for project_state.py",
        branch="feat/mmu-state",
        resume_instructions=[
            "Continue from test_parse_roundtrip",
            "Run pytest tests/test_state/ to verify",
        ],
        decisions=["Use YAML frontmatter for metadata", "Render stays under 100 lines"],
        files_touched=[
            "src/library_server/state/project_state.py",
            "tests/test_state/test_project_state.py",
        ],
        domains_loaded=["mmu", "checkpoint"],
        turns=5,
        context_usage=0.34,
        started="2026-04-11T09:00:00Z",
        last_updated="2026-04-11T10:30:00Z",
    )


# ── Render tests ──────────────────────────────────────────────────────────────


def test_render_contains_session_id(full_session: SessionStateData):
    output = render_session_state(full_session)
    assert "sess-042" in output


def test_render_contains_yaml_frontmatter(full_session: SessionStateData):
    output = render_session_state(full_session)
    assert output.startswith("---")
    assert "session_id: sess-042" in output
    assert "turns: 5" in output
    assert "context_usage: 0.34" in output


def test_render_contains_current_section(full_session: SessionStateData):
    output = render_session_state(full_session)
    assert "Current" in output
    assert "CLO-42" in output
    assert "Writing tests" in output
    assert "feat/mmu-state" in output


def test_render_contains_resume_section(full_session: SessionStateData):
    output = render_session_state(full_session)
    assert "Resume" in output
    assert "Continue from test_parse_roundtrip" in output
    assert "Run pytest" in output


def test_render_contains_files_touched(full_session: SessionStateData):
    output = render_session_state(full_session)
    assert "Files Touched" in output
    assert "project_state.py" in output


def test_render_contains_decisions(full_session: SessionStateData):
    output = render_session_state(full_session)
    assert "Decisions" in output
    assert "YAML frontmatter" in output


def test_render_contains_domains_loaded(full_session: SessionStateData):
    output = render_session_state(full_session)
    assert "Domains" in output
    assert "mmu" in output
    assert "checkpoint" in output


def test_render_empty_session(empty_session: SessionStateData):
    """Empty session should render without errors."""
    output = render_session_state(empty_session)
    assert "sess-001" in output
    # Empty lists should not cause errors
    assert output  # non-empty


# ── Parse tests ───────────────────────────────────────────────────────────────


def test_parse_roundtrip_full(tmp_path: Path, full_session: SessionStateData):
    """render → write → parse should recover all fields."""
    state_file = tmp_path / "SESSION.md"
    state_file.write_text(render_session_state(full_session), encoding="utf-8")

    parsed = parse_session_state(state_file)

    assert parsed.session_id == full_session.session_id
    assert parsed.task == full_session.task
    assert parsed.doing == full_session.doing
    assert parsed.branch == full_session.branch
    assert parsed.turns == full_session.turns
    assert abs(parsed.context_usage - full_session.context_usage) < 0.001
    assert "Continue from test_parse_roundtrip" in parsed.resume_instructions
    assert "Use YAML frontmatter for metadata" in parsed.decisions
    assert any("project_state.py" in f for f in parsed.files_touched)
    assert "mmu" in parsed.domains_loaded
    assert "checkpoint" in parsed.domains_loaded


def test_parse_roundtrip_empty(tmp_path: Path, empty_session: SessionStateData):
    """Empty session should roundtrip cleanly."""
    state_file = tmp_path / "SESSION.md"
    state_file.write_text(render_session_state(empty_session), encoding="utf-8")

    parsed = parse_session_state(state_file)
    assert parsed.session_id == "sess-001"
    assert parsed.turns == 0
    assert parsed.resume_instructions == []
    assert parsed.decisions == []
    assert parsed.files_touched == []
    assert parsed.domains_loaded == []


# ── update_session_turn tests ─────────────────────────────────────────────────


def test_update_session_turn_increments_turns(tmp_path: Path, empty_session: SessionStateData):
    state_file = tmp_path / "SESSION.md"
    state_file.write_text(render_session_state(empty_session), encoding="utf-8")

    update_session_turn(
        state_file,
        context_usage=0.10,
        doing="Implementing render",
        new_files=["src/library_server/state/project_state.py"],
        new_decision=None,
        new_domain=None,
    )

    parsed = parse_session_state(state_file)
    assert parsed.turns == 1
    assert parsed.doing == "Implementing render"
    assert abs(parsed.context_usage - 0.10) < 0.001
    assert any("project_state.py" in f for f in parsed.files_touched)


def test_update_session_turn_appends_multiple_times(tmp_path: Path, empty_session: SessionStateData):
    state_file = tmp_path / "SESSION.md"
    state_file.write_text(render_session_state(empty_session), encoding="utf-8")

    update_session_turn(
        state_file,
        context_usage=0.10,
        doing="Turn one",
        new_files=["file_a.py"],
        new_decision="Decision A",
        new_domain="mmu",
    )
    update_session_turn(
        state_file,
        context_usage=0.20,
        doing="Turn two",
        new_files=["file_b.py"],
        new_decision="Decision B",
        new_domain="checkpoint",
    )

    parsed = parse_session_state(state_file)
    assert parsed.turns == 2
    assert parsed.doing == "Turn two"
    assert any("file_a.py" in f for f in parsed.files_touched)
    assert any("file_b.py" in f for f in parsed.files_touched)
    assert "Decision A" in parsed.decisions
    assert "Decision B" in parsed.decisions
    assert "mmu" in parsed.domains_loaded
    assert "checkpoint" in parsed.domains_loaded


def test_update_session_turn_updates_last_updated(tmp_path: Path, empty_session: SessionStateData):
    state_file = tmp_path / "SESSION.md"
    state_file.write_text(render_session_state(empty_session), encoding="utf-8")

    update_session_turn(
        state_file,
        context_usage=0.15,
        doing="Some work",
        new_files=[],
        new_decision=None,
        new_domain=None,
    )

    parsed = parse_session_state(state_file)
    # last_updated should be set to a non-empty timestamp
    assert parsed.last_updated != ""
    assert parsed.last_updated != empty_session.started


def test_update_session_turn_empty_doing_preserves_existing(tmp_path: Path, full_session: SessionStateData):
    """Passing doing='' should preserve the existing 'Doing' value."""
    state_file = tmp_path / "SESSION.md"
    state_file.write_text(render_session_state(full_session), encoding="utf-8")

    update_session_turn(
        state_file,
        context_usage=0.50,
        doing="",
        new_files=[],
        new_decision=None,
        new_domain=None,
    )

    parsed = parse_session_state(state_file)
    assert parsed.doing == full_session.doing


def test_update_session_turn_nonempty_doing_updates(tmp_path: Path, full_session: SessionStateData):
    """Passing a non-empty doing value should update the field."""
    state_file = tmp_path / "SESSION.md"
    state_file.write_text(render_session_state(full_session), encoding="utf-8")

    update_session_turn(
        state_file,
        context_usage=0.50,
        doing="New task now",
        new_files=[],
        new_decision=None,
        new_domain=None,
    )

    parsed = parse_session_state(state_file)
    assert parsed.doing == "New task now"


def test_update_session_turn_no_duplicates_in_domains(tmp_path: Path, empty_session: SessionStateData):
    """Calling update twice with same domain should not duplicate."""
    state_file = tmp_path / "SESSION.md"
    state_file.write_text(render_session_state(empty_session), encoding="utf-8")

    update_session_turn(state_file, 0.1, "Turn 1", [], None, "mmu")
    update_session_turn(state_file, 0.2, "Turn 2", [], None, "mmu")

    parsed = parse_session_state(state_file)
    assert parsed.domains_loaded.count("mmu") == 1
