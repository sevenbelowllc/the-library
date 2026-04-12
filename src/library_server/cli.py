"""CLI commands for The Library.

Provides `library init` to bootstrap a project for Library usage.
Creates all runtime directories, state files, hooks, and domain manifests
so the user can start using The Library immediately after running one command.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from library_server import __version__
from library_server.config import CONFIG_FILENAME, load_config, validate_config


def main() -> None:
    """CLI entry point — dispatches to subcommands or starts MCP server."""
    parser = argparse.ArgumentParser(
        prog="library",
        description="The Library — MCP server for AI-assisted project management",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="command")

    # --- init ---
    init_parser = sub.add_parser(
        "init",
        help="Initialize The Library for the current project",
    )
    init_parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path.cwd(),
        help="Project root directory (default: current directory)",
    )
    init_parser.add_argument(
        "--reading-room",
        type=str,
        default=None,
        help="Path to Reading Room (relative to project dir or absolute)",
    )
    init_parser.add_argument(
        "--vault",
        type=str,
        default=None,
        help="Path to knowledge vault (relative to project dir or absolute)",
    )
    init_parser.add_argument(
        "--pm",
        choices=["jira", "linear", "none"],
        default="none",
        help="PM provider (default: none)",
    )
    init_parser.add_argument(
        "--skip-hooks",
        action="store_true",
        help="Skip installing Claude Code hooks",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing config and state files",
    )

    # --- validate ---
    sub.add_parser("validate", help="Validate current Library installation")

    # --- doctor ---
    sub.add_parser("doctor", help="Diagnose and fix common installation issues")

    args = parser.parse_args()

    if args.command == "init":
        _cmd_init(args)
    elif args.command == "validate":
        _cmd_validate()
    elif args.command == "doctor":
        _cmd_doctor()
    elif args.command is None:
        # No subcommand — run MCP server (default behavior)
        from library_server.server import main as server_main
        server_main()


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

def _cmd_init(args: argparse.Namespace) -> None:
    """Initialize The Library for a project."""
    project_dir = args.project_dir.resolve()
    print(f"Initializing The Library v{__version__} in {project_dir}\n")

    steps_ok = 0
    steps_total = 0

    # Step 1: Create library-config.yaml
    steps_total += 1
    config_path = project_dir / CONFIG_FILENAME
    if config_path.exists() and not args.force:
        print(f"  [skip] {CONFIG_FILENAME} already exists (use --force to overwrite)")
        steps_ok += 1
    else:
        reading_room = args.reading_room or "./library-reading-room"
        vault = args.vault or "./vault"
        pm_provider = args.pm or "none"

        config_content = _generate_config(
            reading_room=reading_room,
            vault=vault,
            pm_provider=pm_provider,
        )
        config_path.write_text(config_content, encoding="utf-8")
        print(f"  [done] Created {CONFIG_FILENAME}")
        steps_ok += 1

    # Step 2: Create Reading Room structure
    steps_total += 1
    config = load_config(config_path)
    rr_raw = config.get_section("reading_room").get("path", "./library-reading-room")
    rr_path = (project_dir / rr_raw).resolve()
    rr_created = _ensure_reading_room(rr_path)
    if rr_created:
        print(f"  [done] Reading Room at {rr_path}")
    else:
        print(f"  [skip] Reading Room already exists at {rr_path}")
    steps_ok += 1

    # Step 3: Create vault structure
    steps_total += 1
    vault_raw = config.get_section("vault").get("path", "./vault")
    vault_path = (project_dir / vault_raw).resolve()
    vault_created = _ensure_vault(vault_path)
    if vault_created:
        print(f"  [done] Vault at {vault_path}")
    else:
        print(f"  [skip] Vault already exists at {vault_path}")
    steps_ok += 1

    # Step 4: Create ~/.library runtime directories
    steps_total += 1
    runtime_created = _ensure_runtime_dirs()
    if runtime_created:
        print(f"  [done] Runtime directories at ~/.library/")
    else:
        print(f"  [skip] Runtime directories already exist")
    steps_ok += 1

    # Step 5: Create SESSION.md
    steps_total += 1
    session_path = Path.home() / ".library" / "sessions" / "SESSION.md"
    if not session_path.exists() or args.force:
        _create_session_md(session_path)
        print(f"  [done] Created SESSION.md")
        steps_ok += 1
    else:
        print(f"  [skip] SESSION.md already exists")
        steps_ok += 1

    # Step 6: Create PROJECT-STATE.md
    steps_total += 1
    ps_path = rr_path / "PROJECT-STATE.md"
    if not ps_path.exists() or args.force:
        project_name = config.get_section("library").get("name", project_dir.name)
        _create_project_state(ps_path, project_name)
        print(f"  [done] Created PROJECT-STATE.md")
        steps_ok += 1
    else:
        print(f"  [skip] PROJECT-STATE.md already exists")
        steps_ok += 1

    # Step 7: Seed domain manifests from CLAUDE.md
    steps_total += 1
    claude_md = project_dir / "CLAUDE.md"
    domains_dir = vault_path / "domains"
    if claude_md.exists():
        from library_server.memory.domain_seeder import seed_domains_from_claude_md
        created = seed_domains_from_claude_md(claude_md, domains_dir)
        if created:
            print(f"  [done] Seeded {len(created)} domain(s): {', '.join(created)}")
        else:
            print(f"  [skip] Domain manifests already exist or no patterns matched")
        steps_ok += 1
    else:
        print(f"  [skip] No CLAUDE.md found — skipping domain seeding")
        steps_ok += 1

    # Step 8: Install hooks
    steps_total += 1
    if not args.skip_hooks:
        settings_path = project_dir / ".claude" / "settings.json"
        hooks_installed = _install_hooks(settings_path, project_dir)
        if hooks_installed:
            print(f"  [done] Installed hooks in .claude/settings.json")
        else:
            print(f"  [skip] Hooks already installed")
        steps_ok += 1
    else:
        print(f"  [skip] Hook installation skipped (--skip-hooks)")
        steps_ok += 1

    # Step 9: Create hook wrapper scripts
    steps_total += 1
    hooks_dir = project_dir / ".claude" / "hooks"
    scripts_created = _ensure_hook_scripts(hooks_dir, project_dir)
    if scripts_created:
        print(f"  [done] Created {scripts_created} hook wrapper script(s)")
    else:
        print(f"  [skip] Hook wrapper scripts already exist")
    steps_ok += 1

    # Step 10: Initialize routing journal
    steps_total += 1
    journal = Path.home() / ".library" / "routing.jsonl"
    if not journal.exists():
        journal.touch()
        print(f"  [done] Created routing journal")
    else:
        print(f"  [skip] Routing journal already exists")
    steps_ok += 1

    # Step 11: Validate
    steps_total += 1
    config = load_config(config_path)
    result = validate_config(config)
    if result["valid"]:
        print(f"  [done] Configuration valid")
        steps_ok += 1
    else:
        print(f"  [warn] Configuration has warnings:")
        for w in result["warnings"]:
            print(f"         - {w}")
        steps_ok += 1

    # Summary
    print(f"\n{'='*50}")
    print(f"The Library v{__version__} initialized ({steps_ok}/{steps_total} steps)")
    print(f"{'='*50}")
    print()
    print("Next steps:")
    print("  1. Review library-config.yaml and adjust paths")
    print("  2. Run `library:config` in Claude Code for interactive setup")
    print("  3. Run `library:ingest` to populate the vault with content")
    print()

    if not (project_dir / ".mcp.json").exists():
        print("Note: No .mcp.json found. To register the MCP server, add to your")
        print("project's .mcp.json or Claude Code MCP settings:")
        print('  {"library": {"command": "library", "env": {}}}')
        print()


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

def _cmd_validate() -> None:
    """Validate current Library installation."""
    print(f"Validating The Library v{__version__}\n")

    issues: list[str] = []
    ok: list[str] = []

    # Config
    config_path = Path.cwd() / CONFIG_FILENAME
    if config_path.exists():
        ok.append(f"{CONFIG_FILENAME} exists")
        config = load_config(config_path)
        result = validate_config(config)
        if result["valid"]:
            ok.append("Configuration is valid")
        else:
            for w in result["warnings"]:
                issues.append(f"Config: {w}")
    else:
        issues.append(f"{CONFIG_FILENAME} not found in {Path.cwd()}")

    # Runtime dirs
    for d in ["sessions", "state", "vault/transcripts", "vault/sessions"]:
        p = Path.home() / ".library" / d
        if p.is_dir():
            ok.append(f"~/.library/{d}/ exists")
        else:
            issues.append(f"~/.library/{d}/ missing")

    # SESSION.md
    session = Path.home() / ".library" / "sessions" / "SESSION.md"
    if session.is_file():
        ok.append("SESSION.md exists")
    else:
        issues.append("SESSION.md missing — session continuity broken")

    # Hooks
    settings = Path.cwd() / ".claude" / "settings.json"
    if settings.is_file():
        try:
            data = json.loads(settings.read_text())
            hooks = data.get("hooks", {})
            expected = ["SessionStart", "UserPromptSubmit", "Stop", "PreCompact", "SessionEnd"]
            for h in expected:
                if h in hooks:
                    ok.append(f"Hook {h} registered")
                else:
                    issues.append(f"Hook {h} not registered")
        except (json.JSONDecodeError, ValueError):
            issues.append(".claude/settings.json is malformed")
    else:
        issues.append(".claude/settings.json not found")

    # Hook scripts
    hooks_dir = Path.cwd() / ".claude" / "hooks"
    for script in ["session_start.py", "prompt_scan.py", "stop_capture.py",
                    "pre_compact.py", "session_end.py", "status_line.py"]:
        if (hooks_dir / script).is_file():
            ok.append(f"Hook script {script} exists")
        else:
            issues.append(f"Hook script {script} missing")

    # library binary
    if shutil.which("library"):
        ok.append("library binary on PATH")
    else:
        issues.append("library not found on PATH")

    # Print results
    for item in ok:
        print(f"  ✅ {item}")
    for item in issues:
        print(f"  ❌ {item}")

    print(f"\n{len(ok)} passed, {len(issues)} issues")
    if issues:
        print("\nRun `library doctor` to fix issues automatically.")
        sys.exit(1)


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

def _cmd_doctor() -> None:
    """Diagnose and fix common installation issues."""
    print(f"The Library v{__version__} — Doctor\n")

    fixes = 0

    # Fix runtime dirs
    for d in ["sessions", "state", "vault/transcripts", "vault/sessions"]:
        p = Path.home() / ".library" / d
        if not p.is_dir():
            p.mkdir(parents=True, exist_ok=True)
            print(f"  [fix] Created ~/.library/{d}/")
            fixes += 1

    # Fix SESSION.md
    session = Path.home() / ".library" / "sessions" / "SESSION.md"
    if not session.is_file():
        _create_session_md(session)
        print(f"  [fix] Created SESSION.md")
        fixes += 1

    # Fix routing journal
    journal = Path.home() / ".library" / "routing.jsonl"
    if not journal.exists():
        journal.touch()
        print(f"  [fix] Created routing journal")
        fixes += 1

    # Fix context usage file
    usage = Path.home() / ".library" / "state" / "context_usage.txt"
    if not usage.exists():
        usage.parent.mkdir(parents=True, exist_ok=True)
        usage.write_text("0", encoding="utf-8")
        print(f"  [fix] Created context usage tracker")
        fixes += 1

    if fixes == 0:
        print("  No issues found. Everything looks good.")
    else:
        print(f"\n  Fixed {fixes} issue(s). Run `library validate` to verify.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_config(reading_room: str, vault: str, pm_provider: str) -> str:
    """Generate a starter library-config.yaml."""
    lines = [
        f'library:',
        f'  version: "{__version__}"',
        f'  name: ""  # Your project name',
        f'',
        f'reading_room:',
        f'  path: {reading_room}',
        f'  type: directory  # "repo" if dedicated git repo, "directory" otherwise',
        f'',
        f'vault:',
        f'  path: {vault}',
        f'  schema_version: karpathy-v1',
        f'',
        f'pm:',
        f'  provider: {pm_provider}',
    ]
    if pm_provider == "jira":
        lines += [
            f'  site_url: https://your-site.atlassian.net',
            f'  projects: []  # e.g. [PROJ1, PROJ2]',
        ]
    elif pm_provider == "linear":
        lines += [
            f'  teams: []  # e.g. [TEAM1]',
        ]
    lines += [
        f'',
        f'graphify:',
        f'  enabled: false',
        f'',
        f'# See library-config.example.yaml for all options including:',
        f'# - vault_builder (source ingestion pipeline)',
        f'# - memory (budgets, pruning, keyword learning)',
        f'# - context (warn/checkpoint percentages)',
        f'# - hooks (enable/disable lifecycle hooks)',
    ]
    return "\n".join(lines) + "\n"


def _ensure_reading_room(rr_path: Path) -> bool:
    """Create Reading Room structure if it doesn't exist. Returns True if created."""
    created = False
    for subdir in ["specs", "plans", "checkpoints"]:
        p = rr_path / subdir
        if not p.is_dir():
            p.mkdir(parents=True, exist_ok=True)
            created = True
    return created


