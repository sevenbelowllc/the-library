"""Tests for hooks/domain_scanner.py — domain manifest loading and prompt scanning."""

from __future__ import annotations

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_FRONTMATTER = """\
---
domain: auth
keywords:
  starter: [requireAuth, requireOrgScope, clerk, jwt]
  learned: []
exclude:
  starter: [author, authority]
  learned: []
match_threshold: 1
token_estimate: 380
---

# Auth Domain

Handles authentication and authorization using Clerk JWT tokens.
requireAuth guard is applied to all resolvers.
"""

BILLING_FRONTMATTER = """\
---
domain: billing
keywords:
  starter: [stripe, invoice, subscription, payment]
  learned: [refund]
exclude:
  starter: [subscribe_newsletter]
  learned: []
match_threshold: 2
token_estimate: 200
---

# Billing Domain

Handles Stripe payments, invoices, and subscription management.
"""

NO_FRONTMATTER = """\
# No YAML here

Just plain markdown content.
"""


def write_domain(domains_dir: Path, filename: str, content: str) -> Path:
    """Write a domain markdown file and return its path."""
    path = domains_dir / filename
    path.write_text(content)
    return path


# ---------------------------------------------------------------------------
# Tests: DomainManifest dataclass
# ---------------------------------------------------------------------------

class TestDomainManifest:
    def test_dataclass_fields(self) -> None:
        from library_server.hooks.domain_scanner import DomainManifest
        dm = DomainManifest(
            domain="auth",
            keywords=["requireAuth", "clerk"],
            excludes=["author"],
            match_threshold=1,
            token_estimate=380,
            file_path=Path("/vault/domains/auth.md"),
            content="# Auth\nsome content",
        )
        assert dm.domain == "auth"
        assert dm.keywords == ["requireAuth", "clerk"]
        assert dm.excludes == ["author"]
        assert dm.match_threshold == 1
        assert dm.token_estimate == 380
        assert isinstance(dm.file_path, Path)


# ---------------------------------------------------------------------------
# Tests: DomainMatch dataclass
# ---------------------------------------------------------------------------

class TestDomainMatch:
    def test_dataclass_fields(self) -> None:
        from library_server.hooks.domain_scanner import DomainMatch
        dm = DomainMatch(
            domain="auth",
            matched_keywords=["requireAuth"],
            token_estimate=380,
            file_path=Path("/vault/domains/auth.md"),
            content="# Auth content",
        )
        assert dm.domain == "auth"
        assert dm.matched_keywords == ["requireAuth"]
        assert dm.token_estimate == 380


# ---------------------------------------------------------------------------
# Tests: load_domain_manifests
# ---------------------------------------------------------------------------

