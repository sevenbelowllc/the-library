"""Tests for hooks/config_loader.py — load_hook_config and deep merge."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_config(tmp_path: Path, data: dict) -> Path:
    """Write a library-config.yaml to tmp_path and return the project dir."""
    config_path = tmp_path / "library-config.yaml"
    with open(config_path, "w") as fh:
        yaml.dump(data, fh)
    return tmp_path


# ---------------------------------------------------------------------------
# Tests: load_hook_config
# ---------------------------------------------------------------------------

class TestLoadHookConfigDefaults:
    """When no library-config.yaml exists, defaults are returned."""

    def test_returns_dict(self, tmp_path: Path) -> None:
        from library_server.hooks.config_loader import load_hook_config
        result = load_hook_config(tmp_path)
        assert isinstance(result, dict)

    def test_memory_section_present(self, tmp_path: Path) -> None:
        from library_server.hooks.config_loader import load_hook_config
        result = load_hook_config(tmp_path)
        assert "memory" in result

    def test_context_section_present(self, tmp_path: Path) -> None:
        from library_server.hooks.config_loader import load_hook_config
        result = load_hook_config(tmp_path)
        assert "context" in result

    def test_hooks_section_present(self, tmp_path: Path) -> None:
        from library_server.hooks.config_loader import load_hook_config
        result = load_hook_config(tmp_path)
        assert "hooks" in result

    def test_default_session_dir(self, tmp_path: Path) -> None:
        from library_server.hooks.config_loader import load_hook_config
        result = load_hook_config(tmp_path)
        assert result["memory"]["session_dir"] == "~/.library/sessions"

    def test_default_budgets(self, tmp_path: Path) -> None:
        from library_server.hooks.config_loader import load_hook_config
        result = load_hook_config(tmp_path)
        budgets = result["memory"]["budgets"]
        assert budgets["critical"] == 300
        assert budgets["fresh"] == 500
        assert budgets["moderate_max"] == 1500
        assert budgets["domain_file_max"] == 500

    def test_default_pruning(self, tmp_path: Path) -> None:
        from library_server.hooks.config_loader import load_hook_config
        result = load_hook_config(tmp_path)
        pruning = result["memory"]["pruning"]
        assert pruning["graduation_threshold"] == 5
        assert pruning["hitl_required"] is True

    def test_default_keyword_learning(self, tmp_path: Path) -> None:
        from library_server.hooks.config_loader import load_hook_config
        result = load_hook_config(tmp_path)
        kl = result["memory"]["keyword_learning"]
        assert kl["enabled"] is True
        assert kl["hitl_required"] is True
        assert kl["min_observations"] == 10
        assert kl["hit_threshold"] == 0.8
        assert kl["noise_threshold"] == 0.3
        assert kl["drift_window_days"] == 30
        assert kl["drift_drop_threshold"] == 0.4

    def test_default_context(self, tmp_path: Path) -> None:
        from library_server.hooks.config_loader import load_hook_config
        result = load_hook_config(tmp_path)
        assert result["context"]["warn_percentage"] == 50
        assert result["context"]["checkpoint_percentage"] == 60

    def test_default_hooks_enabled(self, tmp_path: Path) -> None:
        from library_server.hooks.config_loader import load_hook_config
        result = load_hook_config(tmp_path)
        hooks = result["hooks"]
        assert hooks["enabled"] is True
        assert hooks["session_start"] is True
        assert hooks["user_prompt_submit"] is True
        assert hooks["stop"] is True
        assert hooks["pre_compact"] is True
        assert hooks["session_end"] is True
        assert hooks["status_line"] is True


class TestLoadHookConfigOverrides:
    """User-supplied values override defaults."""

    def test_override_session_dir(self, tmp_path: Path) -> None:
        from library_server.hooks.config_loader import load_hook_config
        write_config(tmp_path, {"memory": {"session_dir": "/custom/sessions"}})
        result = load_hook_config(tmp_path)
        assert result["memory"]["session_dir"] == "/custom/sessions"

    def test_override_budget_critical(self, tmp_path: Path) -> None:
        from library_server.hooks.config_loader import load_hook_config
        write_config(tmp_path, {"memory": {"budgets": {"critical": 999}}})
        result = load_hook_config(tmp_path)
        assert result["memory"]["budgets"]["critical"] == 999
        # Other budget keys should still come from defaults
        assert result["memory"]["budgets"]["fresh"] == 500

    def test_override_hooks_disabled(self, tmp_path: Path) -> None:
        from library_server.hooks.config_loader import load_hook_config
        write_config(tmp_path, {"hooks": {"enabled": False}})
        result = load_hook_config(tmp_path)
        assert result["hooks"]["enabled"] is False
        # Other hook keys still come from defaults
        assert result["hooks"]["session_start"] is True

    def test_override_context_warn(self, tmp_path: Path) -> None:
        from library_server.hooks.config_loader import load_hook_config
        write_config(tmp_path, {"context": {"warn_percentage": 70}})
        result = load_hook_config(tmp_path)
        assert result["context"]["warn_percentage"] == 70
        assert result["context"]["checkpoint_percentage"] == 60

    def test_non_mmu_keys_preserved(self, tmp_path: Path) -> None:
        from library_server.hooks.config_loader import load_hook_config
        write_config(tmp_path, {"pm": {"provider": "jira"}, "memory": {}})
        result = load_hook_config(tmp_path)
        assert result["pm"]["provider"] == "jira"


class TestDeepMerge:
    """Unit tests for the _deep_merge helper."""

    def test_shallow_merge(self) -> None:
        from library_server.hooks.config_loader import _deep_merge
        defaults = {"a": 1, "b": 2}
        overrides = {"b": 99, "c": 3}
        result = _deep_merge(defaults, overrides)
        assert result == {"a": 1, "b": 99, "c": 3}

    def test_nested_merge(self) -> None:
        from library_server.hooks.config_loader import _deep_merge
        defaults = {"outer": {"x": 1, "y": 2}}
        overrides = {"outer": {"y": 99}}
        result = _deep_merge(defaults, overrides)
        assert result["outer"]["x"] == 1
        assert result["outer"]["y"] == 99

    def test_does_not_mutate_defaults(self) -> None:
        from library_server.hooks.config_loader import _deep_merge
        defaults = {"a": {"b": 1}}
        overrides = {"a": {"b": 2}}
        _deep_merge(defaults, overrides)
        assert defaults["a"]["b"] == 1

    def test_override_replaces_non_dict_with_dict(self) -> None:
        from library_server.hooks.config_loader import _deep_merge
        defaults = {"a": 1}
        overrides = {"a": {"nested": True}}
        result = _deep_merge(defaults, overrides)
        assert result["a"] == {"nested": True}

    def test_empty_overrides_returns_defaults(self) -> None:
        from library_server.hooks.config_loader import _deep_merge
        defaults = {"a": 1}
        result = _deep_merge(defaults, {})
        assert result == {"a": 1}

    def test_deeply_nested_merge(self) -> None:
        from library_server.hooks.config_loader import _deep_merge
        defaults = {"a": {"b": {"c": 1, "d": 2}}}
        overrides = {"a": {"b": {"c": 99}}}
        result = _deep_merge(defaults, overrides)
        assert result["a"]["b"]["c"] == 99
        assert result["a"]["b"]["d"] == 2
