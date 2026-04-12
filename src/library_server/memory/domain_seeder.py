"""Domain seeder — bootstrap domain files from CLAUDE.md content.

Scans CLAUDE.md for known technology/domain patterns and creates starter
domain ``.md`` files in *domains_dir* that the MMU scanner can later refine.
"""

from __future__ import annotations

import re
from pathlib import Path
from textwrap import dedent
from typing import NamedTuple


class _DomainPattern(NamedTuple):
    scan_patterns: list[str]   # regex strings matched against lowercased content
    starter_keywords: list[str]
    excludes: list[str]
    description: str


# ---------------------------------------------------------------------------
# Pre-defined domain patterns
# ---------------------------------------------------------------------------

DOMAIN_PATTERNS: dict[str, _DomainPattern] = {
    "auth": _DomainPattern(
        scan_patterns=[
            r"\bclerk\b",
            r"\bjwt\b",
            r"\brequireauth\b",
            r"\bauthentication\b",
            r"\bauthorization\b",
            r"\bsession\b.*\btoken\b",
        ],
        starter_keywords=["clerk", "jwt", "requireAuth", "auth", "token", "session"],
        excludes=["mock", "test-token"],
        description=(
            "Authentication and authorisation — Clerk JWT verification, "
            "session management, and access control guards"
        ),
    ),
    "database": _DomainPattern(
        scan_patterns=[
            r"\bpostgres(ql)?\b",
            r"\bmigration\b",
            r"\bsql\b",
            r"\bpg\s+driver\b",
            r"\braw\s+sql\b",
            r"\bdb\b.*\bentit",
        ],
        starter_keywords=["postgres", "migration", "sql", "pg", "database", "schema"],
        excludes=["mock-db", "in-memory"],
        description=(
            "Database layer — PostgreSQL via raw SQL / pg driver, "
            "entity definitions, and numbered migrations"
        ),
    ),
    "graphql": _DomainPattern(
        scan_patterns=[
            r"\bgraphql\b",
            r"\bresolver\b",
            r"\btypedefs\b",
            r"\bapollo\b",
            r"\bschema\b.*\bquery\b",
        ],
        starter_keywords=["graphql", "resolver", "typeDefs", "apollo", "query", "mutation"],
        excludes=["rest", "openapi"],
        description=(
            "GraphQL API layer — Apollo Server, type definitions, resolvers, "
            "and schema-driven query / mutation design"
        ),
    ),
    "frontend": _DomainPattern(
        scan_patterns=[
            r"\bnext\.js\b",
            r"\bnextjs\b",
            r"\breact\b",
            r"\btailwind\b",
            r"\bapp\s+router\b",
            r"\bturbopack\b",
        ],
        starter_keywords=["next.js", "react", "tailwind", "app-router", "tsx", "component"],
        excludes=["server-only", "node-only"],
        description=(
            "Frontend application — Next.js 15 App Router, React 18 components, "
            "Tailwind CSS design tokens, and Turbopack dev server"
        ),
    ),
    "testing": _DomainPattern(
        scan_patterns=[
            r"\bjest\b",
            r"\bplaywright\b",
            r"\btest\s+suite\b",
            r"\bunit\s+test\b",
            r"\bintegration\s+test\b",
            r"\be2e\b",
            r"\bcoverage\b",
        ],
        starter_keywords=["jest", "playwright", "test", "coverage", "e2e", "spec"],
        excludes=["production", "mock-only"],
        description=(
            "Testing infrastructure — Jest unit/integration tests and "
            "Playwright end-to-end tests with coverage reporting"
        ),
    ),
    "infrastructure": _DomainPattern(
        scan_patterns=[
            r"\bterraform\b",
            r"\bdocker\b",
            r"\bgcp\b",
            r"\bgoogle\s+cloud\b",
            r"\bkubernetes\b",
            r"\bk8s\b",
            r"\bgke\b",
            r"\bcloud\s+sql\b",
        ],
        starter_keywords=["terraform", "docker", "gcp", "kubernetes", "gke", "cloud-sql"],
        excludes=["local-only", "dev-only"],
        description=(
            "Infrastructure — Terraform modules, Docker containers, "
            "GCP / GKE compute, Cloud SQL, and Cloudflare networking"
        ),
    ),
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def seed_domains_from_claude_md(claude_md_path: Path, domains_dir: Path) -> list[str]:
    """Seed domain files from *claude_md_path* into *domains_dir*.

    Parameters
    ----------
    claude_md_path:
        Path to the project's ``CLAUDE.md`` file.
    domains_dir:
        Directory where domain ``.md`` files will be written.

    Returns
    -------
    list[str]
        Names of domains for which files were created (e.g. ``["auth", "database"]``).
        Returns an empty list if *claude_md_path* does not exist or no patterns
        match the content.
    """
    if not claude_md_path.exists():
        return []

    content = claude_md_path.read_text(encoding="utf-8").lower()
    created: list[str] = []

    domains_dir.mkdir(parents=True, exist_ok=True)

    for domain_name, pattern in DOMAIN_PATTERNS.items():
        if not _any_pattern_matches(pattern.scan_patterns, content):
            continue

        domain_file = domains_dir / f"{domain_name}.md"
        if domain_file.exists():
            # Never overwrite an existing domain file
            continue

        domain_file.write_text(
            _render_domain_file(domain_name, pattern),
            encoding="utf-8",
        )
        created.append(domain_name)

    return created


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _any_pattern_matches(patterns: list[str], text: str) -> bool:
    """Return True if any regex in *patterns* matches *text*."""
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def _render_domain_file(name: str, pattern: _DomainPattern) -> str:
    """Render the markdown content for a domain file."""
    starter_kw = "\n".join(f"    - {kw}" for kw in pattern.starter_keywords)
    starter_ex = "\n".join(f"    - {ex}" for ex in pattern.excludes)
    title = name.title()

    lines = [
        "---",
        f"domain: {name}",
        "keywords:",
        "  starter:",
        starter_kw,
        "  learned: []",
        "exclude:",
        "  starter:",
        starter_ex,
        "  learned: []",
        "match_threshold: 1",
        "token_estimate: 400",
        "---",
        "",
        f"## {title} Domain",
        f"{pattern.description}.",
        "",
    ]
    return "\n".join(lines)