def _ensure_vault(vault_path: Path) -> bool:
    """Create vault directory structure if it doesn't exist. Returns True if created."""
    created = False
    for subdir in ["domains", "sources", "wiki", "decisions", "sessions",
                   "learning", "archive", "_schema"]:
        p = vault_path / subdir
        if not p.is_dir():
            p.mkdir(parents=True, exist_ok=True)
            created = True
    return created


def _ensure_runtime_dirs() -> bool:
    """Create ~/.library runtime directories. Returns True if any created."""
    created = False
    base = Path.home() / ".library"
    for subdir in ["sessions", "state", "vault/transcripts", "vault/sessions"]:
        p = base / subdir
        if not p.is_dir():
            p.mkdir(parents=True, exist_ok=True)
            created = True

    # Ensure context_usage.txt exists
    usage = base / "state" / "context_usage.txt"
    if not usage.exists():
        usage.write_text("0", encoding="utf-8")
        created = True

    return created


def _create_session_md(path: Path) -> None:
    """Create a fresh SESSION.md."""
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    content = f"""---
session_id: init
started: {now}
project: ""
---

## Current
- task: Initial setup
- doing: Library initialization
- branch: main
- turns: 0

## Decisions
(none yet)

## Files Touched
(none yet)

## Domains Loaded
(none yet)

## Resume Instructions
Fresh session — The Library has been initialized. Run library:config for interactive setup.
"""
    path.write_text(content, encoding="utf-8")


