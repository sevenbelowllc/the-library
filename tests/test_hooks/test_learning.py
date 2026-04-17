"""Tests for the auto-learning engine (routing journal, accuracy analysis, drift detection)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from library_server.types import RoutingOutcome


class TestLogRoutingDecision:
    """Tests for log_routing_decision."""

    def test_log_routing_decision_writes_entry(self, tmp_path: Path):
        """Verify entry is written to journal and required fields are present."""
        from library_server.hooks.learning import log_routing_decision

        journal = tmp_path / "routing.jsonl"
        log_routing_decision(
            journal_path=journal,
            session_id="sess-001",
            prompt_keywords=["risk", "assessment"],
            matched_domain="risk",
            match_type="keyword",
            injection_tokens=512,
        )

        assert journal.exists()
        lines = journal.read_text().strip().splitlines()
        assert len(lines) == 1

        entry = json.loads(lines[0])
        assert entry["session_id"] == "sess-001"
        assert entry["prompt_keywords"] == ["risk", "assessment"]
        assert entry["matched_domain"] == "risk"
        assert entry["match_type"] == "keyword"
        assert entry["injection_tokens"] == 512
        assert entry["outcome"] is None
        assert entry["outcome_signal"] == ""
        assert "timestamp" in entry

    def test_log_routing_decision_prompt_hash_not_empty(self, tmp_path: Path):
        """Verify prompt_hash is computed and non-empty."""
        from library_server.hooks.learning import log_routing_decision

        journal = tmp_path / "routing.jsonl"
        log_routing_decision(
            journal_path=journal,
            session_id="sess-002",
            prompt_keywords=["audit", "log"],
            matched_domain="audit",
            match_type="keyword",
            injection_tokens=256,
        )

        entry = json.loads(journal.read_text().strip())
        assert "prompt_hash" in entry
        assert len(entry["prompt_hash"]) == 12
        assert entry["prompt_hash"] != ""

    def test_log_routing_decision_appends_multiple(self, tmp_path: Path):
        """Multiple calls append entries; each is a separate line."""
        from library_server.hooks.learning import log_routing_decision

        journal = tmp_path / "routing.jsonl"
        for i in range(3):
            log_routing_decision(
                journal_path=journal,
                session_id=f"sess-{i:03d}",
                prompt_keywords=["keyword"],
                matched_domain="domain",
                match_type="keyword",
                injection_tokens=100,
            )

        lines = journal.read_text().strip().splitlines()
        assert len(lines) == 3


class TestUpdateRoutingOutcome:
    """Tests for update_routing_outcome."""

    def test_update_routing_outcome_sets_outcome(self, tmp_path: Path):
        """Log an entry then update it; outcome and signal must be set."""
        from library_server.hooks.learning import (
            log_routing_decision,
            read_journal,
            update_routing_outcome,
        )

        journal = tmp_path / "routing.jsonl"
        log_routing_decision(
            journal_path=journal,
            session_id="sess-upd",
            prompt_keywords=["control", "mapping"],
            matched_domain="controls",
            match_type="keyword",
            injection_tokens=300,
        )

        update_routing_outcome(
            journal_path=journal,
            session_id="sess-upd",
            outcome=RoutingOutcome.HIT,
            outcome_signal="user confirmed relevant",
        )

        entries = read_journal(journal)
        assert len(entries) == 1
        assert entries[0]["outcome"] == RoutingOutcome.HIT.value
        assert entries[0]["outcome_signal"] == "user confirmed relevant"

    def test_update_routing_outcome_targets_last_pending(self, tmp_path: Path):
        """Only the last pending entry for the session_id is updated."""
        from library_server.hooks.learning import (
            log_routing_decision,
            read_journal,
            update_routing_outcome,
        )

        journal = tmp_path / "routing.jsonl"
        # Log two entries for same session
        for _ in range(2):
            log_routing_decision(
                journal_path=journal,
                session_id="sess-multi",
                prompt_keywords=["evidence"],
                matched_domain="evidence",
                match_type="keyword",
                injection_tokens=200,
            )

        update_routing_outcome(
            journal_path=journal,
            session_id="sess-multi",
            outcome=RoutingOutcome.NOISE,
            outcome_signal="irrelevant injection",
        )

        entries = read_journal(journal)
        # First entry still None, second entry updated
        pending = [e for e in entries if e["outcome"] is None]
        updated = [e for e in entries if e["outcome"] == RoutingOutcome.NOISE.value]
        assert len(pending) == 1
        assert len(updated) == 1

    def test_update_routing_outcome_empty_journal(self, tmp_path: Path):
        """Updating a missing journal file is a no-op (line 76)."""
        from library_server.hooks.learning import update_routing_outcome

        journal = tmp_path / "nonexistent.jsonl"
        # Should return early without error
        update_routing_outcome(
            journal_path=journal,
            session_id="sess-ghost",
            outcome=RoutingOutcome.HIT,
            outcome_signal="no file",
        )
        assert not journal.exists()

    def test_update_routing_outcome_no_pending_entry(self, tmp_path: Path):
        """Updating when no pending entry exists for session_id is a no-op (line 86)."""
        from library_server.hooks.learning import (
            log_routing_decision,
            read_journal,
            update_routing_outcome,
        )

        journal = tmp_path / "routing.jsonl"
        log_routing_decision(
            journal_path=journal,
            session_id="sess-resolved",
            prompt_keywords=["test"],
            matched_domain="test",
            match_type="keyword",
            injection_tokens=100,
        )
        # Resolve it
        update_routing_outcome(
            journal_path=journal,
            session_id="sess-resolved",
            outcome=RoutingOutcome.HIT,
            outcome_signal="done",
        )
        # Try to update again — no pending entry for this session
        update_routing_outcome(
            journal_path=journal,
            session_id="sess-resolved",
            outcome=RoutingOutcome.MISS,
            outcome_signal="should not apply",
        )

        entries = read_journal(journal)
        assert len(entries) == 1
        # Original outcome unchanged
        assert entries[0]["outcome"] == RoutingOutcome.HIT.value
        assert entries[0]["outcome_signal"] == "done"


class TestReadJournal:
    """Tests for read_journal."""

    def test_read_journal_missing_file_returns_empty(self, tmp_path: Path):
        """Missing journal file returns empty list (no error)."""
        from library_server.hooks.learning import read_journal

        journal = tmp_path / "nonexistent.jsonl"
        result = read_journal(journal)
        assert result == []

    def test_read_journal_empty_file_returns_empty(self, tmp_path: Path):
        """Empty journal file returns empty list."""
        from library_server.hooks.learning import read_journal

        journal = tmp_path / "empty.jsonl"
        journal.write_text("")
        result = read_journal(journal)
        assert result == []

    def test_read_journal_returns_all_entries(self, tmp_path: Path):
        """read_journal returns all written entries in order."""
        from library_server.hooks.learning import log_routing_decision, read_journal

        journal = tmp_path / "routing.jsonl"
        for i in range(5):
            log_routing_decision(
                journal_path=journal,
                session_id=f"sess-{i}",
                prompt_keywords=["kw"],
                matched_domain="d",
                match_type="keyword",
                injection_tokens=10,
            )

        entries = read_journal(journal)
        assert len(entries) == 5
        assert entries[0]["session_id"] == "sess-0"
        assert entries[4]["session_id"] == "sess-4"


class TestAnalyzeRoutingAccuracy:
    """Tests for analyze_routing_accuracy."""

    def test_analyze_accuracy_correct(self, tmp_path: Path):
        """10 entries (8 HIT, 2 NOISE) for one domain → accuracy=0.8."""
        from library_server.hooks.learning import (
            analyze_routing_accuracy,
            log_routing_decision,
            update_routing_outcome,
        )

        journal = tmp_path / "routing.jsonl"

        for i in range(10):
            log_routing_decision(
                journal_path=journal,
                session_id=f"s{i}",
                prompt_keywords=["risk"],
                matched_domain="risk",
                match_type="keyword",
                injection_tokens=100,
            )
            outcome = RoutingOutcome.HIT if i < 8 else RoutingOutcome.NOISE
            update_routing_outcome(
                journal_path=journal,
                session_id=f"s{i}",
                outcome=outcome,
                outcome_signal="",
            )

        report = analyze_routing_accuracy(journal, min_observations=10)

        assert "risk" in report
        assert report["risk"]["accuracy"] == pytest.approx(0.8)
        assert report["risk"]["hits"] == 8
        assert report["risk"]["total"] == 10
        assert report["risk"]["noise_count"] == 2
        assert report["risk"]["misses_count"] == 0

    def test_analyze_insufficient_data_excluded(self, tmp_path: Path):
        """Domain with fewer entries than min_observations is not in report."""
        from library_server.hooks.learning import (
            analyze_routing_accuracy,
            log_routing_decision,
            update_routing_outcome,
        )

        journal = tmp_path / "routing.jsonl"
        log_routing_decision(
            journal_path=journal,
            session_id="only-one",
            prompt_keywords=["audit"],
            matched_domain="audit",
            match_type="keyword",
            injection_tokens=50,
        )
        update_routing_outcome(
            journal_path=journal,
            session_id="only-one",
            outcome=RoutingOutcome.HIT,
            outcome_signal="",
        )

        report = analyze_routing_accuracy(journal, min_observations=10)
        assert "audit" not in report

    def test_analyze_empty_journal(self, tmp_path: Path):
        """Empty journal returns empty dict."""
        from library_server.hooks.learning import analyze_routing_accuracy

        journal = tmp_path / "routing.jsonl"
        report = analyze_routing_accuracy(journal)
        assert report == {}

    def test_analyze_skips_unresolved_entries(self, tmp_path: Path):
        """Entries with outcome=None are excluded from analysis (line 145)."""
        from library_server.hooks.learning import (
            analyze_routing_accuracy,
            log_routing_decision,
            update_routing_outcome,
        )

        journal = tmp_path / "routing.jsonl"

        # Create 10 resolved entries
        for i in range(10):
            log_routing_decision(
                journal_path=journal,
                session_id=f"res-{i}",
                prompt_keywords=["controls"],
                matched_domain="controls",
                match_type="keyword",
                injection_tokens=100,
            )
            update_routing_outcome(
                journal_path=journal,
                session_id=f"res-{i}",
                outcome=RoutingOutcome.HIT,
                outcome_signal="",
            )

        # Create 5 unresolved entries (outcome stays None)
        for i in range(5):
            log_routing_decision(
                journal_path=journal,
                session_id=f"unres-{i}",
                prompt_keywords=["controls"],
                matched_domain="controls",
                match_type="keyword",
                injection_tokens=100,
            )

        report = analyze_routing_accuracy(journal, min_observations=10)
        assert "controls" in report
        # Only the 10 resolved entries count
        assert report["controls"]["total"] == 10
        assert report["controls"]["hits"] == 10


class TestDetectDrift:
    """Tests for detect_drift."""

    def test_detect_drift_flags_domain(self, tmp_path: Path):
        """20 old HITs followed by 10 recent NOISEs → drift detected."""
        from library_server.hooks.learning import (
            detect_drift,
            log_routing_decision,
            update_routing_outcome,
        )

        journal = tmp_path / "routing.jsonl"

        # 20 historical HITs
        for i in range(20):
            log_routing_decision(
                journal_path=journal,
                session_id=f"old-{i}",
                prompt_keywords=["vendor"],
                matched_domain="vendor",
                match_type="keyword",
                injection_tokens=100,
            )
            update_routing_outcome(
                journal_path=journal,
                session_id=f"old-{i}",
                outcome=RoutingOutcome.HIT,
                outcome_signal="",
            )

        # 10 recent NOISEs
        for i in range(10):
            log_routing_decision(
                journal_path=journal,
                session_id=f"new-{i}",
                prompt_keywords=["vendor"],
                matched_domain="vendor",
                match_type="keyword",
                injection_tokens=100,
            )
            update_routing_outcome(
                journal_path=journal,
                session_id=f"new-{i}",
                outcome=RoutingOutcome.NOISE,
                outcome_signal="",
            )

        drift_report = detect_drift(journal, window_entries=10, drop_threshold=0.4)

        assert len(drift_report) == 1
        item = drift_report[0]
        assert item["domain"] == "vendor"
        assert item["lifetime_accuracy"] > 0.5
        assert item["recent_accuracy"] < 0.4
        assert "recommendation" in item
        assert item["window_size"] == 10

    def test_detect_drift_no_drift_when_stable(self, tmp_path: Path):
        """Consistently high accuracy produces no drift entries."""
        from library_server.hooks.learning import (
            detect_drift,
            log_routing_decision,
            update_routing_outcome,
        )

        journal = tmp_path / "routing.jsonl"

        for i in range(30):
            log_routing_decision(
                journal_path=journal,
                session_id=f"stable-{i}",
                prompt_keywords=["policy"],
                matched_domain="policy",
                match_type="keyword",
                injection_tokens=100,
            )
            update_routing_outcome(
                journal_path=journal,
                session_id=f"stable-{i}",
                outcome=RoutingOutcome.HIT,
                outcome_signal="",
            )

        drift_report = detect_drift(journal, window_entries=10, drop_threshold=0.4)
        assert drift_report == []

    def test_detect_drift_empty_journal(self, tmp_path: Path):
        """Empty journal returns empty drift list."""
        from library_server.hooks.learning import detect_drift

        journal = tmp_path / "routing.jsonl"
        assert detect_drift(journal) == []

    def test_detect_drift_skips_unresolved_entries(self, tmp_path: Path):
        """Unresolved entries (outcome=None) are excluded from drift analysis (line 208)."""
        from library_server.hooks.learning import (
            detect_drift,
            log_routing_decision,
            update_routing_outcome,
        )

        journal = tmp_path / "routing.jsonl"

        # 20 resolved HITs
        for i in range(20):
            log_routing_decision(
                journal_path=journal,
                session_id=f"hit-{i}",
                prompt_keywords=["vendor"],
                matched_domain="vendor",
                match_type="keyword",
                injection_tokens=100,
            )
            update_routing_outcome(
                journal_path=journal,
                session_id=f"hit-{i}",
                outcome=RoutingOutcome.HIT,
                outcome_signal="",
            )

        # 10 unresolved entries — should be ignored
        for i in range(10):
            log_routing_decision(
                journal_path=journal,
                session_id=f"pending-{i}",
                prompt_keywords=["vendor"],
                matched_domain="vendor",
                match_type="keyword",
                injection_tokens=100,
            )

        # No drift because unresolved entries are skipped
        drift_report = detect_drift(journal, window_entries=10, drop_threshold=0.4)
        assert drift_report == []

    def test_detect_drift_skips_low_lifetime_accuracy(self, tmp_path: Path):
        """Domain with lifetime accuracy <= 0.5 is skipped (line 225)."""
        from library_server.hooks.learning import (
            detect_drift,
            log_routing_decision,
            update_routing_outcome,
        )

        journal = tmp_path / "routing.jsonl"

        # Create domain with exactly 50% lifetime accuracy (5 HIT, 5 NOISE)
        for i in range(10):
            log_routing_decision(
                journal_path=journal,
                session_id=f"low-{i}",
                prompt_keywords=["fragile"],
                matched_domain="fragile",
                match_type="keyword",
                injection_tokens=100,
            )
            outcome = RoutingOutcome.HIT if i < 5 else RoutingOutcome.NOISE
            update_routing_outcome(
                journal_path=journal,
                session_id=f"low-{i}",
                outcome=outcome,
                outcome_signal="",
            )

        # lifetime_accuracy == 0.5, which is <= 0.5 → skipped
        drift_report = detect_drift(journal, window_entries=5, drop_threshold=0.4)
        assert drift_report == []

    def test_detect_drift_at_exact_threshold_boundary(self, tmp_path: Path):
        """Recent accuracy exactly at drop_threshold does NOT trigger drift."""
        from library_server.hooks.learning import (
            detect_drift,
            log_routing_decision,
            update_routing_outcome,
        )

        journal = tmp_path / "routing.jsonl"

        # 20 HITs for high lifetime accuracy
        for i in range(20):
            log_routing_decision(
                journal_path=journal,
                session_id=f"good-{i}",
                prompt_keywords=["policy"],
                matched_domain="policy",
                match_type="keyword",
                injection_tokens=100,
            )
            update_routing_outcome(
                journal_path=journal,
                session_id=f"good-{i}",
                outcome=RoutingOutcome.HIT,
                outcome_signal="",
            )

        # 10 recent: 4 HIT, 6 NOISE → recent_accuracy = 0.4 (exactly at threshold)
        for i in range(10):
            log_routing_decision(
                journal_path=journal,
                session_id=f"recent-{i}",
                prompt_keywords=["policy"],
                matched_domain="policy",
                match_type="keyword",
                injection_tokens=100,
            )
            outcome = RoutingOutcome.HIT if i < 4 else RoutingOutcome.NOISE
            update_routing_outcome(
                journal_path=journal,
                session_id=f"recent-{i}",
                outcome=outcome,
                outcome_signal="",
            )

        # recent_accuracy == 0.4, drop_threshold == 0.4 → NOT < threshold → no drift
        drift_report = detect_drift(journal, window_entries=10, drop_threshold=0.4)
        assert drift_report == []
