"""Tests for VaultBuildOrchestrator."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from library_server.vault_builder.extractors.base import BaseExtractor
from library_server.vault_builder.types import SurveyResult, PreviewResult, ExtractResult


class SuccessExtractor(BaseExtractor):
    name = "success"
    display_name = "Success"
    source_description = "Always succeeds"
    output_subdir = "success"

    async def survey(self) -> SurveyResult:
        return SurveyResult(source_name=self.name, file_count=2, total_size_bytes=100)

    async def preview(self) -> PreviewResult:
        return PreviewResult(source_name=self.name, files_to_create=["a.md"])

    async def extract(self, output_dir: Path) -> ExtractResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "a.md").write_text("---\ntitle: A\n---\n# A\n")
        return ExtractResult(source_name=self.name, files_written=["a.md"], success=True, duration_seconds=1.0)

    def validate_config(self) -> list[str]:
        return []


class FailExtractor(BaseExtractor):
    name = "fail"
    display_name = "Fail"
    source_description = "Always fails"
    output_subdir = "fail"

    async def survey(self) -> SurveyResult:
        return SurveyResult(source_name=self.name, file_count=0, total_size_bytes=0)

    async def preview(self) -> PreviewResult:
        return PreviewResult(source_name=self.name)

    async def extract(self, output_dir: Path) -> ExtractResult:
        return ExtractResult(source_name=self.name, errors=["Connection refused"], success=False, duration_seconds=0.5)

    def validate_config(self) -> list[str]:
        return []


async def test_parallel_execution(tmp_path: Path):
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner

    registry = PluginRegistry()
    registry.register(SuccessExtractor(config={"enabled": True}))
    graphify = GraphifyRunner(config={"enabled": False})
    orch = VaultBuildOrchestrator(registry=registry, graphify_runner=graphify, output_vault=tmp_path / "vault", mode="create")
    result = await orch.build()
    assert result.any_succeeded is True
    assert result.status == "completed"


async def test_failure_isolation(tmp_path: Path):
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner

    registry = PluginRegistry()
    registry.register(SuccessExtractor(config={"enabled": True}))
    registry.register(FailExtractor(config={"enabled": True}))
    graphify = GraphifyRunner(config={"enabled": False})
    orch = VaultBuildOrchestrator(registry=registry, graphify_runner=graphify, output_vault=tmp_path / "vault", mode="create")
    result = await orch.build()
    assert result.any_succeeded is True
    assert result.status == "completed_with_warnings"
    assert len(result.extract_results) == 2


async def test_graphify_skipped_on_all_failures(tmp_path: Path):
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner

    registry = PluginRegistry()
    registry.register(FailExtractor(config={"enabled": True}))
    graphify = GraphifyRunner(config={"enabled": True})
    orch = VaultBuildOrchestrator(registry=registry, graphify_runner=graphify, output_vault=tmp_path / "vault", mode="create")

    with patch.object(graphify, "build_from_vault", new_callable=AsyncMock) as mock_build:
        result = await orch.build()
        mock_build.assert_not_called()
    assert result.status == "failed"
    assert result.graphify_status == "skipped"


async def test_build_manifest_written(tmp_path: Path):
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner

    registry = PluginRegistry()
    registry.register(SuccessExtractor(config={"enabled": True}))
    graphify = GraphifyRunner(config={"enabled": False})
    orch = VaultBuildOrchestrator(registry=registry, graphify_runner=graphify, output_vault=tmp_path / "vault", mode="create")
    await orch.build()
    manifest = tmp_path / "vault" / "raw" / "_build-manifest.md"
    assert manifest.exists()
    assert "success" in manifest.read_text()


async def test_build_manifest_records_failures(tmp_path: Path):
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner

    registry = PluginRegistry()
    registry.register(FailExtractor(config={"enabled": True}))
    graphify = GraphifyRunner(config={"enabled": False})
    orch = VaultBuildOrchestrator(registry=registry, graphify_runner=graphify, output_vault=tmp_path / "vault", mode="create")
    await orch.build()
    manifest = tmp_path / "vault" / "raw" / "_build-manifest.md"
    assert manifest.exists()
    content = manifest.read_text()
    assert "failed" in content
    assert "Connection refused" in content


# ---------------------------------------------------------------------------
# survey() tests
# ---------------------------------------------------------------------------

async def test_survey_returns_results(tmp_path: Path):
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner

    registry = PluginRegistry()
    registry.register(SuccessExtractor(config={"enabled": True}))
    graphify = GraphifyRunner(config={"enabled": False})
    orch = VaultBuildOrchestrator(registry=registry, graphify_runner=graphify, output_vault=tmp_path / "vault", mode="create")

    surveys = await orch.survey()
    assert len(surveys) == 1
    assert surveys[0]["source"] == "success"
    assert surveys[0]["file_count"] == 2


async def test_survey_with_specific_sources(tmp_path: Path):
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner

    registry = PluginRegistry()
    registry.register(SuccessExtractor(config={"enabled": True}))
    registry.register(FailExtractor(config={"enabled": True}))
    graphify = GraphifyRunner(config={"enabled": False})
    orch = VaultBuildOrchestrator(registry=registry, graphify_runner=graphify, output_vault=tmp_path / "vault", mode="create")

    surveys = await orch.survey(["success"])
    assert len(surveys) == 1
    assert surveys[0]["source"] == "success"


async def test_survey_handles_extractor_errors(tmp_path: Path):
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner

    class ErrorExtractor(SuccessExtractor):
        name = "error_ext"
        display_name = "Error"
        output_subdir = "error_ext"
        async def survey(self):
            raise RuntimeError("Survey failed")

    registry = PluginRegistry()
    registry.register(ErrorExtractor(config={"enabled": True}))
    graphify = GraphifyRunner(config={"enabled": False})
    orch = VaultBuildOrchestrator(registry=registry, graphify_runner=graphify, output_vault=tmp_path / "vault", mode="create")

    surveys = await orch.survey()
    assert len(surveys) == 1
    assert "error" in surveys[0]


# ---------------------------------------------------------------------------
# preview() tests
# ---------------------------------------------------------------------------

async def test_preview_returns_results(tmp_path: Path):
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner

    registry = PluginRegistry()
    registry.register(SuccessExtractor(config={"enabled": True}))
    graphify = GraphifyRunner(config={"enabled": False})
    orch = VaultBuildOrchestrator(registry=registry, graphify_runner=graphify, output_vault=tmp_path / "vault", mode="create")

    previews = await orch.preview()
    assert len(previews) == 1
    assert previews[0]["source"] == "success"
    assert "files_to_create" in previews[0]


async def test_preview_with_specific_sources(tmp_path: Path):
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner

    registry = PluginRegistry()
    registry.register(SuccessExtractor(config={"enabled": True}))
    registry.register(FailExtractor(config={"enabled": True}))
    graphify = GraphifyRunner(config={"enabled": False})
    orch = VaultBuildOrchestrator(registry=registry, graphify_runner=graphify, output_vault=tmp_path / "vault", mode="create")

    previews = await orch.preview(["fail"])
    assert len(previews) == 1
    assert previews[0]["source"] == "fail"


async def test_preview_handles_extractor_errors(tmp_path: Path):
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner

    class ErrorExtractor(SuccessExtractor):
        name = "error_ext"
        display_name = "Error"
        output_subdir = "error_ext"
        async def preview(self):
            raise RuntimeError("Preview failed")

    registry = PluginRegistry()
    registry.register(ErrorExtractor(config={"enabled": True}))
    graphify = GraphifyRunner(config={"enabled": False})
    orch = VaultBuildOrchestrator(registry=registry, graphify_runner=graphify, output_vault=tmp_path / "vault", mode="create")

    previews = await orch.preview()
    assert len(previews) == 1
    assert "error" in previews[0]


# ---------------------------------------------------------------------------
# build() — Graphify-enabled path and obsidian config branches
# ---------------------------------------------------------------------------

async def test_build_runs_graphify_when_enabled(tmp_path: Path):
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner

    registry = PluginRegistry()
    registry.register(SuccessExtractor(config={"enabled": True}))
    graphify = GraphifyRunner(config={"enabled": True, "command": "graphify"})
    orch = VaultBuildOrchestrator(registry=registry, graphify_runner=graphify, output_vault=tmp_path / "vault", mode="create")

    with patch.object(graphify, "build_from_vault", new_callable=AsyncMock, return_value={"status": "success", "nodes": 10}) as mock_build:
        result = await orch.build()
        mock_build.assert_called_once()

    assert result.graphify_status == "success"
    assert result.status == "completed"


async def test_build_writes_obsidian_config_in_create_mode(tmp_path: Path):
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner
    import json

    registry = PluginRegistry()
    registry.register(SuccessExtractor(config={"enabled": True}))
    graphify = GraphifyRunner(config={"enabled": False})
    orch = VaultBuildOrchestrator(registry=registry, graphify_runner=graphify, output_vault=tmp_path / "vault", mode="create")

    await orch.build()

    obsidian_dir = tmp_path / "vault" / ".obsidian"
    assert obsidian_dir.exists()
    assert (obsidian_dir / "graph.json").exists()
    assert (obsidian_dir / "app.json").exists()

    graph_cfg = json.loads((obsidian_dir / "graph.json").read_text())
    assert "colorGroups" in graph_cfg


async def test_build_skips_obsidian_config_in_enrich_mode(tmp_path: Path):
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner

    vault = tmp_path / "vault"
    vault.mkdir()

    registry = PluginRegistry()
    registry.register(SuccessExtractor(config={"enabled": True}))
    graphify = GraphifyRunner(config={"enabled": False})
    orch = VaultBuildOrchestrator(registry=registry, graphify_runner=graphify, output_vault=vault, mode="enrich")

    await orch.build()

    # .obsidian should NOT be created in enrich mode
    assert not (vault / ".obsidian").exists()


async def test_build_with_no_extractors(tmp_path: Path):
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner

    registry = PluginRegistry()
    graphify = GraphifyRunner(config={"enabled": False})
    orch = VaultBuildOrchestrator(registry=registry, graphify_runner=graphify, output_vault=tmp_path / "vault", mode="create")

    result = await orch.build()
    assert result.status == "failed"


async def test_build_handles_extractor_exception(tmp_path: Path):
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner

    class CrashExtractor(SuccessExtractor):
        name = "crash"
        display_name = "Crash"
        output_subdir = "crash"
        async def extract(self, output_dir):
            raise RuntimeError("Extractor crashed")

    registry = PluginRegistry()
    registry.register(CrashExtractor(config={"enabled": True}))
    graphify = GraphifyRunner(config={"enabled": False})
    orch = VaultBuildOrchestrator(registry=registry, graphify_runner=graphify, output_vault=tmp_path / "vault", mode="create")

    result = await orch.build()
    assert result.status == "failed"
    assert len(result.extract_results) == 1
    assert "Extractor crashed" in result.extract_results[0].errors[0]


# ---------------------------------------------------------------------------
# validate_all() — pre-build validation gate (Gap 1)
# ---------------------------------------------------------------------------

class InvalidConfigExtractor(BaseExtractor):
    name = "bad_config"
    display_name = "Bad Config"
    source_description = "Has config errors"
    output_subdir = "bad_config"

    async def survey(self) -> SurveyResult:
        return SurveyResult(source_name=self.name, file_count=0, total_size_bytes=0)

    async def preview(self) -> PreviewResult:
        return PreviewResult(source_name=self.name)

    async def extract(self, output_dir: Path) -> ExtractResult:
        return ExtractResult(source_name=self.name, success=False)

    def validate_config(self) -> list[str]:
        return ["Missing required config: api_key", "Missing env var: SOME_TOKEN"]


async def test_validate_all_returns_errors_for_invalid_extractors(tmp_path: Path):
    """validate_all() must surface config errors from each extractor."""
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner

    registry = PluginRegistry()
    registry.register(SuccessExtractor(config={"enabled": True}))
    registry.register(InvalidConfigExtractor(config={"enabled": True}))
    graphify = GraphifyRunner(config={"enabled": False})
    orch = VaultBuildOrchestrator(registry=registry, graphify_runner=graphify, output_vault=tmp_path / "vault", mode="create")

    errors = orch.validate_all(registry.get_enabled())
    assert "bad_config" in errors
    assert len(errors["bad_config"]) == 2
    assert "success" not in errors


async def test_build_includes_config_warnings_in_result(tmp_path: Path):
    """Build result must carry config_warnings so callers know about misconfigured extractors."""
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner

    registry = PluginRegistry()
    registry.register(SuccessExtractor(config={"enabled": True}))
    registry.register(InvalidConfigExtractor(config={"enabled": True}))
    graphify = GraphifyRunner(config={"enabled": False})
    orch = VaultBuildOrchestrator(registry=registry, graphify_runner=graphify, output_vault=tmp_path / "vault", mode="create")

    result = await orch.build()
    assert "bad_config" in result.config_warnings
    # Build continues — validation errors are warnings, not hard failures
    assert result.any_succeeded is True
    # Status should reflect warnings from both failed extractor AND config errors
    assert result.status == "completed_with_warnings"


async def test_build_with_all_valid_config_has_no_warnings(tmp_path: Path):
    """When all extractors have valid config, config_warnings must be empty."""
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner

    registry = PluginRegistry()
    registry.register(SuccessExtractor(config={"enabled": True}))
    graphify = GraphifyRunner(config={"enabled": False})
    orch = VaultBuildOrchestrator(registry=registry, graphify_runner=graphify, output_vault=tmp_path / "vault", mode="create")

    result = await orch.build()
    assert result.config_warnings == {}
    assert result.status == "completed"


# ---------------------------------------------------------------------------
# Graphify quality gate (Gap 3)
# ---------------------------------------------------------------------------

async def test_graphify_skipped_when_no_extractors_succeed(tmp_path: Path):
    """Graphify must not run if no extractor succeeded — even if graphify is enabled."""
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner

    registry = PluginRegistry()
    registry.register(FailExtractor(config={"enabled": True}))
    graphify = GraphifyRunner(config={"enabled": True, "command": "graphify"})
    orch = VaultBuildOrchestrator(registry=registry, graphify_runner=graphify, output_vault=tmp_path / "vault", mode="create")

    with patch.object(graphify, "build_from_vault", new_callable=AsyncMock) as mock_build:
        result = await orch.build()
        mock_build.assert_not_called()

    assert result.graphify_status == "skipped"
    assert "skipped" in result.graphify_message.lower()


async def test_graphify_runs_when_any_extractor_succeeds(tmp_path: Path):
    """Graphify must run when at least one extractor succeeds, even if others fail."""
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner

    registry = PluginRegistry()
    registry.register(SuccessExtractor(config={"enabled": True}))
    registry.register(FailExtractor(config={"enabled": True}))
    graphify = GraphifyRunner(config={"enabled": True, "command": "graphify"})
    orch = VaultBuildOrchestrator(registry=registry, graphify_runner=graphify, output_vault=tmp_path / "vault", mode="create")

    with patch.object(graphify, "build_from_vault", new_callable=AsyncMock, return_value={"status": "success"}) as mock_build:
        result = await orch.build()
        mock_build.assert_called_once()

    assert result.graphify_status == "success"


async def test_build_with_sources_filter_runs_only_named_extractors(tmp_path: Path):
    """build(sources=[...]) must only run the named extractors."""
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner

    registry = PluginRegistry()
    registry.register(SuccessExtractor(config={"enabled": True}))
    registry.register(FailExtractor(config={"enabled": True}))
    graphify = GraphifyRunner(config={"enabled": False})
    orch = VaultBuildOrchestrator(registry=registry, graphify_runner=graphify, output_vault=tmp_path / "vault", mode="create")

    result = await orch.build(sources=["success"])
    # Only "success" extractor ran — FailExtractor was not included
    assert result.any_succeeded is True
    assert len(result.extract_results) == 1
    assert result.extract_results[0].source_name == "success"


async def test_survey_includes_structure_summary_as_detail(tmp_path: Path):
    """survey() must include structure_summary in the 'detail' key when non-empty."""
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner

    class DetailedExtractor(SuccessExtractor):
        name = "detailed"
        display_name = "Detailed"
        output_subdir = "detailed"
        async def survey(self) -> SurveyResult:
            return SurveyResult(
                source_name=self.name, file_count=5, total_size_bytes=1000,
                structure_summary="5 repos: compliance-core, compliance-ui",
            )

    registry = PluginRegistry()
    registry.register(DetailedExtractor(config={"enabled": True}))
    graphify = GraphifyRunner(config={"enabled": False})
    orch = VaultBuildOrchestrator(registry=registry, graphify_runner=graphify, output_vault=tmp_path / "vault", mode="create")

    surveys = await orch.survey()
    assert surveys[0]["detail"] == "5 repos: compliance-core, compliance-ui"


# ---------------------------------------------------------------------------
# Concurrency controls: parallel / max_parallel_extractors / fail_fast
# ---------------------------------------------------------------------------

class _CountingExtractor(BaseExtractor):
    """Records max concurrent extract() calls via a shared tracker dict."""
    def __init__(self, name, tracker, delay=0.02, fail=False):
        super().__init__(config={"enabled": True})
        self.name = name
        self.output_subdir = name
        self._tracker = tracker
        self._delay = delay
        self._fail = fail

    def validate_config(self):
        return []

    async def survey(self):
        raise NotImplementedError

    async def preview(self):
        raise NotImplementedError

    async def extract(self, output_dir):
        self._tracker["running"] += 1
        self._tracker["max"] = max(self._tracker["max"], self._tracker["running"])
        await asyncio.sleep(self._delay)
        self._tracker["running"] -= 1
        if self._fail:
            return ExtractResult(source_name=self.name, errors=["boom"], success=False)
        return ExtractResult(source_name=self.name, files_written=["f.md"], success=True)


@pytest.mark.asyncio
async def test_max_parallel_extractors_limits_concurrency(tmp_path):
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner

    tracker = {"running": 0, "max": 0}
    registry = PluginRegistry()
    for i in range(4):
        registry.register(_CountingExtractor(f"e{i}", tracker))
    orch = VaultBuildOrchestrator(
        registry=registry, graphify_runner=GraphifyRunner(config={}),
        output_vault=tmp_path, mode="enrich",
        parallel=True, max_parallel_extractors=2,
    )
    await orch.build()
    assert tracker["max"] <= 2


@pytest.mark.asyncio
async def test_parallel_false_runs_sequentially(tmp_path):
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner

    tracker = {"running": 0, "max": 0}
    registry = PluginRegistry()
    for i in range(3):
        registry.register(_CountingExtractor(f"e{i}", tracker))
    orch = VaultBuildOrchestrator(
        registry=registry, graphify_runner=GraphifyRunner(config={}),
        output_vault=tmp_path, mode="enrich",
        parallel=False,
    )
    await orch.build()
    assert tracker["max"] == 1


@pytest.mark.asyncio
async def test_fail_fast_skips_undispatched_extractors(tmp_path):
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner

    tracker = {"running": 0, "max": 0}
    registry = PluginRegistry()
    registry.register(_CountingExtractor("failer", tracker, fail=True))
    for i in range(3):
        registry.register(_CountingExtractor(f"e{i}", tracker))
    orch = VaultBuildOrchestrator(
        registry=registry, graphify_runner=GraphifyRunner(config={}),
        output_vault=tmp_path, mode="enrich",
        parallel=False, fail_fast=True,  # sequential => deterministic ordering
    )
    result = await orch.build()
    skipped = [r for r in result.extract_results if r.errors and "Skipped: fail_fast" in r.errors[0]]
    assert len(skipped) == 3
    assert result.status in ("failed", "completed_with_warnings")


# ---------------------------------------------------------------------------
# detect_vault_state() — target directory classification
# ---------------------------------------------------------------------------

def test_detect_vault_state_missing_directory(tmp_path: Path):
    from library_server.vault_builder.orchestrator import detect_vault_state
    from library_server.vault_builder.types import VaultState

    assert detect_vault_state(tmp_path / "does-not-exist") == VaultState.NEW_VAULT


def test_detect_vault_state_empty_directory(tmp_path: Path):
    from library_server.vault_builder.orchestrator import detect_vault_state
    from library_server.vault_builder.types import VaultState

    empty = tmp_path / "empty"
    empty.mkdir()
    assert detect_vault_state(empty) == VaultState.NEW_VAULT


def test_detect_vault_state_previous_build(tmp_path: Path):
    """A raw/_build-manifest.md marks a vault The Library has already built."""
    from library_server.vault_builder.orchestrator import detect_vault_state
    from library_server.vault_builder.types import VaultState

    vault = tmp_path / "vault"
    (vault / "raw").mkdir(parents=True)
    (vault / "raw" / "_build-manifest.md").write_text("# Build manifest")
    assert detect_vault_state(vault) == VaultState.PREVIOUS_BUILD


def test_detect_vault_state_existing_vault_with_raw(tmp_path: Path):
    """.obsidian + raw/ but no manifest — a vault built by something else, or a
    partial/interrupted build."""
    from library_server.vault_builder.orchestrator import detect_vault_state
    from library_server.vault_builder.types import VaultState

    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / "raw").mkdir()
    assert detect_vault_state(vault) == VaultState.EXISTING_VAULT_WITH_RAW


def test_detect_vault_state_existing_vault_no_raw(tmp_path: Path):
    """A real Obsidian vault (has .obsidian/) that The Library has never touched."""
    from library_server.vault_builder.orchestrator import detect_vault_state
    from library_server.vault_builder.types import VaultState

    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / "some-note.md").write_text("hi")
    assert detect_vault_state(vault) == VaultState.EXISTING_VAULT_NO_RAW


def test_detect_vault_state_non_vault_directory(tmp_path: Path):
    """A non-empty directory with neither .obsidian/ nor raw/ — some unrelated content."""
    from library_server.vault_builder.orchestrator import detect_vault_state
    from library_server.vault_builder.types import VaultState

    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "random-file.txt").write_text("hi")
    assert detect_vault_state(vault) == VaultState.NON_VAULT_DIRECTORY


# ---------------------------------------------------------------------------
# check_safety_gate() — create-mode overwrite protection
# ---------------------------------------------------------------------------

def test_check_safety_gate_enrich_mode_never_blocks():
    """enrich mode is explicitly designed to layer onto existing content."""
    from library_server.vault_builder.orchestrator import check_safety_gate
    from library_server.vault_builder.types import VaultState

    gate = check_safety_gate("enrich", VaultState.EXISTING_VAULT_WITH_RAW, force=False)
    assert gate["blocked"] is False


def test_check_safety_gate_create_mode_new_vault_not_blocked():
    """A brand-new target directory is always safe under create mode."""
    from library_server.vault_builder.orchestrator import check_safety_gate
    from library_server.vault_builder.types import VaultState

    gate = check_safety_gate("create", VaultState.NEW_VAULT, force=False)
    assert gate["blocked"] is False


def test_check_safety_gate_create_mode_blocks_existing_content_without_force():
    """create mode over existing content must be blocked unless force=True — this is
    the safety gate that prevents an accidental overwrite of a real vault."""
    from library_server.vault_builder.orchestrator import check_safety_gate
    from library_server.vault_builder.types import VaultState

    gate = check_safety_gate("create", VaultState.EXISTING_VAULT_WITH_RAW, force=False)
    assert gate["blocked"] is True
    assert "force" in gate["message"].lower()


def test_check_safety_gate_create_mode_force_overrides_block():
    from library_server.vault_builder.orchestrator import check_safety_gate
    from library_server.vault_builder.types import VaultState

    gate = check_safety_gate("create", VaultState.EXISTING_VAULT_NO_RAW, force=True)
    assert gate["blocked"] is False
    assert "force" in gate["message"].lower()


def test_check_safety_gate_create_mode_blocks_non_vault_directory():
    from library_server.vault_builder.orchestrator import check_safety_gate
    from library_server.vault_builder.types import VaultState

    gate = check_safety_gate("create", VaultState.NON_VAULT_DIRECTORY, force=False)
    assert gate["blocked"] is True
