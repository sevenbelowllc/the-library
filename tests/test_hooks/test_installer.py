"""Tests for hooks/installer.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from library_server.hooks.installer import (
    _SCRIPT_NAMES,
    _deploy_scripts,
    generate_hooks_config,
    install_hooks,
)


class TestGenerateHooksConfig:
    def test_has_all_hook_types(self) -> None:
        """generate_hooks_config must include all five hook event types."""
        config = generate_hooks_config()
        hooks = config["hooks"]

        assert "SessionStart" in hooks
        assert "UserPromptSubmit" in hooks
        assert "Stop" in hooks
        assert "PreCompact" in hooks
        assert "SessionEnd" in hooks

    def test_session_start_has_three_entries(self) -> None:
        """SessionStart must have 3 matcher entries: startup|resume, compact, clear."""
        config = generate_hooks_config()
        session_start = config["hooks"]["SessionStart"]

        assert len(session_start) == 3

        matchers = {entry["matcher"] for entry in session_start}
        assert "startup|resume" in matchers
        assert "compact" in matchers
        assert "clear" in matchers

    def test_all_entries_have_command_hooks(self) -> None:
        """Every hook entry must include a 'hooks' list with a command type."""
        config = generate_hooks_config()
        for event_name, entries in config["hooks"].items():
            for entry in entries:
                assert "hooks" in entry, f"Missing 'hooks' key in {event_name} entry"
                assert len(entry["hooks"]) >= 1
                for h in entry["hooks"]:
                    assert h["type"] == "command", (
                        f"Expected type 'command' in {event_name}, got {h['type']}"
                    )
                    assert "command" in h

    def test_commands_use_project_dir(self) -> None:
        """All commands must reference the project_dir path."""
        project_dir = "/my/project"
        config = generate_hooks_config(project_dir=project_dir)
        for event_name, entries in config["hooks"].items():
            for entry in entries:
                for h in entry["hooks"]:
                    assert project_dir in h["command"], (
                        f"project_dir not found in command for {event_name}: {h['command']}"
                    )

    def test_commands_use_python3(self) -> None:
        """All commands must start with 'python3'."""
        config = generate_hooks_config()
        for event_name, entries in config["hooks"].items():
            for entry in entries:
                for h in entry["hooks"]:
                    assert h["command"].startswith("python3 "), (
                        f"Command does not start with python3 in {event_name}: {h['command']}"
                    )

    def test_has_status_line(self) -> None:
        """Config must include a statusLine with command and refreshInterval."""
        config = generate_hooks_config()
        assert "statusLine" in config
        status_line = config["statusLine"]
        assert "command" in status_line
        assert "refreshInterval" in status_line
        assert status_line["refreshInterval"] == 30

    def test_default_project_dir_is_env_var(self) -> None:
        """Default project_dir should be $CLAUDE_PROJECT_DIR."""
        config = generate_hooks_config()
        # Check at least one command references the default placeholder
        found = False
        for event_name, entries in config["hooks"].items():
            for entry in entries:
                for h in entry["hooks"]:
                    if "$CLAUDE_PROJECT_DIR" in h["command"]:
                        found = True
                        break
        assert found, "Expected $CLAUDE_PROJECT_DIR in at least one command"

    def test_hooks_count_is_five(self) -> None:
        """There should be exactly 5 hook event types."""
        config = generate_hooks_config()
        assert len(config["hooks"]) == 5


class TestDeployScripts:
    def test_deploys_all_scripts(self, tmp_path: Path) -> None:
        """_deploy_scripts should copy all hook scripts to the target directory."""
        target = tmp_path / "hooks"
        deployed = _deploy_scripts(target)

        assert deployed == len(_SCRIPT_NAMES)
        for name in _SCRIPT_NAMES:
            assert (target / f"{name}.py").is_file()

    def test_creates_target_directory(self, tmp_path: Path) -> None:
        """_deploy_scripts should create the target directory if it doesn't exist."""
        target = tmp_path / "deep" / "nested" / "hooks"
        assert not target.exists()

        _deploy_scripts(target)

        assert target.is_dir()

    def test_overwrites_existing_scripts(self, tmp_path: Path) -> None:
        """_deploy_scripts should overwrite scripts that already exist."""
        target = tmp_path / "hooks"
        target.mkdir()
        old_file = target / f"{_SCRIPT_NAMES[0]}.py"
        old_file.write_text("# old content", encoding="utf-8")

        _deploy_scripts(target)

        assert old_file.read_text(encoding="utf-8") != "# old content"


