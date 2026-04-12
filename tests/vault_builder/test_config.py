"""Tests for VaultBuilderConfig — loading and validation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import yaml


def _write_config(tmp_path: Path, data: dict) -> Path:
    config_path = tmp_path / "library-config.yaml"
    config_path.write_text(yaml.dump(data, default_flow_style=False))
    return config_path


def test_load_vault_builder_config(tmp_path: Path):
    from library_server.vault_builder.config import load_vault_builder_config
    config_path = _write_config(tmp_path, {
        "vault_builder": {
            "mode": "create",
            "output_vault": str(tmp_path / "output"),
            "sources": {"specs": {"enabled": True, "source_path": str(tmp_path)}},
        }
    })
    cfg = load_vault_builder_config(config_path)
    assert cfg.mode == "create"
    assert cfg.output_vault == Path(tmp_path / "output")
    assert "specs" in cfg.sources


def test_load_returns_defaults_when_section_missing(tmp_path: Path):
    from library_server.vault_builder.config import load_vault_builder_config
    config_path = _write_config(tmp_path, {"library": {"version": "1.0"}})
    cfg = load_vault_builder_config(config_path)
    assert cfg.mode == "create"
    assert cfg.sources == {}


def test_validate_config_valid(tmp_path: Path):
    from library_server.vault_builder.config import load_vault_builder_config, validate_vault_builder_config
    source_dir = tmp_path / "specs"
    source_dir.mkdir()
    config_path = _write_config(tmp_path, {
        "vault_builder": {
            "mode": "create",
            "output_vault": str(tmp_path / "output"),
            "sources": {"specs": {"enabled": True, "source_path": str(source_dir)}},
        }
    })
    cfg = load_vault_builder_config(config_path)
    errors = validate_vault_builder_config(cfg)
    assert errors == []


def test_validate_config_missing_output_vault(tmp_path: Path):
    from library_server.vault_builder.config import load_vault_builder_config, validate_vault_builder_config
    config_path = _write_config(tmp_path, {"vault_builder": {"mode": "create", "sources": {}}})
    cfg = load_vault_builder_config(config_path)
    errors = validate_vault_builder_config(cfg)
    assert any("output_vault" in e for e in errors)


def test_validate_config_invalid_mode(tmp_path: Path):
    from library_server.vault_builder.config import load_vault_builder_config, validate_vault_builder_config
    config_path = _write_config(tmp_path, {
        "vault_builder": {"mode": "destroy", "output_vault": str(tmp_path / "out"), "sources": {}}
    })
    cfg = load_vault_builder_config(config_path)
    errors = validate_vault_builder_config(cfg)
    assert any("mode" in e for e in errors)


def test_validate_config_missing_source_path(tmp_path: Path):
    from library_server.vault_builder.config import load_vault_builder_config, validate_vault_builder_config
    config_path = _write_config(tmp_path, {
        "vault_builder": {
            "mode": "create",
            "output_vault": str(tmp_path / "output"),
            "sources": {"specs": {"enabled": True, "source_path": "/nonexistent/path"}},
        }
    })
    cfg = load_vault_builder_config(config_path)
    errors = validate_vault_builder_config(cfg)
    assert any("source_path" in e and "nonexistent" in e for e in errors)


def test_validate_config_axon_not_found(tmp_path: Path):
    from library_server.vault_builder.config import load_vault_builder_config, validate_vault_builder_config
    config_path = _write_config(tmp_path, {
        "vault_builder": {
            "mode": "create",
            "output_vault": str(tmp_path / "output"),
            "axon": {"enabled": True},
            "sources": {"axon_bridge": {"enabled": True, "repos": []}},
        }
    })
    cfg = load_vault_builder_config(config_path)
    with patch("shutil.which", return_value=None):
        errors = validate_vault_builder_config(cfg)
    assert any("axon" in e.lower() for e in errors)


def test_validate_config_graphify_not_found(tmp_path: Path):
    from library_server.vault_builder.config import load_vault_builder_config, validate_vault_builder_config
    config_path = _write_config(tmp_path, {
        "vault_builder": {
            "mode": "create",
            "output_vault": str(tmp_path / "output"),
            "graphify": {"enabled": True},
            "sources": {},
        }
    })
    cfg = load_vault_builder_config(config_path)
    with patch("shutil.which", return_value=None):
        errors = validate_vault_builder_config(cfg)
    assert any("graphify" in e.lower() for e in errors)


def test_validate_config_disabled_source_skips_path_check(tmp_path: Path):
    from library_server.vault_builder.config import load_vault_builder_config, validate_vault_builder_config
    config_path = _write_config(tmp_path, {
        "vault_builder": {
            "mode": "create",
            "output_vault": str(tmp_path / "output"),
            "sources": {"specs": {"enabled": False, "source_path": "/nonexistent"}},
        }
    })
    cfg = load_vault_builder_config(config_path)
    errors = validate_vault_builder_config(cfg)
    assert not any("nonexistent" in e for e in errors)
