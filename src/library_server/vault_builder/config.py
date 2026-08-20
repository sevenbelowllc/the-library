"""VaultBuilderConfig — loads and validates vault_builder section from library-config.yaml."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class VaultBuilderConfigError(Exception):
    """Raised when vault_builder config cannot be turned into a build.

    Carries the full list of validation errors so the tool layer can return
    them as a structured error instead of a bare failed build.
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass
class VaultBuilderConfig:
    """Parsed vault_builder configuration."""
    mode: str = "create"
    output_vault: Path | None = None
    parallel: bool = True
    max_parallel_extractors: int = 8
    fail_fast: bool = False
    sources: dict[str, dict[str, Any]] = field(default_factory=dict)
    graphify: dict[str, Any] = field(default_factory=dict)


def load_vault_builder_config(config_path: Path) -> VaultBuilderConfig:
    """Load vault_builder section from library-config.yaml."""
    if not config_path.exists():
        return VaultBuilderConfig()

    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}

    vb = raw.get("vault_builder", {})
    if not vb:
        return VaultBuilderConfig()

    output_vault = vb.get("output_vault")
    return VaultBuilderConfig(
        mode=vb.get("mode", "create"),
        output_vault=Path(output_vault) if output_vault else None,
        parallel=vb.get("parallel", True),
        max_parallel_extractors=vb.get("max_parallel_extractors", 8),
        fail_fast=vb.get("fail_fast", False),
        sources=vb.get("sources", {}),
        graphify=vb.get("graphify", {}),
    )


def validate_vault_builder_config(config: VaultBuilderConfig) -> list[str]:
    """Validate vault builder config. Returns list of errors (empty = valid)."""
    errors: list[str] = []

    if config.mode not in ("create", "enrich"):
        errors.append(f"Invalid mode: '{config.mode}'. Must be 'create' or 'enrich'.")

    if not config.output_vault:
        errors.append("Missing required config: output_vault")
    elif config.output_vault and not config.output_vault.parent.exists():
        errors.append(f"output_vault parent directory does not exist: {config.output_vault.parent}")

    if config.graphify.get("enabled"):
        graphify_cmd = config.graphify.get("command", "graphify")
        if not shutil.which(graphify_cmd):
            errors.append(f"Graphify is enabled but CLI not found: {graphify_cmd}. Install with: pip install graphifyy")

    if "axon_bridge" in config.sources:
        errors.append(
            "sources.axon_bridge was renamed to sources.code_repo "
            "(axon retired in favor of graphify) — update library-config.yaml"
        )

    for source_name, source_cfg in config.sources.items():
        if not isinstance(source_cfg, dict):
            if source_cfg is not None:
                errors.append(f"Source '{source_name}' must be a mapping, got {type(source_cfg).__name__}")
            continue
        if not source_cfg.get("enabled", True):
            continue
        source_path = source_cfg.get("source_path")
        if source_path and not Path(source_path).exists():
            errors.append(f"Source '{source_name}' source_path does not exist: {source_path}")

    return errors
