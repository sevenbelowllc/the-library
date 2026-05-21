"""Secret redaction — strip tokens/keys from text before persisting to disk.

Single chokepoint for transcript/checkpoint/SESSION.md write paths. The
patterns target well-known token formats (provider prefixes + length anchors)
and assignments of well-known secret env-var names. Plain emails and short
words are left alone.

Apply at write-time, not read-time, so secrets never reach the vault, the
knowledge graph, or PM task descriptions.
"""

from __future__ import annotations

import re

# Env-var names whose RHS is always a secret. Matched case-insensitively.
_SECRET_KEY_NAMES = (
    "JIRA_API_TOKEN",
    "LINEAR_API_KEY",
    "ATLASSIAN_API_TOKEN",
    "ATLASSIAN_TOKEN",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "CLERK_SECRET_KEY",
    "STRIPE_SECRET_KEY",
    "SENTRY_AUTH_TOKEN",
    "DATABASE_URL",
    "DATABASE_PASSWORD",
    "DB_PASSWORD",
)

_KEY_ALTERNATION = "|".join(_SECRET_KEY_NAMES)

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # KEY=VALUE / KEY: VALUE / KEY = VALUE — known secret env var names.
    # Captures the key + separator; replaces value (quoted or not) with [REDACTED].
    (
        re.compile(
            rf"(?i)\b({_KEY_ALTERNATION})(\s*[:=]\s*)(\"[^\"]+\"|'[^']+'|\S+)"
        ),
        r"\1\2[REDACTED]",
    ),
    # Atlassian API token (ATATT3 prefix, >=50 trailing chars).
    (re.compile(r"ATATT3[A-Za-z0-9_=\-]{50,}"), "[REDACTED_ATLASSIAN_TOKEN]"),
    # Stripe secret keys.
    (re.compile(r"sk_(test|live)_[A-Za-z0-9]{20,}"), "[REDACTED_STRIPE]"),
    # Linear API tokens.
    (re.compile(r"lin_(api|oauth)_[A-Za-z0-9]{32,}"), "[REDACTED_LINEAR]"),
    # GitHub tokens — PAT, OAuth, user-to-server, server-to-server, refresh.
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"), "[REDACTED_GITHUB]"),
    # AWS access key IDs.
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    # Slack tokens.
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "[REDACTED_SLACK]"),
    # Clerk secret keys.
    (re.compile(r"sk_(test|live)_clerk_[A-Za-z0-9]{20,}"), "[REDACTED_CLERK]"),
    # JWTs — three base64url segments separated by dots, each segment ≥10 chars.
    (
        re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
        "[REDACTED_JWT]",
    ),
    # Bearer tokens — long random tail.
    (
        re.compile(r"(?i)(\bBearer\s+)([A-Za-z0-9_\-\.=]{30,})"),
        r"\1[REDACTED]",
    ),
]


def redact(text) -> str:
    """Return *text* with secret-shaped substrings replaced by ``[REDACTED]``.

    Non-string input returns ``""`` (defensive — callers may pass exception
    objects, None, ints, lists, etc., from heterogeneous code paths).
    """
    if not isinstance(text, str):
        return ""
    if not text:
        return text
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


def redact_list(items) -> list[str]:
    """Redact each element of *items*; non-strings become ``""``."""
    if not items:
        return []
    return [redact(x) if isinstance(x, str) else "" for x in items]


def redact_exception(exc: BaseException) -> str:
    """Return ``"<ExceptionType>: <redacted message>"``.

    Use when logging or persisting exception text — exception args may include
    paths, credentials, or request bodies.
    """
    name = type(exc).__name__
    msg = redact(str(exc))
    return f"{name}: {msg}" if msg else name
