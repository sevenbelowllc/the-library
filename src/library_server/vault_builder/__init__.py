"""The Library Vault Builder Toolkit.

ETL pipeline that extracts data from multiple sources, normalizes to
structured Markdown with YAML frontmatter, and triggers Graphify to
build a connected Obsidian vault.
"""

from library_server.vault_builder.config import (
    VaultBuilderConfig,
    load_vault_builder_config,
    validate_vault_builder_config,
)
from library_server.vault_builder.orchestrator import (
    VaultBuildOrchestrator,
    detect_vault_state,
    check_safety_gate,
)
from library_server.vault_builder.registry import PluginRegistry
from library_server.vault_builder.graphify_runner import GraphifyRunner
from library_server.vault_builder.output import OutputWriter
from library_server.vault_builder.types import (
    BuildResult,
    ExtractResult,
    PreviewResult,
    SurveyResult,
    VaultState,
)

__all__ = [
    "VaultBuilderConfig",
    "load_vault_builder_config",
    "validate_vault_builder_config",
    "VaultBuildOrchestrator",
    "detect_vault_state",
    "check_safety_gate",
    "PluginRegistry",
    "GraphifyRunner",
    "OutputWriter",
    "BuildResult",
    "ExtractResult",
    "PreviewResult",
    "SurveyResult",
    "VaultState",
]
