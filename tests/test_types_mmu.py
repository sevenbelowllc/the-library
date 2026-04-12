"""Tests for MMU types: DomainFile, RoutingEntry, RoutingOutcome, ProjectStateData, SessionStateData."""

from __future__ import annotations

import pytest

from library_server.types import (
    DomainFile,
    ProjectStateData,
    RoutingEntry,
    RoutingOutcome,
    SessionStateData,
)


# ---------------------------------------------------------------------------
# RoutingOutcome
# ---------------------------------------------------------------------------


class TestRoutingOutcome:
    def test_all_values_exist(self):
        values = {o.value for o in RoutingOutcome}
        assert values == {"hit", "noise", "miss", "missed_trigger", "correct_silence"}

    def test_from_value(self):
        assert RoutingOutcome("hit") is RoutingOutcome.HIT
        assert RoutingOutcome("noise") is RoutingOutcome.NOISE
        assert RoutingOutcome("miss") is RoutingOutcome.MISS
        assert RoutingOutcome("missed_trigger") is RoutingOutcome.MISSED_TRIGGER
        assert RoutingOutcome("correct_silence") is RoutingOutcome.CORRECT_SILENCE

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            RoutingOutcome("unknown")


# ---------------------------------------------------------------------------
# DomainFile
# ---------------------------------------------------------------------------


class TestDomainFile:
    def test_minimal_construction(self):
        df = DomainFile(domain="auth")
        assert df.domain == "auth"
        assert df.starter_keywords == []
        assert df.learned_keywords == []
        assert df.starter_excludes == []
        assert df.learned_excludes == []
        assert df.match_threshold == 1
        assert df.token_estimate == 500
        assert df.last_updated == ""

    def test_full_construction(self):
        df = DomainFile(
            domain="billing",
            starter_keywords=["stripe", "invoice"],
            learned_keywords=["subscription"],
            starter_excludes=["test"],
            learned_excludes=["mock"],
            match_threshold=2,
            token_estimate=800,
            last_updated="2026-04-11",
        )
        assert df.domain == "billing"
        assert df.match_threshold == 2
        assert df.token_estimate == 800
        assert df.last_updated == "2026-04-11"

    def test_all_keywords_property(self):
        df = DomainFile(
            domain="auth",
            starter_keywords=["jwt", "clerk"],
            learned_keywords=["session", "token"],
        )
        assert df.all_keywords == ["jwt", "clerk", "session", "token"]

    def test_all_keywords_empty(self):
        df = DomainFile(domain="auth")
        assert df.all_keywords == []

    def test_all_excludes_property(self):
        df = DomainFile(
            domain="auth",
            starter_excludes=["mock"],
            learned_excludes=["test", "fixture"],
        )
        assert df.all_excludes == ["mock", "test", "fixture"]

    def test_all_excludes_empty(self):
        df = DomainFile(domain="auth")
        assert df.all_excludes == []

    def test_mutable_defaults_are_independent(self):
        """Verify dataclass field() factories don't share state between instances."""
        df1 = DomainFile(domain="a")
        df2 = DomainFile(domain="b")
        df1.starter_keywords.append("shared?")
        assert df2.starter_keywords == []

    def test_all_keywords_order_preserved(self):
        df = DomainFile(
            domain="x",
            starter_keywords=["alpha", "beta"],
            learned_keywords=["gamma"],
        )
        assert df.all_keywords == ["alpha", "beta", "gamma"]


# ---------------------------------------------------------------------------
# RoutingEntry
# ---------------------------------------------------------------------------


class TestRoutingEntry:
    def _make(self, **kwargs) -> RoutingEntry:
        defaults = dict(
            timestamp="2026-04-11T10:00:00Z",
            session_id="sess-001",
            prompt_hash="abc123",
            prompt_keywords=["auth", "jwt"],
            matched_domain="auth",
            match_type="keyword",
        )
        defaults.update(kwargs)
        return RoutingEntry(**defaults)

    def test_minimal_construction(self):
        entry = self._make()
        assert entry.injection_tokens == 0
        assert entry.outcome is None
        assert entry.outcome_signal == ""

    def test_full_construction(self):
        entry = self._make(
            injection_tokens=450,
            outcome=RoutingOutcome.HIT,
            outcome_signal="user confirmed",
        )
        assert entry.injection_tokens == 450
        assert entry.outcome is RoutingOutcome.HIT
        assert entry.outcome_signal == "user confirmed"

    def test_matched_domain_none(self):
        entry = self._make(matched_domain=None)
        assert entry.matched_domain is None

    def test_prompt_keywords_list(self):
        entry = self._make(prompt_keywords=["stripe", "billing", "invoice"])
        assert len(entry.prompt_keywords) == 3
        assert "stripe" in entry.prompt_keywords

    def test_outcome_all_enum_values_assignable(self):
        for outcome in RoutingOutcome:
            entry = self._make(outcome=outcome)
            assert entry.outcome is outcome

    def test_mutable_defaults_are_independent(self):
        entry1 = self._make()
        entry2 = self._make()
        entry1.prompt_keywords.append("extra")
        # prompt_keywords is passed explicitly so these are distinct lists anyway
        assert "extra" not in entry2.prompt_keywords


