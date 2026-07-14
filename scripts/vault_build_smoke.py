"""T2/T3 smoke: invoke vault builder over a synthetic fixture.

Hardcoded paths target /tmp/test-rr → /tmp/test-vault. Standalone — does not
read library-config.yaml. Verifies:
  - orchestrator.build() runs to completion
  - raw/vault/** files created with expected names
  - manifest written
  - frontmatter parses as YAML and contains required keys
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from library_server.vault_builder.config import VaultBuilderConfig  # noqa: E402
from library_server.vault_builder.extractors.obsidian_vault import ObsidianVaultExtractor  # noqa: E402
from library_server.vault_builder.graphify_runner import GraphifyRunner  # noqa: E402
from library_server.vault_builder.orchestrator import VaultBuildOrchestrator, detect_vault_state  # noqa: E402
from library_server.vault_builder.registry import PluginRegistry  # noqa: E402


async def main() -> int:
    source_root = Path("/tmp/test-rr")
    output_vault = Path("/tmp/test-vault")
    assert source_root.exists(), f"source not found: {source_root}"
    output_vault.mkdir(parents=True, exist_ok=True)

    state = detect_vault_state(output_vault)
    print(f"== pre-build state: {state.name}")

    cfg = VaultBuilderConfig(
        mode="create",
        output_vault=output_vault,
        parallel=True,
        max_parallel_extractors=2,
        fail_fast=False,
        sources={
            "obsidian_vault": {
                "enabled": True,
                "source_path": str(source_root),
                "include_extensions": [".md"],
                "exclude_dirs": [],
            }
        },
        graphify={"enabled": True, "command": "graphify", "mode": "deep"},
        axon={"enabled": False},
        preserve=[],
    )

    registry = PluginRegistry()
    registry.register(ObsidianVaultExtractor(config=cfg.sources["obsidian_vault"]))
    graphify_runner = GraphifyRunner(config=cfg.graphify)
    orch = VaultBuildOrchestrator(
        registry=registry,
        graphify_runner=graphify_runner,
        output_vault=output_vault,
        mode=cfg.mode,
    )

    result = await orch.build(force=False)
    print(f"== build status:    {result.status}")
    print(f"== duration:        {result.duration_seconds:.2f}s")
    for r in result.extract_results:
        print(f"   - {r.source_name}: success={r.success} written={len(r.files_written)} errors={len(r.errors)}")
        for err in r.errors:
            print(f"        ERR: {err}")

    raw = output_vault / "raw"
    print()
    print("== raw/ tree:")
    for p in sorted(raw.rglob("*")):
        if p.is_file():
            rel = p.relative_to(raw)
            size = p.stat().st_size
            print(f"   {rel}  ({size}b)")

    print()
    print(f"== manifest exists: {(raw / '_build-manifest.md').exists()}")

    # T3: inspect one file's frontmatter
    candidates = list(raw.rglob("scope.md"))
    if candidates:
        sample = candidates[0]
        text = sample.read_text()
        parts = text.split("---\n", 2)
        if len(parts) >= 3:
            fm = yaml.safe_load(parts[1])
            body = parts[2]
            print()
            print(f"== sample frontmatter ({sample.relative_to(raw)}):")
            for k, v in fm.items():
                print(f"   {k}: {v}")
            print("== body preview:")
            print("   " + "\n   ".join(body.splitlines()[:5]))
        else:
            print(f"!! sample {sample}: no frontmatter delimiter found")
            return 1

    # Sanity assertions
    expected_files = {"CLAUDE.md", "scope.md", "glossary.md", "TESTING-STANDARD.md", "JIRA-WORKFLOW.md"}
    written = {Path(r.files_written[i]).name
               for r in result.extract_results
               for i in range(len(r.files_written))}
    missing = expected_files - written
    if missing:
        print(f"!! MISSING: {missing}")
        return 1
    print("== all 5 expected files written: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
