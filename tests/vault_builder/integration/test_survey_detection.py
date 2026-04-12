"""Tests for vault state detection."""

from __future__ import annotations

from pathlib import Path


def test_detect_new_vault(tmp_path: Path):
    from library_server.vault_builder.orchestrator import detect_vault_state
    from library_server.vault_builder.types import VaultState
    assert detect_vault_state(tmp_path / "nonexistent") == VaultState.NEW_VAULT


def test_detect_empty_dir(tmp_path: Path):
    from library_server.vault_builder.orchestrator import detect_vault_state
    from library_server.vault_builder.types import VaultState
    empty = tmp_path / "empty"
    empty.mkdir()
    assert detect_vault_state(empty) == VaultState.NEW_VAULT


def test_detect_existing_vault_no_raw(tmp_path: Path):
    from library_server.vault_builder.orchestrator import detect_vault_state
    from library_server.vault_builder.types import VaultState
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / ".obsidian").mkdir()
    (vault / "notes").mkdir()
    (vault / "notes" / "note.md").write_text("# Note")
    assert detect_vault_state(vault) == VaultState.EXISTING_VAULT_NO_RAW


def test_detect_existing_vault_with_raw(tmp_path: Path):
    from library_server.vault_builder.orchestrator import detect_vault_state
    from library_server.vault_builder.types import VaultState
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / ".obsidian").mkdir()
    raw = vault / "raw"
    raw.mkdir()
    (raw / "test.md").write_text("# Test")
    assert detect_vault_state(vault) == VaultState.EXISTING_VAULT_WITH_RAW


def test_detect_previous_build(tmp_path: Path):
    from library_server.vault_builder.orchestrator import detect_vault_state
    from library_server.vault_builder.types import VaultState
    vault = tmp_path / "vault"
    vault.mkdir()
    raw = vault / "raw"
    raw.mkdir()
    (raw / "_build-manifest.md").write_text("---\ntitle: Build Manifest\n---\n")
    assert detect_vault_state(vault) == VaultState.PREVIOUS_BUILD


def test_detect_non_vault_directory(tmp_path: Path):
    from library_server.vault_builder.orchestrator import detect_vault_state
    from library_server.vault_builder.types import VaultState
    content = tmp_path / "content"
    content.mkdir()
    (content / "file.txt").write_text("stuff")
    assert detect_vault_state(content) == VaultState.NON_VAULT_DIRECTORY


def test_create_mode_blocks_on_existing_vault(tmp_path: Path):
    from library_server.vault_builder.orchestrator import check_safety_gate
    from library_server.vault_builder.types import VaultState
    result = check_safety_gate(mode="create", vault_state=VaultState.EXISTING_VAULT_NO_RAW, force=False)
    assert result["blocked"] is True


def test_create_mode_allowed_with_force(tmp_path: Path):
    from library_server.vault_builder.orchestrator import check_safety_gate
    from library_server.vault_builder.types import VaultState
    result = check_safety_gate(mode="create", vault_state=VaultState.EXISTING_VAULT_NO_RAW, force=True)
    assert result["blocked"] is False


def test_create_mode_allowed_on_new_vault():
    from library_server.vault_builder.orchestrator import check_safety_gate
    from library_server.vault_builder.types import VaultState
    result = check_safety_gate(mode="create", vault_state=VaultState.NEW_VAULT, force=False)
    assert result["blocked"] is False


def test_enrich_mode_allowed_on_existing_vault():
    from library_server.vault_builder.orchestrator import check_safety_gate
    from library_server.vault_builder.types import VaultState
    result = check_safety_gate(mode="enrich", vault_state=VaultState.EXISTING_VAULT_NO_RAW, force=False)
    assert result["blocked"] is False
