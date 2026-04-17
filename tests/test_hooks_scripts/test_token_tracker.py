"""Tests for hooks/scripts/token_tracker.py — TDD first pass."""

from __future__ import annotations

import json
import io
from pathlib import Path
from unittest.mock import patch


# ── classify_component ───────────────────────────────────────────────────────


class TestClassifyComponent:
    def test_vault_builder_prefix(self) -> None:
        from library_server.hooks.scripts.token_tracker import classify_component

        assert classify_component("library_vault_builder_build") == "vault_builder"

    def test_config_prefix(self) -> None:
        from library_server.hooks.scripts.token_tracker import classify_component

        assert classify_component("library_config_get") == "config"

    def test_checkpoint_prefix(self) -> None:
        from library_server.hooks.scripts.token_tracker import classify_component

        assert classify_component("library_checkpoint_write") == "checkpoint"

    def test_memory_prefix(self) -> None:
        from library_server.hooks.scripts.token_tracker import classify_component

        assert classify_component("library_memory_scan") == "memory"

    def test_vault_prefix(self) -> None:
        from library_server.hooks.scripts.token_tracker import classify_component

        assert classify_component("library_vault_ingest") == "vault"

    def test_graph_prefix(self) -> None:
        from library_server.hooks.scripts.token_tracker import classify_component

        assert classify_component("library_graph_rebuild") == "graph"

    def test_pm_prefix(self) -> None:
        from library_server.hooks.scripts.token_tracker import classify_component

        assert classify_component("library_pm_sync") == "pm"

    def test_dev_prefix(self) -> None:
        from library_server.hooks.scripts.token_tracker import classify_component

        assert classify_component("library_dev_token_report") == "dev"

    def test_fallback_to_claude_tools(self) -> None:
        from library_server.hooks.scripts.token_tracker import classify_component

        assert classify_component("Read") == "claude_tools"
        assert classify_component("Write") == "claude_tools"
        assert classify_component("Bash") == "claude_tools"

    def test_vault_builder_takes_priority_over_vault(self) -> None:
        """vault_builder_ prefix must match before vault_ prefix."""
        from library_server.hooks.scripts.token_tracker import classify_component

        assert classify_component("library_vault_builder_survey") == "vault_builder"
        # But plain vault_ should still work
        assert classify_component("library_vault_parse") == "vault"


# ── _is_dev_enabled ─────────────────────────────────────────────────────────


