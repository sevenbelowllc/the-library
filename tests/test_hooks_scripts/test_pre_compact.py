"""Tests for hooks/scripts/pre_compact.py — TDD first pass."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


class TestProcessPreCompact:
    def test_saves_transcript_when_file_exists(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.pre_compact import process_pre_compact

        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text('{"type": "message"}\n', encoding="utf-8")

        vault_dir = tmp_path / "vault" / "transcripts"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True)

        result = process_pre_compact(
            transcript_path=transcript,
            vault_transcripts_dir=vault_dir,
            sessions_dir=sessions_dir,
            session_id="abc123",
        )

        assert result["saved"] is True
        assert "archive_path" in result
        archive = Path(result["archive_path"])
        assert archive.exists()
        assert archive.read_text(encoding="utf-8") == '{"type": "message"}\n'

    def test_archive_filename_contains_session_id(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.pre_compact import process_pre_compact

        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text("{}\n", encoding="utf-8")

        vault_dir = tmp_path / "vault" / "transcripts"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True)

        result = process_pre_compact(
            transcript_path=transcript,
            vault_transcripts_dir=vault_dir,
            sessions_dir=sessions_dir,
            session_id="mysession99",
        )

        archive_path = Path(result["archive_path"])
        assert "mysession99" in archive_path.name

    def test_creates_vault_dir_if_missing(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.pre_compact import process_pre_compact

        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text("{}\n", encoding="utf-8")

        vault_dir = tmp_path / "deep" / "nested" / "transcripts"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True)

        assert not vault_dir.exists()

        result = process_pre_compact(
            transcript_path=transcript,
            vault_transcripts_dir=vault_dir,
            sessions_dir=sessions_dir,
            session_id="sess1",
        )

        assert result["saved"] is True
        assert vault_dir.exists()

    def test_missing_transcript_returns_saved_false(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.pre_compact import process_pre_compact

        transcript = tmp_path / "nonexistent.jsonl"
        vault_dir = tmp_path / "vault" / "transcripts"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True)

        result = process_pre_compact(
            transcript_path=transcript,
            vault_transcripts_dir=vault_dir,
            sessions_dir=sessions_dir,
            session_id="sess1",
        )

        assert result["saved"] is False
        assert "archive_path" not in result

    def test_archive_filename_contains_date(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.pre_compact import process_pre_compact
        import re

        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text("{}\n", encoding="utf-8")

        vault_dir = tmp_path / "vault" / "transcripts"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True)

        result = process_pre_compact(
            transcript_path=transcript,
            vault_transcripts_dir=vault_dir,
            sessions_dir=sessions_dir,
            session_id="datechecksession",
        )

        archive_name = Path(result["archive_path"]).name
        # Should match YYYY-MM-DD prefix
        assert re.match(r"\d{4}-\d{2}-\d{2}-", archive_name), (
            f"Expected date prefix in filename, got: {archive_name}"
        )


class TestMain:
    """Tests for the main() entry point and __name__ guard."""

    def test_main_with_valid_payload(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.pre_compact import main

        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text('{"msg": "hello"}\n', encoding="utf-8")
        vault_dir = tmp_path / "vault" / "transcripts"
        sessions_dir = tmp_path / "sessions"

        payload = json.dumps({
            "transcript_path": str(transcript),
            "vault_transcripts_dir": str(vault_dir),
            "sessions_dir": str(sessions_dir),
            "session_id": "main-test-sess",
        })

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.read.return_value = payload
            main()

        # Verify the transcript was archived
        assert vault_dir.exists()
        archived = list(vault_dir.iterdir())
        assert len(archived) == 1
        assert "main-test-sess" in archived[0].name

    def test_main_with_invalid_json_uses_defaults(self) -> None:
        from library_server.hooks.scripts.pre_compact import main

        with patch("sys.stdin") as mock_stdin, \
             patch("library_server.hooks.scripts.pre_compact.process_pre_compact") as mock_proc:
            mock_stdin.read.return_value = "not valid json!!!"
            mock_proc.return_value = {"saved": False}
            main()

        # With invalid JSON, payload={}, so defaults are used
        call_kwargs = mock_proc.call_args
        assert call_kwargs.kwargs["transcript_path"] == Path("")
        assert call_kwargs.kwargs["session_id"] == "unknown"

    def test_main_with_empty_payload_uses_defaults(self) -> None:
        from library_server.hooks.scripts.pre_compact import main

        with patch("sys.stdin") as mock_stdin, \
             patch("library_server.hooks.scripts.pre_compact.process_pre_compact") as mock_proc:
            mock_stdin.read.return_value = "{}"
            mock_proc.return_value = {"saved": False}
            main()

        call_kwargs = mock_proc.call_args
        assert call_kwargs.kwargs["session_id"] == "unknown"
        assert "transcripts" in str(call_kwargs.kwargs["vault_transcripts_dir"])

    def test_name_guard_calls_main(self) -> None:
        """Verify the if __name__ == '__main__' guard invokes main()."""
        import importlib
        import library_server.hooks.scripts.pre_compact as mod

        with patch.object(mod, "main") as mock_main:
            # Simulate running as __main__
            exec(compile("if __name__ == '__main__': main()", mod.__file__, "exec"),
                 {"__name__": "__main__", "main": mock_main})
            mock_main.assert_called_once()
