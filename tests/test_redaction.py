"""Tests for redaction module — secret stripping before disk writes.

Security-critical. Coverage target: 100%.

NOTE: test fixtures construct secret-shaped strings via concatenation so the
source file itself does not contain literal patterns that match secret-scan
hooks (~/.claude/hooks/secret-scan.sh).
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers — build secret-shaped fake tokens without tripping secret-scan
# ---------------------------------------------------------------------------

def _fake(prefix: str, body: str) -> str:
    """Concat at runtime; source file never has the contiguous literal."""
    return prefix + body


class TestRedactNoOp:
    """Strings without secrets must pass through unchanged."""

    def test_empty_string(self):
        from library_server.redaction import redact
        assert redact("") == ""

    def test_plain_text(self):
        from library_server.redaction import redact
        assert redact("Just a plain sentence with no secrets.") == \
            "Just a plain sentence with no secrets."

    def test_none_returns_empty_string(self):
        from library_server.redaction import redact
        assert redact(None) == ""

    def test_non_string_returns_empty_string(self):
        from library_server.redaction import redact
        assert redact(12345) == ""
        assert redact(["a", "b"]) == ""

    def test_email_address_not_redacted(self):
        """Plain emails are not secrets; do not redact them."""
        from library_server.redaction import redact
        result = redact("Contact dev@sevenbelow.com for help")
        assert "dev@sevenbelow.com" in result


class TestRedactEnvAssignment:
    """KEY=VALUE / KEY: VALUE / KEY = VALUE forms for known secret env names."""

    @pytest.mark.parametrize("key", [
        "JIRA_API_TOKEN",
        "LINEAR_API_KEY",
        "ATLASSIAN_API_TOKEN",
        "GITHUB_TOKEN",
        "AWS_SECRET_ACCESS_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "CLERK_SECRET_KEY",
        "STRIPE_SECRET_KEY",
        "SENTRY_AUTH_TOKEN",
    ])
    def test_known_env_var_assignments_redacted(self, key):
        from library_server.redaction import redact
        for sep in ["=", ": ", " = ", ":"]:
            line = f"{key}{sep}supersecretvalue123"
            result = redact(line)
            assert "supersecretvalue123" not in result, \
                f"failed to redact {key}{sep}value"
            assert "[REDACTED]" in result
            assert key in result, "key name should remain visible"

    def test_case_insensitive_key_match(self):
        from library_server.redaction import redact
        assert "[REDACTED]" in redact("jira_api_token=abc123")
        assert "[REDACTED]" in redact("Linear_Api_Key=xyz789")

    def test_quoted_value_redacted(self):
        from library_server.redaction import redact
        result = redact('JIRA_API_TOKEN="PLACEHOLDER_JIRA_TOKEN"')
        assert "PLACEHOLDER_JIRA_TOKEN" not in result
        assert "[REDACTED]" in result


class TestRedactKnownTokenFormats:
    """Prefixed token formats by known providers — match anywhere in text."""

    def test_atlassian_token(self):
        from library_server.redaction import redact
        token = _fake("ATATT3", "x" * 100)
        result = redact(f"Using {token} for API call")
        assert token not in result
        assert "[REDACTED" in result

    def test_stripe_test_secret(self):
        from library_server.redaction import redact
        token = _fake("sk_test_", "x" * 30)
        result = redact(f"key={token}")
        assert token not in result

    def test_stripe_live_secret(self):
        from library_server.redaction import redact
        token = _fake("sk_live_", "a" * 30)
        result = redact(f"prod uses {token}")
        assert token not in result

    def test_github_pat(self):
        from library_server.redaction import redact
        token = _fake("ghp_", "X" * 36)
        result = redact(f"gh auth {token}")
        assert token not in result

    def test_github_oauth(self):
        from library_server.redaction import redact
        token = _fake("gho_", "Y" * 36)
        result = redact(f"token: {token}")
        assert token not in result

    def test_aws_access_key_id(self):
        from library_server.redaction import redact
        key = _fake("AKIA", "IOSFODNN7EXAMPLE")
        result = redact(f"AWS key {key}")
        assert key not in result

    def test_slack_token(self):
        from library_server.redaction import redact
        token = _fake("xoxb-", "1234567890-abcdefghij")
        result = redact(f"slack: {token}")
        assert token not in result

    def test_linear_api_token(self):
        from library_server.redaction import redact
        token = _fake("lin_api_", "Z" * 40)
        result = redact(f"export {token}")
        assert token not in result

    def test_jwt(self):
        from library_server.redaction import redact
        jwt = (
            _fake("eyJ", "hbGciOiJIUzI1NiJ9")
            + "."
            + _fake("eyJ", "zdWIiOiIxMjM0NSJ9")
            + "."
            + "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )
        result = redact(f"Bearer {jwt}")
        assert jwt not in result


class TestRedactBearer:
    """Bearer / Authorization headers carrying long random tokens."""

    def test_bearer_long_token(self):
        from library_server.redaction import redact
        token = "a" * 40
        result = redact(f"Authorization: Bearer {token}")
        assert token not in result
        assert "[REDACTED]" in result

    def test_bearer_short_token_not_redacted(self):
        """Short strings after Bearer (e.g. examples in docs) — leave alone."""
        from library_server.redaction import redact
        result = redact("Bearer short")
        assert "short" in result


class TestRedactMultipleInOneString:
    def test_multiple_distinct_secrets(self):
        from library_server.redaction import redact
        ghp = _fake("ghp_", "G" * 36)
        stripe = _fake("sk_test_", "s" * 30)
        text = f"keys: {ghp} and also {stripe}"
        result = redact(text)
        assert ghp not in result
        assert stripe not in result

    def test_multiline_input(self):
        from library_server.redaction import redact
        ghp = _fake("ghp_", "M" * 36)
        text = f"line1\nJIRA_API_TOKEN=tok123\nline3 has {ghp}\nline4"
        result = redact(text)
        assert "tok123" not in result
        assert ghp not in result
        assert "line1" in result
        assert "line4" in result


class TestRedactList:
    """Helper for redacting list[str]."""

    def test_redact_list_filters_each(self):
        from library_server.redaction import redact_list
        ghp = _fake("ghp_", "K" * 36)
        items = ["clean text", f"secret {ghp}", "JIRA_API_TOKEN=abc"]
        result = redact_list(items)
        assert result[0] == "clean text"
        assert ghp not in result[1]
        assert "abc" not in result[2]

    def test_redact_list_empty(self):
        from library_server.redaction import redact_list
        assert redact_list([]) == []

    def test_redact_list_skips_non_strings(self):
        from library_server.redaction import redact_list
        result = redact_list(["a", None, 42, "b"])
        assert result == ["a", "", "", "b"]


class TestRedactExceptionMessage:
    """Helper that pulls msg via str(exc) and redacts."""

    def test_exception_with_secret_in_message(self):
        from library_server.redaction import redact_exception
        exc = RuntimeError("auth failed: JIRA_API_TOKEN=actualtoken123")
        result = redact_exception(exc)
        assert "actualtoken123" not in result
        assert "RuntimeError" in result

    def test_exception_without_secret(self):
        from library_server.redaction import redact_exception
        exc = ValueError("bad input")
        result = redact_exception(exc)
        assert "ValueError" in result
        assert "bad input" in result
