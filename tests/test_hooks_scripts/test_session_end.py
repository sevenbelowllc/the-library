"""Tests for hooks/scripts/session_end.py — TDD first pass."""

from __future__ import annotations

from pathlib import Path

import pytest

from library_server.state.project_state import parse_project_state, render_project_state
from library_server.state.session_state import render_session_state
from library_server.types import ProjectStateData, SessionStateData


def _make_session_md(path: Path, session_id: str = "sess-001", started: str = "2026-04-11T10:00:00Z") -> Path:
    """Write a minimal SESSION.md and return its path."""
    data = SessionStateData(
        session_id=session_id,
        task="Test task",
        doing="Testing",
        branch="main",
        started=started,
        last_updated=started,
    )
    session_file = path / "SESSION.md"
    session_file.write_text(render_session_state(data), encoding="utf-8")
    return session_file


def _make_project_state(path: Path, session_count: int = 5) -> Path:
    """Write a minimal PROJECT-STATE.md and return its path."""
    data = ProjectStateData(project="compliance-os", session_count=session_count)
    state_file = path / "PROJECT-STATE.md"
    state_file.write_text(render_project_state(data), encoding="utf-8")
    return state_file


class TestProcessSessionEnd:
    def test_archives_session_md(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.session_end import process_session_end

        reading_room = tmp_path / "reading-room"
        reading_room.mkdir()
        _make_session_md(reading_room)
        _make_project_state(reading_room)

        vault_sessions = tmp_path / "vault" / "sessions"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True)

        result = process_session_end(
            reading_room=reading_room,
            sessions_dir=sessions_dir,
            vault_sessions_dir=vault_sessions,
            session_id="sess-001",
        )

        assert result["archived"] is True
        assert vault_sessions.exists()
        archived_files = list(vault_sessions.iterdir())
        assert len(archived_files) == 1
        assert "session.md" in archived_files[0].name.lower()

    def test_archive_filename_contains_session_id(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.session_end import process_session_end

        reading_room = tmp_path / "reading-room"
        reading_room.mkdir()
        _make_session_md(reading_room, session_id="my-session-42")
        _make_project_state(reading_room)

        vault_sessions = tmp_path / "vault" / "sessions"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True)

        result = process_session_end(
            reading_room=reading_room,
            sessions_dir=sessions_dir,
            vault_sessions_dir=vault_sessions,
            session_id="my-session-42",
        )

        archived_files = list(vault_sessions.iterdir())
        assert any("my-session-42" in f.name for f in archived_files)

    def test_increments_session_count(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.session_end import process_session_end

        reading_room = tmp_path / "reading-room"
        reading_room.mkdir()
        _make_session_md(reading_room)
        state_file = _make_project_state(reading_room, session_count=7)

        vault_sessions = tmp_path / "vault" / "sessions"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True)

        process_session_end(
            reading_room=reading_room,
            sessions_dir=sessions_dir,
            vault_sessions_dir=vault_sessions,
            session_id="sess-001",
        )

        updated = parse_project_state(state_file)
        assert updated.session_count == 8

    def test_creates_vault_sessions_dir_if_missing(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.session_end import process_session_end

        reading_room = tmp_path / "reading-room"
        reading_room.mkdir()
        _make_session_md(reading_room)
        _make_project_state(reading_room)

        vault_sessions = tmp_path / "deep" / "nested" / "vault" / "sessions"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True)

        assert not vault_sessions.exists()

        result = process_session_end(
            reading_room=reading_room,
            sessions_dir=sessions_dir,
            vault_sessions_dir=vault_sessions,
            session_id="sess-001",
        )

        assert result["archived"] is True
        assert vault_sessions.exists()

    def test_missing_session_file_returns_archived_false(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.session_end import process_session_end

        reading_room = tmp_path / "reading-room"
        reading_room.mkdir()
        # No SESSION.md created
        _make_project_state(reading_room)

        vault_sessions = tmp_path / "vault" / "sessions"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True)

        result = process_session_end(
            reading_room=reading_room,
            sessions_dir=sessions_dir,
            vault_sessions_dir=vault_sessions,
            session_id="sess-001",
        )

        assert result["archived"] is False
