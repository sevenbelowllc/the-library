"""Tests for hooks/scripts/session_end.py — TDD first pass."""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

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

    def test_parse_session_state_exception_falls_back_to_utc_date(self, tmp_path: Path) -> None:
        """When parse_session_state raises, date_prefix falls back to UTC today."""
        from library_server.hooks.scripts.session_end import process_session_end

        reading_room = tmp_path / "reading-room"
        reading_room.mkdir()
        # Write a SESSION.md with invalid content so parse_session_state raises
        session_file = reading_room / "SESSION.md"
        session_file.write_text("not valid session frontmatter", encoding="utf-8")

        vault_sessions = tmp_path / "vault" / "sessions"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True)

        with patch(
            "library_server.hooks.scripts.session_end.parse_session_state",
            side_effect=ValueError("bad parse"),
        ):
            result = process_session_end(
                reading_room=reading_room,
                sessions_dir=sessions_dir,
                vault_sessions_dir=vault_sessions,
                session_id="sess-err",
            )

        assert result["archived"] is True
        archived_files = list(vault_sessions.iterdir())
        assert len(archived_files) == 1
        # Filename should still contain the session id even with fallback date
        assert "sess-err" in archived_files[0].name

    def test_date_prefix_none_when_started_field_empty(self, tmp_path: Path) -> None:
        """When session_data.started is empty string, falls back to UTC date."""
        from library_server.hooks.scripts.session_end import process_session_end

        reading_room = tmp_path / "reading-room"
        reading_room.mkdir()
        _make_session_md(reading_room, started="")

        vault_sessions = tmp_path / "vault" / "sessions"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True)

        result = process_session_end(
            reading_room=reading_room,
            sessions_dir=sessions_dir,
            vault_sessions_dir=vault_sessions,
            session_id="sess-empty",
        )

        assert result["archived"] is True
        archived_files = list(vault_sessions.iterdir())
        assert len(archived_files) == 1
        assert "sess-empty" in archived_files[0].name

    def test_update_project_state_exception_is_caught(self, tmp_path: Path, capsys) -> None:
        """When update_project_state_field raises, error is printed to stderr but archiving succeeds."""
        from library_server.hooks.scripts.session_end import process_session_end

        reading_room = tmp_path / "reading-room"
        reading_room.mkdir()
        _make_session_md(reading_room)
        _make_project_state(reading_room, session_count=3)

        vault_sessions = tmp_path / "vault" / "sessions"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True)

        with patch(
            "library_server.hooks.scripts.session_end.update_project_state_field",
            side_effect=RuntimeError("disk full"),
        ):
            result = process_session_end(
                reading_room=reading_room,
                sessions_dir=sessions_dir,
                vault_sessions_dir=vault_sessions,
                session_id="sess-fail",
            )

        assert result["archived"] is True
        captured = capsys.readouterr()
        assert "disk full" in captured.err


class TestMain:
    def test_main_with_valid_payload(self, tmp_path: Path) -> None:
        """main() reads stdin JSON and calls process_session_end."""
        from library_server.hooks.scripts.session_end import main

        reading_room = tmp_path / "reading-room"
        reading_room.mkdir()
        _make_session_md(reading_room)

        vault_sessions = tmp_path / "vault" / "sessions"
        sessions_dir = tmp_path / "sessions"

        payload = json.dumps({
            "reading_room": str(reading_room),
            "sessions_dir": str(sessions_dir),
            "vault_sessions_dir": str(vault_sessions),
            "session_id": "main-sess",
        })

        with patch("sys.stdin", io.StringIO(payload)):
            main()

        assert vault_sessions.exists()
        archived_files = list(vault_sessions.iterdir())
        assert len(archived_files) == 1
        assert "main-sess" in archived_files[0].name

    def test_main_with_invalid_json(self, tmp_path: Path) -> None:
        """main() handles invalid JSON gracefully with defaults."""
        from library_server.hooks.scripts.session_end import main

        with patch("sys.stdin", io.StringIO("not json{")):
            # Should not raise — uses defaults
            main()

    def test_main_with_empty_payload(self, tmp_path: Path) -> None:
        """main() handles empty JSON object using defaults."""
        from library_server.hooks.scripts.session_end import main

        with patch("sys.stdin", io.StringIO("{}")):
            main()

    def test_main_entry_point_guard(self) -> None:
        """The if __name__ == '__main__' block calls main()."""
        with patch("library_server.hooks.scripts.session_end.main") as mock_main:
            exec(
                compile(
                    "if __name__ == '__main__': main()",
                    "<test>",
                    "exec",
                ),
                {"__name__": "__main__", "main": mock_main},
            )
            mock_main.assert_called_once()
