"""StatusLine hook script — emit a compact context-usage line to the terminal.

Reads stdin JSON from Claude Code's PostToolUse / notification hook,
writes context usage percentage to a state file, and prints a single
formatted line to stdout for the terminal status bar.

Output format:
    {used_pct}% LIB | 5h:{five_hour}% 7d:{seven_day}% | CLAUDE.md: {lines}/200
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


# ── Public helpers (used by main and directly testable) ──────────────────────


def format_status_line(data: dict, claude_md_lines: int) -> str:
    """Format context/rate-limit data as a single status line string.

    Parameters
    ----------
    data:
        Dict with keys ``context_window.used_percentage`` and
        ``rate_limits.five_hour.used_percentage`` /
        ``rate_limits.seven_day.used_percentage``.
    claude_md_lines:
        Total CLAUDE.md line count from the project hierarchy.

    Returns
    -------
    str
        Formatted status line, e.g.
        ``23% LIB | 5h:3% 7d:2% | CLAUDE.md: 185/200``
    """
    used_pct = int(data.get("context_window", {}).get("used_percentage", 0))
    rate_limits = data.get("rate_limits", {})
    five_hour = rate_limits.get("five_hour", {}).get("used_percentage", 0)
    seven_day = rate_limits.get("seven_day", {}).get("used_percentage", 0)

    five_hour_str = f"{int(five_hour)}"
    seven_day_str = f"{int(seven_day)}"

    return (
        f"{used_pct}% LIB | "
        f"5h:{five_hour_str}% 7d:{seven_day_str}% | "
        f"CLAUDE.md: {claude_md_lines}/200"
    )


def write_context_usage(usage_path: Path, percentage: float) -> None:
    """Write the context usage percentage to a file.

    Creates parent directories as needed. Overwrites any existing content.

    Parameters
    ----------
    usage_path:
        File path to write the percentage value to.
    percentage:
        Float percentage value, e.g. ``45.5``.
    """
    usage_path.parent.mkdir(parents=True, exist_ok=True)
    usage_path.write_text(str(percentage), encoding="utf-8")


def count_claude_md_lines(cwd: Path, _max_levels: int = 10) -> int:
    """Walk up from *cwd* accumulating lines in CLAUDE.md files.

    Stops after *_max_levels* parent traversals (default 10) or when the
    filesystem root is reached.

    Parameters
    ----------
    cwd:
        Starting directory (typically the project working directory).
    _max_levels:
        Maximum number of ancestor levels to inspect.

    Returns
    -------
    int
        Total line count across all CLAUDE.md files found in the hierarchy.
    """
    total = 0
    current = cwd.resolve()
    levels_checked = 0

    while levels_checked < _max_levels:
        candidate = current / "CLAUDE.md"
        if candidate.is_file():
            try:
                text = candidate.read_text(encoding="utf-8", errors="replace")
                total += len(text.splitlines())
            except OSError:
                pass

        parent = current.parent
        if parent == current:
            # Filesystem root reached
            break
        current = parent
        levels_checked += 1

    return total


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point — reads stdin JSON, writes usage file, prints status line."""
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        payload = {}

    cwd = Path(payload.get("cwd", ".")).expanduser()
    claude_md_lines = count_claude_md_lines(cwd)

    usage_path = Path(
        payload.get("usage_path", "~/.library/state/context_usage.txt")
    ).expanduser()

    used_percentage = float(
        payload.get("context_window", {}).get("used_percentage", 0)
    )
    write_context_usage(usage_path, used_percentage)

    line = format_status_line(payload, claude_md_lines)
    print(line)


if __name__ == "__main__":
    main()
