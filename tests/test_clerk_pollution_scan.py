"""Tests for bin/library-clerk-pollution-scan — Clerk test-user/org purge tool.

Script has no .py extension so we load it as a module by path, then exercise
its pure filter functions against fixture JSON and its main() flow against a
stub httpx client.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "library-clerk-pollution-scan"


def _load_module():
    loader = importlib.machinery.SourceFileLoader("_clerk_pollution_scan", str(_SCRIPT))
    spec = importlib.util.spec_from_loader("_clerk_pollution_scan", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_clerk_pollution_scan"] = mod
    loader.exec_module(mod)
    return mod


mod = _load_module()


# ---------------------------------------------------------------------------
# Precision email filter — regression: marker must be a PREFIX, not substring
# ---------------------------------------------------------------------------


class TestPollutedEmailFilter:
    def test_matches_e2e_dash_prefix(self):
        assert mod._is_polluted_email("e2e-owner-1234567890@sevenbelow.com")

    def test_matches_e2e_dot_prefix(self):
        assert mod._is_polluted_email("e2e.admin@sevenbelow.com")

    def test_matches_e2e_underscore_prefix(self):
        assert mod._is_polluted_email("e2e_employee@sevenbelow.com")

    def test_matches_e2etest_prefix(self):
        assert mod._is_polluted_email("e2etest1@sevenbelow.com")

    def test_matches_case_insensitively(self):
        assert mod._is_polluted_email("E2E-OWNER@SEVENBELOW.COM")

    def test_rejects_substring_in_real_user_email(self):
        """Canonical false-positive we must NOT purge."""
        assert not mod._is_polluted_email("bob.e2easton@real.com")

    def test_rejects_marker_mid_local_part(self):
        assert not mod._is_polluted_email("charlie-e2e-notes@sevenbelow.com")

    def test_rejects_empty_email(self):
        assert not mod._is_polluted_email("")

    def test_rejects_similar_but_different_prefix(self):
        assert not mod._is_polluted_email("e2easy@real.com")


class TestPollutedOrgFilter:
    def test_matches_e2e_dash_prefix(self):
        assert mod._is_polluted_org("e2e-tenant-1234567890")

    def test_matches_e2e_tenant_phrase(self):
        assert mod._is_polluted_org("e2e tenant alpha")

    def test_matches_case_insensitively(self):
        assert mod._is_polluted_org("E2E-TENANT-DEMO")

    def test_rejects_substring_in_real_org(self):
        assert not mod._is_polluted_org("E2E Design — Consulting Partner")

    def test_rejects_empty_name(self):
        assert not mod._is_polluted_org("")


# ---------------------------------------------------------------------------
# primary_email — Clerk user shape
# ---------------------------------------------------------------------------


class TestPrimaryEmail:
    def test_returns_primary_email(self):
        user = {
            "primary_email_address_id": "eml_b",
            "email_addresses": [
                {"id": "eml_a", "email_address": "alt@x.com"},
                {"id": "eml_b", "email_address": "primary@x.com"},
            ],
        }
        assert mod._primary_email(user) == "primary@x.com"

    def test_falls_back_to_first_email(self):
        user = {"email_addresses": [{"id": "eml_x", "email_address": "only@x.com"}]}
        assert mod._primary_email(user) == "only@x.com"

    def test_empty_when_no_emails(self):
        assert mod._primary_email({"email_addresses": []}) == ""
        assert mod._primary_email({}) == ""


# ---------------------------------------------------------------------------
# Age filter
# ---------------------------------------------------------------------------


class TestAgeFilter:
    def test_zero_hours_matches_everything(self):
        now_ms = int(time.time() * 1000)
        assert mod._is_older_than(now_ms, 0)

    def test_rejects_younger_than_threshold(self):
        one_hour_ago_ms = int((time.time() - 1 * 3600) * 1000)
        assert not mod._is_older_than(one_hour_ago_ms, 6)

    def test_accepts_older_than_threshold(self):
        seven_hours_ago_ms = int((time.time() - 7 * 3600) * 1000)
        assert mod._is_older_than(seven_hours_ago_ms, 6)

    def test_missing_timestamp_defaults_to_old(self):
        """Missing created_at shouldn't block a purge — treat as old."""
        assert mod._is_older_than(None, 24)


