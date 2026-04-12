"""Tests for hooks/dedup.py — session deduplication for domain injection."""

from __future__ import annotations

from pathlib import Path

import pytest


class TestGetDedupPath:
    def test_returns_path_object(self) -> None:
        from library_server.hooks.dedup import get_dedup_path
        result = get_dedup_path("abc123")
        assert isinstance(result, Path)

    def test_path_contains_session_id(self) -> None:
        from library_server.hooks.dedup import get_dedup_path
        result = get_dedup_path("mysession")
        assert "mysession" in str(result)

    def test_path_prefix(self) -> None:
        from library_server.hooks.dedup import get_dedup_path
        result = get_dedup_path("xyz")
        assert result.name == "library-session-xyz.domains"

    def test_path_in_tmp(self) -> None:
        from library_server.hooks.dedup import get_dedup_path
        result = get_dedup_path("abc")
        assert str(result).startswith("/tmp/")

    def test_unique_per_session(self) -> None:
        from library_server.hooks.dedup import get_dedup_path
        p1 = get_dedup_path("session-1")
        p2 = get_dedup_path("session-2")
        assert p1 != p2


class TestIsDomainInjected:
    def test_returns_false_when_file_missing(self, tmp_path: Path) -> None:
        from library_server.hooks.dedup import is_domain_injected
        p = tmp_path / "missing.domains"
        assert is_domain_injected(p, "auth") is False

    def test_returns_false_when_domain_not_in_file(self, tmp_path: Path) -> None:
        from library_server.hooks.dedup import is_domain_injected
        p = tmp_path / "session.domains"
        p.write_text("billing\nroles\n")
        assert is_domain_injected(p, "auth") is False

    def test_returns_true_when_domain_present(self, tmp_path: Path) -> None:
        from library_server.hooks.dedup import is_domain_injected
        p = tmp_path / "session.domains"
        p.write_text("auth\nbilling\n")
        assert is_domain_injected(p, "auth") is True

    def test_exact_match_not_substring(self, tmp_path: Path) -> None:
        from library_server.hooks.dedup import is_domain_injected
        p = tmp_path / "session.domains"
        p.write_text("authorization\n")
        # "auth" should NOT match "authorization"
        assert is_domain_injected(p, "auth") is False

    def test_empty_file_returns_false(self, tmp_path: Path) -> None:
        from library_server.hooks.dedup import is_domain_injected
        p = tmp_path / "session.domains"
        p.write_text("")
        assert is_domain_injected(p, "auth") is False


class TestMarkDomainInjected:
    def test_creates_file_if_missing(self, tmp_path: Path) -> None:
        from library_server.hooks.dedup import mark_domain_injected
        p = tmp_path / "session.domains"
        assert not p.exists()
        mark_domain_injected(p, "auth")
        assert p.exists()

    def test_appends_domain(self, tmp_path: Path) -> None:
        from library_server.hooks.dedup import mark_domain_injected, is_domain_injected
        p = tmp_path / "session.domains"
        mark_domain_injected(p, "auth")
        assert is_domain_injected(p, "auth") is True

    def test_appends_multiple_domains(self, tmp_path: Path) -> None:
        from library_server.hooks.dedup import mark_domain_injected, is_domain_injected
        p = tmp_path / "session.domains"
        mark_domain_injected(p, "auth")
        mark_domain_injected(p, "billing")
        assert is_domain_injected(p, "auth") is True
        assert is_domain_injected(p, "billing") is True

    def test_does_not_duplicate_domain(self, tmp_path: Path) -> None:
        from library_server.hooks.dedup import mark_domain_injected
        p = tmp_path / "session.domains"
        mark_domain_injected(p, "auth")
        mark_domain_injected(p, "auth")
        lines = [ln.strip() for ln in p.read_text().splitlines() if ln.strip()]
        assert lines.count("auth") == 1

    def test_preserves_existing_entries(self, tmp_path: Path) -> None:
        from library_server.hooks.dedup import mark_domain_injected, is_domain_injected
        p = tmp_path / "session.domains"
        p.write_text("roles\n")
        mark_domain_injected(p, "auth")
        assert is_domain_injected(p, "roles") is True
        assert is_domain_injected(p, "auth") is True

    def test_returns_none(self, tmp_path: Path) -> None:
        from library_server.hooks.dedup import mark_domain_injected
        p = tmp_path / "session.domains"
        result = mark_domain_injected(p, "auth")
        assert result is None
