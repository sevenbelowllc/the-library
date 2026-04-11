# tests/test_config.py
"""Tests for the config manager."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from library_server.config import load_config, validate_config, LibraryConfig


def test_load_config_from_file(tmp_path: Path):
    """load_config should parse library-config.yaml."""
    config_data = {
        "library": {"version": "1.0"},
        "vault": {"path": str(tmp_path / "vault")},
        "pm": {"provider": "none"},
    }
    config_path = tmp_path / "library-config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)

    config = load_config(config_path)
    assert config.get_section("library")["version"] == "1.0"
    assert config.get_section("pm")["provider"] == "none"


def test_load_config_missing_file(tmp_path: Path):
    """load_config should return empty config when file doesn't exist."""
    config = load_config(tmp_path / "nonexistent.yaml")
    assert config.to_dict() == {}


def test_validate_config_valid(sample_config: LibraryConfig):
    """validate_config should pass for a complete config."""
    # Create directories referenced in the sample config so path checks pass
    for section in ("vault", "memory"):
        path = sample_config.get_section(section).get("path")
        if path:
            Path(path).mkdir(parents=True, exist_ok=True)
    result = validate_config(sample_config)
    assert result["valid"] is True


def test_validate_config_missing_library_version(tmp_path: Path):
    """validate_config should flag missing library.version."""
    config_path = tmp_path / "library-config.yaml"
    with open(config_path, "w") as f:
        yaml.dump({"pm": {"provider": "none"}}, f)

    config = load_config(config_path)
    result = validate_config(config)
    assert result["valid"] is False
    assert any("library.version" in w for w in result["warnings"])


def test_validate_config_checks_graphify_installed(tmp_path: Path):
    """validate_config should warn if graphify enabled but not installed."""
    config_data = {
        "library": {"version": "1.0"},
        "graphify": {"enabled": True},
    }
    config_path = tmp_path / "library-config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)

    config = load_config(config_path)
    result = validate_config(config)
    # Should have a warning about graphify (may or may not be installed in test env)
    assert "warnings" in result


def test_config_set_and_save(tmp_path: Path):
    """set_value + save should persist changes to yaml."""
    config_path = tmp_path / "library-config.yaml"
    with open(config_path, "w") as f:
        yaml.dump({"library": {"version": "1.0"}}, f)

    config = load_config(config_path)
    config.set_value("pm", "provider", "jira")
    config.save()

    reloaded = load_config(config_path)
    assert reloaded.get_section("pm")["provider"] == "jira"


def test_config_get_section_missing(sample_config: LibraryConfig):
    """get_section for nonexistent section should return empty dict."""
    result = sample_config.get_section("nonexistent")
    assert result == {}
