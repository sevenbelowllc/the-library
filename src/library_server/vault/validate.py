"""Vault schema validation."""

from __future__ import annotations

from pathlib import Path

REQUIRED_DIRS = ["_schema", "sources", "wiki", "archive"]
REQUIRED_FILES = ["CLAUDE.md", "kb.yaml"]


def validate_vault(vault_path: str) -> dict:
    """Validate a vault against the Karpathy v1 schema.

    Returns {"valid": bool, "issues": list[str]}.
    """
    path = Path(vault_path)
    issues: list[str] = []

    if not path.exists():
        return {"valid": False, "issues": [f"Vault path does not exist: {vault_path}"]}

    if not path.is_dir():
        return {"valid": False, "issues": [f"Vault path is not a directory: {vault_path}"]}

    for dir_name in REQUIRED_DIRS:
        if not (path / dir_name).is_dir():
            issues.append(f"Missing required directory: {dir_name}/")

    for file_name in REQUIRED_FILES:
        if not (path / file_name).is_file():
            issues.append(f"Missing required file: {file_name}")

    return {"valid": len(issues) == 0, "issues": issues}
