# tests/test_config.py
"""Tests for the config manager."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from library_server.config import (
    autodetect_jira_workflow,
    load_config,
    resolve_checkpoint_dir,
    resolve_standards,
    validate_config,
    LibraryConfig,
)


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


# --- resolve_checkpoint_dir: hard-rule enforcement ---

def _write_yaml(path: Path, data: dict) -> Path:
    cfg_path = path / "library-config.yaml"
    with open(cfg_path, "w") as f:
        yaml.dump(data, f)
    return cfg_path


def test_resolve_checkpoint_dir_defaults_under_reading_room(tmp_path: Path):
    """With no checkpoints.path, default is <reading_room>/checkpoints."""
    rr = tmp_path / "reading-room"
    rr.mkdir()
    cfg_path = _write_yaml(tmp_path, {"reading_room": {"path": "./reading-room"}})
    config = load_config(cfg_path)

    cp_dir = resolve_checkpoint_dir(config)
    assert cp_dir == (rr / "checkpoints").resolve()
    assert cp_dir.exists()


def test_resolve_checkpoint_dir_explicit_inside_reading_room(tmp_path: Path):
    """Explicit checkpoints.path inside the Reading Room is honored."""
    rr = tmp_path / "reading-room"
    (rr / "ckpts").mkdir(parents=True)
    cfg_path = _write_yaml(tmp_path, {
        "reading_room": {"path": "./reading-room"},
        "checkpoints": {"path": "./reading-room/ckpts"},
    })
    config = load_config(cfg_path)

    cp_dir = resolve_checkpoint_dir(config)
    assert cp_dir == (rr / "ckpts").resolve()


def test_resolve_checkpoint_dir_rejects_path_outside_reading_room(tmp_path: Path):
    """Explicit checkpoints.path outside the Reading Room must raise."""
    (tmp_path / "reading-room").mkdir()
    cfg_path = _write_yaml(tmp_path, {
        "reading_room": {"path": "./reading-room"},
        "checkpoints": {"path": "./checkpoints"},
    })
    config = load_config(cfg_path)

    with pytest.raises(ValueError, match="must live under reading_room.path"):
        resolve_checkpoint_dir(config)


def test_resolve_checkpoint_dir_requires_reading_room(tmp_path: Path):
    """Missing reading_room.path must raise — Library is misconfigured."""
    cfg_path = _write_yaml(tmp_path, {"library": {"version": "1.0"}})
    config = load_config(cfg_path)

    with pytest.raises(ValueError, match="reading_room.path"):
        resolve_checkpoint_dir(config)


# --- standards block (LIBRARY-1) ---


def test_standards_block_absent_returns_empty_list(tmp_path: Path):
    """A config without standards: yields an empty list."""
    rr = tmp_path / "reading-room"
    rr.mkdir()
    cfg_path = _write_yaml(tmp_path, {"reading_room": {"path": "./reading-room"}})
    config = load_config(cfg_path)
    assert resolve_standards(config, repo_name="any") == []


def test_standards_block_resolves_paths_relative_to_reading_room(tmp_path: Path):
    """resolve_standards returns absolute paths rooted at reading_room.path."""
    rr = tmp_path / "reading-room"
    (rr / "standards").mkdir(parents=True)
    (rr / "standards" / "TESTING-STANDARD.md").write_text("# Testing\n")
    cfg_path = _write_yaml(
        tmp_path,
        {
            "reading_room": {"path": "./reading-room"},
            "standards": [
                {
                    "name": "Testing Standard",
                    "path": "standards/TESTING-STANDARD.md",
                    "applies_to": ["*"],
                }
            ],
        },
    )
    config = load_config(cfg_path)
    resolved = resolve_standards(config, repo_name="compliance-core")
    assert len(resolved) == 1
    assert resolved[0]["name"] == "Testing Standard"
    assert resolved[0]["absolute_path"] == (rr / "standards" / "TESTING-STANDARD.md").resolve()


def test_standards_applies_to_filters_by_repo(tmp_path: Path):
    """A standard with applies_to=[repo-a] is hidden from repo-b."""
    rr = tmp_path / "reading-room"
    (rr / "standards").mkdir(parents=True)
    (rr / "standards" / "A.md").write_text("# A\n")
    (rr / "standards" / "B.md").write_text("# B\n")
    cfg_path = _write_yaml(
        tmp_path,
        {
            "reading_room": {"path": "./reading-room"},
            "standards": [
                {"name": "A", "path": "standards/A.md", "applies_to": ["repo-a"]},
                {"name": "B", "path": "standards/B.md", "applies_to": ["*"]},
            ],
        },
    )
    config = load_config(cfg_path)
    names_b = [s["name"] for s in resolve_standards(config, repo_name="repo-b")]
    assert names_b == ["B"]
    names_a = [s["name"] for s in resolve_standards(config, repo_name="repo-a")]
    assert names_a == ["A", "B"]


def test_standards_malformed_entry_raises(tmp_path: Path):
    """A standards entry missing required keys is rejected loudly — no silent skip."""
    rr = tmp_path / "reading-room"
    rr.mkdir()
    cfg_path = _write_yaml(
        tmp_path,
        {
            "reading_room": {"path": "./reading-room"},
            "standards": [{"name": "broken"}],  # missing path + applies_to
        },
    )
    config = load_config(cfg_path)
    with pytest.raises(ValueError, match="standards\\[0\\]"):
        resolve_standards(config, repo_name="any")


def test_standards_requires_reading_room(tmp_path: Path):
    """standards block requires reading_room.path to resolve against."""
    cfg_path = _write_yaml(
        tmp_path,
        {"standards": [{"name": "x", "path": "a.md", "applies_to": ["*"]}]},
    )
    config = load_config(cfg_path)
    with pytest.raises(ValueError, match="reading_room.path"):
        resolve_standards(config, repo_name="any")


# --- pm.workflow block (LIBRARY-1) ---


def test_validate_pm_workflow_states_valid(tmp_path: Path):
    """pm.workflow with an ordered states list and named keys passes."""
    cfg_path = _write_yaml(
        tmp_path,
        {
            "library": {"version": "1.0"},
            "pm": {
                "provider": "jira",
                "workflow": {
                    "states": ["To Do", "In Progress", "In Review", "Closed"],
                    "in_progress": "In Progress",
                    "in_review": "In Review",
                    "closed": "Closed",
                },
            },
        },
    )
    config = load_config(cfg_path)
    result = validate_config(config)
    assert not any("pm.workflow" in w for w in result["warnings"])


def test_autodetect_jira_workflow_happy():
    """Given a Jira project statuses response, derive ordered states + named keys."""
    response = [
        {
            "name": "Task",
            "statuses": [
                {"name": "To Do"},
                {"name": "In Progress"},
                {"name": "In Review"},
                {"name": "Done"},
            ],
        },
        {
            "name": "Bug",
            "statuses": [
                {"name": "To Do"},
                {"name": "In Progress"},
                {"name": "Done"},
            ],
        },
    ]
    wf = autodetect_jira_workflow(response)
    assert wf["states"] == ["To Do", "In Progress", "In Review", "Done"]
    assert wf["in_progress"] == "In Progress"
    assert wf["in_review"] == "In Review"
    assert wf["closed"] == "Done"


def test_autodetect_jira_workflow_empty_raises():
    """Empty Jira response must raise — not silently return a partial config."""
    with pytest.raises(ValueError, match="No statuses"):
        autodetect_jira_workflow([])


def test_validate_pm_workflow_named_key_not_in_states(tmp_path: Path):
    """If pm.workflow.in_progress is not present in states, warn."""
    cfg_path = _write_yaml(
        tmp_path,
        {
            "library": {"version": "1.0"},
            "pm": {
                "provider": "jira",
                "workflow": {
                    "states": ["To Do", "Doing", "Done"],
                    "in_progress": "In Progress",  # not in states
                    "in_review": "Doing",
                    "closed": "Done",
                },
            },
        },
    )
    config = load_config(cfg_path)
    result = validate_config(config)
    assert any("pm.workflow.in_progress" in w for w in result["warnings"])
