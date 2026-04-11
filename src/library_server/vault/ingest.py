"""Source ingestion — classify, bucket, and track new material."""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml


def ingest_source(
    vault_path: str,
    source_path: str,
    tier: str,
    category: str,
) -> dict:
    """Ingest a file or directory into the vault's sources.

    Copies source material to sources/<tier>/<category>/.
    Updates kb.yaml with new category if needed.

    Args:
        vault_path: Root path to the vault.
        source_path: File or directory to ingest.
        tier: Contamination tier (e.g. 'raw', 'llm-generated', 'curated').
        category: Content category (e.g. 'prds', 'session-notes').

    Returns:
        {"status": "ingested", "path": str, "file_count": int, "category": str, "tier": str}
    """
    vault = Path(vault_path)
    source = Path(source_path)
    dest_dir = vault / "sources" / tier / category

    dest_dir.mkdir(parents=True, exist_ok=True)

    file_count = 0
    if source.is_file():
        shutil.copy2(source, dest_dir / source.name)
        file_count = 1
    elif source.is_dir():
        for item in source.iterdir():
            if item.is_file():
                shutil.copy2(item, dest_dir / item.name)
                file_count += 1
    else:
        return {"status": "error", "message": f"Source not found: {source_path}"}

    _update_kb_yaml(vault, category)

    return {
        "status": "ingested",
        "path": str(dest_dir),
        "file_count": file_count,
        "category": category,
        "tier": tier,
    }


def _update_kb_yaml(vault: Path, category: str) -> None:
    """Add category to kb.yaml if not already present."""
    kb_path = vault / "kb.yaml"
    if not kb_path.exists():
        return

    with open(kb_path) as f:
        kb = yaml.safe_load(f) or {}

    categories = kb.get("categories", [])
    if category not in categories:
        categories.append(category)
        kb["categories"] = categories
        with open(kb_path, "w") as f:
            yaml.dump(kb, f, default_flow_style=False)