def _create_project_state(path: Path, project_name: str) -> None:
    """Create a starter PROJECT-STATE.md."""
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    content = f"""---
library_version: "{__version__}"
updated: {now}
session_count: 0
---

## Active
- Project: {project_name}
- Focus: Initial setup
- Active task: Run library:config for interactive configuration
- Blockers: none

## PM Projects
(none configured — run library:config pm to set up)
"""
    path.write_text(content, encoding="utf-8")


def _install_hooks(settings_path: Path, project_dir: Path) -> bool:
    """Install hooks into .claude/settings.json. Returns True if modified."""
    from library_server.hooks.installer import install_hooks

    # Check if hooks already installed
    if settings_path.is_file():
        try:
            data = json.loads(settings_path.read_text())
            if "hooks" in data and "SessionStart" in data.get("hooks", {}):
                return False
        except (json.JSONDecodeError, ValueError):
            pass

    install_hooks(settings_path)
    return True


def _ensure_hook_scripts(hooks_dir: Path, project_dir: Path) -> int:
    """Create thin wrapper hook scripts in .claude/hooks/. Returns count created."""
    hooks_dir.mkdir(parents=True, exist_ok=True)
    created = 0

    # Find the-library directory relative to project
    # Look for it as a subdirectory or sibling
    library_dir = None
    for candidate in [
        project_dir / "the-library",
        project_dir.parent / "the-library",
    ]:
        if (candidate / "src" / "library_server").is_dir():
            library_dir = candidate
            break

    # If we can't find it locally, the package is pip-installed — use module paths
    use_module = library_dir is None

    scripts = {
        "session_start": {
            "defaults": {
                "reading_room": "os.path.join(PROJECT_DIR, 'library-reading-room')",
                "sessions_dir": "os.path.expanduser('~/.library/sessions')",
            },
            "pass_args": True,
        },
        "prompt_scan": {
            "defaults": {
                "domains_dir": "_find_domains_dir(PROJECT_DIR)",
                "dedup_dir": "'/tmp'",
                "journal_path": "os.path.expanduser('~/.library/routing.jsonl')",
            },
            "pass_args": False,
        },
        "stop_capture": {
            "defaults": {
                "sessions_dir": "os.path.expanduser('~/.library/sessions')",
                "context_usage_path": "os.path.expanduser('~/.library/state/context_usage.txt')",
                "journal_path": "os.path.expanduser('~/.library/routing.jsonl')",
            },
            "pass_args": False,
        },
        "pre_compact": {
            "defaults": {
                "vault_transcripts_dir": "os.path.expanduser('~/.library/vault/transcripts')",
                "sessions_dir": "os.path.expanduser('~/.library/sessions')",
            },
            "pass_args": False,
        },
        "session_end": {
            "defaults": {
                "reading_room": "os.path.join(PROJECT_DIR, 'library-reading-room')",
                "sessions_dir": "os.path.expanduser('~/.library/sessions')",
                "vault_sessions_dir": "os.path.expanduser('~/.library/vault/sessions')",
            },
            "pass_args": False,
        },
        "status_line": {
            "defaults": {
                "usage_path": "os.path.expanduser('~/.library/state/context_usage.txt')",
            },
            "pass_args": False,
        },
    }

    for script_name, info in scripts.items():
        script_path = hooks_dir / f"{script_name}.py"
        if script_path.exists() and not True:  # always overwrite hook wrappers
            continue

        defaults_lines = []
        for key, val in info["defaults"].items():
            defaults_lines.append(f'payload.setdefault("{key}", {val})')

        args_line = ' + sys.argv[1:]' if info["pass_args"] else ''

        if use_module:
            script_ref = f'"-m", "library_server.hooks.scripts.{script_name}"'
        else:
            lib_rel = _relpath_or_abs(library_dir, project_dir)
            script_ref = f'os.path.join(LIBRARY_DIR, "src/library_server/hooks/scripts/{script_name}.py")'

        if use_module:
            content = f'''#!/usr/bin/env python3
"""Auto-generated by library init — delegates to The Library hook."""
import json, subprocess, sys, os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _find_domains_dir(project_dir):
    """Find domains directory in vault or the-library subdir."""
    for candidate in [
        os.path.join(project_dir, "vault", "domains"),
        os.path.join(project_dir, "the-library", "vault", "domains"),
    ]:
        if os.path.isdir(candidate):
            return candidate
    return os.path.join(project_dir, "vault", "domains")

raw = sys.stdin.buffer.read()
try:
    payload = json.loads(raw)
except (json.JSONDecodeError, ValueError):
    payload = {{}}

{chr(10).join(defaults_lines)}

augmented = json.dumps(payload).encode()
result = subprocess.run([sys.executable, {script_ref}]{args_line}, input=augmented, capture_output=True)
sys.stdout.buffer.write(result.stdout)
sys.exit(result.returncode)
'''
        else:
            content = f'''#!/usr/bin/env python3
"""Auto-generated by library init — delegates to The Library hook."""
import json, subprocess, sys, os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIBRARY_DIR = os.path.join(PROJECT_DIR, "{lib_rel}")
SCRIPT = {script_ref}

def _find_domains_dir(project_dir):
    """Find domains directory in vault or the-library subdir."""
    for candidate in [
        os.path.join(project_dir, "vault", "domains"),
        os.path.join(project_dir, "the-library", "vault", "domains"),
    ]:
        if os.path.isdir(candidate):
            return candidate
    return os.path.join(project_dir, "vault", "domains")

raw = sys.stdin.buffer.read()
try:
    payload = json.loads(raw)
except (json.JSONDecodeError, ValueError):
    payload = {{}}

{chr(10).join(defaults_lines)}

augmented = json.dumps(payload).encode()
result = subprocess.run([sys.executable, SCRIPT]{args_line}, input=augmented, capture_output=True)
sys.stdout.buffer.write(result.stdout)
sys.exit(result.returncode)
'''

        script_path.write_text(content, encoding="utf-8")
        script_path.chmod(0o755)
        created += 1

    return created


def _relpath_or_abs(target: Path, base: Path) -> str:
    """Get relative path from base to target, or absolute if not possible."""
    try:
        return str(target.relative_to(base))
    except ValueError:
        return str(target)


if __name__ == "__main__":
    main()
