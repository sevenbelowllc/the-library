"""Tests for the bin/library-pm-pollution-scan filter logic.

The script lives under bin/ so we load it as a module by path and exercise
its pure filter functions against fixture JSON shaped like the Jira REST
response.
"""

from __future__ import annotations

import importlib.util
import importlib.machinery
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "library-pm-pollution-scan"


def _load_module():
    # The bin/ script has no .py extension; use SourceFileLoader explicitly.
    loader = importlib.machinery.SourceFileLoader("_pollution_scan", str(_SCRIPT))
    spec = importlib.util.spec_from_loader("_pollution_scan", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    # @dataclass resolves type annotations through sys.modules[cls.__module__];
    # register the module before exec so that resolution succeeds.
    sys.modules["_pollution_scan"] = mod
    loader.exec_module(mod)
    return mod


mod = _load_module()


# ---------------------------------------------------------------------------
# filter_polluted_projects
# ---------------------------------------------------------------------------


class TestFilterPollutedProjects:
    def test_matches_zzt_prefix(self):
        resp = {
            "values": [
                {"key": "ZZTABCD", "name": "whatever"},
                {"key": "COS", "name": "Main project"},
            ]
        }
        out = mod.filter_polluted_projects(resp)
        assert [p["key"] for p in out] == ["ZZTABCD"]

    def test_matches_integration_test_in_name(self):
        resp = {
            "values": [
                {"key": "ABC", "name": "INTEGRATION-TEST-DELETE-ME-123"},
                {"key": "XYZ", "name": "Real Project"},
            ]
        }
        out = mod.filter_polluted_projects(resp)
        assert [p["key"] for p in out] == ["ABC"]

    def test_matches_delete_me_in_name_case_insensitive(self):
        resp = {"values": [{"key": "ABC", "name": "please-delete-me"}]}
        out = mod.filter_polluted_projects(resp)
        assert len(out) == 1

    def test_returns_empty_when_no_matches(self):
        """Negative: the filter must NOT match innocuous projects."""
        resp = {
            "values": [
                {"key": "COS", "name": "Compliance OS"},
                {"key": "LIBRARY", "name": "The Library"},
                {"key": "DEIOCAP", "name": "Data Eng Capstone"},
            ]
        }
        assert mod.filter_polluted_projects(resp) == []

    def test_empty_values_key(self):
        assert mod.filter_polluted_projects({}) == []
        assert mod.filter_polluted_projects({"values": []}) == []


# ---------------------------------------------------------------------------
# filter_polluted_issues
# ---------------------------------------------------------------------------


class TestFilterPollutedIssues:
    def test_returns_issues_list(self):
        resp = {
            "issues": [
                {"key": "DEIOCAP-1", "fields": {"summary": "INTEGRATION-TEST foo"}},
                {"key": "DEIOCAP-2", "fields": {"summary": "DELETE-ME bar"}},
            ]
        }
        out = mod.filter_polluted_issues(resp)
        assert len(out) == 2
        assert out[0]["key"] == "DEIOCAP-1"

    def test_empty(self):
        assert mod.filter_polluted_issues({}) == []
        assert mod.filter_polluted_issues({"issues": []}) == []


# ---------------------------------------------------------------------------
# scan() — ties search_issues + list_projects together
# ---------------------------------------------------------------------------


class TestScan:
    @pytest.mark.asyncio
    async def test_scan_combines_search_and_list(self):
        client = AsyncMock()
        client.search_issues = AsyncMock(
            return_value={
                "issues": [
                    {"key": "DEIOCAP-1", "fields": {"summary": "INTEGRATION-TEST a"}}
                ]
            }
        )
        # Single page with <50 results to terminate the pagination loop.
        client.list_projects = AsyncMock(
            return_value={
                "values": [
                    {"key": "ZZTABCD", "name": "junk"},
                    {"key": "COS", "name": "Real project"},
                ]
            }
        )
        report = await mod.scan(client)
        assert report.ticket_count == 1
        assert report.project_count == 1
        assert report.projects[0]["key"] == "ZZTABCD"

    @pytest.mark.asyncio
    async def test_scan_paginates_projects(self):
        """list_projects pagination continues while full pages come back."""
        client = AsyncMock()
        client.search_issues = AsyncMock(return_value={"issues": []})

        page1 = {"values": [{"key": f"P{i}", "name": "x"} for i in range(50)]}
        page2 = {"values": [{"key": "ZZTEND", "name": "y"}]}
        client.list_projects = AsyncMock(side_effect=[page1, page2])

        report = await mod.scan(client)
        # Only ZZTEND matches pollution filter
        assert report.project_count == 1
        assert client.list_projects.await_count == 2

    @pytest.mark.asyncio
    async def test_scan_default_has_no_age_filter(self):
        """Default min_age_hours=0 so scan finds same-session garbage."""
        client = AsyncMock()
        client.search_issues = AsyncMock(return_value={"issues": []})
        client.list_projects = AsyncMock(return_value={"values": []})

        await mod.scan(client)
        jql = client.search_issues.call_args[1]["jql"]
        assert "INTEGRATION-TEST" in jql
        assert "DELETE-ME" in jql
        assert "created < -" not in jql

    @pytest.mark.asyncio
    async def test_scan_honors_min_age_hours(self):
        """Passing min_age_hours adds the age clause."""
        client = AsyncMock()
        client.search_issues = AsyncMock(return_value={"issues": []})
        client.list_projects = AsyncMock(return_value={"values": []})

        await mod.scan(client, min_age_hours=24)
        jql = client.search_issues.call_args[1]["jql"]
        assert "created < -24h" in jql


# ---------------------------------------------------------------------------
# _is_polluted_summary — precision filter
# ---------------------------------------------------------------------------


class TestPrecisionSummaryFilter:
    """The summary must START with a pollution marker — substring alone is not
    enough. Regression: LIBRARY-7 "Fix integration-test cleanup" was matched by
    the JQL `~` operator and would have been deleted by an earlier version."""

    def test_matches_delete_me_prefix(self):
        assert mod._is_polluted_summary("INTEGRATION-TEST-DELETE-ME RMBQ")

    def test_matches_link_prefixes(self):
        assert mod._is_polluted_summary("INTEGRATION-TEST-LINK-A XYZQ")
        assert mod._is_polluted_summary("INTEGRATION-TEST-LINK-B ABCD")

    def test_matches_case_insensitively(self):
        assert mod._is_polluted_summary("integration-test-delete-me abcd")

    def test_rejects_substring_in_real_ticket_summary(self):
        """The canonical false-positive that motivated this filter."""
        assert not mod._is_polluted_summary(
            "Fix integration-test cleanup + purge existing pollution"
        )

    def test_rejects_marker_mid_sentence(self):
        assert not mod._is_polluted_summary("Add tests for DELETE-ME behaviour")

    def test_rejects_similar_but_different_prefix(self):
        """``INTEGRATION-TESTING`` is not a pollution marker — only the exact
        ``INTEGRATION-TEST-*`` forms are."""
        assert not mod._is_polluted_summary("INTEGRATION-TESTING-LIBRARY-SCRATCH")


# ---------------------------------------------------------------------------
# main() safety guards — --yes requires --confirm-count, --max-deletions cap
# ---------------------------------------------------------------------------


class TestSafetyGuards:
    """End-to-end tests of the main() confirmation layer. No live Jira."""

    def _stub_jira(self, monkeypatch, report):
        """Patch scan() and JiraClient so main() runs without network."""
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")

        async def fake_scan(client, *, min_age_hours=0):
            return report

        monkeypatch.setattr(mod, "scan", fake_scan)

        class _StubClient:
            def __init__(self, *a, **kw):
                pass

            async def delete_issue(self, key):
                pass

            async def delete_project(self, key):
                pass

        monkeypatch.setattr(mod, "JiraClient", _StubClient)

    def _report(self, tickets: int, projects: int = 0):
        return mod.PollutionReport(
            tickets=[{"key": f"X-{i}", "fields": {"summary": "INTEGRATION-TEST-DELETE-ME X"}} for i in range(tickets)],
            projects=[{"key": f"ZZT{i:03d}", "name": f"P{i}"} for i in range(projects)],
        )

    def test_yes_without_confirm_count_refuses(self, monkeypatch, capsys):
        self._stub_jira(monkeypatch, self._report(5))
        rc = mod.main(["--execute", "--yes"])
        err = capsys.readouterr().err
        assert rc == 2
        assert "--confirm-count" in err

    def test_yes_with_wrong_count_refuses(self, monkeypatch, capsys):
        self._stub_jira(monkeypatch, self._report(5))
        rc = mod.main(["--execute", "--yes", "--confirm-count", "999"])
        err = capsys.readouterr().err
        assert rc == 2
        assert "does not match" in err
        assert "5" in err  # the actual count is shown

    def test_yes_with_matching_count_proceeds(self, monkeypatch, capsys):
        self._stub_jira(monkeypatch, self._report(5))
        rc = mod.main(["--execute", "--yes", "--confirm-count", "5"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "confirm-count matches" in out

    def test_max_deletions_ceiling_aborts(self, monkeypatch, capsys):
        self._stub_jira(monkeypatch, self._report(1000))
        rc = mod.main(["--execute", "--yes", "--confirm-count", "1000"])
        err = capsys.readouterr().err
        assert rc == 2
        assert "max-deletions" in err

    def test_max_deletions_ceiling_raisable(self, monkeypatch, capsys):
        self._stub_jira(monkeypatch, self._report(1000))
        rc = mod.main(["--execute", "--yes", "--confirm-count", "1000", "--max-deletions", "2000"])
        assert rc == 0

    def test_interactive_requires_exact_typed_phrase(self, monkeypatch, capsys):
        self._stub_jira(monkeypatch, self._report(3, 1))
        monkeypatch.setattr("builtins.input", lambda _: "wrong phrase")
        rc = mod.main(["--execute"])
        assert rc == 1
        out = capsys.readouterr().out
        assert "did not match" in out.lower() or "Confirmation" in out

    def test_interactive_accepts_correct_phrase(self, monkeypatch):
        self._stub_jira(monkeypatch, self._report(3, 1))
        monkeypatch.setattr("builtins.input", lambda _: "DELETE 3 tickets and 1 projects")
        rc = mod.main(["--execute"])
        assert rc == 0

    def test_dry_run_never_calls_purge(self, monkeypatch, capsys):
        self._stub_jira(monkeypatch, self._report(10))
        # Should not raise even though no confirmation was given
        rc = mod.main([])  # no --execute
        assert rc == 0
        out = capsys.readouterr().out
        assert "dry-run" in out.lower()

    def test_report_printed_before_confirmation(self, monkeypatch, capsys):
        """The user must see what's about to be deleted BEFORE being asked
        to confirm — the core of 'confirmation with output report'."""
        self._stub_jira(monkeypatch, self._report(2))
        monkeypatch.setattr("builtins.input", lambda _: "DELETE 2 tickets and 0 projects")
        mod.main(["--execute"])
        out = capsys.readouterr().out
        # Report banner appears before the destructive-action banner
        report_idx = out.index("Pollution scan result")
        action_idx = out.index("DESTRUCTIVE ACTION")
        assert report_idx < action_idx, "report must print before confirmation prompt"
