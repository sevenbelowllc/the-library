"""VaultBuilderConfig — loads and validates vault_builder section from library-config.yaml."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


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
    axon: dict[str, Any] = field(default_factory=dict)
    preserve: list[str] = field(default_factory=list)


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
        axon=vb.get("axon", {}),
        preserve=vb.get("preserve", []),
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

    if config.axon.get("enabled"):
        axon_cmd = config.axon.get("command", "axon")
        if not shutil.which(axon_cmd):
            errors.append(f"Axon is enabled but CLI not found: {axon_cmd}. Install with: pip install axoniq")

    if config.graphify.get("enabled"):
        graphify_cmd = config.graphify.get("command", "graphify")
        if not shutil.which(graphify_cmd):
            errors.append(f"Graphify is enabled but CLI not found: {graphify_cmd}. Install with: pip install graphifyy")

    for source_name, source_cfg in config.sources.items():
        if not source_cfg.get("enabled", True):
            continue
        source_path = source_cfg.get("source_path")
        if source_path and not Path(source_path).exists():
            errors.append(f"Source '{source_name}' source_path does not exist: {source_path}")

    return errors
