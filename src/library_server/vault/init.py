"""Vault initialization — scaffolds Karpathy 3-layer structure."""

from __future__ import annotations

from pathlib import Path

import yaml


VAULT_DIRS = ["_schema", "sources", "wiki", "archive"]

DEFAULT_COMPILE_PROTOCOL = """# Vault Compile Protocol

This vault follows the Karpathy 3-layer pattern:

## Structure
- `sources/` — Raw, immutable source material organized by contamination tier
- `wiki/` — LLM-compiled articles derived from sources
- `_schema/` — Schema definitions and compile instructions
- `archive/` — Superseded content kept for reference

## Compile Rules
1. Wiki articles are compiled from sources, never written from scratch
2. Tag uncertain content: `[VERIFY]`, `[CONFLICT]`, `[PLANNED]`
3. Sources are immutable — never edit files in sources/
4. Compile order is defined in kb.yaml
"""

DEFAULT_KB_YAML = {
    "version": "1.0",
    "compile_order": [],
    "categories": [],
}


def init_vault(vault_path: str) -> dict:
    """Initialize a vault with Karpathy 3-layer structure.

    Creates _schema/, sources/, wiki/, archive/ directories,
    CLAUDE.md compile protocol, and kb.yaml compile order.

    Idempotent — won't destroy existing content.
    """
    path = Path(vault_path)

    if path.exists() and all((path / d).is_dir() for d in VAULT_DIRS):
        return {"status": "exists", "path": str(path)}

    # Create directories
    for dir_name in VAULT_DIRS:
        (path / dir_name).mkdir(parents=True, exist_ok=True)

    # Create compile protocol if missing
    claude_md = path / "CLAUDE.md"
    if not claude_md.exists():
        claude_md.write_text(DEFAULT_COMPILE_PROTOCOL)

    # Create kb.yaml if missing
    kb_yaml = path / "kb.yaml"
    if not kb_yaml.exists():
        with open(kb_yaml, "w") as f:
            yaml.dump(DEFAULT_KB_YAML, f, default_flow_style=False)

    return {"status": "created", "path": str(path)}
