"""Token tracker hook script — track per-component token usage across a session.

Reads stdin JSON from Claude Code's PostToolUse hook, classifies the tool
by Library component, and appends a usage event to a session accumulator file.

Dev mode must be enabled in library-config.yaml for tracking to occur.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Prefix rules ordered longest-first so vault_builder_ matches before vault_
_PREFIX_MAP: list[tuple[str, str]] = [
    ("library_vault_builder_", "vault_builder"),
    ("library_checkpoint_", "checkpoint"),
    ("library_config_", "config"),
    ("library_memory_", "memory"),
    ("library_vault_", "vault"),
    ("library_graph_", "graph"),
    ("library_pm_", "pm"),
    ("library_dev_", "dev"),
]


# ── Public helpers ───────────────────────────────────────────────────────────


def classify_component(tool_name: str) -> str:
    """Map a tool name to its Library component.

    Uses prefix matching with longest-prefix-first ordering.
    Tools that don't match any Library prefix are classified as ``claude_tools``.

    Parameters
    ----------
    tool_name:
        The MCP tool name, e.g. ``library_pm_sync`` or ``Read``.

    Returns
    -------
    str
        Component name such as ``pm``, ``vault_builder``, or ``claude_tools``.
    """
    for prefix, component in _PREFIX_MAP:
        if tool_name.startswith(prefix):
            return component
    return "claude_tools"


def _is_dev_enabled() -> bool:
    """Check whether dev mode is enabled in library-config.yaml.

    Searches CWD then home directory. Returns False on any error.
    """
    try:
        import yaml  # type: ignore[import-untyped]

        for base in [Path.cwd(), Path.home()]:
            cfg_path = base / "library-config.yaml"
            if cfg_path.is_file():
                cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
                if isinstance(cfg, dict):
                    return bool(cfg.get("dev", {}).get("enabled", False))
        return False
    except Exception:
        return False


def track_tool_usage(
    tool_name: str,
    response_chars: int,
    context_used_pct: float,
    prev_context_pct: float,
    state_path: Path,
) -> None:
    """Record a tool usage event to the session accumulator.

    No-op if dev mode is disabled. Creates the accumulator file on first call.
    Recreates the file if it's corrupt.

    Parameters
    ----------
    tool_name:
        Name of the tool that was used.
    response_chars:
        Character count of the tool response.
    context_used_pct:
        Current context window usage percentage.
    prev_context_pct:
        Previous context window usage percentage (before this tool call).
    state_path:
        Path to the accumulator JSON file.
    """
    if not _is_dev_enabled():
        return

    # Load or create accumulator
    accumulator: dict = {
        "session_id": "",
        "started_at": "",
        "events": [],
    }

    if state_path.is_file():
        try:
            accumulator = json.loads(state_path.read_text(encoding="utf-8"))
            if not isinstance(accumulator, dict) or "events" not in accumulator:
                raise ValueError("missing events key")
        except (json.JSONDecodeError, ValueError):
            accumulator = {"session_id": "", "started_at": "", "events": []}

    event = {
        "tool": tool_name,
        "component": classify_component(tool_name),
        "response_chars": response_chars,
        "context_delta_pct": round(context_used_pct - prev_context_pct, 4),
        "cumulative_context_pct": context_used_pct,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    accumulator["events"].append(event)

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(accumulator, indent=2), encoding="utf-8")


def aggregate_usage(state_path: Path) -> dict:
    """Aggregate token usage from the session accumulator.

    Parameters
    ----------
    state_path:
        Path to the accumulator JSON file.

    Returns
    -------
    dict
        Aggregated report with ``session_total_calls``, ``session_context_peak``,
        ``components`` (by component name), and ``top_consumers`` (by tool, sorted
        by estimated tokens descending).
    """
    empty_report: dict = {
        "session_total_calls": 0,
        "session_context_peak": 0,
        "components": {},
        "top_consumers": [],
    }

    if not state_path.is_file():
        return empty_report

    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        events = data.get("events", [])
    except (json.JSONDecodeError, ValueError, KeyError):
        return empty_report

    if not events:
        return empty_report

    # Aggregate by component
    components: dict[str, dict] = {}
    tool_agg: dict[str, dict] = {}
    peak_context = 0.0

    for ev in events:
        comp = ev.get("component", "claude_tools")
        chars = ev.get("response_chars", 0)
        delta = ev.get("context_delta_pct", 0.0)
        cum = ev.get("cumulative_context_pct", 0.0)
        tool = ev.get("tool", "unknown")

        if cum > peak_context:
            peak_context = cum

        if comp not in components:
            components[comp] = {"calls": 0, "total_chars": 0, "context_delta": 0.0}
        components[comp]["calls"] += 1
        components[comp]["total_chars"] += chars
        components[comp]["context_delta"] += delta

        if tool not in tool_agg:
            tool_agg[tool] = {"calls": 0, "total_chars": 0}
        tool_agg[tool]["calls"] += 1
        tool_agg[tool]["total_chars"] += chars

    # Build component summary with est_tokens
    comp_summary = {}
    for name, info in components.items():
        comp_summary[name] = {
            "calls": info["calls"],
            "est_tokens": info["total_chars"] // 4,
            "context_delta": round(info["context_delta"], 4),
        }

    # Build top consumers sorted by est_tokens desc
    top_consumers = sorted(
        [
            {
                "tool": tool,
                "calls": info["calls"],
                "est_tokens": info["total_chars"] // 4,
            }
            for tool, info in tool_agg.items()
        ],
        key=lambda x: x["est_tokens"],
        reverse=True,
    )

    return {
        "session_total_calls": len(events),
        "session_context_peak": peak_context,
        "components": comp_summary,
        "top_consumers": top_consumers,
    }


# ── Entry point ──────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point — reads stdin JSON, tracks tool usage. No stdout output."""
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        return

    if not payload:
        return

    tool_name = payload.get("tool_name", "")
    if not tool_name:
        return

    response_text = payload.get("tool_response", "")
    response_chars = len(response_text) if isinstance(response_text, str) else 0
    context_used_pct = float(
        payload.get("context_window", {}).get("used_percentage", 0)
    )
    prev_context_pct = float(payload.get("_prev_context_pct", 0))
    state_path = Path(
        payload.get("_state_path", "~/.library/state/token-usage.json")
    ).expanduser()

    track_tool_usage(tool_name, response_chars, context_used_pct, prev_context_pct, state_path)


if __name__ == "__main__":
    main()
