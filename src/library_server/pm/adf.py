"""Atlassian Document Format helpers shared by the PM adapter and extractors."""

from __future__ import annotations


def adf_to_text(node: dict | str | None) -> str:
    """Flatten Atlassian Document Format to plain text. Tolerates str input."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return node.get("text", "")
    parts: list[str] = []
    for child in node.get("content", []) or []:
        parts.append(adf_to_text(child))
    text = "".join(parts)
    if node.get("type") in ("paragraph", "heading"):
        return text + "\n"
    return text
