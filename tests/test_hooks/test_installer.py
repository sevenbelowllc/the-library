"""Tests for hooks/installer.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from library_server.hooks.installer import generate_hooks_config, install_hooks


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


class TestInstallHooks:
    def test_install_hooks_creates_new_file(self, tmp_path: Path) -> None:
        """install_hooks should create settings.json when it doesn't exist."""
        settings_path = tmp_path / ".claude" / "settings.json"

        result = install_hooks(settings_path)

        assert result["status"] == "installed"
        assert result["hooks_count"] == 5
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