# ---------------------------------------------------------------------------
# filter_polluted_users — combines email + age
# ---------------------------------------------------------------------------


class TestFilterPollutedUsers:
    def _user(self, email: str, age_hours: float = 99):
        return {
            "id": f"user_{email}",
            "primary_email_address_id": "e1",
            "email_addresses": [{"id": "e1", "email_address": email}],
            "created_at": int((time.time() - age_hours * 3600) * 1000),
        }

    def test_returns_only_e2e_prefixed_emails(self):
        users = [
            self._user("e2e-owner-1@sevenbelow.com"),
            self._user("real.user@sevenbelow.com"),
            self._user("e2e-admin-2@sevenbelow.com"),
        ]
        out = mod.filter_polluted_users(users, min_age_hours=0)
        assert {u["id"] for u in out} == {"user_e2e-owner-1@sevenbelow.com",
                                           "user_e2e-admin-2@sevenbelow.com"}

    def test_excludes_fresh_users_when_age_gate(self):
        users = [
            self._user("e2e-old@sevenbelow.com", age_hours=10),
            self._user("e2e-fresh@sevenbelow.com", age_hours=0.1),
        ]
        out = mod.filter_polluted_users(users, min_age_hours=6)
        assert [u["id"] for u in out] == ["user_e2e-old@sevenbelow.com"]


# ---------------------------------------------------------------------------
# Async scan — stubs Clerk httpx responses
# ---------------------------------------------------------------------------


class TestScan:
    def _client_with_pages(self, users_pages, orgs_pages):
        """Make a stub httpx.AsyncClient whose .get yields the given pages in order."""
        call_log = []

        async def get(path, params=None):
            call_log.append((path, params))
            if path == "/users":
                idx = (params or {}).get("offset", 0) // (params or {}).get("limit", 500)
                page = users_pages[idx] if idx < len(users_pages) else []
            elif path == "/organizations":
                idx = (params or {}).get("offset", 0) // (params or {}).get("limit", 500)
                page = orgs_pages[idx] if idx < len(orgs_pages) else []
            else:
                page = []
            r = MagicMock()
            r.status_code = 200
            r.json = lambda: page
            r.raise_for_status = lambda: None
            return r

        client = MagicMock()
        client.get = AsyncMock(side_effect=get)
        client._calls = call_log
        return client

    @pytest.mark.asyncio
    async def test_scan_single_page(self):
        users = [
            {"id": "u1", "primary_email_address_id": "e",
             "email_addresses": [{"id": "e", "email_address": "e2e-a@x.com"}],
             "created_at": 0},
            {"id": "u2", "primary_email_address_id": "e",
             "email_addresses": [{"id": "e", "email_address": "real@x.com"}],
             "created_at": 0},
        ]
        orgs = [{"id": "org_a", "name": "e2e-tenant-1", "created_at": 0}]
        client = self._client_with_pages([users], [orgs])

        report = await mod.scan(client)
        assert report.user_count == 1
        assert report.users[0]["id"] == "u1"
        assert report.org_count == 1

    @pytest.mark.asyncio
    async def test_scan_paginates(self):
        """500 users returned → scan must fetch a second page and keep going."""
        full_page = [
            {"id": f"u{i}", "primary_email_address_id": "e",
             "email_addresses": [{"id": "e", "email_address": f"e2e-{i}@x.com"}],
             "created_at": 0}
            for i in range(500)
        ]
        tail = [
            {"id": "u500", "primary_email_address_id": "e",
             "email_addresses": [{"id": "e", "email_address": "e2e-last@x.com"}],
             "created_at": 0}
        ]
        client = self._client_with_pages([full_page, tail], [[]])

        report = await mod.scan(client)
        assert report.user_count == 501
        # /users hit twice — once for offset=0, once for offset=500 — plus orgs once.
        user_calls = [c for c in client._calls if c[0] == "/users"]
        assert len(user_calls) == 2


# ---------------------------------------------------------------------------
# main() safety guards
# ---------------------------------------------------------------------------


