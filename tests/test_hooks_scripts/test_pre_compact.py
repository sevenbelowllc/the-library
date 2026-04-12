"""Tests for hooks/scripts/pre_compact.py — TDD first pass."""

from __future__ import annotations

from pathlib import Path

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
