"""Tests for project_state.py — TDD first pass."""

from __future__ import annotations

from pathlib import Path

import pytest

from library_server.state.project_state import (
    render_project_state,
    parse_project_state,
    update_project_state_field,
)
from library_server.types import ProjectStateData


@pytest.fixture
def minimal_data() -> ProjectStateData:
    return ProjectStateData(project="compliance-os")


@pytest.fixture
def full_data() -> ProjectStateData:
    return ProjectStateData(
        project="compliance-os",
        focus="MMU implementation",
        active_task="CLO-42 — Build state file management",
        blockers=["Waiting on spec approval"],
        invariants=["No frontend state machines", "RLS on all tenant tables"],
        pm_projects=[
            {"key": "CLO", "name": "Compliance OS", "open": 5, "blocked": 1},
            {"key": "COS", "name": "Core Services", "open": 3, "blocked": 0},
        ],
        recent_decisions=[
            {"id": "D-01", "decision": "Use YAML frontmatter for state files"},
            {"id": "D-02", "decision": "Markdown rendering stays under 100 lines"},
        ],
        session_count=12,
        vault_file_count=3220,
        domain_count=8,
        decision_count=42,
        claude_md_lines=180,
        keyword_accuracy=0.87,
        keyword_observations=150,
    )


# ── Render tests ──────────────────────────────────────────────────────────────


def test_render_contains_project_name(minimal_data: ProjectStateData):
    output = render_project_state(minimal_data)
    assert "compliance-os" in output


def test_render_contains_active_section(full_data: ProjectStateData):
    output = render_project_state(full_data)
    assert "Active" in output
    assert "MMU implementation" in output
    assert "CLO-42" in output


def test_render_contains_invariants(full_data: ProjectStateData):
    output = render_project_state(full_data)
    assert "Invariants" in output
    assert "No frontend state machines" in output
    assert "RLS on all tenant tables" in output


def test_render_contains_pm_projects_when_non_empty(full_data: ProjectStateData):
    output = render_project_state(full_data)
    assert "PM Projects" in output
    assert "CLO" in output
    assert "COS" in output


def test_render_omits_pm_projects_when_empty(minimal_data: ProjectStateData):
    output = render_project_state(minimal_data)
    assert "PM Projects" not in output


def test_render_contains_recent_decisions(full_data: ProjectStateData):
    output = render_project_state(full_data)
    assert "Recent Decisions" in output
    assert "D-01" in output
    assert "YAML frontmatter" in output


def test_render_contains_library_health(full_data: ProjectStateData):
    output = render_project_state(full_data)
    assert "Library Health" in output
    assert "3220" in output
    assert "0.87" in output


def test_render_contains_yaml_frontmatter(full_data: ProjectStateData):
    output = render_project_state(full_data)
    # Should start with --- YAML frontmatter
    assert output.startswith("---")
    assert "library_version" in output
    assert "session_count: 12" in output


def test_render_stays_under_100_lines(full_data: ProjectStateData):
    output = render_project_state(full_data)
    line_count = len(output.splitlines())
    assert line_count <= 100, f"Rendered output is {line_count} lines (max 100)"


def test_render_contains_blockers(full_data: ProjectStateData):
    output = render_project_state(full_data)
    assert "Waiting on spec approval" in output


# ── Parse tests ───────────────────────────────────────────────────────────────


def test_parse_roundtrip(tmp_path: Path, full_data: ProjectStateData):
    """render → write → parse should recover all fields."""
    state_file = tmp_path / "PROJECT-STATE.md"
    state_file.write_text(render_project_state(full_data), encoding="utf-8")

    parsed = parse_project_state(state_file)

    assert parsed.project == full_data.project
    assert parsed.focus == full_data.focus
    assert parsed.active_task == full_data.active_task
    assert parsed.session_count == full_data.session_count
    assert parsed.vault_file_count == full_data.vault_file_count
    assert parsed.domain_count == full_data.domain_count
    assert parsed.decision_count == full_data.decision_count
    assert parsed.claude_md_lines == full_data.claude_md_lines
    assert abs(parsed.keyword_accuracy - full_data.keyword_accuracy) < 0.001
    assert parsed.keyword_observations == full_data.keyword_observations
    assert "No frontend state machines" in parsed.invariants
    assert "RLS on all tenant tables" in parsed.invariants


def test_parse_roundtrip_minimal(tmp_path: Path, minimal_data: ProjectStateData):
    """Minimal data roundtrip should not error."""
    state_file = tmp_path / "PROJECT-STATE.md"
    state_file.write_text(render_project_state(minimal_data), encoding="utf-8")

    parsed = parse_project_state(state_file)
    assert parsed.project == "compliance-os"
    assert parsed.pm_projects == []
    assert parsed.blockers == []


# ── update_field tests ────────────────────────────────────────────────────────


def test_update_project_state_field_scalar(tmp_path: Path, minimal_data: ProjectStateData):
    """update_project_state_field should update a scalar field and re-render."""
    state_file = tmp_path / "PROJECT-STATE.md"
    state_file.write_text(render_project_state(minimal_data), encoding="utf-8")

    update_project_state_field(state_file, "focus", "New focus area")

    parsed = parse_project_state(state_file)
    assert parsed.focus == "New focus area"


def test_update_project_state_field_integer(tmp_path: Path, minimal_data: ProjectStateData):
    state_file = tmp_path / "PROJECT-STATE.md"
    state_file.write_text(render_project_state(minimal_data), encoding="utf-8")

    update_project_state_field(state_file, "session_count", 99)

    parsed = parse_project_state(state_file)
    assert parsed.session_count == 99


def test_update_project_state_field_list(tmp_path: Path, minimal_data: ProjectStateData):
    state_file = tmp_path / "PROJECT-STATE.md"
    state_file.write_text(render_project_state(minimal_data), encoding="utf-8")

    update_project_state_field(state_file, "blockers", ["Blocker A", "Blocker B"])

    parsed = parse_project_state(state_file)
    assert "Blocker A" in parsed.blockers
    assert "Blocker B" in parsed.blockers
