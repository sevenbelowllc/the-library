"""Hook installer for Claude Code settings.json.

Generates and installs MMU hook configuration into a Claude Code
``settings.json`` file, merging with any existing settings.

Usage::

    from pathlib import Path
    from library_server.hooks.installer import generate_hooks_config, install_hooks

    config = generate_hooks_config(project_dir="/path/to/project")
    result = install_hooks(Path("/path/to/project/.claude/settings.json"))
"""

from __future__ import annotations

import json
from pathlib import Path


def generate_hooks_config(project_dir: str = "$CLAUDE_PROJECT_DIR") -> dict:
    """Generate a Claude Code hooks configuration dict.

    Produces a ``settings.json``-compatible dict with entries for every
    MMU hook event: SessionStart (startup/resume, compact, clear),
    UserPromptSubmit, Stop, PreCompact, and SessionEnd.

    Parameters
    ----------
    project_dir:
        Base directory for the project. Used to build hook command paths.
        Defaults to ``$CLAUDE_PROJECT_DIR`` for use in template-style configs.

    Returns
    -------
    dict
        Dict with two top-level keys:

        * ``"hooks"`` — mapping of hook event names to lists of hook entries
        * ``"statusLine"`` — status bar command and refresh interval
    """
    hooks_base = f"{project_dir}/.claude/hooks"

    def _cmd(script: str) -> str:
        return f"python3 {hooks_base}/{script}.py"

    config: dict = {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "startup|resume",
                    "hooks": [
                        {
                            "type": "command",
                            "command": _cmd("session_start"),
                        }
                    ],
                },
                {
                    "matcher": "compact",
                    "hooks": [
                        {
                            "type": "command",
                            "command": _cmd("session_start"),
                        }
                    ],
                },
                {
                    "matcher": "clear",
                    "hooks": [
                        {
                            "type": "command",
                            "command": _cmd("session_start"),
                        }
                    ],
                },
            ],
            "UserPromptSubmit": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": _cmd("prompt_scan"),
                        }
                    ],
                }
            ],
            "Stop": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": _cmd("stop_capture"),
                        }
                    ],
                }
            ],
            "PreCompact": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": _cmd("pre_compact"),
                        }
                    ],
                }
            ],
            "SessionEnd": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": _cmd("session_end"),
                        }
                    ],
                }
            ],
        },
        "statusLine": {
            "command": _cmd("status_line"),
            "refreshInterval": 30,
        },
    }

    return config


def install_hooks(settings_path: Path) -> dict:
    """Merge MMU hook configuration into a Claude Code ``settings.json`` file.

    Reads existing settings (or starts from ``{}`` if the file does not
    exist), merges the generated hooks config in, and writes the result back.
    Existing top-level keys not related to hooks or statusLine are preserved.

    Parameters
    ----------
    settings_path:
        Absolute path to the ``settings.json`` file to update.

    Returns
    -------
    dict
        ``{"status": "installed", "hooks_count": <int>}``
        where ``hooks_count`` is the number of top-level hook event types
        installed.
    """
    # Load existing settings (may not exist yet)
    existing: dict = {}
    if settings_path.is_file():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            existing = {}

    # Determine project_dir from the settings_path location (.claude/settings.json)
    project_dir = str(settings_path.parent.parent)

    hooks_config = generate_hooks_config(project_dir=project_dir)

    # Deep-merge: preserve all existing keys, overwrite hooks + statusLine
    merged = {**existing}
    merged["hooks"] = hooks_config["hooks"]
    merged["statusLine"] = hooks_config["statusLine"]

    # Ensure parent directory exists
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(merged, indent=2) + "\n", encoding="utf-8"
    )

    hooks_count = len(hooks_config["hooks"])
    return {"status": "installed", "hooks_count": hooks_count}
