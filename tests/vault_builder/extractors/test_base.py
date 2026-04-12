"""Tests for BaseExtractor ABC — contract enforcement."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_cannot_instantiate_base_directly():
    from library_server.vault_builder.extractors.base import BaseExtractor
    with pytest.raises(TypeError, match="abstract"):
        BaseExtractor(config={})


def test_concrete_extractor_must_implement_all_methods():
    from library_server.vault_builder.extractors.base import BaseExtractor

    class IncompleteExtractor(BaseExtractor):
        name = "incomplete"
        display_name = "Incomplete"
        source_description = "Missing methods"
        output_subdir = "incomplete"

    with pytest.raises(TypeError, match="abstract"):
        IncompleteExtractor(config={})


def test_concrete_extractor_works(tmp_path: Path):
    from library_server.vault_builder.extractors.base import BaseExtractor
    from library_server.vault_builder.types import SurveyResult, PreviewResult, ExtractResult

    class GoodExtractor(BaseExtractor):
        name = "good"
        display_name = "Good Extractor"
        source_description = "A test extractor"
        output_subdir = "good"

        async def survey(self) -> SurveyResult:
            return SurveyResult(source_name=self.name, file_count=5, total_size_bytes=1000)

        async def preview(self) -> PreviewResult:
            return PreviewResult(source_name=self.name, files_to_create=["a.md"])

        async def extract(self, output_dir: Path) -> ExtractResult:
            return ExtractResult(source_name=self.name, files_written=["a.md"], success=True)

        def validate_config(self) -> list[str]:
            return []

    ext = GoodExtractor(config={"enabled": True})
    assert ext.name == "good"
    assert ext.display_name == "Good Extractor"
    assert ext.config == {"enabled": True}


def test_validate_config_returns_errors(tmp_path: Path):
    from library_server.vault_builder.extractors.base import BaseExtractor
    from library_server.vault_builder.types import SurveyResult, PreviewResult, ExtractResult

    class NeedsPathExtractor(BaseExtractor):
        name = "needs_path"
        display_name = "Needs Path"
        source_description = "Requires source_path"
        output_subdir = "needs_path"

        async def survey(self) -> SurveyResult:
            return SurveyResult(source_name=self.name, file_count=0, total_size_bytes=0)

        async def preview(self) -> PreviewResult:
            return PreviewResult(source_name=self.name)

        async def extract(self, output_dir: Path) -> ExtractResult:
            return ExtractResult(source_name=self.name, success=False)

        def validate_config(self) -> list[str]:
            errors = []
            if "source_path" not in self.config:
                errors.append("Missing required config: source_path")
            return errors

    ext = NeedsPathExtractor(config={})
    errors = ext.validate_config()
    assert len(errors) == 1
    assert "source_path" in errors[0]


def test_extractor_is_enabled_default():
    from library_server.vault_builder.extractors.base import BaseExtractor
    from library_server.vault_builder.types import SurveyResult, PreviewResult, ExtractResult

    class SimpleExtractor(BaseExtractor):
        name = "simple"
        display_name = "Simple"
        source_description = "Simple"
        output_subdir = "simple"

        async def survey(self) -> SurveyResult:
            return SurveyResult(source_name=self.name, file_count=0, total_size_bytes=0)

        async def preview(self) -> PreviewResult:
            return PreviewResult(source_name=self.name)

        async def extract(self, output_dir: Path) -> ExtractResult:
            return ExtractResult(source_name=self.name, success=True)

        def validate_config(self) -> list[str]:
            return []

    ext = SimpleExtractor(config={})
    assert ext.is_enabled is True

    ext2 = SimpleExtractor(config={"enabled": False})
    assert ext2.is_enabled is False
