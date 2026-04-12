"""Tests for vault_builder types."""

from __future__ import annotations


def test_survey_result_defaults():
    from library_server.vault_builder.types import SurveyResult
    result = SurveyResult(source_name="specs", file_count=11, total_size_bytes=50000)
    assert result.source_name == "specs"
    assert result.file_count == 11
    assert result.total_size_bytes == 50000
    assert result.structure_summary == ""
    assert result.health == "unknown"
    assert result.last_modified is None


def test_preview_result_defaults():
    from library_server.vault_builder.types import PreviewResult
    result = PreviewResult(source_name="specs", files_to_create=["raw/specs/GLOSSARY.md"])
    assert result.source_name == "specs"
    assert len(result.files_to_create) == 1
    assert result.estimated_tokens == 0
    assert result.warnings == []


def test_extract_result_success():
    from library_server.vault_builder.types import ExtractResult
    result = ExtractResult(
        source_name="specs",
        files_written=["raw/specs/GLOSSARY.md"],
        files_skipped=[],
        errors=[],
        duration_seconds=2.5,
        success=True,
    )
    assert result.success is True
    assert result.files_written == ["raw/specs/GLOSSARY.md"]
    assert result.duration_seconds == 2.5


def test_extract_result_failure():
    from library_server.vault_builder.types import ExtractResult
    result = ExtractResult(
        source_name="jira",
        files_written=[],
        files_skipped=[],
        errors=["Connection refused"],
        duration_seconds=3.0,
        success=False,
    )
    assert result.success is False
    assert "Connection refused" in result.errors


def test_build_result_with_mixed_results():
    from library_server.vault_builder.types import BuildResult, ExtractResult
    results = [
        ExtractResult(source_name="specs", files_written=["a.md"], files_skipped=[], errors=[], duration_seconds=1.0, success=True),
        ExtractResult(source_name="jira", files_written=[], files_skipped=[], errors=["fail"], duration_seconds=2.0, success=False),
    ]
    build = BuildResult(
        status="completed_with_warnings",
        extract_results=results,
        graphify_status="skipped",
        duration_seconds=5.0,
    )
    assert build.status == "completed_with_warnings"
    assert len(build.extract_results) == 2
    assert build.any_succeeded is True


def test_build_result_all_failed():
    from library_server.vault_builder.types import BuildResult, ExtractResult
    results = [
        ExtractResult(source_name="jira", files_written=[], files_skipped=[], errors=["fail"], duration_seconds=2.0, success=False),
    ]
    build = BuildResult(
        status="failed",
        extract_results=results,
        graphify_status="skipped",
        duration_seconds=2.0,
    )
    assert build.any_succeeded is False


def test_vault_state_enum():
    from library_server.vault_builder.types import VaultState
    assert VaultState.NEW_VAULT.value == "new_vault"
    assert VaultState.EXISTING_VAULT_NO_RAW.value == "existing_vault_no_raw"
    assert VaultState.EXISTING_VAULT_WITH_RAW.value == "existing_vault_with_raw"
    assert VaultState.PREVIOUS_BUILD.value == "previous_build"
    assert VaultState.NON_VAULT_DIRECTORY.value == "non_vault_directory"
