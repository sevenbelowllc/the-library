"""Configuration loading and validation."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


CONFIG_FILENAME = "library-config.yaml"


@dataclass
class LibraryConfig:
    """Parsed library configuration."""

    raw: dict[str, Any] = field(default_factory=dict)
    path: Path = field(default_factory=lambda: Path.cwd() / CONFIG_FILENAME)

    def get_section(self, section: str) -> dict:
        return self.raw.get(section, {})

    def set_value(self, section: str, key: str, value: Any) -> None:
        if section not in self.raw:
            self.raw[section] = {}
        self.raw[section][key] = value

    def to_dict(self) -> dict:
        return dict(self.raw)

    def save(self) -> None:
        with open(self.path, "w") as f:
            yaml.dump(self.raw, f, default_flow_style=False, sort_keys=False)


def load_config(config_path: Path | None = None) -> LibraryConfig:
    """Load config from yaml file. Returns empty config if file doesn't exist."""
    path = config_path or Path.cwd() / CONFIG_FILENAME
    if path.exists():
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
    else:
        raw = {}
    return LibraryConfig(raw=raw, path=path)


def validate_config(config: LibraryConfig) -> dict:
    """Validate a loaded config for completeness and dependency availability.

    Returns:
        {"valid": bool, "warnings": [str, ...]}
    """
    warnings: list[str] = []

    # Check required sections
    library = config.get_section("library")
    if not library.get("version"):
        warnings.append("Missing library.version — config may be malformed")

    # Check vault path exists if configured
    vault = config.get_section("vault")
    vault_path = vault.get("path")
    if vault_path and not Path(vault_path).exists():
        warnings.append(f"Vault path does not exist: {vault_path}")

    # Check Graphify availability if enabled
    graphify = config.get_section("graphify")
    if graphify.get("enabled"):
        if not shutil.which("graphify"):
            warnings.append(
                "Graphify is enabled but CLI not found. "
                "Install with: pip install the-library[graphify]"
            )

    # Check PM provider validity
    pm = config.get_section("pm")
    provider = pm.get("provider", "none")
    if provider not in ("jira", "linear", "none"):
        warnings.append(f"Unknown PM provider: {provider}. Use 'jira', 'linear', or 'none'.")

    # Check memory path
    memory = config.get_section("memory")
    memory_path = memory.get("path")
    if memory_path and not Path(memory_path).exists():
        warnings.append(f"Memory path does not exist: {memory_path} (will be created on first use)")

    memory_cfg = config.raw.get("memory", {})
    if memory_cfg:
        budgets = memory_cfg.get("budgets", {})
        if budgets.get("critical", 300) + budgets.get("fresh", 500) > 1000:
            warnings.append("CRITICAL + FRESH budget exceeds 1000 tokens — high baseline cost")
        learning = memory_cfg.get("keyword_learning", {})
        if learning.get("hit_threshold", 0.8) <= learning.get("noise_threshold", 0.3):
            warnings.append("hit_threshold must be greater than noise_threshold")

    context_cfg = config.raw.get("context", {})
    if context_cfg:
        warn = context_cfg.get("warn_percentage", 50)
        checkpoint = context_cfg.get("checkpoint_percentage", 60)
        if warn >= checkpoint:
            warnings.append("warn_percentage must be less than checkpoint_percentage")

    # Check vault builder config
    vb = config.raw.get("vault_builder", {})
    if vb:
        vb_mode = vb.get("mode", "create")
        if vb_mode not in ("create", "enrich"):
            warnings.append(f"vault_builder.mode must be 'create' or 'enrich', got: {vb_mode}")
        if not vb.get("output_vault"):
            warnings.append("vault_builder.output_vault is not configured")

    return {"valid": len(warnings) == 0, "warnings": warnings}
