"""Integration tests — redaction reaches the three write sites.

Verifies that:
  1. transcript.extract_decision_patterns() returns redacted content
  2. checkpoint.write_checkpoint() persists redacted fields to disk
  3. stop_capture exception path emits redacted stderr

Test fixtures construct secret-shaped strings via concatenation so the source
file does not contain literal patterns that trip secret-scan hooks.
"""

from __future__ import annotations

import json
from pathlib import Path



def _fake(prefix: str, body: str) -> str:
    return prefix + body


# ---------------------------------------------------------------------------
# 1. transcript.extract_decision_patterns
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, entries: list[dict]) -> None:
    with open(path, "w") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")


class TestTranscriptDecisionRedacted:
    def test_secret_in_user_decision_is_redacted(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import extract_decision_patterns
        ghp = _fake("ghp_", "Q" * 36)
        entries = [
            {
                "type": "message",
                "role": "user",
                "content": f"the decision is to use {ghp} for auth",
            },
        ]
        p = tmp_path / "t.jsonl"
        _write_jsonl(p, entries)

        results = extract_decision_patterns(p)
        assert len(results) == 1
        assert ghp not in results[0]
        assert "[REDACTED" in results[0]

    def test_env_var_assignment_redacted(self, tmp_path: Path) -> None:
        from library_server.hooks.transcript import extract_decision_patterns
        entries = [
            {
                "type": "message",
                "role": "user",
                "content": "agreed, set JIRA_API_TOKEN=verysecretvalue and ship",
            },
        ]
        p = tmp_path / "t.jsonl"
        _write_jsonl(p, entries)

        results = extract_decision_patterns(p)
        assert len(results) == 1
        assert "verysecretvalue" not in results[0]
        assert "[REDACTED]" in results[0]


# ---------------------------------------------------------------------------
# 2. checkpoint.write_checkpoint
# ---------------------------------------------------------------------------

class TestCheckpointWriteRedacted:
    def test_accomplished_field_redacted_on_disk(self, tmp_path: Path) -> None:
        from library_server.checkpoint.checkpoint import write_checkpoint
        from library_server.types import CheckpointData

        ghp = _fake("ghp_", "R" * 36)
        data = CheckpointData(
            topic="auth fix",
            date="2026-05-21",
            status="In Progress",
            next_session="ship it",
            accomplished=[f"rotated token {ghp}", "ran tests"],
        )

        result = write_checkpoint(str(tmp_path), data)
        content = Path(result["path"]).read_text()
        assert ghp not in content
        assert "[REDACTED" in content
        assert "ran tests" in content  # benign text preserved

    def test_next_actions_field_redacted(self, tmp_path: Path) -> None:
        from library_server.checkpoint.checkpoint import write_checkpoint
        from library_server.types import CheckpointData

        data = CheckpointData(
            topic="task",
            date="2026-05-21",
            status="Done",
            next_session="N/A",
            next_actions=["plain step", "set LINEAR_API_KEY=hardcoded_value_oops"],
        )

        result = write_checkpoint(str(tmp_path), data)
        content = Path(result["path"]).read_text()
        assert "hardcoded_value_oops" not in content
        assert "[REDACTED]" in content
        assert "plain step" in content

    def test_key_context_field_redacted(self, tmp_path: Path) -> None:
        from library_server.checkpoint.checkpoint import write_checkpoint
        from library_server.types import CheckpointData

        stripe = _fake("sk_test_", "k" * 30)
        data = CheckpointData(
            topic="t",
            date="2026-05-21",
            status="Done",
            next_session="N/A",
            key_context=[f"old key was {stripe}"],
        )

        result = write_checkpoint(str(tmp_path), data)
        content = Path(result["path"]).read_text()
        assert stripe not in content

    def test_open_decisions_dict_redacted(self, tmp_path: Path) -> None:
        from library_server.checkpoint.checkpoint import write_checkpoint
        from library_server.types import CheckpointData

        ghp = _fake("ghp_", "S" * 36)
        data = CheckpointData(
            topic="t",
            date="2026-05-21",
            status="Done",
            next_session="N/A",
            open_decisions=[{
                "question": f"rotate {ghp}?",
                "options": "yes/no",
                "impact": "auth",
            }],
        )

        result = write_checkpoint(str(tmp_path), data)
        content = Path(result["path"]).read_text()
        assert ghp not in content

    def test_memory_updates_dict_redacted(self, tmp_path: Path) -> None:
        from library_server.checkpoint.checkpoint import write_checkpoint
        from library_server.types import CheckpointData

        data = CheckpointData(
            topic="t",
            date="2026-05-21",
            status="Done",
            next_session="N/A",
            memory_updates=[{
                "file": "creds.md",
                "type": "secret",
                "content": "ANTHROPIC_API_KEY=my-real-key-here",
            }],
        )

        result = write_checkpoint(str(tmp_path), data)
        content = Path(result["path"]).read_text()
        assert "my-real-key-here" not in content


# ---------------------------------------------------------------------------
# 3. stop_capture exception path
# ---------------------------------------------------------------------------

class TestStopCaptureExceptionRedacted:
    def test_exception_with_secret_redacted_in_stderr(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        from library_server.hooks.scripts import stop_capture

        # Force update_session_turn to raise with a secret in the message.
        def boom(**kwargs):
            raise RuntimeError("connect failed JIRA_API_TOKEN=secretboom")

        monkeypatch.setattr(stop_capture, "update_session_turn", boom)

        sessions_dir = tmp_path
        (sessions_dir / "SESSION.md").write_text("# stub\n")
        transcript_path = tmp_path / "tx.jsonl"
        transcript_path.write_text("")
        context_usage_path = tmp_path / "ctx.json"
        context_usage_path.write_text("0")

        stop_capture.process_stop(
            sessions_dir=sessions_dir,
            transcript_path=transcript_path,
            context_usage_path=context_usage_path,
            journal_path=tmp_path / "j.jsonl",
        )

        err = capsys.readouterr().err
        assert "secretboom" not in err
        assert "[REDACTED]" in err
        assert "RuntimeError" in err