class TestSafetyGuards:
    def _stub_api(self, monkeypatch, report):
        monkeypatch.setenv("CLERK_SECRET_KEY", "test-secret")

        async def fake_scan(client, *, min_age_hours=0):
            return report

        monkeypatch.setattr(mod, "scan", fake_scan)

        class _StubClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                pass

            async def delete(self, *a, **k):
                r = MagicMock()
                r.status_code = 204
                r.text = ""
                return r

        monkeypatch.setattr(mod.httpx, "AsyncClient", lambda *a, **k: _StubClient())

    def _report(self, n_users: int = 0, n_orgs: int = 0):
        users = [{"id": f"u{i}",
                  "primary_email_address_id": "e",
                  "email_addresses": [{"id": "e", "email_address": f"e2e-{i}@x.com"}]}
                 for i in range(n_users)]
        orgs = [{"id": f"org_{i}", "name": f"e2e-tenant-{i}"} for i in range(n_orgs)]
        return mod.PollutionReport(users=users, orgs=orgs)

    def test_missing_secret_aborts(self, monkeypatch, capsys):
        monkeypatch.delenv("CLERK_SECRET_KEY", raising=False)
        rc = mod.main([])
        err = capsys.readouterr().err
        assert rc == 2
        assert "CLERK_SECRET_KEY" in err

    def test_yes_without_confirm_count_refuses(self, monkeypatch, capsys):
        self._stub_api(monkeypatch, self._report(n_users=5))
        rc = mod.main(["--execute", "--yes"])
        err = capsys.readouterr().err
        assert rc == 2
        assert "--confirm-count" in err

    def test_yes_with_wrong_count_refuses(self, monkeypatch, capsys):
        self._stub_api(monkeypatch, self._report(n_users=5))
        rc = mod.main(["--execute", "--yes", "--confirm-count", "999"])
        err = capsys.readouterr().err
        assert rc == 2
        assert "!= scan total 5" in err

    def test_yes_with_matching_count_proceeds(self, monkeypatch, capsys):
        self._stub_api(monkeypatch, self._report(n_users=3, n_orgs=2))
        rc = mod.main(["--execute", "--yes", "--confirm-count", "5"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "confirm-count matches" in out

    def test_max_deletions_ceiling_aborts(self, monkeypatch, capsys):
        self._stub_api(monkeypatch, self._report(n_users=600))
        rc = mod.main(["--execute", "--yes", "--confirm-count", "600"])
        err = capsys.readouterr().err
        assert rc == 2
        assert "max-deletions" in err

    def test_max_deletions_raisable(self, monkeypatch, capsys):
        self._stub_api(monkeypatch, self._report(n_users=600))
        rc = mod.main(["--execute", "--yes", "--confirm-count", "600", "--max-deletions", "1000"])
        assert rc == 0

    def test_interactive_typed_phrase_required(self, monkeypatch, capsys):
        self._stub_api(monkeypatch, self._report(n_users=3, n_orgs=1))
        monkeypatch.setattr("builtins.input", lambda _: "wrong phrase")
        rc = mod.main(["--execute"])
        out = capsys.readouterr().out
        assert rc == 1
        assert "did not match" in out.lower() or "Aborting" in out

    def test_interactive_correct_phrase_proceeds(self, monkeypatch):
        self._stub_api(monkeypatch, self._report(n_users=2, n_orgs=1))
        monkeypatch.setattr("builtins.input", lambda _: "DELETE 2 users and 1 orgs")
        rc = mod.main(["--execute"])
        assert rc == 0

    def test_dry_run_never_calls_purge(self, monkeypatch, capsys):
        self._stub_api(monkeypatch, self._report(n_users=10))
        rc = mod.main([])  # no --execute
        out = capsys.readouterr().out
        assert rc == 0
        assert "dry-run" in out.lower()

    def test_report_printed_before_confirmation(self, monkeypatch, capsys):
        """Users must see what's about to be deleted BEFORE being asked to confirm."""
        self._stub_api(monkeypatch, self._report(n_users=2))
        monkeypatch.setattr("builtins.input", lambda _: "DELETE 2 users and 0 orgs")
        mod.main(["--execute"])
        out = capsys.readouterr().out
        report_idx = out.index("Clerk pollution scan result")
        action_idx = out.index("DESTRUCTIVE ACTION")
        assert report_idx < action_idx
