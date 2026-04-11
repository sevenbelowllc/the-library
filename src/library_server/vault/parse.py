"""Vault markdown parsing — tag extraction, frontmatter, headings."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


TAG_PATTERN = re.compile(r"\[(VERIFY|CONFLICT|PLANNED)\](?:\s*—?\s*(.*))?")


def parse_vault(vault_path: str) -> dict:
    """Parse all wiki articles in the vault.

    Returns:
        {
            "tags": [{"tag_type", "content", "source_file", "line_number"}, ...],
            "articles": [{"filename", "path", "frontmatter", "headings"}, ...],
        }
    """
    path = Path(vault_path)
    wiki_dir = path / "wiki"

    tags: list[dict] = []
    articles: list[dict] = []

    if not wiki_dir.is_dir():
        return {"tags": tags, "articles": articles}

    for md_file in sorted(wiki_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        frontmatter = _extract_frontmatter(content)
        headings = _extract_headings(content)
        file_tags = _extract_tags(content, str(md_file.relative_to(path)))

        tags.extend(file_tags)
        articles.append({
            "filename": md_file.name,
            "path": str(md_file.relative_to(path)),
            "frontmatter": frontmatter,
            "headings": headings,
        })

    return {"tags": tags, "articles": articles}


def _extract_frontmatter(content: str) -> dict[str, Any]:
    """Extract YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}


def _extract_headings(content: str) -> list[dict]:
    """Extract markdown headings with levels."""
    headings = []
    in_frontmatter = False
    for i, line in enumerate(content.split("\n"), 1):
        if line.strip() == "---":
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter:
            continue
        match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if match:
            headings.append({
                "level": len(match.group(1)),
                "text": match.group(2).strip(),
                "line": i,
            })
    return headings


def _extract_tags(content: str, relative_path: str) -> list[dict]:
    """Extract [VERIFY], [CONFLICT], [PLANNED] tags from content."""
    tags = []
    for i, line in enumerate(content.split("\n"), 1):
        for match in TAG_PATTERN.finditer(line):
            tags.append({
                "tag_type": match.group(1),
                "content": (match.group(2) or "").strip(),
                "source_file": relative_path,
                "line_number": i,
            })
    return tags
