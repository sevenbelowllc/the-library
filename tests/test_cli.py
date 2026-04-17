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
    _ensure_hook_scripts,
    _ensure_reading_room,
    _ensure_runtime_dirs,
    _ensure_vault,
    _generate_config,
    _install_hooks,
    _relpath_or_abs,
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

    def test_dispatch_init(self, tmp_path: Path):
        """main() dispatches to _cmd_init when 'init' subcommand is given."""
        with patch("library_server.cli.argparse._sys.argv", ["library", "init", "--project-dir", str(tmp_path), "--skip-hooks"]), \
             patch("library_server.cli._cmd_init") as mock_init:
            main()
        mock_init.assert_called_once()

    def test_dispatch_validate(self):
        """main() dispatches to _cmd_validate when 'validate' subcommand is given."""
        with patch("library_server.cli.argparse._sys.argv", ["library", "validate"]), \
             patch("library_server.cli._cmd_validate") as mock_validate:
            main()
        mock_validate.assert_called_once()

    def test_dispatch_doctor(self):
        """main() dispatches to _cmd_doctor when 'doctor' subcommand is given."""
        with patch("library_server.cli.argparse._sys.argv", ["library", "doctor"]), \
             patch("library_server.cli._cmd_doctor") as mock_doctor:
            main()
        mock_doctor.assert_called_once()


# ---------------------------------------------------------------------------
# _install_hooks
# ---------------------------------------------------------------------------


class TestInstallHooks:
    def test_installs_when_no_settings_file(self, tmp_path: Path):
        settings = tmp_path / ".claude" / "settings.json"
        with patch("library_server.hooks.installer.install_hooks") as mock_install:
            result = _install_hooks(settings, tmp_path)
        assert result is True
        mock_install.assert_called_once_with(settings)

    def test_skips_when_hooks_already_installed(self, tmp_path: Path):
        settings = tmp_path / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({
            "hooks": {"SessionStart": [{"command": "test"}]}
        }))
        with patch("library_server.hooks.installer.install_hooks") as mock_install:
            result = _install_hooks(settings, tmp_path)
        assert result is False
        mock_install.assert_not_called()

    def test_installs_when_settings_malformed(self, tmp_path: Path):
        settings = tmp_path / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text("not valid json {{{")
        with patch("library_server.hooks.installer.install_hooks") as mock_install:
            result = _install_hooks(settings, tmp_path)
        assert result is True
        mock_install.assert_called_once_with(settings)

    def test_installs_when_hooks_key_missing(self, tmp_path: Path):
        settings = tmp_path / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({"other": "data"}))
        with patch("library_server.hooks.installer.install_hooks") as mock_install:
            result = _install_hooks(settings, tmp_path)
        assert result is True
        mock_install.assert_called_once_with(settings)


# ---------------------------------------------------------------------------
# _ensure_hook_scripts
# ---------------------------------------------------------------------------


class TestEnsureHookScripts:
    def test_creates_scripts_module_mode(self, tmp_path: Path):
        """When library_server is not found locally, uses module mode."""
        hooks_dir = tmp_path / ".claude" / "hooks"
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        # No the-library subdirectory or sibling — triggers module mode
        count = _ensure_hook_scripts(hooks_dir, project_dir)
        assert count == 6
        assert (hooks_dir / "session_start.py").exists()
        assert (hooks_dir / "prompt_scan.py").exists()
        assert (hooks_dir / "stop_capture.py").exists()
        assert (hooks_dir / "pre_compact.py").exists()
        assert (hooks_dir / "session_end.py").exists()
        assert (hooks_dir / "status_line.py").exists()
        # Verify module mode content
        content = (hooks_dir / "session_start.py").read_text()
        assert '"-m"' in content

    def test_creates_scripts_local_mode(self, tmp_path: Path):
        """When the-library is found as subdirectory, uses local path mode."""
        hooks_dir = tmp_path / ".claude" / "hooks"
        project_dir = tmp_path
        # Create the-library/src/library_server so it's found locally
        lib_dir = project_dir / "the-library" / "src" / "library_server"
        lib_dir.mkdir(parents=True)
        count = _ensure_hook_scripts(hooks_dir, project_dir)
        assert count == 6
        content = (hooks_dir / "session_start.py").read_text()
        assert "LIBRARY_DIR" in content
        assert "SCRIPT" in content

    def test_creates_scripts_sibling_mode(self, tmp_path: Path):
        """When the-library is found as sibling directory, uses local path mode."""
        hooks_dir = tmp_path / "project" / ".claude" / "hooks"
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        # Create sibling the-library/src/library_server
        lib_dir = tmp_path / "the-library" / "src" / "library_server"
        lib_dir.mkdir(parents=True)
        count = _ensure_hook_scripts(hooks_dir, project_dir)
        assert count == 6
        content = (hooks_dir / "session_start.py").read_text()
        assert "LIBRARY_DIR" in content


