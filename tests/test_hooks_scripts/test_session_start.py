"""Tests for hooks/scripts/session_start.py — TDD first pass."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from library_server.state.project_state import render_project_state
from library_server.state.session_state import render_session_state
from library_server.types import ProjectStateData, SessionStateData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_project_state_file(reading_room: Path) -> Path:
    data = ProjectStateData(
        project="SevenBelow Compliance OS",
        focus="MMU hook scripts",
        active_task="CLO-42 — Implement hook scripts",
        blockers=["Waiting for spec review"],
        invariants=["No frontend state machines", "RLS enforced always"],
        session_count=5,
    )
    path = reading_room / "PROJECT-STATE.md"
    path.write_text(render_project_state(data), encoding="utf-8")
    return path


def make_session_state_file(sessions_dir: Path, session_id: str = "sess-001") -> Path:
    data = SessionStateData(
        session_id=session_id,
        task="CLO-42 — Implement hook scripts",
        doing="Writing session_start.py",
        branch="feat/mmu-hooks",
        resume_instructions=["Run pytest tests/test_hooks_scripts/", "Check coverage"],
        decisions=["Use YAML frontmatter"],
        files_touched=["src/library_server/hooks/scripts/session_start.py"],
        domains_loaded=["mmu"],
        turns=3,
        context_usage=0.25,
        started="2026-04-11T09:00:00Z",
        last_updated="2026-04-11T10:00:00Z",
    )
    path = sessions_dir / "SESSION.md"
    path.write_text(render_session_state(data), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Tests: build_session_context
# ---------------------------------------------------------------------------


class TestBuildSessionContext:
    def test_startup_includes_project_info(self, tmp_path: Path) -> None:
        """Startup mode should include project name and active task."""
        from library_server.hooks.scripts.session_start import build_session_context

        reading_room = tmp_path / "reading-room"
        reading_room.mkdir()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        make_project_state_file(reading_room)
        make_session_state_file(sessions_dir)

        context = build_session_context("startup", reading_room, sessions_dir)

        assert "SevenBelow Compliance OS" in context
        assert "CLO-42" in context

    def test_startup_includes_session_info(self, tmp_path: Path) -> None:
        """Startup mode should include current session task and doing."""
        from library_server.hooks.scripts.session_start import build_session_context

        reading_room = tmp_path / "reading-room"
        reading_room.mkdir()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        make_project_state_file(reading_room)
        make_session_state_file(sessions_dir)

        context = build_session_context("startup", reading_room, sessions_dir)

        assert "Writing session_start.py" in context

    def test_startup_includes_resume_instructions(self, tmp_path: Path) -> None:
        """Startup mode should include resume instructions."""
        from library_server.hooks.scripts.session_start import build_session_context

        reading_room = tmp_path / "reading-room"
        reading_room.mkdir()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        make_project_state_file(reading_room)
        make_session_state_file(sessions_dir)

        context = build_session_context("startup", reading_room, sessions_dir)

        assert "Run pytest" in context

    def test_startup_includes_invariants(self, tmp_path: Path) -> None:
        """Startup mode should include invariants from project state."""
        from library_server.hooks.scripts.session_start import build_session_context

        reading_room = tmp_path / "reading-room"
        reading_room.mkdir()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        make_project_state_file(reading_room)
        make_session_state_file(sessions_dir)

        context = build_session_context("startup", reading_room, sessions_dir)

        assert "RLS" in context or "frontend" in context.lower()

    def test_output_under_4000_chars(self, tmp_path: Path) -> None:
        """Context output must stay within the ~4000 char budget."""
        from library_server.hooks.scripts.session_start import build_session_context

        reading_room = tmp_path / "reading-room"
        reading_room.mkdir()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        make_project_state_file(reading_room)
        make_session_state_file(sessions_dir)

        context = build_session_context("startup", reading_room, sessions_dir)

        assert len(context) < 4000

    def test_missing_project_state_does_not_crash(self, tmp_path: Path) -> None:
        """If PROJECT-STATE.md is missing, should return gracefully."""
        from library_server.hooks.scripts.session_start import build_session_context

        reading_room = tmp_path / "reading-room"
        reading_room.mkdir()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        # No project state file
        make_session_state_file(sessions_dir)

        context = build_session_context("startup", reading_room, sessions_dir)

        # Should not crash; should return something
        assert isinstance(context, str)

    def test_missing_session_state_does_not_crash(self, tmp_path: Path) -> None:
        """If SESSION.md is missing, should return gracefully."""
        from library_server.hooks.scripts.session_start import build_session_context

        reading_room = tmp_path / "reading-room"
        reading_room.mkdir()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        make_project_state_file(reading_room)
        # No session state file

        context = build_session_context("startup", reading_room, sessions_dir)

        assert isinstance(context, str)
        assert "SevenBelow Compliance OS" in context

    def test_both_files_missing_does_not_crash(self, tmp_path: Path) -> None:
        """If both state files are missing, should return empty string or minimal stub."""
        from library_server.hooks.scripts.session_start import build_session_context

        reading_room = tmp_path / "reading-room"
        reading_room.mkdir()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()

        context = build_session_context("startup", reading_room, sessions_dir)

        assert isinstance(context, str)

    def test_compact_mode_returns_string(self, tmp_path: Path) -> None:
        """Compact mode should return a non-empty string."""
        from library_server.hooks.scripts.session_start import build_session_context

        reading_room = tmp_path / "reading-room"
        reading_room.mkdir()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        make_project_state_file(reading_room)
        make_session_state_file(sessions_dir)

        context = build_session_context("compact", reading_room, sessions_dir)

        assert isinstance(context, str)
        assert len(context) > 0

    def test_resume_mode_returns_string(self, tmp_path: Path) -> None:
        """Resume mode should return a string."""
        from library_server.hooks.scripts.session_start import build_session_context

        reading_room = tmp_path / "reading-room"
        reading_room.mkdir()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        make_project_state_file(reading_room)
        make_session_state_file(sessions_dir)

        context = build_session_context("resume", reading_room, sessions_dir)

        assert isinstance(context, str)

    def test_clear_mode_archives_previous_session(self, tmp_path: Path) -> None:
        """Clear mode should archive SESSION.md before returning."""
        from library_server.hooks.scripts.session_start import build_session_context

        reading_room = tmp_path / "reading-room"
        reading_room.mkdir()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        make_project_state_file(reading_room)
        make_session_state_file(sessions_dir, session_id="sess-001")

        context = build_session_context("clear", reading_room, sessions_dir)

        # Archive file should exist
        archives = list(sessions_dir.glob("SESSION-*.md"))
        assert len(archives) >= 1
        assert isinstance(context, str)

    def test_context_contains_blockers(self, tmp_path: Path) -> None:
        """Context should mention any active blockers."""
        from library_server.hooks.scripts.session_start import build_session_context

        reading_room = tmp_path / "reading-room"
        reading_room.mkdir()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        make_project_state_file(reading_room)
        make_session_state_file(sessions_dir)

        context = build_session_context("startup", reading_room, sessions_dir)

        assert "Waiting for spec review" in context

    def test_context_contains_recent_decisions(self, tmp_path: Path) -> None:
        """Context should include recent decisions from session state."""
        from library_server.hooks.scripts.session_start import build_session_context

        reading_room = tmp_path / "reading-room"
        reading_room.mkdir()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        make_project_state_file(reading_room)
        make_session_state_file(sessions_dir)

        context = build_session_context("startup", reading_room, sessions_dir)

        assert "YAML frontmatter" in context


# ---------------------------------------------------------------------------
# Tests: main() I/O contract
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_outputs_hook_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """main() should output JSON with hookSpecificOutput.additionalContext."""
        import io
        import sys
        from library_server.hooks.scripts.session_start import build_session_context

        reading_room = tmp_path / "reading-room"
        reading_room.mkdir()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        make_project_state_file(reading_room)
        make_session_state_file(sessions_dir)

        stdin_data = json.dumps({
            "session_id": "sess-test",
            "mode": "startup",
            "cwd": str(tmp_path),
            "reading_room": str(reading_room),
            "sessions_dir": str(sessions_dir),
        })

        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        from library_server.hooks.scripts import session_start
        session_start.main()

        output = json.loads(captured.getvalue())
        assert "hookSpecificOutput" in output
        assert output["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        assert "additionalContext" in output["hookSpecificOutput"]
        assert isinstance(output["hookSpecificOutput"]["additionalContext"], str)
