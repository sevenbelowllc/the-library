"""Tests for PluginRegistry — extractor discovery and management."""

from __future__ import annotations

from pathlib import Path

import pytest

from library_server.vault_builder.extractors.base import BaseExtractor
from library_server.vault_builder.types import SurveyResult, PreviewResult, ExtractResult


class FakeExtractor(BaseExtractor):
    name = "fake"
    display_name = "Fake Extractor"
    source_description = "For testing"
    output_subdir = "fake"

    async def survey(self) -> SurveyResult:
        return SurveyResult(source_name=self.name, file_count=1, total_size_bytes=100)

    async def preview(self) -> PreviewResult:
        return PreviewResult(source_name=self.name, files_to_create=["a.md"])

    async def extract(self, output_dir: Path) -> ExtractResult:
        return ExtractResult(source_name=self.name, files_written=["a.md"], success=True)

    def validate_config(self) -> list[str]:
        return []


class BadExtractor(BaseExtractor):
    name = "bad"
    display_name = "Bad Extractor"
    source_description = "Always invalid"
    output_subdir = "bad"

    async def survey(self) -> SurveyResult:
        return SurveyResult(source_name=self.name, file_count=0, total_size_bytes=0)

    async def preview(self) -> PreviewResult:
        return PreviewResult(source_name=self.name)

    async def extract(self, output_dir: Path) -> ExtractResult:
        return ExtractResult(source_name=self.name, success=False)

    def validate_config(self) -> list[str]:
        return ["Always fails"]


def test_register_and_list():
    from library_server.vault_builder.registry import PluginRegistry
    registry = PluginRegistry()
    registry.register(FakeExtractor(config={"enabled": True}))
    names = registry.list_extractors()
    assert "fake" in names


def test_get_extractor_by_name():
    from library_server.vault_builder.registry import PluginRegistry
    registry = PluginRegistry()
    ext = FakeExtractor(config={"enabled": True})
    registry.register(ext)
    found = registry.get("fake")
    assert found is ext


def test_get_unknown_extractor_returns_none():
    from library_server.vault_builder.registry import PluginRegistry
    registry = PluginRegistry()
    assert registry.get("nonexistent") is None


def test_get_enabled_extractors():
    from library_server.vault_builder.registry import PluginRegistry
    registry = PluginRegistry()
    registry.register(FakeExtractor(config={"enabled": True}))
    registry.register(BadExtractor(config={"enabled": False}))
    enabled = registry.get_enabled()
    assert len(enabled) == 1
    assert enabled[0].name == "fake"


def test_get_extractors_by_names():
    from library_server.vault_builder.registry import PluginRegistry
    registry = PluginRegistry()
    registry.register(FakeExtractor(config={"enabled": True}))
    registry.register(BadExtractor(config={"enabled": True}))
    selected = registry.get_by_names(["fake"])
    assert len(selected) == 1
    assert selected[0].name == "fake"


def test_validate_all():
    from library_server.vault_builder.registry import PluginRegistry
    registry = PluginRegistry()
    registry.register(FakeExtractor(config={"enabled": True}))
    registry.register(BadExtractor(config={"enabled": True}))
    errors = registry.validate_all()
    assert "bad" in errors
    assert "fake" not in errors


def test_duplicate_name_raises():
    from library_server.vault_builder.registry import PluginRegistry
    registry = PluginRegistry()
    registry.register(FakeExtractor(config={"enabled": True}))
    with pytest.raises(ValueError, match="already registered"):
        registry.register(FakeExtractor(config={"enabled": True}))


def test_duplicate_output_subdir_raises():
    from library_server.vault_builder.registry import PluginRegistry

    class DuplicateSubdir(FakeExtractor):
        name = "duplicate"
        output_subdir = "fake"  # same as FakeExtractor

    registry = PluginRegistry()
    registry.register(FakeExtractor(config={"enabled": True}))
    with pytest.raises(ValueError, match="output_subdir"):
        registry.register(DuplicateSubdir(config={"enabled": True}))
