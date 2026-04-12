"""Tests for VaultBuildOrchestrator."""

from __future__ import annotations

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

    with patch.object(graphify, "build", new_callable=AsyncMock) as mock_build:
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
    result = await orch.build()
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
    result = await orch.build()
    manifest = tmp_path / "vault" / "raw" / "_build-manifest.md"
    assert manifest.exists()
    content = manifest.read_text()
    assert "failed" in content
    assert "Connection refused" in content
