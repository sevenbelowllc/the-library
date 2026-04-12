"""Hook infrastructure: keyword regex scanner for vault domain manifests.

Parses ``vault/domains/*.md`` files (which carry YAML front-matter), builds
:class:`DomainManifest` objects, and matches a user prompt string against
all loaded manifests to produce :class:`DomainMatch` results.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class DomainManifest:
    """Parsed representation of a single ``vault/domains/*.md`` file."""

    domain: str
    """Canonical domain name (e.g. ``"auth"``)."""

    keywords: list[str]
    """Combined starter + learned keywords to match against prompts."""

    excludes: list[str]
    """Combined starter + learned exclude words. If any exclude word appears
    in the prompt the domain is skipped entirely."""

    match_threshold: int
    """Minimum number of distinct keywords that must match before the domain
    is reported as a hit."""

    token_estimate: int
    """Rough token count of the domain context file."""

    file_path: Path
    """Absolute path to the source ``.md`` file."""

    content: str
    """Body text of the domain file (everything after the YAML front-matter)."""


@dataclass
class DomainMatch:
    """A domain that matched a user prompt."""

    domain: str
    """Canonical domain name."""

    matched_keywords: list[str]
    """Keywords that were found in the prompt."""

    token_estimate: int
    """Token estimate from the manifest."""

    file_path: Path
    """Source file path."""

    content: str
    """Domain body content."""


# ---------------------------------------------------------------------------
# Front-matter parsing
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict[str, Any] | None, str]:
    """Split a markdown string into (frontmatter_dict, body).

    Returns ``(None, text)`` if no YAML front-matter block is found.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None, text
    try:
        fm = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None, text
    body = m.group(2)
    return (fm if isinstance(fm, dict) else None), body


def _combine(section: dict[str, Any] | None, *keys: str) -> list[str]:
    """Merge multiple keyword lists from a YAML section into one flat list."""
    if not isinstance(section, dict):
        return []
    result: list[str] = []
    for key in keys:
        items = section.get(key) or []
        if isinstance(items, list):
            result.extend(str(i) for i in items)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_domain_manifests(domains_dir: Path) -> dict[str, DomainManifest]:
    """Load all ``*.md`` domain files from *domains_dir*.

    Each file must have a YAML front-matter block with at least a ``domain``
    key.  Files without front-matter, or with unparsable YAML, are silently
    skipped.

    Parameters
    ----------
    domains_dir:
        Directory containing domain ``.md`` files (typically
        ``<vault>/domains/``).

    Returns
    -------
    dict[str, DomainManifest]
        Mapping of domain name → manifest.  Empty dict if the directory does
        not exist or contains no valid domain files.
    """
    if not domains_dir.is_dir():
        return {}

    manifests: dict[str, DomainManifest] = {}
    for md_file in sorted(domains_dir.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        fm, body = _parse_frontmatter(text)
        if fm is None:
            continue
        domain = fm.get("domain")
        if not domain:
            continue

        keywords = _combine(fm.get("keywords"), "starter", "learned")
        excludes = _combine(fm.get("exclude"), "starter", "learned")

        manifests[domain] = DomainManifest(
            domain=domain,
            keywords=keywords,
            excludes=excludes,
            match_threshold=int(fm.get("match_threshold", 1)),
            token_estimate=int(fm.get("token_estimate", 0)),
            file_path=md_file,
            content=body,
        )

    return manifests


def scan_prompt(
    prompt: str,
    manifests: dict[str, DomainManifest],
) -> list[DomainMatch]:
    """Match *prompt* against all loaded domain manifests.

    Algorithm per domain:

    1. If any **exclude** word is present in the prompt (whole-word,
       case-insensitive), skip this domain.
    2. Count how many **keywords** appear in the prompt (whole-word,
       case-insensitive).
    3. If the count meets or exceeds ``match_threshold``, emit a
       :class:`DomainMatch`.

    Parameters
    ----------
    prompt:
        The user's prompt text.
    manifests:
        Pre-loaded manifests from :func:`load_domain_manifests`.

    Returns
    -------
    list[DomainMatch]
        All domains that matched, in manifest-iteration order.
    """
    if not prompt or not manifests:
        return []

    matches: list[DomainMatch] = []

    for manifest in manifests.values():
        # --- exclude check ---
        excluded = False
        for ex in manifest.excludes:
            if re.search(r"\b" + re.escape(ex) + r"\b", prompt, re.IGNORECASE):
                excluded = True
                break
        if excluded:
            continue

        # --- keyword match ---
        matched: list[str] = []
        for kw in manifest.keywords:
            if re.search(r"\b" + re.escape(kw) + r"\b", prompt, re.IGNORECASE):
                matched.append(kw)

        if len(matched) >= manifest.match_threshold:
            matches.append(
                DomainMatch(
                    domain=manifest.domain,
                    matched_keywords=matched,
                    token_estimate=manifest.token_estimate,
                    file_path=manifest.file_path,
                    content=manifest.content,
                )
            )

    return matches
