"""Tests for library CLI commands (init, validate, doctor)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from library_server.cli import (
    _cmd_doctor,
    _cmd_init,
    _cmd_validate,
    _create_project_state,
    _create_session_md,
    _ensure_reading_room,
    _ensure_runtime_dirs,
    _ensure_vault,
    _generate_config,
    main,
)


# ---------------------------------------------------------------------------
# _generate_config
# ---------------------------------------------------------------------------


class TestGenerateConfig:
    def test_default_config(self):
        config = _generate_config("./reading-room", "./vault", "none")
        assert 'version: "0.3.0"' in config
        assert "reading_room:" in config
        assert "path: ./reading-room" in config
        assert "provider: none" in config
        assert "graphify:" in config

    def test_jira_config(self):
        config = _generate_config("./rr", "./v", "jira")
        assert "provider: jira" in config
        assert "site_url:" in config
        assert "projects:" in config

    def test_linear_config(self):
        config = _generate_config("./rr", "./v", "linear")
        assert "provider: linear" in config
        assert "teams:" in config


# ---------------------------------------------------------------------------
# _ensure_reading_room
# ---------------------------------------------------------------------------


class TestEnsureReadingRoom:
    def test_creates_subdirs(self, tmp_path: Path):
        rr = tmp_path / "reading-room"
        result = _ensure_reading_room(rr)
        assert result is True
        assert (rr / "specs").is_dir()
        assert (rr / "plans").is_dir()
        assert (rr / "checkpoints").is_dir()

    def test_skips_existing(self, tmp_path: Path):
        rr = tmp_path / "reading-room"
        for d in ["specs", "plans", "checkpoints"]:
            (rr / d).mkdir(parents=True)
        result = _ensure_reading_room(rr)
        assert result is False


# ---------------------------------------------------------------------------
# _ensure_vault
# ---------------------------------------------------------------------------


class TestEnsureVault:
    def test_creates_all_dirs(self, tmp_path: Path):
        vault = tmp_path / "vault"
        result = _ensure_vault(vault)
        assert result is True
        for d in ["domains", "sources", "wiki", "decisions", "sessions",
                   "learning", "archive", "_schema"]:
            assert (vault / d).is_dir(), f"{d}/ not created"

    def test_skips_existing(self, tmp_path: Path):
        vault = tmp_path / "vault"
        for d in ["domains", "sources", "wiki", "decisions", "sessions",
                   "learning", "archive", "_schema"]:
            (vault / d).mkdir(parents=True)
        result = _ensure_vault(vault)
        assert result is False


# ---------------------------------------------------------------------------
# _ensure_runtime_dirs
# ---------------------------------------------------------------------------


class TestEnsureRuntimeDirs:
    def test_creates_dirs(self, tmp_path: Path):
        with patch("library_server.cli.Path.home", return_value=tmp_path):
            result = _ensure_runtime_dirs()
        assert result is True
        assert (tmp_path / ".library" / "sessions").is_dir()
        assert (tmp_path / ".library" / "state").is_dir()
        assert (tmp_path / ".library" / "vault" / "transcripts").is_dir()
        assert (tmp_path / ".library" / "vault" / "sessions").is_dir()
        assert (tmp_path / ".library" / "state" / "context_usage.txt").is_file()

    def test_skips_existing(self, tmp_path: Path):
        base = tmp_path / ".library"
        for d in ["sessions", "state", "vault/transcripts", "vault/sessions"]:
            (base / d).mkdir(parents=True)
        (base / "state" / "context_usage.txt").write_text("0")
        with patch("library_server.cli.Path.home", return_value=tmp_path):
            result = _ensure_runtime_dirs()
        assert result is False


# ---------------------------------------------------------------------------
# _create_session_md
# ---------------------------------------------------------------------------


class TestCreateSessionMd:
    def test_creates_file(self, tmp_path: Path):
        path = tmp_path / "sessions" / "SESSION.md"
        _create_session_md(path)
        assert path.is_file()
        content = path.read_text()
        assert "session_id: init" in content
        assert "## Current" in content
        assert "## Resume Instructions" in content

    def test_creates_parent_dirs(self, tmp_path: Path):
        path = tmp_path / "deep" / "nested" / "SESSION.md"
        _create_session_md(path)
        assert path.is_file()


# ---------------------------------------------------------------------------
# _create_project_state
# ---------------------------------------------------------------------------


class TestCreateProjectState:
    def test_creates_file(self, tmp_path: Path):
        path = tmp_path / "PROJECT-STATE.md"
        _create_project_state(path, "My Project")
        assert path.is_file()
        content = path.read_text()
        assert "My Project" in content
        assert "library_version:" in content
        assert "## Active" in content

    def test_creates_parent_dirs(self, tmp_path: Path):
        path = tmp_path / "rr" / "PROJECT-STATE.md"
        _create_project_state(path, "Test")
        assert path.is_file()


# ---------------------------------------------------------------------------
# _cmd_init (integration)
# ---------------------------------------------------------------------------


class TestCmdInit:
    def _make_args(self, project_dir: Path, **kwargs):
        """Build a namespace simulating parsed CLI args."""
        import argparse
        defaults = {
            "project_dir": project_dir,
            "reading_room": None,
            "vault": None,
            "pm": "none",
            "skip_hooks": True,  # skip hooks in tests — no .claude dir needed
            "force": False,
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def test_full_init(self, tmp_path: Path, capsys):
        project = tmp_path / "project"
        project.mkdir()
        # Create a CLAUDE.md for domain seeding
        (project / "CLAUDE.md").write_text("Uses PostgreSQL and Jest for testing.")

        with patch("library_server.cli.Path.home", return_value=tmp_path):
            args = self._make_args(project)
            _cmd_init(args)

        captured = capsys.readouterr()
        assert "11/11 steps" in captured.out

        # Verify files created
        assert (project / "library-config.yaml").is_file()
        assert (project / "library-reading-room" / "specs").is_dir()
        assert (project / "library-reading-room" / "PROJECT-STATE.md").is_file()
        assert (project / "vault" / "domains").is_dir()
        assert (project / "vault" / "_schema").is_dir()

    def test_init_skips_existing(self, tmp_path: Path, capsys):
        project = tmp_path / "project"
        project.mkdir()
        (project / "library-config.yaml").write_text("library:\n  version: '0.3.0'\n")

        with patch("library_server.cli.Path.home", return_value=tmp_path):
            args = self._make_args(project)
            _cmd_init(args)

        captured = capsys.readouterr()
        assert "[skip] library-config.yaml already exists" in captured.out

    def test_init_force_overwrites(self, tmp_path: Path, capsys):
        project = tmp_path / "project"
        project.mkdir()
        (project / "library-config.yaml").write_text("old config")

        with patch("library_server.cli.Path.home", return_value=tmp_path):
            args = self._make_args(project, force=True)
            _cmd_init(args)

        captured = capsys.readouterr()
        assert "[done] Created library-config.yaml" in captured.out
        # Verify it was overwritten
        content = (project / "library-config.yaml").read_text()
        assert "old config" not in content

    def test_init_custom_paths(self, tmp_path: Path, capsys):
        project = tmp_path / "project"
        project.mkdir()

        with patch("library_server.cli.Path.home", return_value=tmp_path):
            args = self._make_args(
                project,
                reading_room="./docs/reading-room",
                vault="./knowledge",
                pm="jira",
            )
            _cmd_init(args)

        config = (project / "library-config.yaml").read_text()
        assert "path: ./docs/reading-room" in config
        assert "path: ./knowledge" in config
        assert "provider: jira" in config


# ---------------------------------------------------------------------------
# _cmd_validate
# ---------------------------------------------------------------------------


class TestCmdValidate:
    def test_validates_healthy_install(self, tmp_path: Path, capsys):
        # Set up a complete installation
        project = tmp_path / "project"
        project.mkdir()

        # Config
        (project / "vault").mkdir()
        (project / "library-config.yaml").write_text(
            "library:\n  version: '0.3.0'\nvault:\n  path: ./vault\npm:\n  provider: none\n"
        )

        # Hooks
        hooks_dir = project / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True)
        settings = project / ".claude" / "settings.json"
        settings.write_text(json.dumps({
            "hooks": {
                "SessionStart": [],
                "UserPromptSubmit": [],
                "Stop": [],
                "PreCompact": [],
                "SessionEnd": [],
            }
        }))
        for script in ["session_start.py", "prompt_scan.py", "stop_capture.py",
                        "pre_compact.py", "session_end.py", "status_line.py"]:
            (hooks_dir / script).write_text("# stub")

        # Runtime
        home = tmp_path / "home"
        for d in ["sessions", "state", "vault/transcripts", "vault/sessions"]:
            (home / ".library" / d).mkdir(parents=True)
        (home / ".library" / "sessions" / "SESSION.md").write_text("---\nsession_id: test\n---\n")

        import os
        orig_cwd = os.getcwd()
        os.chdir(project)
        try:
            with patch("library_server.cli.Path.home", return_value=home), \
                 patch("shutil.which", return_value="/usr/bin/library"):
                _cmd_validate()
        finally:
            os.chdir(orig_cwd)

        captured = capsys.readouterr()
        assert "0 issues" in captured.out

    def test_validates_broken_install(self, tmp_path: Path, capsys):
        project = tmp_path / "project"
        project.mkdir()
        # No config, no hooks, no runtime

        home = tmp_path / "home"
        home.mkdir()

        import os
        orig_cwd = os.getcwd()
        os.chdir(project)
        try:
            with patch("library_server.cli.Path.home", return_value=home), \
                 patch("shutil.which", return_value=None), \
                 pytest.raises(SystemExit) as exc_info:
                _cmd_validate()
        finally:
            os.chdir(orig_cwd)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "issues" in captured.out


# ---------------------------------------------------------------------------
# _cmd_doctor
# ---------------------------------------------------------------------------


class TestCmdDoctor:
    def test_fixes_missing_dirs(self, tmp_path: Path, capsys):
        with patch("library_server.cli.Path.home", return_value=tmp_path):
            _cmd_doctor()

        captured = capsys.readouterr()
        assert "[fix]" in captured.out
        assert (tmp_path / ".library" / "sessions" / "SESSION.md").is_file()
        assert (tmp_path / ".library" / "vault" / "transcripts").is_dir()
        assert (tmp_path / ".library" / "vault" / "sessions").is_dir()

    def test_no_fixes_needed(self, tmp_path: Path, capsys):
        # Pre-create everything
        base = tmp_path / ".library"
        for d in ["sessions", "state", "vault/transcripts", "vault/sessions"]:
            (base / d).mkdir(parents=True)
        (base / "sessions" / "SESSION.md").write_text("---\nsession_id: test\n---\n")
        (base / "state" / "context_usage.txt").write_text("0")
        (base / "routing.jsonl").touch()

        with patch("library_server.cli.Path.home", return_value=tmp_path):
            _cmd_doctor()

        captured = capsys.readouterr()
        assert "No issues found" in captured.out


# ---------------------------------------------------------------------------
# main() dispatch
# ---------------------------------------------------------------------------


class TestMainDispatch:
    def test_no_args_runs_server(self):
        """With no subcommand, main() should call server main."""
        with patch("library_server.cli.argparse._sys.argv", ["library"]), \
             patch("library_server.server.main") as mock_server:
            main()
        mock_server.assert_called_once()

    def test_version(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            with patch("library_server.cli.argparse._sys.argv", ["library", "--version"]):
                main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "0.3.0" in captured.out