class TestInstallHooks:
    def test_install_hooks_creates_new_file(self, tmp_path: Path) -> None:
        """install_hooks should create settings.json when it doesn't exist."""
        settings_path = tmp_path / ".claude" / "settings.json"

        result = install_hooks(settings_path)

        assert result["status"] == "installed"
        assert result["hooks_count"] == 5
        assert result["scripts_deployed"] == len(_SCRIPT_NAMES)
        assert settings_path.exists()

        content = json.loads(settings_path.read_text(encoding="utf-8"))
        assert "hooks" in content
        assert "statusLine" in content

    def test_install_hooks_new_file_has_all_hook_types(self, tmp_path: Path) -> None:
        """New settings.json must contain all five hook types after install."""
        settings_path = tmp_path / ".claude" / "settings.json"

        install_hooks(settings_path)

        content = json.loads(settings_path.read_text(encoding="utf-8"))
        hooks = content["hooks"]

        assert "SessionStart" in hooks
        assert "UserPromptSubmit" in hooks
        assert "Stop" in hooks
        assert "PreCompact" in hooks
        assert "SessionEnd" in hooks

    def test_install_hooks_preserves_existing_settings(self, tmp_path: Path) -> None:
        """install_hooks must not clobber non-hook keys in existing settings."""
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)

        existing = {
            "enabledPlugins": ["some-plugin"],
            "theme": "dark",
            "someOtherKey": {"nested": True},
        }
        settings_path.write_text(json.dumps(existing), encoding="utf-8")

        result = install_hooks(settings_path)

        assert result["status"] == "installed"

        content = json.loads(settings_path.read_text(encoding="utf-8"))

        # Original keys preserved
        assert content["enabledPlugins"] == ["some-plugin"]
        assert content["theme"] == "dark"
        assert content["someOtherKey"] == {"nested": True}

        # Hooks were added
        assert "hooks" in content
        assert "statusLine" in content

    def test_install_hooks_overwrites_existing_hooks(self, tmp_path: Path) -> None:
        """install_hooks replaces any previously installed hooks section."""
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)

        old_settings = {
            "hooks": {"OldEvent": [{"matcher": "", "hooks": []}]},
            "preservedKey": "value",
        }
        settings_path.write_text(json.dumps(old_settings), encoding="utf-8")

        install_hooks(settings_path)

        content = json.loads(settings_path.read_text(encoding="utf-8"))

        # Old event gone, new events present
        assert "OldEvent" not in content["hooks"]
        assert "SessionStart" in content["hooks"]

        # Non-hook keys preserved
        assert content["preservedKey"] == "value"

    def test_install_hooks_commands_reference_project_dir(self, tmp_path: Path) -> None:
        """Commands in installed settings must reference the project directory."""
        settings_path = tmp_path / ".claude" / "settings.json"

        install_hooks(settings_path)

        content = json.loads(settings_path.read_text(encoding="utf-8"))
        project_dir = str(tmp_path)

        # At least one command should reference tmp_path (the project dir)
        found = False
        for event_name, entries in content["hooks"].items():
            for entry in entries:
                for h in entry["hooks"]:
                    if project_dir in h["command"]:
                        found = True
                        break
        assert found, (
            f"Expected project dir {project_dir} to appear in at least one hook command"
        )

    def test_install_hooks_returns_correct_hooks_count(self, tmp_path: Path) -> None:
        """Return dict should report exactly 5 hooks_count."""
        settings_path = tmp_path / ".claude" / "settings.json"

        result = install_hooks(settings_path)

        assert result["hooks_count"] == 5

    def test_install_hooks_deploys_scripts_to_hooks_dir(self, tmp_path: Path) -> None:
        """install_hooks must deploy script files alongside the settings config."""
        settings_path = tmp_path / ".claude" / "settings.json"

        install_hooks(settings_path)

        hooks_dir = tmp_path / ".claude" / "hooks"
        assert hooks_dir.is_dir()
        for name in _SCRIPT_NAMES:
            assert (hooks_dir / f"{name}.py").is_file(), f"Missing {name}.py in hooks dir"

    def test_install_hooks_handles_corrupt_existing_file(self, tmp_path: Path) -> None:
        """install_hooks should not crash if existing settings.json is corrupt JSON."""
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text("{ not valid json }", encoding="utf-8")

        # Should not raise
        result = install_hooks(settings_path)

        assert result["status"] == "installed"
        content = json.loads(settings_path.read_text(encoding="utf-8"))
        assert "hooks" in content


