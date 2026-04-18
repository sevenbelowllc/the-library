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
    async def test_scan_uses_24h_jql_marker(self):
        """Negative-ish: proves the JQL the script sends is the 24h-aged pollution JQL."""
        client = AsyncMock()
        client.search_issues = AsyncMock(return_value={"issues": []})
        client.list_projects = AsyncMock(return_value={"values": []})

        await mod.scan(client)
        jql = client.search_issues.call_args[1]["jql"]
        assert "INTEGRATION-TEST" in jql
        assert "DELETE-ME" in jql
        assert "created < -24h" in jql
