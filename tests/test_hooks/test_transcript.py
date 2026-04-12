"""Tests for hooks/transcript.py — JSONL transcript parsing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_jsonl(path: Path, entries: list[dict]) -> None:
    """Write a list of dicts as newline-delimited JSON."""
    with open(path, "w") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Tests: read_transcript_tail
# ---------------------------------------------------------------------------

class TestReadTranscriptTail:
    def test_returns_last_n_entries(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import read_transcript_tail
        entries = [{"i": i} for i in range(20)]
        p = tmp_path / "t.jsonl"
        write_jsonl(p, entries)
        result = read_transcript_tail(p, n=5)
        assert len(result) == 5
        assert [r["i"] for r in result] == [15, 16, 17, 18, 19]

    def test_default_n_is_10(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import read_transcript_tail
        entries = [{"i": i} for i in range(15)]
        p = tmp_path / "t.jsonl"
        write_jsonl(p, entries)
        result = read_transcript_tail(p)
        assert len(result) == 10

    def test_returns_all_when_fewer_than_n(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import read_transcript_tail
        entries = [{"i": i} for i in range(3)]
        p = tmp_path / "t.jsonl"
        write_jsonl(p, entries)
        result = read_transcript_tail(p, n=10)
        assert len(result) == 3

    def test_empty_file_returns_empty_list(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import read_transcript_tail
        p = tmp_path / "empty.jsonl"
        p.write_text("")
        result = read_transcript_tail(p)
        assert result == []

    def test_missing_file_returns_empty_list(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import read_transcript_tail
        p = tmp_path / "nonexistent.jsonl"
        result = read_transcript_tail(p)
        assert result == []

    def test_skips_blank_lines(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import read_transcript_tail
        p = tmp_path / "t.jsonl"
        p.write_text('{"i": 0}\n\n{"i": 1}\n\n{"i": 2}\n')
        result = read_transcript_tail(p, n=10)
        assert len(result) == 3
        assert result[0]["i"] == 0

    def test_returns_list_of_dicts(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import read_transcript_tail
        p = tmp_path / "t.jsonl"
        write_jsonl(p, [{"type": "message", "content": "hello"}])
        result = read_transcript_tail(p)
        assert isinstance(result[0], dict)


# ---------------------------------------------------------------------------
# Tests: extract_files_from_transcript
# ---------------------------------------------------------------------------

class TestExtractFilesFromTranscript:
    def _make_tool_use(self, tool_name: str, file_path: str) -> dict:
        return {
            "type": "tool_use",
            "name": tool_name,
            "input": {"file_path": file_path},
        }

    def test_extracts_read_tool_paths(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import extract_files_from_transcript
        p = tmp_path / "t.jsonl"
        write_jsonl(p, [self._make_tool_use("Read", "/foo/bar.py")])
        result = extract_files_from_transcript(p)
        assert "/foo/bar.py" in result

    def test_extracts_write_tool_paths(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import extract_files_from_transcript
        p = tmp_path / "t.jsonl"
        write_jsonl(p, [self._make_tool_use("Write", "/foo/new.py")])
        result = extract_files_from_transcript(p)
        assert "/foo/new.py" in result

    def test_extracts_edit_tool_paths(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import extract_files_from_transcript
        p = tmp_path / "t.jsonl"
        write_jsonl(p, [self._make_tool_use("Edit", "/foo/edit.py")])
        result = extract_files_from_transcript(p)
        assert "/foo/edit.py" in result

    def test_deduplicates_paths(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import extract_files_from_transcript
        p = tmp_path / "t.jsonl"
        entries = [
            self._make_tool_use("Read", "/foo/bar.py"),
            self._make_tool_use("Edit", "/foo/bar.py"),
        ]
        write_jsonl(p, entries)
        result = extract_files_from_transcript(p)
        assert result.count("/foo/bar.py") == 1

    def test_ignores_non_tool_use_entries(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import extract_files_from_transcript
        p = tmp_path / "t.jsonl"
        entries = [
            {"type": "message", "role": "assistant", "content": "hello"},
            self._make_tool_use("Read", "/src/main.py"),
        ]
        write_jsonl(p, entries)
        result = extract_files_from_transcript(p)
        assert result == ["/src/main.py"]

    def test_ignores_other_tools(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import extract_files_from_transcript
        p = tmp_path / "t.jsonl"
        write_jsonl(p, [self._make_tool_use("Bash", "/ignored")])
        result = extract_files_from_transcript(p)
        assert "/ignored" not in result

    def test_empty_transcript_returns_empty_list(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import extract_files_from_transcript
        p = tmp_path / "t.jsonl"
        p.write_text("")
        result = extract_files_from_transcript(p)
        assert result == []

    def test_missing_file_returns_empty_list(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import extract_files_from_transcript
        p = tmp_path / "nonexistent.jsonl"
        result = extract_files_from_transcript(p)
        assert result == []

    def test_entry_without_file_path_key_skipped(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import extract_files_from_transcript
        p = tmp_path / "t.jsonl"
        write_jsonl(p, [{"type": "tool_use", "name": "Read", "input": {}}])
        result = extract_files_from_transcript(p)
        assert result == []

    def test_multiple_unique_files(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import extract_files_from_transcript
        p = tmp_path / "t.jsonl"
        entries = [
            self._make_tool_use("Read", "/a.py"),
            self._make_tool_use("Write", "/b.py"),
            self._make_tool_use("Edit", "/c.py"),
        ]
        write_jsonl(p, entries)
        result = extract_files_from_transcript(p)
        assert set(result) == {"/a.py", "/b.py", "/c.py"}


# ---------------------------------------------------------------------------
# Tests: extract_decision_patterns
# ---------------------------------------------------------------------------

class TestExtractDecisionPatterns:
    def _user_msg(self, text: str) -> dict:
        return {"type": "message", "role": "user", "content": text}

    def test_detects_lets_go_with(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import extract_decision_patterns
        p = tmp_path / "t.jsonl"
        write_jsonl(p, [self._user_msg("let's go with Option A for the auth layer")])
        result = extract_decision_patterns(p)
        assert len(result) == 1
        assert "Option A" in result[0]

    def test_detects_agreed(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import extract_decision_patterns
        p = tmp_path / "t.jsonl"
        write_jsonl(p, [self._user_msg("agreed, we'll use PostgreSQL")])
        result = extract_decision_patterns(p)
        assert len(result) == 1

    def test_detects_confirmed(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import extract_decision_patterns
        p = tmp_path / "t.jsonl"
        write_jsonl(p, [self._user_msg("confirmed, let's proceed")])
        result = extract_decision_patterns(p)
        assert len(result) == 1

    def test_detects_locked(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import extract_decision_patterns
        p = tmp_path / "t.jsonl"
        write_jsonl(p, [self._user_msg("locked — the schema is final")])
        result = extract_decision_patterns(p)
        assert len(result) == 1

    def test_detects_the_decision_is(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import extract_decision_patterns
        p = tmp_path / "t.jsonl"
        write_jsonl(p, [self._user_msg("the decision is to use Redis for caching")])
        result = extract_decision_patterns(p)
        assert len(result) == 1

    def test_detects_no_use_x_instead(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import extract_decision_patterns
        p = tmp_path / "t.jsonl"
        write_jsonl(p, [self._user_msg("no, use Memcached instead")])
        result = extract_decision_patterns(p)
        assert len(result) == 1

    def test_ignores_assistant_messages(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import extract_decision_patterns
        p = tmp_path / "t.jsonl"
        write_jsonl(p, [{"type": "message", "role": "assistant", "content": "let's go with X"}])
        result = extract_decision_patterns(p)
        assert result == []

    def test_multiple_matches_returned(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import extract_decision_patterns
        p = tmp_path / "t.jsonl"
        entries = [
            self._user_msg("agreed, use TypeScript"),
            self._user_msg("locked — no more changes"),
        ]
        write_jsonl(p, entries)
        result = extract_decision_patterns(p)
        assert len(result) == 2

    def test_empty_file_returns_empty_list(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import extract_decision_patterns
        p = tmp_path / "t.jsonl"
        p.write_text("")
        result = extract_decision_patterns(p)
        assert result == []

    def test_missing_file_returns_empty_list(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import extract_decision_patterns
        p = tmp_path / "nonexistent.jsonl"
        result = extract_decision_patterns(p)
        assert result == []

    def test_case_insensitive_match(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import extract_decision_patterns
        p = tmp_path / "t.jsonl"
        write_jsonl(p, [self._user_msg("Agreed, proceed")])
        result = extract_decision_patterns(p)
        assert len(result) == 1
