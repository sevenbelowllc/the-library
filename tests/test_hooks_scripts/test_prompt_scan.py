"""Tests for hooks/scripts/prompt_scan.py — TDD first pass."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AUTH_DOMAIN_MD = """\
---
domain: auth
keywords:
  starter: [requireAuth, requireOrgScope, clerk, jwt]
  learned: []
exclude:
  starter: [author]
  learned: []
match_threshold: 1
token_estimate: 380
---

# Auth Domain

Handles authentication and authorization using Clerk JWT tokens.
Use requireAuth guard on all resolvers.
"""

BILLING_DOMAIN_MD = """\
---
domain: billing
keywords:
  starter: [stripe, invoice, subscription, payment]
  learned: [refund]
exclude:
  starter: []
  learned: []
match_threshold: 2
token_estimate: 250
---

# Billing Domain

Handles Stripe payments and subscription management.
"""


def make_domains_dir(tmp_path: Path) -> Path:
    domains_dir = tmp_path / "domains"
    domains_dir.mkdir(parents=True)
    (domains_dir / "auth.md").write_text(AUTH_DOMAIN_MD, encoding="utf-8")
    (domains_dir / "billing.md").write_text(BILLING_DOMAIN_MD, encoding="utf-8")
    return domains_dir


# ---------------------------------------------------------------------------
# Tests: process_prompt
# ---------------------------------------------------------------------------


class TestProcessPrompt:
    def test_match_returns_context_dict(self, tmp_path: Path) -> None:
        """A matching prompt returns a dict with context and tokens."""
        from library_server.hooks.scripts.prompt_scan import process_prompt

        domains_dir = make_domains_dir(tmp_path)
        dedup_dir = tmp_path / "dedup"
        dedup_dir.mkdir()
        journal = tmp_path / "journal.jsonl"

        result = process_prompt(
            prompt="Add requireAuth to the resolver",
            session_id="sess-001",
            domains_dir=domains_dir,
            dedup_dir=dedup_dir,
            journal_path=journal,
        )

        assert result is not None
        assert "context" in result
        assert "tokens" in result
        assert "domain" in result
        assert "match_type" in result

    def test_match_returns_first_hit_type(self, tmp_path: Path) -> None:
        """First match should have match_type 'first_hit'."""
        from library_server.hooks.scripts.prompt_scan import process_prompt

        domains_dir = make_domains_dir(tmp_path)
        dedup_dir = tmp_path / "dedup"
        dedup_dir.mkdir()
        journal = tmp_path / "journal.jsonl"

        result = process_prompt(
            prompt="Add requireAuth to the resolver",
            session_id="sess-001",
            domains_dir=domains_dir,
            dedup_dir=dedup_dir,
            journal_path=journal,
        )

        assert result["match_type"] == "first_hit"

    def test_match_sets_domain_name(self, tmp_path: Path) -> None:
        """Matched domain name is returned correctly."""
        from library_server.hooks.scripts.prompt_scan import process_prompt

        domains_dir = make_domains_dir(tmp_path)
        dedup_dir = tmp_path / "dedup"
        dedup_dir.mkdir()
        journal = tmp_path / "journal.jsonl"

        result = process_prompt(
            prompt="Add requireAuth to the resolver",
            session_id="sess-001",
            domains_dir=domains_dir,
            dedup_dir=dedup_dir,
            journal_path=journal,
        )

        assert result["domain"] == "auth"

    def test_match_returns_domain_content(self, tmp_path: Path) -> None:
        """Context field contains domain content."""
        from library_server.hooks.scripts.prompt_scan import process_prompt

        domains_dir = make_domains_dir(tmp_path)
        dedup_dir = tmp_path / "dedup"
        dedup_dir.mkdir()
        journal = tmp_path / "journal.jsonl"

        result = process_prompt(
            prompt="Add requireAuth to the resolver",
            session_id="sess-001",
            domains_dir=domains_dir,
            dedup_dir=dedup_dir,
            journal_path=journal,
        )

        assert "Auth Domain" in result["context"]

    def test_no_match_returns_none(self, tmp_path: Path) -> None:
        """An unrelated prompt returns None (silent)."""
        from library_server.hooks.scripts.prompt_scan import process_prompt

        domains_dir = make_domains_dir(tmp_path)
        dedup_dir = tmp_path / "dedup"
        dedup_dir.mkdir()
        journal = tmp_path / "journal.jsonl"

        result = process_prompt(
            prompt="Update the CSS color of the navigation bar",
            session_id="sess-001",
            domains_dir=domains_dir,
            dedup_dir=dedup_dir,
            journal_path=journal,
        )

        assert result is None

    def test_no_match_logs_to_journal(self, tmp_path: Path) -> None:
        """No-match should still write an entry to the journal."""
        from library_server.hooks.scripts.prompt_scan import process_prompt

        domains_dir = make_domains_dir(tmp_path)
        dedup_dir = tmp_path / "dedup"
        dedup_dir.mkdir()
        journal = tmp_path / "journal.jsonl"

        process_prompt(
            prompt="Update the CSS color of the navigation bar",
            session_id="sess-001",
            domains_dir=domains_dir,
            dedup_dir=dedup_dir,
            journal_path=journal,
        )

        assert journal.exists()
        entries = [json.loads(l) for l in journal.read_text().splitlines() if l.strip()]
        assert len(entries) >= 1
        assert entries[-1]["match_type"] == "no_match"

    def test_first_hit_logs_to_journal(self, tmp_path: Path) -> None:
        """First hit should log to the journal."""
        from library_server.hooks.scripts.prompt_scan import process_prompt

        domains_dir = make_domains_dir(tmp_path)
        dedup_dir = tmp_path / "dedup"
        dedup_dir.mkdir()
        journal = tmp_path / "journal.jsonl"

        process_prompt(
            prompt="Add requireAuth to the resolver",
            session_id="sess-001",
            domains_dir=domains_dir,
            dedup_dir=dedup_dir,
            journal_path=journal,
        )

        entries = [json.loads(l) for l in journal.read_text().splitlines() if l.strip()]
        assert any(e["match_type"] == "first_hit" for e in entries)

    def test_repeat_hit_returns_reminder(self, tmp_path: Path) -> None:
        """Second match for the same domain returns a reminder instead of full content."""
        from library_server.hooks.scripts.prompt_scan import process_prompt

        domains_dir = make_domains_dir(tmp_path)
        dedup_dir = tmp_path / "dedup"
        dedup_dir.mkdir()
        journal = tmp_path / "journal.jsonl"

        # First hit
        process_prompt(
            prompt="Add requireAuth to the resolver",
            session_id="sess-001",
            domains_dir=domains_dir,
            dedup_dir=dedup_dir,
            journal_path=journal,
        )

        # Second hit (same session, same domain)
        result = process_prompt(
            prompt="Use requireAuth for this new endpoint",
            session_id="sess-001",
            domains_dir=domains_dir,
            dedup_dir=dedup_dir,
            journal_path=journal,
        )

        assert result is not None
        assert result["match_type"] == "repeat"
        assert "Reminder" in result["context"]

    def test_repeat_hit_has_lower_tokens(self, tmp_path: Path) -> None:
        """Repeat hit should return fewer tokens than first hit."""
        from library_server.hooks.scripts.prompt_scan import process_prompt

        domains_dir = make_domains_dir(tmp_path)
        dedup_dir = tmp_path / "dedup"
        dedup_dir.mkdir()
        journal = tmp_path / "journal.jsonl"

        first = process_prompt(
            prompt="Add requireAuth to the resolver",
            session_id="sess-001",
            domains_dir=domains_dir,
            dedup_dir=dedup_dir,
            journal_path=journal,
        )

        repeat = process_prompt(
            prompt="Use requireAuth here too",
            session_id="sess-001",
            domains_dir=domains_dir,
            dedup_dir=dedup_dir,
            journal_path=journal,
        )

        assert repeat["tokens"] < first["tokens"]
        assert repeat["tokens"] == 50

    def test_different_session_does_not_repeat(self, tmp_path: Path) -> None:
        """A different session ID should not see previous session's dedup state."""
        from library_server.hooks.scripts.prompt_scan import process_prompt

        domains_dir = make_domains_dir(tmp_path)
        dedup_dir = tmp_path / "dedup"
        dedup_dir.mkdir()
        journal = tmp_path / "journal.jsonl"

        # First hit on sess-001
        process_prompt(
            prompt="Add requireAuth to the resolver",
            session_id="sess-001",
            domains_dir=domains_dir,
            dedup_dir=dedup_dir,
            journal_path=journal,
        )

        # Same prompt on different session
        result = process_prompt(
            prompt="Add requireAuth to the resolver",
            session_id="sess-002",
            domains_dir=domains_dir,
            dedup_dir=dedup_dir,
            journal_path=journal,
        )

        assert result is not None
        assert result["match_type"] == "first_hit"

    def test_empty_domains_dir_returns_none(self, tmp_path: Path) -> None:
        """If no domain manifests found, returns None."""
        from library_server.hooks.scripts.prompt_scan import process_prompt

        empty_domains = tmp_path / "empty-domains"
        empty_domains.mkdir()
        dedup_dir = tmp_path / "dedup"
        dedup_dir.mkdir()
        journal = tmp_path / "journal.jsonl"

        result = process_prompt(
            prompt="requireAuth should be applied",
            session_id="sess-001",
            domains_dir=empty_domains,
            dedup_dir=dedup_dir,
            journal_path=journal,
        )

        assert result is None

    def test_token_estimate_matches_manifest(self, tmp_path: Path) -> None:
        """Token estimate in result should come from the manifest."""
        from library_server.hooks.scripts.prompt_scan import process_prompt

        domains_dir = make_domains_dir(tmp_path)
        dedup_dir = tmp_path / "dedup"
        dedup_dir.mkdir()
        journal = tmp_path / "journal.jsonl"

        result = process_prompt(
            prompt="Add requireAuth to the resolver",
            session_id="sess-001",
            domains_dir=domains_dir,
            dedup_dir=dedup_dir,
            journal_path=journal,
        )

        # AUTH domain has token_estimate 380
        assert result["tokens"] == 380