# ---------------------------------------------------------------------------
# ProjectStateData
# ---------------------------------------------------------------------------


class TestProjectStateData:
    def test_minimal_construction(self):
        ps = ProjectStateData(project="COS")
        assert ps.project == "COS"
        assert ps.focus == ""
        assert ps.active_task == ""
        assert ps.blockers == []
        assert ps.invariants == []
        assert ps.pm_projects == []
        assert ps.recent_decisions == []
        assert ps.session_count == 0
        assert ps.vault_file_count == 0
        assert ps.domain_count == 0
        assert ps.decision_count == 0
        assert ps.claude_md_lines == 0
        assert ps.keyword_accuracy == 0.0
        assert ps.keyword_observations == 0

    def test_full_construction(self):
        ps = ProjectStateData(
            project="COS",
            focus="MVP auth",
            active_task="COS-42",
            blockers=["missing DB migration"],
            invariants=["RLS must be enforced"],
            pm_projects=[{"key": "COS", "name": "Compliance OS"}],
            recent_decisions=[{"date": "2026-04-10", "text": "Use Clerk"}],
            session_count=10,
            vault_file_count=3220,
            domain_count=8,
            decision_count=15,
            claude_md_lines=200,
            keyword_accuracy=0.87,
            keyword_observations=50,
        )
        assert ps.session_count == 10
        assert ps.vault_file_count == 3220
        assert ps.keyword_accuracy == 0.87

    def test_mutable_defaults_are_independent(self):
        ps1 = ProjectStateData(project="A")
        ps2 = ProjectStateData(project="B")
        ps1.blockers.append("blocker-1")
        assert ps2.blockers == []

    def test_keyword_accuracy_float_precision(self):
        ps = ProjectStateData(project="X", keyword_accuracy=0.123456)
        assert abs(ps.keyword_accuracy - 0.123456) < 1e-9


# ---------------------------------------------------------------------------
# SessionStateData
# ---------------------------------------------------------------------------


class TestSessionStateData:
    def test_minimal_construction(self):
        ss = SessionStateData(session_id="sess-001")
        assert ss.session_id == "sess-001"
        assert ss.task == ""
        assert ss.doing == ""
        assert ss.branch == "main"
        assert ss.resume_instructions == []
        assert ss.decisions == []
        assert ss.files_touched == []
        assert ss.domains_loaded == []
        assert ss.turns == 0
        assert ss.context_usage == 0.0
        assert ss.started == ""
        assert ss.last_updated == ""

    def test_full_construction(self):
        ss = SessionStateData(
            session_id="sess-042",
            task="COS-99",
            doing="implementing auth middleware",
            branch="feat/mmu",
            resume_instructions=["Continue from step 3", "Check test output"],
            decisions=["Use httpx for HTTP client"],
            files_touched=["src/auth.py", "tests/test_auth.py"],
            domains_loaded=["auth", "billing"],
            turns=15,
            context_usage=0.48,
            started="2026-04-11T09:00:00Z",
            last_updated="2026-04-11T11:30:00Z",
        )
        assert ss.session_id == "sess-042"
        assert ss.branch == "feat/mmu"
        assert ss.turns == 15
        assert ss.context_usage == 0.48
        assert len(ss.domains_loaded) == 2

    def test_mutable_defaults_are_independent(self):
        ss1 = SessionStateData(session_id="a")
        ss2 = SessionStateData(session_id="b")
        ss1.files_touched.append("file.py")
        assert ss2.files_touched == []

    def test_context_usage_boundary_values(self):
        for val in (0.0, 0.5, 1.0):
            ss = SessionStateData(session_id="x", context_usage=val)
            assert ss.context_usage == val