class TestDeployScriptsEdgeCases:
    def test_skips_missing_source_script(self, tmp_path: Path) -> None:
        """_deploy_scripts skips scripts whose source .py file doesn't exist."""
        target = tmp_path / "hooks"
        # Patch _SCRIPT_NAMES to include a name that has no corresponding source file
        fake_names = list(_SCRIPT_NAMES) + ["nonexistent_script"]
        with patch("library_server.hooks.installer._SCRIPT_NAMES", fake_names):
            deployed = _deploy_scripts(target)

        # Only real scripts should be deployed, not the fake one
        assert deployed == len(_SCRIPT_NAMES)
        assert not (target / "nonexistent_script.py").exists()

    def test_copy2_oserror_propagates(self, tmp_path: Path) -> None:
        """_deploy_scripts should propagate OSError when shutil.copy2 fails."""
        target = tmp_path / "hooks"
        with patch("library_server.hooks.installer.shutil.copy2", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                _deploy_scripts(target)


class TestInstallHooksEdgeCases:
    def test_invalid_json_falls_back_to_empty(self, tmp_path: Path) -> None:
        """install_hooks with invalid JSON in settings.json falls back to {}."""
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text("{bad json!!", encoding="utf-8")

        result = install_hooks(settings_path)

        assert result["status"] == "installed"
        content = json.loads(settings_path.read_text(encoding="utf-8"))
        # Should only have hooks and statusLine (no leftover keys from corrupt file)
        assert set(content.keys()) == {"hooks", "statusLine"}

    def test_settings_dir_created_when_missing(self, tmp_path: Path) -> None:
        """install_hooks creates the settings directory when it doesn't exist."""
        settings_path = tmp_path / "new_project" / ".claude" / "settings.json"
        assert not settings_path.parent.exists()

        result = install_hooks(settings_path)

        assert result["status"] == "installed"
        assert settings_path.parent.is_dir()
        assert settings_path.is_file()

    def test_value_error_in_json_falls_back_to_empty(self, tmp_path: Path) -> None:
        """install_hooks handles ValueError from json.loads gracefully."""
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)
        # Write valid-looking but problematic content, mock ValueError
        settings_path.write_text("{}", encoding="utf-8")
        with patch.object(Path, "read_text", return_value="{}"), \
             patch("library_server.hooks.installer.json.loads", side_effect=ValueError("bad")):
            result = install_hooks(settings_path)

        assert result["status"] == "installed"


class TestGenerateHooksConfigEdgeCases:
    def test_project_dir_with_spaces(self) -> None:
        """generate_hooks_config handles paths containing spaces."""
        config = generate_hooks_config(project_dir="/path/with spaces/my project")
        for entries in config["hooks"].values():
            for entry in entries:
                for h in entry["hooks"]:
                    assert "/path/with spaces/my project" in h["command"]

    def test_status_line_command_uses_project_dir(self) -> None:
        """statusLine command should reference the custom project_dir."""
        config = generate_hooks_config(project_dir="/custom/dir")
        assert "/custom/dir" in config["statusLine"]["command"]