# ---------------------------------------------------------------------------
# Tests: main() I/O contract
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_outputs_additional_context_on_match(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """main() outputs JSON with additionalContext when domain matched."""
        domains_dir = make_domains_dir(tmp_path)
        dedup_dir = tmp_path / "dedup"
        dedup_dir.mkdir()
        journal = tmp_path / "journal.jsonl"

        stdin_data = json.dumps({
            "session_id": "sess-001",
            "prompt": "Add requireAuth to the resolver",
            "domains_dir": str(domains_dir),
            "dedup_dir": str(dedup_dir),
            "journal_path": str(journal),
        })

        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        from library_server.hooks.scripts import prompt_scan
        prompt_scan.main()

        output_str = captured.getvalue().strip()
        assert output_str  # not empty
        output = json.loads(output_str)
        assert "hookSpecificOutput" in output
        assert "additionalContext" in output["hookSpecificOutput"]

    def test_main_silent_on_no_match(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """main() outputs nothing when no domain matched."""
        domains_dir = make_domains_dir(tmp_path)
        dedup_dir = tmp_path / "dedup"
        dedup_dir.mkdir()
        journal = tmp_path / "journal.jsonl"

        stdin_data = json.dumps({
            "session_id": "sess-001",
            "prompt": "Update the navigation bar color",
            "domains_dir": str(domains_dir),
            "dedup_dir": str(dedup_dir),
            "journal_path": str(journal),
        })

        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        from library_server.hooks.scripts import prompt_scan
        prompt_scan.main()

        output_str = captured.getvalue().strip()
        assert output_str == ""