class TestIsDevEnabled:
    def test_returns_true_when_enabled(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.token_tracker import _is_dev_enabled

        config_file = tmp_path / "library-config.yaml"
        config_file.write_text("dev:\n  enabled: true\n", encoding="utf-8")

        with patch("library_server.hooks.scripts.token_tracker.Path.cwd", return_value=tmp_path):
            assert _is_dev_enabled() is True

    def test_returns_false_when_disabled(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.token_tracker import _is_dev_enabled

        config_file = tmp_path / "library-config.yaml"
        config_file.write_text("dev:\n  enabled: false\n", encoding="utf-8")

        with patch("library_server.hooks.scripts.token_tracker.Path.cwd", return_value=tmp_path):
            assert _is_dev_enabled() is False

    def test_returns_false_when_no_config(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.token_tracker import _is_dev_enabled

        with patch("library_server.hooks.scripts.token_tracker.Path.cwd", return_value=tmp_path):
            assert _is_dev_enabled() is False

    def test_returns_false_on_corrupt_yaml(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.token_tracker import _is_dev_enabled

        config_file = tmp_path / "library-config.yaml"
        config_file.write_text(": : : bad yaml [[[", encoding="utf-8")

        with patch("library_server.hooks.scripts.token_tracker.Path.cwd", return_value=tmp_path):
            assert _is_dev_enabled() is False

    def test_returns_false_when_dev_section_missing(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.token_tracker import _is_dev_enabled

        config_file = tmp_path / "library-config.yaml"
        config_file.write_text("vault:\n  path: ./vault\n", encoding="utf-8")

        with patch("library_server.hooks.scripts.token_tracker.Path.cwd", return_value=tmp_path):
            assert _is_dev_enabled() is False


# ── track_tool_usage ─────────────────────────────────────────────────────────


class TestTrackToolUsage:
    def test_creates_file_on_first_call(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.token_tracker import track_tool_usage

        state_path = tmp_path / "state" / "token-usage.json"

        with patch("library_server.hooks.scripts.token_tracker._is_dev_enabled", return_value=True):
            track_tool_usage("library_pm_sync", 500, 23.4, 22.2, state_path)

        assert state_path.exists()
        data = json.loads(state_path.read_text(encoding="utf-8"))
        assert "events" in data
        assert len(data["events"]) == 1
        assert data["events"][0]["tool"] == "library_pm_sync"
        assert data["events"][0]["component"] == "pm"
        assert data["events"][0]["response_chars"] == 500
        assert data["events"][0]["context_delta_pct"] == pytest.approx(1.2, abs=0.01)
        assert data["events"][0]["cumulative_context_pct"] == 23.4

    def test_appends_to_existing(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.token_tracker import track_tool_usage

        state_path = tmp_path / "token-usage.json"

        with patch("library_server.hooks.scripts.token_tracker._is_dev_enabled", return_value=True):
            track_tool_usage("library_pm_sync", 500, 20.0, 19.0, state_path)
            track_tool_usage("Read", 1000, 22.0, 20.0, state_path)

        data = json.loads(state_path.read_text(encoding="utf-8"))
        assert len(data["events"]) == 2
        assert data["events"][1]["tool"] == "Read"
        assert data["events"][1]["component"] == "claude_tools"

    def test_handles_corrupt_file(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.token_tracker import track_tool_usage

        state_path = tmp_path / "token-usage.json"
        state_path.write_text("{corrupt data!!!!", encoding="utf-8")

        with patch("library_server.hooks.scripts.token_tracker._is_dev_enabled", return_value=True):
            track_tool_usage("library_vault_ingest", 200, 10.0, 9.5, state_path)

        data = json.loads(state_path.read_text(encoding="utf-8"))
        assert len(data["events"]) == 1
        assert data["events"][0]["tool"] == "library_vault_ingest"

    def test_noop_when_dev_disabled(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.token_tracker import track_tool_usage

        state_path = tmp_path / "token-usage.json"

        with patch("library_server.hooks.scripts.token_tracker._is_dev_enabled", return_value=False):
            track_tool_usage("library_pm_sync", 500, 23.4, 22.2, state_path)

        assert not state_path.exists()

    def test_token_estimate_is_chars_div_4(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.token_tracker import track_tool_usage

        state_path = tmp_path / "token-usage.json"

        with patch("library_server.hooks.scripts.token_tracker._is_dev_enabled", return_value=True):
            track_tool_usage("Read", 400, 10.0, 9.0, state_path)

        data = json.loads(state_path.read_text(encoding="utf-8"))
        # 400 // 4 = 100 — check via aggregate later, but event stores response_chars
        assert data["events"][0]["response_chars"] == 400


# ── aggregate_usage ──────────────────────────────────────────────────────────


class TestAggregateUsage:
    def test_with_events(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.token_tracker import aggregate_usage

        state_path = tmp_path / "token-usage.json"
        state_path.write_text(json.dumps({
            "session_id": "test-session",
            "started_at": "2026-04-17T10:00:00+00:00",
            "events": [
                {
                    "tool": "library_pm_sync",
                    "component": "pm",
                    "response_chars": 400,
                    "context_delta_pct": 1.0,
                    "cumulative_context_pct": 21.0,
                    "timestamp": "2026-04-17T10:00:01+00:00",
                },
                {
                    "tool": "library_pm_query",
                    "component": "pm",
                    "response_chars": 800,
                    "context_delta_pct": 2.0,
                    "cumulative_context_pct": 23.0,
                    "timestamp": "2026-04-17T10:00:02+00:00",
                },
                {
                    "tool": "Read",
                    "component": "claude_tools",
                    "response_chars": 200,
                    "context_delta_pct": 0.5,
                    "cumulative_context_pct": 23.5,
                    "timestamp": "2026-04-17T10:00:03+00:00",
                },
            ],
        }), encoding="utf-8")

        result = aggregate_usage(state_path)

        assert result["session_total_calls"] == 3
        assert result["session_context_peak"] == 23.5
        assert "pm" in result["components"]
        assert result["components"]["pm"]["calls"] == 2
        assert result["components"]["pm"]["est_tokens"] == 300  # (400+800)//4
        assert "claude_tools" in result["components"]
        assert result["components"]["claude_tools"]["calls"] == 1

    def test_top_consumers_sorted_by_tokens_desc(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.token_tracker import aggregate_usage

        state_path = tmp_path / "token-usage.json"
        state_path.write_text(json.dumps({
            "session_id": "test",
            "started_at": "2026-04-17T10:00:00+00:00",
            "events": [
                {"tool": "Read", "component": "claude_tools", "response_chars": 2000,
                 "context_delta_pct": 1.0, "cumulative_context_pct": 10.0,
                 "timestamp": "2026-04-17T10:00:01+00:00"},
                {"tool": "library_pm_sync", "component": "pm", "response_chars": 400,
                 "context_delta_pct": 0.5, "cumulative_context_pct": 10.5,
                 "timestamp": "2026-04-17T10:00:02+00:00"},
                {"tool": "Read", "component": "claude_tools", "response_chars": 2000,
                 "context_delta_pct": 1.0, "cumulative_context_pct": 11.5,
                 "timestamp": "2026-04-17T10:00:03+00:00"},
            ],
        }), encoding="utf-8")

        result = aggregate_usage(state_path)

        top = result["top_consumers"]
        assert len(top) >= 2
        # Read has 4000 chars total -> 1000 tokens, pm has 400 -> 100 tokens
        assert top[0]["tool"] == "Read"
        assert top[0]["est_tokens"] == 1000
        assert top[1]["tool"] == "library_pm_sync"
        assert top[1]["est_tokens"] == 100

    def test_empty_events(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.token_tracker import aggregate_usage

        state_path = tmp_path / "token-usage.json"
        state_path.write_text(json.dumps({
            "session_id": "test",
            "started_at": "2026-04-17T10:00:00+00:00",
            "events": [],
        }), encoding="utf-8")

        result = aggregate_usage(state_path)

        assert result["session_total_calls"] == 0
        assert result["session_context_peak"] == 0
        assert result["components"] == {}
        assert result["top_consumers"] == []

    def test_missing_file(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.token_tracker import aggregate_usage

        state_path = tmp_path / "nonexistent.json"
        result = aggregate_usage(state_path)

        assert result["session_total_calls"] == 0
        assert result["components"] == {}
        assert result["top_consumers"] == []

    def test_corrupt_file(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.token_tracker import aggregate_usage

        state_path = tmp_path / "token-usage.json"
        state_path.write_text("not json at all!!!", encoding="utf-8")

        result = aggregate_usage(state_path)

        assert result["session_total_calls"] == 0
        assert result["components"] == {}
        assert result["top_consumers"] == []

    def test_context_delta_aggregated_per_component(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.token_tracker import aggregate_usage

        state_path = tmp_path / "token-usage.json"
        state_path.write_text(json.dumps({
            "session_id": "test",
            "started_at": "2026-04-17T10:00:00+00:00",
            "events": [
                {"tool": "library_pm_sync", "component": "pm", "response_chars": 400,
                 "context_delta_pct": 1.5, "cumulative_context_pct": 21.5,
                 "timestamp": "2026-04-17T10:00:01+00:00"},
                {"tool": "library_pm_query", "component": "pm", "response_chars": 400,
                 "context_delta_pct": 2.0, "cumulative_context_pct": 23.5,
                 "timestamp": "2026-04-17T10:00:02+00:00"},
            ],
        }), encoding="utf-8")

        result = aggregate_usage(state_path)
        assert result["components"]["pm"]["context_delta"] == pytest.approx(3.5)


# ── main ─────────────────────────────────────────────────────────────────────


class TestMain:
    def test_main_with_valid_payload(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.token_tracker import main

        state_path = tmp_path / "state" / "token-usage.json"
        payload = {
            "tool_name": "library_pm_sync",
            "tool_response": "x" * 500,
            "context_window": {"used_percentage": 23.4},
            "_prev_context_pct": 22.2,
            "_state_path": str(state_path),
        }

        with patch("sys.stdin", io.StringIO(json.dumps(payload))), \
             patch("library_server.hooks.scripts.token_tracker._is_dev_enabled", return_value=True), \
             patch("builtins.print") as mock_print:
            main()

        # main should not print anything (silent hook)
        mock_print.assert_not_called()

    def test_main_with_invalid_json(self) -> None:
        from library_server.hooks.scripts.token_tracker import main

        with patch("sys.stdin", io.StringIO("{bad json!")), \
             patch("builtins.print") as mock_print:
            # Should not raise
            main()

        mock_print.assert_not_called()

    def test_main_with_empty_stdin(self) -> None:
        from library_server.hooks.scripts.token_tracker import main

        with patch("sys.stdin", io.StringIO("")), \
             patch("builtins.print") as mock_print:
            # Should not raise
            main()

        mock_print.assert_not_called()


import pytest
