"""Real vault build driver — mirrors what library_vault_builder_build MCP tool does.

Loads ./library-config.yaml, instantiates enabled extractors per registry,
runs VaultBuildOrchestrator.build(force=False), reports.

Run:
    .venv/bin/python scripts/vault_build.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from library_server.vault_builder.config import (  # noqa: E402
    load_vault_builder_config,
    validate_vault_builder_config,
)
from library_server.vault_builder.extractors.axon_bridge import AxonBridgeExtractor  # noqa: E402
from library_server.vault_builder.extractors.claude_memory import ClaudeMemoryExtractor  # noqa: E402
from library_server.vault_builder.extractors.jira import JiraExtractor  # noqa: E402
from library_server.vault_builder.extractors.notebooklm import NotebookLMExtractor  # noqa: E402
from library_server.vault_builder.extractors.obsidian_vault import ObsidianVaultExtractor  # noqa: E402
from library_server.vault_builder.extractors.session_context import SessionContextExtractor  # noqa: E402
from library_server.vault_builder.extractors.specs import SpecsExtractor  # noqa: E402
from library_server.vault_builder.graphify_runner import GraphifyRunner  # noqa: E402
from library_server.vault_builder.orchestrator import (  # noqa: E402
    VaultBuildOrchestrator,
    check_safety_gate,
    detect_vault_state,
)
from library_server.vault_builder.registry import PluginRegistry  # noqa: E402


_EXTRACTOR_MAP = {
    "specs": SpecsExtractor,
    "claude_memory": ClaudeMemoryExtractor,
    "session_context": SessionContextExtractor,
    "notebooklm": NotebookLMExtractor,
    "obsidian_vault": ObsidianVaultExtractor,
    "jira": JiraExtractor,
    "axon_bridge": AxonBridgeExtractor,
}


async def main() -> int:
    config_path = Path("library-config.yaml")
    if not config_path.exists():
        print(f"ERROR: {config_path} not found. Run from the-library/ root.")
        return 1

    vb_cfg = load_vault_builder_config(config_path)
    errors = validate_vault_builder_config(vb_cfg)
    if errors:
        print("Config errors:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("== vault build ==")
    print(f"mode:              {vb_cfg.mode}")
    print(f"output_vault:      {vb_cfg.output_vault}")
    print(f"parallel:          {vb_cfg.parallel}")
    print(f"max_parallel:      {vb_cfg.max_parallel_extractors}")
    print(f"graphify enabled:  {vb_cfg.graphify.get('enabled')}")
    print()

    state = detect_vault_state(vb_cfg.output_vault)
    print(f"vault state:       {state.name}")
    gate = check_safety_gate(vb_cfg.mode, state, force=False)
    if gate["blocked"]:
        print(f"BLOCKED: {gate['message']}")
        return 1
    print("safety gate:       cleared")
    print()

    registry = PluginRegistry()
    for name, cls in _EXTRACTOR_MAP.items():
        source_cfg = vb_cfg.sources.get(name)
        if source_cfg and source_cfg.get("enabled", True):
            registry.register(cls(config=source_cfg))
            print(f"  + registered:    {name}")
        else:
            print(f"  - skipped:       {name}")
    print()

    graphify_runner = GraphifyRunner(config=vb_cfg.graphify)
    orch = VaultBuildOrchestrator(
        registry=registry,
        graphify_runner=graphify_runner,
        output_vault=vb_cfg.output_vault,
        mode=vb_cfg.mode,
    )

    print("== executing build ==")
    result = await orch.build(force=False)
    print()
    print(f"status:            {result.status}")
    print(f"duration:          {result.duration_seconds:.2f}s")
    print(f"manifest:          {result.manifest_path}")
    print(f"graphify_status:   {result.graphify_status}")
    if result.graphify_message:
        print(f"graphify_message:  {result.graphify_message}")
    print()
    for r in result.extract_results:
        print(f"  {r.source_name}: success={r.success} written={len(r.files_written)} errors={len(r.errors)}")
        for err in r.errors[:5]:
            print(f"      ERR: {err}")
        if len(r.errors) > 5:
            print(f"      ... and {len(r.errors) - 5} more errors")

    return 0 if result.status in ("completed", "completed_with_warnings") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
