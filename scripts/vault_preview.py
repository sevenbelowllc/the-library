"""One-shot preview of the vault build for the current library-config.yaml.

Loads vault_builder config, instantiates enabled extractors, runs survey + preview,
prints counts and a sample of files-to-create. Does NOT write to vault.

Run:
    .venv/bin/python scripts/vault_preview.py
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


_EXTRACTOR_CLASSES = {
    "specs": SpecsExtractor,
    "obsidian_vault": ObsidianVaultExtractor,
    "claude_memory": ClaudeMemoryExtractor,
    "session_context": SessionContextExtractor,
    "jira": JiraExtractor,
    "notebooklm": NotebookLMExtractor,
    "axon_bridge": AxonBridgeExtractor,
}


async def main() -> int:
    config_path = Path("library-config.yaml")
    if not config_path.exists():
        print(f"ERROR: {config_path} not found. Run from the-library/ root.")
        return 1

    vbc = load_vault_builder_config(config_path)
    errors = validate_vault_builder_config(vbc)
    if errors:
        print("Config validation errors:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"== vault_builder preview ==")
    print(f"mode:              {vbc.mode}")
    print(f"output_vault:      {vbc.output_vault}")
    print(f"parallel:          {vbc.parallel}")
    print(f"graphify enabled:  {vbc.graphify.get('enabled')}")
    print(f"axon enabled:      {vbc.axon.get('enabled')}")
    print()

    grand_total = 0
    grand_bytes = 0
    for name, source_cfg in vbc.sources.items():
        if not source_cfg.get("enabled", True):
            print(f"[skip] {name} (disabled)")
            continue
        cls = _EXTRACTOR_CLASSES.get(name)
        if cls is None:
            print(f"[warn] {name}: no extractor class registered")
            continue
        ext = cls(config=source_cfg)
        cfg_errors = ext.validate_config()
        if cfg_errors:
            print(f"[fail] {name}: {cfg_errors}")
            continue

        survey = await ext.survey()
        preview = await ext.preview()
        print(f"[run]  {name}")
        print(f"         health:         {survey.health}")
        print(f"         file_count:     {survey.file_count}")
        print(f"         total_bytes:    {survey.total_size_bytes:,}")
        print(f"         est_tokens:     {preview.estimated_tokens:,}")
        if preview.files_to_create:
            sample = preview.files_to_create[:5]
            print(f"         sample (head):  {sample}")
            if len(preview.files_to_create) > 5:
                print(f"         ... and {len(preview.files_to_create) - 5} more")
        print()
        grand_total += survey.file_count
        grand_bytes += survey.total_size_bytes

    print(f"== totals ==")
    print(f"files: {grand_total}")
    print(f"bytes: {grand_bytes:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
