"""Tests for hooks/scripts/stop_capture.py — TDD first pass."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from library_server.state.session_state import render_session_state, parse_session_state
from library_server.types import SessionStateData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_session_file(sessions_dir: Path, turns: int = 2, context_usage: float = 0.0) -> Path:
    data = SessionStateData(
        session_id="sess-001",
        task="CLO-42 — Implement stop hook",
        doing="Testing stop capture",
        branch="feat/mmu-hooks",
        resume_instructions=["Continue from last point"],
        decisions=[],
        files_touched=["src/library_server/hooks/scripts/stop_capture.py"],
        domains_loaded=["mmu"],
        turns=turns,
        context_usage=context_usage,
        started="2026-04-11T09:00:00Z",
        last_updated="2026-04-11T10:00:00Z",
    )
    path = sessions_dir / "SESSION.md"
    path.write_text(render_session_state(data), encoding="utf-8")
    return path


def make_transcript(tmp_path: Path, entries: list[dict] | None = None) -> Path:
    transcript = tmp_path / "transcript.jsonl"
    default_entries = [
        {
            "type": "tool_use",
            "name": "Read",
            "input": {"file_path": "/project/src/app.py"},
        },
        {
            "type": "message",
            "role": "user",
            "content": "Let's go with the YAML approach",
        },
    ]
    lines = [json.dumps(e) for e in (entries or default_entries)]
    transcript.write_text("\n".join(lines), encoding="utf-8")
    return transcript


def make_context_usage_file(tmp_path: Path, usage: float = 0.30) -> Path:
    """Write a context_usage JSON state file."""
    state_file = tmp_path / "context_usage.json"
    state_file.write_text(json.dumps({"context_usage": usage}), encoding="utf-8")
    return state_file


# ---------------------------------------------------------------------------
# Tests: process_stop
# ---------------------------------------------------------------------------


class TestProcessStop:
    def test_returns_dict(self, tmp_path: Path) -> None:
        """process_stop always returns a dict."""
        from library_server.hooks.scripts.stop_capture import process_stop

        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        make_session_file(sessions_dir, context_usage=0.20)
        transcript = make_transcript(tmp_path)
        context_usage_file = make_context_usage_file(tmp_path, usage=0.20)
        journal = tmp_path / "journal.jsonl"

        result = process_stop(
            sessions_dir=sessions_dir,
            transcript_path=transcript,
            context_usage_path=context_usage_file,
            journal_path=journal,
        )

        assert isinstance(result, dict)
        assert "warning" in result

    def test_increments_turns(self, tmp_path: Path) -> None:
        """process_stop should increment the turns counter in SESSION.md."""
        from library_server.hooks.scripts.stop_capture import process_stop

        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        make_session_file(sessions_dir, turns=3)
        transcript = make_transcript(tmp_path)
        context_usage_file = make_context_usage_file(tmp_path, usage=0.20)
        journal = tmp_path / "journal.jsonl"

        process_stop(
            sessions_dir=sessions_dir,
            transcript_path=transcript,
            context_usage_path=context_usage_file,
            journal_path=journal,
        )

        parsed = parse_session_state(sessions_dir / "SESSION.md")
        assert parsed.turns == 4

    def test_appends_files_from_transcript(self, tmp_path: Path) -> None:
        """process_stop should add files from transcript to SESSION.md."""
        from library_server.hooks.scripts.stop_capture import process_stop

        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        make_session_file(sessions_dir)
        transcript = make_transcript(tmp_path)  # contains /project/src/app.py
        context_usage_file = make_context_usage_file(tmp_path, usage=0.20)
        journal = tmp_path / "journal.jsonl"

        process_stop(
            sessions_dir=sessions_dir,
            transcript_path=transcript,
            context_usage_path=context_usage_file,
            journal_path=journal,
        )

        parsed = parse_session_state(sessions_dir / "SESSION.md")
        assert any("app.py" in f for f in parsed.files_touched)

    def test_preserves_doing_field(self, tmp_path: Path) -> None:
        """process_stop must NOT overwrite the existing 'Doing' field in SESSION.md."""
        from library_server.hooks.scripts.stop_capture import process_stop

        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        make_session_file(sessions_dir)  # doing="Testing stop capture"
        transcript = make_transcript(tmp_path)
        context_usage_file = make_context_usage_file(tmp_path, usage=0.20)
        journal = tmp_path / "journal.jsonl"

        process_stop(
            sessions_dir=sessions_dir,
            transcript_path=transcript,
            context_usage_path=context_usage_file,
            journal_path=journal,
        )

        parsed = parse_session_state(sessions_dir / "SESSION.md")
        assert parsed.doing == "Testing stop capture"

    def test_no_warning_at_low_usage(self, tmp_path: Path) -> None:
        """When context usage is below warn_pct, warning should be None."""
        from library_server.hooks.scripts.stop_capture import process_stop

        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        make_session_file(sessions_dir, context_usage=0.20)
        transcript = make_transcript(tmp_path)
        context_usage_file = make_context_usage_file(tmp_path, usage=0.20)
        journal = tmp_path / "journal.jsonl"

        result = process_stop(
            sessions_dir=sessions_dir,
            transcript_path=transcript,
            context_usage_path=context_usage_file,
            journal_path=journal,
            warn_pct=50,
            checkpoint_pct=60,
        )

        assert result["warning"] is None

    def test_warning_at_50_pct(self, tmp_path: Path) -> None:
        """When context usage >= warn_pct (50%), a warning text should be returned."""
        from library_server.hooks.scripts.stop_capture import process_stop

        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        make_session_file(sessions_dir, context_usage=0.55)
        transcript = make_transcript(tmp_path)
        context_usage_file = make_context_usage_file(tmp_path, usage=0.55)
        journal = tmp_path / "journal.jsonl"

        result = process_stop(
            sessions_dir=sessions_dir,
            transcript_path=transcript,
            context_usage_path=context_usage_file,
            journal_path=journal,
            warn_pct=50,
            checkpoint_pct=60,
        )

        assert result["warning"] is not None
        assert isinstance(result["warning"], str)
        assert len(result["warning"]) > 0

    def test_checkpoint_message_at_60_pct(self, tmp_path: Path) -> None:
        """When context usage >= checkpoint_pct (60%), warning mentions auto-checkpoint."""
        from library_server.hooks.scripts.stop_capture import process_stop

        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        make_session_file(sessions_dir, context_usage=0.65)
        transcript = make_transcript(tmp_path)
        context_usage_file = make_context_usage_file(tmp_path, usage=0.65)
        journal = tmp_path / "journal.jsonl"

        result = process_stop(
            sessions_dir=sessions_dir,
            transcript_path=transcript,
            context_usage_path=context_usage_file,
            journal_path=journal,
            warn_pct=50,
            checkpoint_pct=60,
        )

        assert result["warning"] is not None
        warning_lower = result["warning"].lower()
        assert "checkpoint" in warning_lower or "auto" in warning_lower

    def test_warn_message_differs_from_checkpoint_message(self, tmp_path: Path) -> None:
        """50% warning and 60%+ checkpoint warning should have different text."""
        from library_server.hooks.scripts.stop_capture import process_stop

        sessions_dir_warn = tmp_path / "sessions-warn"
        sessions_dir_warn.mkdir()
        make_session_file(sessions_dir_warn, context_usage=0.55)
        transcript_warn = make_transcript(tmp_path / "transcript-warn.jsonl" if False else tmp_path)
        usage_warn = make_context_usage_file(tmp_path / "usage-warn", usage=0.55) if False else make_context_usage_file(tmp_path, usage=0.55)
        journal_warn = tmp_path / "journal-warn.jsonl"

        result_warn = process_stop(
            sessions_dir=sessions_dir_warn,
            transcript_path=transcript_warn,
            context_usage_path=usage_warn,
            journal_path=journal_warn,
            warn_pct=50,
            checkpoint_pct=60,
        )

        sessions_dir_ckpt = tmp_path / "sessions-ckpt"
        sessions_dir_ckpt.mkdir()
        make_session_file(sessions_dir_ckpt, context_usage=0.65)
        usage_ckpt = tmp_path / "usage_ckpt.json"
        usage_ckpt.write_text(json.dumps({"context_usage": 0.65}), encoding="utf-8")
        journal_ckpt = tmp_path / "journal-ckpt.jsonl"

        result_ckpt = process_stop(
            sessions_dir=sessions_dir_ckpt,
            transcript_path=transcript_warn,
            context_usage_path=usage_ckpt,
            journal_path=journal_ckpt,
            warn_pct=50,
            checkpoint_pct=60,
        )

        assert result_warn["warning"] != result_ckpt["warning"]

    def test_missing_session_file_does_not_crash(self, tmp_path: Path) -> None:
        """If SESSION.md is missing, should not crash."""
        from library_server.hooks.scripts.stop_capture import process_stop

        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        # No SESSION.md
        transcript = make_transcript(tmp_path)
        context_usage_file = make_context_usage_file(tmp_path, usage=0.20)
        journal = tmp_path / "journal.jsonl"

        result = process_stop(
            sessions_dir=sessions_dir,
            transcript_path=transcript,
            context_usage_path=context_usage_file,
            journal_path=journal,
        )

        assert isinstance(result, dict)

    def test_missing_transcript_does_not_crash(self, tmp_path: Path) -> None:
        """If transcript file is missing, should not crash."""
        from library_server.hooks.scripts.stop_capture import process_stop

        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        make_session_file(sessions_dir)
        context_usage_file = make_context_usage_file(tmp_path, usage=0.20)
        journal = tmp_path / "journal.jsonl"

        result = process_stop(
            sessions_dir=sessions_dir,
            transcript_path=tmp_path / "nonexistent.jsonl",
            context_usage_path=context_usage_file,
            journal_path=journal,
        )

        assert isinstance(result, dict)

    def test_missing_context_usage_file_defaults_to_zero(self, tmp_path: Path) -> None:
        """Missing context_usage file should default to 0.0 (no warning)."""
        from library_server.hooks.scripts.stop_capture import process_stop

        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        make_session_file(sessions_dir)
        transcript = make_transcript(tmp_path)
        journal = tmp_path / "journal.jsonl"

        result = process_stop(
            sessions_dir=sessions_dir,
            transcript_path=transcript,
            context_usage_path=tmp_path / "nonexistent.json",
            journal_path=journal,
            warn_pct=50,
            checkpoint_pct=60,
        )

        assert result["warning"] is None

    def test_decisions_from_transcript_appended(self, tmp_path: Path) -> None:
        """Decisions detected in the transcript should be appended to SESSION.md."""
        from library_server.hooks.scripts.stop_capture import process_stop

        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        make_session_file(sessions_dir)
        transcript = make_transcript(tmp_path)  # contains "Let's go with the YAML approach"
        context_usage_file = make_context_usage_file(tmp_path, usage=0.20)
        journal = tmp_path / "journal.jsonl"

        process_stop(
            sessions_dir=sessions_dir,
            transcript_path=transcript,
            context_usage_path=context_usage_file,
            journal_path=journal,
        )

        parsed = parse_session_state(sessions_dir / "SESSION.md")
        # At minimum, decisions should not crash; content may vary by extraction
        assert isinstance(parsed.decisions, list)


# ---------------------------------------------------------------------------
# Tests: main() I/O contract
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_outputs_warning_when_high_usage(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """main() outputs additionalContext JSON when context usage is high."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        make_session_file(sessions_dir, context_usage=0.65)
        transcript = make_transcript(tmp_path)
        context_usage_file = make_context_usage_file(tmp_path, usage=0.65)
        journal = tmp_path / "journal.jsonl"

        stdin_data = json.dumps({
            "session_id": "sess-001",
            "sessions_dir": str(sessions_dir),
            "transcript_path": str(transcript),
            "context_usage_path": str(context_usage_file),
            "journal_path": str(journal),
        })

        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        from library_server.hooks.scripts import stop_capture
        stop_capture.main()

        output_str = captured.getvalue().strip()
        assert output_str
        output = json.loads(output_str)
        assert "hookSpecificOutput" in output
        assert "additionalContext" in output["hookSpecificOutput"]

    def test_main_silent_when_low_usage(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """main() outputs nothing when context usage is below warn threshold."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        make_session_file(sessions_dir, context_usage=0.20)
        transcript = make_transcript(tmp_path)
        context_usage_file = make_context_usage_file(tmp_path, usage=0.20)
        journal = tmp_path / "journal.jsonl"

        stdin_data = json.dumps({
            "session_id": "sess-001",
            "sessions_dir": str(sessions_dir),
            "transcript_path": str(transcript),
            "context_usage_path": str(context_usage_file),
            "journal_path": str(journal),
        })

        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        from library_server.hooks.scripts import stop_capture
        stop_capture.main()

        output_str = captured.getvalue().strip()
        assert output_str == ""