class TestLoadDomainManifests:
    def test_returns_dict(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import load_domain_manifests
        domains_dir = tmp_path / "domains"
        domains_dir.mkdir()
        result = load_domain_manifests(domains_dir)
        assert isinstance(result, dict)

    def test_empty_dir_returns_empty_dict(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import load_domain_manifests
        domains_dir = tmp_path / "domains"
        domains_dir.mkdir()
        result = load_domain_manifests(domains_dir)
        assert result == {}

    def test_missing_dir_returns_empty_dict(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import load_domain_manifests
        result = load_domain_manifests(tmp_path / "nonexistent")
        assert result == {}

    def test_loads_single_manifest(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import load_domain_manifests
        domains_dir = tmp_path / "domains"
        domains_dir.mkdir()
        write_domain(domains_dir, "auth.md", SAMPLE_FRONTMATTER)
        result = load_domain_manifests(domains_dir)
        assert "auth" in result

    def test_manifest_has_correct_domain(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import load_domain_manifests
        domains_dir = tmp_path / "domains"
        domains_dir.mkdir()
        write_domain(domains_dir, "auth.md", SAMPLE_FRONTMATTER)
        manifest = load_domain_manifests(domains_dir)["auth"]
        assert manifest.domain == "auth"

    def test_manifest_keywords_combine_starter_and_learned(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import load_domain_manifests
        domains_dir = tmp_path / "domains"
        domains_dir.mkdir()
        write_domain(domains_dir, "billing.md", BILLING_FRONTMATTER)
        manifest = load_domain_manifests(domains_dir)["billing"]
        assert "stripe" in manifest.keywords
        assert "refund" in manifest.keywords  # learned keyword

    def test_manifest_excludes_combine_starter_and_learned(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import load_domain_manifests
        domains_dir = tmp_path / "domains"
        domains_dir.mkdir()
        write_domain(domains_dir, "auth.md", SAMPLE_FRONTMATTER)
        manifest = load_domain_manifests(domains_dir)["auth"]
        assert "author" in manifest.excludes
        assert "authority" in manifest.excludes

    def test_manifest_token_estimate(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import load_domain_manifests
        domains_dir = tmp_path / "domains"
        domains_dir.mkdir()
        write_domain(domains_dir, "auth.md", SAMPLE_FRONTMATTER)
        manifest = load_domain_manifests(domains_dir)["auth"]
        assert manifest.token_estimate == 380

    def test_manifest_match_threshold(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import load_domain_manifests
        domains_dir = tmp_path / "domains"
        domains_dir.mkdir()
        write_domain(domains_dir, "billing.md", BILLING_FRONTMATTER)
        manifest = load_domain_manifests(domains_dir)["billing"]
        assert manifest.match_threshold == 2

    def test_manifest_file_path_set(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import load_domain_manifests
        domains_dir = tmp_path / "domains"
        domains_dir.mkdir()
        write_domain(domains_dir, "auth.md", SAMPLE_FRONTMATTER)
        manifest = load_domain_manifests(domains_dir)["auth"]
        assert manifest.file_path == domains_dir / "auth.md"

    def test_manifest_content_is_body_text(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import load_domain_manifests
        domains_dir = tmp_path / "domains"
        domains_dir.mkdir()
        write_domain(domains_dir, "auth.md", SAMPLE_FRONTMATTER)
        manifest = load_domain_manifests(domains_dir)["auth"]
        assert "# Auth Domain" in manifest.content

    def test_file_without_frontmatter_skipped(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import load_domain_manifests
        domains_dir = tmp_path / "domains"
        domains_dir.mkdir()
        write_domain(domains_dir, "nofm.md", NO_FRONTMATTER)
        result = load_domain_manifests(domains_dir)
        assert result == {}

    def test_non_md_files_ignored(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import load_domain_manifests
        domains_dir = tmp_path / "domains"
        domains_dir.mkdir()
        (domains_dir / "readme.txt").write_text("some text")
        result = load_domain_manifests(domains_dir)
        assert result == {}

    def test_loads_multiple_manifests(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import load_domain_manifests
        domains_dir = tmp_path / "domains"
        domains_dir.mkdir()
        write_domain(domains_dir, "auth.md", SAMPLE_FRONTMATTER)
        write_domain(domains_dir, "billing.md", BILLING_FRONTMATTER)
        result = load_domain_manifests(domains_dir)
        assert "auth" in result
        assert "billing" in result


# ---------------------------------------------------------------------------
# Tests: scan_prompt
# ---------------------------------------------------------------------------

class TestScanPrompt:
    def _make_manifests(self, tmp_path: Path) -> dict:
        from library_server.hooks.domain_scanner import load_domain_manifests
        domains_dir = tmp_path / "domains"
        domains_dir.mkdir()
        write_domain(domains_dir, "auth.md", SAMPLE_FRONTMATTER)
        write_domain(domains_dir, "billing.md", BILLING_FRONTMATTER)
        return load_domain_manifests(domains_dir)

    def test_single_match_returned(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import scan_prompt
        manifests = self._make_manifests(tmp_path)
        result = scan_prompt("I need to add requireAuth to this resolver", manifests)
        domains = [m.domain for m in result]
        assert "auth" in domains

    def test_no_match_returns_empty(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import scan_prompt
        manifests = self._make_manifests(tmp_path)
        result = scan_prompt("update the navigation menu color", manifests)
        assert result == []

    def test_multiple_matches_returned(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import scan_prompt
        manifests = self._make_manifests(tmp_path)
        result = scan_prompt("requireAuth is needed for the stripe payment endpoint", manifests)
        domains = [m.domain for m in result]
        assert "auth" in domains
        assert "billing" in domains

    def test_exclude_word_prevents_match(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import scan_prompt
        manifests = self._make_manifests(tmp_path)
        # "author" is in auth.excludes — even though "auth" is a substring of "author",
        # if the exclude matches the prompt we skip this domain
        result = scan_prompt("the author field was updated", manifests)
        domains = [m.domain for m in result]
        assert "auth" not in domains

    def test_threshold_respected(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import scan_prompt
        manifests = self._make_manifests(tmp_path)
        # billing requires 2 keyword matches; "stripe" alone is not enough
        result = scan_prompt("set up stripe for payments", manifests)
        domains = [m.domain for m in result]
        assert "billing" not in domains

    def test_threshold_met_triggers_match(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import scan_prompt
        manifests = self._make_manifests(tmp_path)
        # billing needs 2 matches; "stripe" + "invoice" satisfies threshold=2
        result = scan_prompt("generate a stripe invoice for the customer", manifests)
        domains = [m.domain for m in result]
        assert "billing" in domains

    def test_matched_keywords_populated(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import scan_prompt
        manifests = self._make_manifests(tmp_path)
        result = scan_prompt("requireAuth clerk integration", manifests)
        auth_match = next(m for m in result if m.domain == "auth")
        assert "requireAuth" in auth_match.matched_keywords or "clerk" in auth_match.matched_keywords

    def test_case_insensitive_keyword_match(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import scan_prompt
        manifests = self._make_manifests(tmp_path)
        result = scan_prompt("REQUIREAUTH should be applied", manifests)
        domains = [m.domain for m in result]
        assert "auth" in domains

    def test_empty_prompt_returns_empty(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import scan_prompt
        manifests = self._make_manifests(tmp_path)
        result = scan_prompt("", manifests)
        assert result == []

    def test_empty_manifests_returns_empty(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import scan_prompt
        result = scan_prompt("requireAuth clerk jwt", {})
        assert result == []

    def test_domain_match_has_token_estimate(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import scan_prompt
        manifests = self._make_manifests(tmp_path)
        result = scan_prompt("requireAuth guard", manifests)
        auth_match = next(m for m in result if m.domain == "auth")
        assert auth_match.token_estimate == 380

    def test_domain_match_has_file_path(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import scan_prompt
        manifests = self._make_manifests(tmp_path)
        result = scan_prompt("requireAuth guard", manifests)
        auth_match = next(m for m in result if m.domain == "auth")
        assert isinstance(auth_match.file_path, Path)

    def test_learned_keyword_triggers_match(self, tmp_path: Path) -> None:
        from library_server.hooks.domain_scanner import scan_prompt
        manifests = self._make_manifests(tmp_path)
        # "refund" is a learned billing keyword; billing threshold=2, add "stripe" too
        result = scan_prompt("process a stripe refund for the user", manifests)
        domains = [m.domain for m in result]
        assert "billing" in domains