# ---------------------------------------------------------------------------
# _relpath_or_abs
# ---------------------------------------------------------------------------


class TestRelpathOrAbs:
    def test_relative_path(self, tmp_path: Path):
        base = tmp_path / "project"
        target = tmp_path / "project" / "sub" / "dir"
        result = _relpath_or_abs(target, base)
        assert result == "sub/dir"

    def test_absolute_fallback(self, tmp_path: Path):
        base = tmp_path / "project"
        target = Path("/completely/different/path")
        result = _relpath_or_abs(target, base)
        assert result == "/completely/different/path"


# ---------------------------------------------------------------------------
# _cmd_init — additional coverage for skip paths
# ---------------------------------------------------------------------------


class TestCmdInitSkipPaths:
    def _make_args(self, project_dir: Path, **kwargs):
        import argparse
        defaults = {
            "project_dir": project_dir,
            "reading_room": None,
            "vault": None,
            "pm": "none",
            "skip_hooks": True,
            "force": False,
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def test_init_skip_paths_for_existing_dirs(self, tmp_path: Path, capsys):
        """Exercise skip branches for reading room, vault, runtime, session, project state, hooks, journal."""
        project = tmp_path / "project"
        project.mkdir()

        # Pre-create config
        (project / "library-config.yaml").write_text(
            "library:\n  version: '0.3.0'\n  name: test\n"
            "reading_room:\n  path: ./library-reading-room\n"
            "vault:\n  path: ./vault\npm:\n  provider: none\n"
        )

        # Pre-create reading room subdirs
        rr = project / "library-reading-room"
        for d in ["specs", "plans", "checkpoints"]:
            (rr / d).mkdir(parents=True)

        # Pre-create vault subdirs
        vault = project / "vault"
        for d in ["domains", "sources", "wiki", "decisions", "sessions",
                   "learning", "archive", "_schema"]:
            (vault / d).mkdir(parents=True)

        # Pre-create runtime dirs
        home = tmp_path / "home"
        base = home / ".library"
        for d in ["sessions", "state", "vault/transcripts", "vault/sessions"]:
            (base / d).mkdir(parents=True)
        (base / "state" / "context_usage.txt").write_text("0")

        # Pre-create SESSION.md
        (base / "sessions" / "SESSION.md").write_text("---\nsession_id: init\n---\n")

        # Pre-create PROJECT-STATE.md
        (rr / "PROJECT-STATE.md").write_text("---\nlibrary_version: '0.3.0'\n---\n")

        # Pre-create routing journal
        (base / "routing.jsonl").touch()

        # Pre-create hook scripts
        hooks_dir = project / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True)
        for s in ["session_start.py", "prompt_scan.py", "stop_capture.py",
                   "pre_compact.py", "session_end.py", "status_line.py"]:
            (hooks_dir / s).write_text("# stub")

        # No CLAUDE.md — triggers skip for domain seeding
        # skip_hooks=True — triggers skip for hook installation

        with patch("library_server.cli.Path.home", return_value=home):
            args = self._make_args(project)
            _cmd_init(args)

        captured = capsys.readouterr()
        assert "[skip] library-config.yaml already exists" in captured.out
        assert "[skip] Reading Room already exists" in captured.out
        assert "[skip] Vault already exists" in captured.out
        assert "[skip] Runtime directories already exist" in captured.out
        assert "[skip] SESSION.md already exists" in captured.out
        assert "[skip] PROJECT-STATE.md already exists" in captured.out
        assert "[skip] No CLAUDE.md found" in captured.out
        assert "[skip] Hook installation skipped" in captured.out
        assert "[skip] Routing journal already exists" in captured.out

    def test_init_with_hooks_enabled(self, tmp_path: Path, capsys):
        """Exercise _install_hooks path within _cmd_init (skip_hooks=False)."""
        project = tmp_path / "project"
        project.mkdir()

        with patch("library_server.cli.Path.home", return_value=tmp_path), \
             patch("library_server.cli._install_hooks", return_value=True):
            args = self._make_args(project, skip_hooks=False)
            _cmd_init(args)

        captured = capsys.readouterr()
        assert "[done] Installed hooks" in captured.out

    def test_init_hooks_already_installed(self, tmp_path: Path, capsys):
        """Exercise skip path when hooks already installed."""
        project = tmp_path / "project"
        project.mkdir()

        with patch("library_server.cli.Path.home", return_value=tmp_path), \
             patch("library_server.cli._install_hooks", return_value=False):
            args = self._make_args(project, skip_hooks=False)
            _cmd_init(args)

        captured = capsys.readouterr()
        assert "[skip] Hooks already installed" in captured.out

    def test_init_domain_seeding_no_match(self, tmp_path: Path, capsys):
        """Exercise domain seeding path when CLAUDE.md exists but no patterns match."""
        project = tmp_path / "project"
        project.mkdir()
        (project / "CLAUDE.md").write_text("nothing relevant here")

        with patch("library_server.cli.Path.home", return_value=tmp_path), \
             patch("library_server.memory.domain_seeder.seed_domains_from_claude_md", return_value=[]):
            args = self._make_args(project)
            _cmd_init(args)

        captured = capsys.readouterr()
        assert "[skip] Domain manifests already exist" in captured.out

    def test_init_hook_scripts_skip(self, tmp_path: Path, capsys):
        """Exercise skip path for hook wrapper scripts."""
        project = tmp_path / "project"
        project.mkdir()

        with patch("library_server.cli.Path.home", return_value=tmp_path), \
             patch("library_server.cli._ensure_hook_scripts", return_value=0):
            args = self._make_args(project)
            _cmd_init(args)

        captured = capsys.readouterr()
        assert "[skip] Hook wrapper scripts already exist" in captured.out


