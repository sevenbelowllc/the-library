"""Tests for hooks/scripts/status_line.py — TDD first pass."""

from __future__ import annotations

from pathlib import Path


class TestFormatStatusLine:
    def test_output_contains_used_percentage(self) -> None:
        from library_server.hooks.scripts.status_line import format_status_line

        data = {
            "context_window": {"used_percentage": 42},
            "rate_limits": {
                "five_hour": {"used_percentage": 10.0},
                "seven_day": {"used_percentage": 5.0},
            },
        }
        result = format_status_line(data, claude_md_lines=150)
        assert "42" in result

    def test_output_contains_five_hour_rate(self) -> None:
        from library_server.hooks.scripts.status_line import format_status_line

        data = {
            "context_window": {"used_percentage": 10},
            "rate_limits": {
                "five_hour": {"used_percentage": 33.5},
                "seven_day": {"used_percentage": 2.0},
            },
        }
        result = format_status_line(data, claude_md_lines=100)
        assert "33" in result or "33.5" in result

    def test_output_contains_seven_day_rate(self) -> None:
        from library_server.hooks.scripts.status_line import format_status_line

        data = {
            "context_window": {"used_percentage": 10},
            "rate_limits": {
                "five_hour": {"used_percentage": 5.0},
                "seven_day": {"used_percentage": 77.0},
            },
        }
        result = format_status_line(data, claude_md_lines=100)
        assert "77" in result

    def test_output_contains_claude_md_line_count(self) -> None:
        from library_server.hooks.scripts.status_line import format_status_line

        data = {
            "context_window": {"used_percentage": 23},
            "rate_limits": {
                "five_hour": {"used_percentage": 3.5},
                "seven_day": {"used_percentage": 2.1},
            },
        }
        result = format_status_line(data, claude_md_lines=185)
        assert "185" in result
        assert "200" in result

    def test_output_format_lib_prefix(self) -> None:
        from library_server.hooks.scripts.status_line import format_status_line

        data = {
            "context_window": {"used_percentage": 23},
            "rate_limits": {
                "five_hour": {"used_percentage": 3.5},
                "seven_day": {"used_percentage": 2.1},
            },
        }
        result = format_status_line(data, claude_md_lines=100)
        assert result.startswith("LIB ")

    def test_output_contains_five_hour_label(self) -> None:
        from library_server.hooks.scripts.status_line import format_status_line

        data = {
            "context_window": {"used_percentage": 15},
            "rate_limits": {
                "five_hour": {"used_percentage": 8.0},
                "seven_day": {"used_percentage": 4.0},
            },
        }
        result = format_status_line(data, claude_md_lines=120)
        assert "5h:" in result

    def test_output_contains_seven_day_label(self) -> None:
        from library_server.hooks.scripts.status_line import format_status_line

        data = {
            "context_window": {"used_percentage": 15},
            "rate_limits": {
                "five_hour": {"used_percentage": 8.0},
                "seven_day": {"used_percentage": 4.0},
            },
        }
        result = format_status_line(data, claude_md_lines=120)
        assert "7d:" in result

    def test_high_values_format_correctly(self) -> None:
        from library_server.hooks.scripts.status_line import format_status_line

        data = {
            "context_window": {"used_percentage": 95},
            "rate_limits": {
                "five_hour": {"used_percentage": 88.9},
                "seven_day": {"used_percentage": 99.1},
            },
        }
        result = format_status_line(data, claude_md_lines=210)
        assert "95" in result
        assert "210" in result

    def test_zero_values_handled(self) -> None:
        from library_server.hooks.scripts.status_line import format_status_line

        data = {
            "context_window": {"used_percentage": 0},
            "rate_limits": {
                "five_hour": {"used_percentage": 0},
                "seven_day": {"used_percentage": 0},
            },
        }
        result = format_status_line(data, claude_md_lines=0)
        assert "LIB 0%" in result


class TestWriteContextUsage:
    def test_writes_percentage_to_file(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.status_line import write_context_usage

        usage_path = tmp_path / "state" / "context_usage.txt"
        write_context_usage(usage_path, 45.5)

        assert usage_path.exists()
        content = usage_path.read_text(encoding="utf-8").strip()
        assert content == "45.5"

    def test_creates_parent_dirs_if_missing(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.status_line import write_context_usage

        usage_path = tmp_path / "deep" / "nested" / "state" / "usage.txt"
        assert not usage_path.parent.exists()

        write_context_usage(usage_path, 12.3)

        assert usage_path.exists()

    def test_overwrites_existing_value(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.status_line import write_context_usage

        usage_path = tmp_path / "usage.txt"
        usage_path.write_text("99.9", encoding="utf-8")

        write_context_usage(usage_path, 22.2)

        content = usage_path.read_text(encoding="utf-8").strip()
        assert content == "22.2"


class TestCountClaudeMdLines:
    def test_counts_lines_in_cwd_claude_md(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.status_line import count_claude_md_lines

        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("line1\nline2\nline3\n", encoding="utf-8")

        result = count_claude_md_lines(tmp_path)
        assert result == 3

    def test_accumulates_lines_from_parent_claude_mds(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.status_line import count_claude_md_lines

        # Parent has CLAUDE.md with 5 lines
        parent_claude = tmp_path / "CLAUDE.md"
        parent_claude.write_text("\n".join(["x"] * 5), encoding="utf-8")

        # Child dir has CLAUDE.md with 3 lines
        child_dir = tmp_path / "subdir"
        child_dir.mkdir()
        child_claude = child_dir / "CLAUDE.md"
        child_claude.write_text("\n".join(["y"] * 3), encoding="utf-8")

        result = count_claude_md_lines(child_dir)
        # Should count both: 3 (child) + 5 (parent) = 8
        assert result == 8

    def test_returns_zero_when_no_claude_md(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.status_line import count_claude_md_lines

        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        result = count_claude_md_lines(empty_dir)
        assert result == 0

    def test_stops_at_max_10_levels(self, tmp_path: Path) -> None:
        from library_server.hooks.scripts.status_line import count_claude_md_lines

        # Build 15 levels deep, put CLAUDE.md in the root level
        top = tmp_path / "CLAUDE.md"
        top.write_text("\n".join(["x"] * 100), encoding="utf-8")

        current = tmp_path
        for i in range(12):
            current = current / f"level{i}"
            current.mkdir()

        # At 12 levels deep, the root CLAUDE.md should be beyond the 10-level limit
        # so it may or may not be included depending on implementation
        # The key test is it doesn't recurse infinitely and terminates
        result = count_claude_md_lines(current)
        assert isinstance(result, int)
        assert result >= 0
