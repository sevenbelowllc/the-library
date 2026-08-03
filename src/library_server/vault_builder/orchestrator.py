"""VaultBuildOrchestrator — parallel extraction, survey detection, and build manifest."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from library_server.vault_builder.graphify_runner import GraphifyRunner
from library_server.vault_builder.output import OutputWriter
from library_server.vault_builder.registry import PluginRegistry
from library_server.vault_builder.types import BuildResult, ExtractResult, VaultState


def detect_vault_state(vault_path: Path) -> VaultState:
    """Detect the current state of the target vault directory."""
    if not vault_path.exists():
        return VaultState.NEW_VAULT
    contents = list(vault_path.iterdir())
    if not contents:
        return VaultState.NEW_VAULT
    has_obsidian = (vault_path / ".obsidian").is_dir()
    has_raw = (vault_path / "raw").is_dir()
    has_manifest = (vault_path / "raw" / "_build-manifest.md").exists() if has_raw else False
    if has_manifest:
        return VaultState.PREVIOUS_BUILD
    if has_obsidian and has_raw:
        return VaultState.EXISTING_VAULT_WITH_RAW
    if has_obsidian:
        return VaultState.EXISTING_VAULT_NO_RAW
    return VaultState.NON_VAULT_DIRECTORY


def check_safety_gate(mode: str, vault_state: VaultState, force: bool = False) -> dict:
    """Check if the build should be blocked based on mode and vault state."""
    if mode == "create" and vault_state in (
        VaultState.EXISTING_VAULT_NO_RAW,
        VaultState.EXISTING_VAULT_WITH_RAW,
        VaultState.NON_VAULT_DIRECTORY,
    ):
        if force:
            return {"blocked": False, "message": "Force flag set — proceeding with create mode."}
        return {
            "blocked": True,
            "message": (
                f"output_vault contains existing content (detected: {vault_state.value}). "
                "Mode is set to 'create' which would overwrite this content. "
                "Options: switch to mode: enrich, change output_vault, or pass force: true."
            ),
        }
    return {"blocked": False, "message": "Safe to proceed."}


class VaultBuildOrchestrator:
    """Orchestrates parallel extraction and Graphify build."""

    def __init__(
        self,
        registry: PluginRegistry,
        graphify_runner: GraphifyRunner,
        output_vault: Path,
        mode: str = "create",
        parallel: bool = True,
        max_parallel_extractors: int = 8,
        fail_fast: bool = False,
    ) -> None:
        self.registry = registry
        self.graphify_runner = graphify_runner
        self.output_vault = output_vault
        self.mode = mode
        self.parallel = parallel
        self.max_parallel_extractors = max_parallel_extractors
        self.fail_fast = fail_fast

    def validate_all(self, extractors: list) -> dict[str, list[str]]:
        """Run validate_config() on each extractor. Returns {name: [errors]} for any with errors."""
        issues: dict[str, list[str]] = {}
        for ext in extractors:
            errors = ext.validate_config()
            if errors:
                issues[ext.name] = errors
        return issues

    async def build(
        self,
        sources: list[str] | None = None,
        force: bool = False,
    ) -> BuildResult:
        """Run full build: validate → extract (parallel) → Graphify."""
        start = time.monotonic()

        raw_dir = self.output_vault / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        # Write .obsidian/ config on first build (create mode only)
        if self.mode == "create":
            self._write_obsidian_config()

        # Get extractors
        if sources:
            extractors = self.registry.get_by_names(sources)
        else:
            extractors = self.registry.get_enabled()

        if not extractors:
            return BuildResult(status="failed", duration_seconds=time.monotonic() - start)

        # Pre-build validation gate — surface config errors before touching anything
        config_errors = self.validate_all(extractors)

        # Run extractors under a concurrency limit. parallel=False degrades to
        # a limit of 1 (sequential). fail_fast skips extractors that have not
        # started once any extractor has failed; in-flight ones finish.
        limit = self.max_parallel_extractors if self.parallel else 1
        semaphore = asyncio.Semaphore(max(1, limit))
        failed_first: list[str] = []  # single-element list as a mutable flag

        async def _run_one(ext) -> ExtractResult:
            async with semaphore:
                if self.fail_fast and failed_first:
                    return ExtractResult(
                        source_name=ext.name,
                        errors=[f"Skipped: fail_fast after '{failed_first[0]}' failed"],
                        success=False,
                    )
                try:
                    result = await ext.extract(raw_dir / ext.output_subdir)
                except BaseException as exc:
                    result = ExtractResult(source_name=ext.name, errors=[str(exc)], success=False)
                if not result.success and not failed_first:
                    failed_first.append(ext.name)
                return result

        extract_results = list(
            await asyncio.gather(*[_run_one(ext) for ext in extractors])
        )

        # Write build manifest
        writer = OutputWriter(base_dir=raw_dir)
        total_duration = time.monotonic() - start
        writer.write_manifest(extract_results, total_duration)

        # Graphify quality gate — require at least one code or document source to succeed
        all_failed = all(not r.success for r in extract_results)
        graphify_status = "skipped"
        graphify_message = ""

        graphify_enabled = self.graphify_runner.config.get("enabled", False)
        if graphify_enabled:
            if all_failed:
                graphify_status = "skipped"
                graphify_message = "All extractors failed — Graphify skipped."
            else:
                graphify_out = self.output_vault / "graphify-out"
                wiki_dir = self.output_vault / "wiki"
                # On a fresh `create` build the wiki/ dir is empty, so the
                # to_wiki() auto-stubs are useful bootstrap content. On any
                # other mode (enrich, re-run), wiki/ likely holds compiled
                # articles — never regenerate. Per 2026-05-22 post-mortem.
                # Path.glob() on a non-existent dir returns an empty iterator,
                # so this expression is safe whether wiki_dir exists or not.
                regenerate_wiki = (
                    self.mode == "create"
                    and not any(wiki_dir.glob("*.md"))
                )
                graphify_result = await self.graphify_runner.build_from_vault(
                    raw_dir=raw_dir,
                    output_dir=graphify_out,
                    wiki_dir=wiki_dir,
                    regenerate_wiki=regenerate_wiki,
                )
                graphify_status = graphify_result.get("status", "error")
                graphify_message = graphify_result.get("message", "")

        # Determine overall status
        if all_failed:
            status = "failed"
        elif any(not r.success for r in extract_results) or config_errors:
            status = "completed_with_warnings"
        else:
            status = "completed"

        return BuildResult(
            status=status, extract_results=extract_results,
            graphify_status=graphify_status, graphify_message=graphify_message,
            duration_seconds=time.monotonic() - start,
            manifest_path=str(raw_dir / "_build-manifest.md"),
            config_warnings=config_errors,
        )

    def _write_obsidian_config(self) -> None:
        """Write .obsidian/ config with graph color groups (create mode only)."""
        obsidian_dir = self.output_vault / ".obsidian"
        obsidian_dir.mkdir(parents=True, exist_ok=True)
        graph_config = {
            "colorGroups": [
                {"query": "path:raw/repos/", "color": {"a": 1, "rgb": 4488191}},
                {"query": "path:raw/specs/", "color": {"a": 1, "rgb": 16766720}},
                {"query": "path:raw/jira/", "color": {"a": 1, "rgb": 5025616}},
                {"query": "path:raw/vault/", "color": {"a": 1, "rgb": 8421504}},
                {"query": "path:wiki/", "color": {"a": 1, "rgb": 16777215}},
            ]
        }
        (obsidian_dir / "graph.json").write_text(json.dumps(graph_config, indent=2))
        (obsidian_dir / "app.json").write_text(json.dumps({"theme": "obsidian"}, indent=2))

    async def survey(self, sources: list[str] | None = None) -> list[dict]:
        """Survey all sources in parallel."""
        extractors = self.registry.get_by_names(sources) if sources else self.registry.get_enabled()
        tasks = [ext.survey() for ext in extractors]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        surveys: list[dict] = []
        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                surveys.append({"source": extractors[i].name, "error": str(result)})
            else:
                entry: dict = {
                    "source": result.source_name, "file_count": result.file_count,
                    "total_size_bytes": result.total_size_bytes, "health": result.health,
                }
                if result.structure_summary:
                    entry["detail"] = result.structure_summary
                surveys.append(entry)
        return surveys

    async def preview(self, sources: list[str] | None = None) -> list[dict]:
        """Preview all sources in parallel."""
        extractors = self.registry.get_by_names(sources) if sources else self.registry.get_enabled()
        tasks = [ext.preview() for ext in extractors]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        previews: list[dict] = []
        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                previews.append({"source": extractors[i].name, "error": str(result)})
            else:
                previews.append({
                    "source": result.source_name, "files_to_create": result.files_to_create,
                    "estimated_tokens": result.estimated_tokens, "warnings": result.warnings,
                })
        return previews