# ---------------------------------------------------------------------------
# _cmd_validate — additional coverage
# ---------------------------------------------------------------------------


class TestCmdValidateAdditional:
    def test_validate_config_warnings(self, tmp_path: Path, capsys):
        """Exercise config validation warnings path."""
        project = tmp_path / "project"
        project.mkdir()
        (project / "library-config.yaml").write_text(
            "library:\n  version: '0.3.0'\n"
        )

        home = tmp_path / "home"
        for d in ["sessions", "state", "vault/transcripts", "vault/sessions"]:
            (home / ".library" / d).mkdir(parents=True)
        (home / ".library" / "sessions" / "SESSION.md").write_text("---\n---\n")

        import os
        orig_cwd = os.getcwd()
        os.chdir(project)
        try:
            with patch("library_server.cli.Path.home", return_value=home), \
                 patch("shutil.which", return_value="/usr/bin/library"), \
                 patch("library_server.cli.validate_config", return_value={"valid": False, "warnings": ["Missing vault path"]}):
                with pytest.raises(SystemExit):
                    _cmd_validate()
        finally:
            os.chdir(orig_cwd)

        captured = capsys.readouterr()
        assert "Config: Missing vault path" in captured.out

    def test_validate_hook_not_registered(self, tmp_path: Path, capsys):
        """Exercise hook not registered and malformed settings paths."""
        project = tmp_path / "project"
        project.mkdir()
        (project / "library-config.yaml").write_text(
            "library:\n  version: '0.3.0'\nvault:\n  path: ./vault\npm:\n  provider: none\n"
        )
        (project / "vault").mkdir()

        # settings.json with only some hooks
        settings_dir = project / ".claude"
        settings_dir.mkdir(parents=True)
        (settings_dir / "settings.json").write_text(json.dumps({
            "hooks": {"SessionStart": []}
        }))
        # No hook scripts dir

        home = tmp_path / "home"
        for d in ["sessions", "state", "vault/transcripts", "vault/sessions"]:
            (home / ".library" / d).mkdir(parents=True)
        (home / ".library" / "sessions" / "SESSION.md").write_text("---\n---\n")

        import os
        orig_cwd = os.getcwd()
        os.chdir(project)
        try:
            with patch("library_server.cli.Path.home", return_value=home), \
                 patch("shutil.which", return_value=None), \
                 pytest.raises(SystemExit):
                _cmd_validate()
        finally:
            os.chdir(orig_cwd)

        captured = capsys.readouterr()
        # Some hooks not registered
        assert "Hook UserPromptSubmit not registered" in captured.out

    def test_validate_malformed_settings(self, tmp_path: Path, capsys):
        """Exercise malformed settings.json path."""
        project = tmp_path / "project"
        project.mkdir()
        (project / "library-config.yaml").write_text(
            "library:\n  version: '0.3.0'\nvault:\n  path: ./vault\npm:\n  provider: none\n"
        )
        (project / "vault").mkdir()

        settings_dir = project / ".claude"
        settings_dir.mkdir(parents=True)
        (settings_dir / "settings.json").write_text("not json {{{")

        home = tmp_path / "home"
        for d in ["sessions", "state", "vault/transcripts", "vault/sessions"]:
            (home / ".library" / d).mkdir(parents=True)
        (home / ".library" / "sessions" / "SESSION.md").write_text("---\n---\n")

        import os
        orig_cwd = os.getcwd()
        os.chdir(project)
        try:
            with patch("library_server.cli.Path.home", return_value=home), \
                 patch("shutil.which", return_value=None), \
                 pytest.raises(SystemExit):
                _cmd_validate()
        finally:
            os.chdir(orig_cwd)

        captured = capsys.readouterr()
        assert "malformed" in captured.out
