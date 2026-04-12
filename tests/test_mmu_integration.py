"""MMU full lifecycle integration test.

Exercises every major MMU hook in sequence against a single tmp_path workspace:
  1. Seed domains from CLAUDE.md
  2. SessionStart build_session_context
  3. UserPromptSubmit process_prompt (keyword match)
  4. Stop process_stop (turns increment, files extracted)
  5. PreCompact process_pre_compact (transcript archived to vault)
  6. SessionEnd process_session_end (SESSION.md archived, session_count++)
  7. Verify routing journal has entries
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from library_server.state.project_state import render_project_state, parse_project_state
from library_server.state.session_state import render_session_state, parse_session_state
from library_server.memory.domain_seeder import seed_domains_from_claude_md
from library_server.hooks.scripts.session_start import build_session_context
from library_server.hooks.scripts.prompt_scan import process_prompt
from library_server.hooks.scripts.stop_capture import process_stop
from library_server.hooks.scripts.session_end import process_session_end
from library_server.hooks.scripts.pre_compact import process_pre_compact
from library_server.hooks.learning import read_journal
from library_server.types import ProjectStateData, SessionStateData


# ---------------------------------------------------------------------------
# Workspace fixture
# ---------------------------------------------------------------------------


def _make_workspace(tmp_path: Path) -> dict[str, Path]:
    """Create a minimal MMU workspace and return a dict of key paths."""
    # reading room
    reading_room = tmp_path / "reading-room"
    reading_room.mkdir(parents=True)

    # vault structure
    vault = tmp_path / "vault"
    for sub in ("domains", "decisions", "sessions", "sources/raw/transcripts"):
        (vault / sub).mkdir(parents=True)

    # sessions dir (runtime)
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()

    # learning dir (for journal)
    learning_dir = tmp_path / "learning"
    learning_dir.mkdir()

    # CLAUDE.md with content that matches seeder patterns
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(
        "# CLAUDE.md\n\n"
        "## Backend\n"
        "PostgreSQL via pg driver. Raw SQL migrations. Auth via Clerk JWT.\n"
        "GraphQL API with Apollo Server. typeDefs and resolvers.\n\n"
        "## Testing\n"
        "Jest unit tests, Playwright e2e tests, integration tests.\n\n"
        "## Infrastructure\n"
        "Terraform, Docker, GCP, GKE, Cloud SQL.\n",
        encoding="utf-8",
    )

    # PROJECT-STATE.md
    project_state_data = ProjectStateData(
        project="SevenBelow Compliance OS",
        focus="MMU lifecycle test",
        active_task="TASK-10 — Integration test",
        blockers=[],
        invariants=["No frontend state machines", "RLS always enforced"],
        session_count=3,
    )
    project_state_file = reading_room / "PROJECT-STATE.md"
    project_state_file.write_text(
        render_project_state(project_state_data), encoding="utf-8"
    )

    # transcript JSONL — tool use + a decision-like message
    transcript = tmp_path / "transcript.jsonl"
    transcript_entries = [
        {
            "type": "tool_use",
            "name": "Read",
            "input": {"file_path": "/project/src/db/migrations/001_init.sql"},
        },
        {
            "type": "tool_use",
            "name": "Edit",
            "input": {"file_path": "/project/src/services/auth.ts"},
        },
        {
            "type": "message",
            "role": "user",
            "content": "Decision: use YAML frontmatter for all state files",
        },
    ]
    transcript.write_text(
        "\n".join(json.dumps(e) for e in transcript_entries), encoding="utf-8"
    )

    # context-usage JSON file
    context_usage_file = tmp_path / "context_usage.json"
    context_usage_file.write_text(
        json.dumps({"context_usage": 0.30}), encoding="utf-8"
    )

    return {
        "reading_room": reading_room,
        "vault": vault,
        "domains_dir": vault / "domains",
        "vault_sessions_dir": vault / "sessions",
        "vault_transcripts_dir": vault / "sources" / "raw" / "transcripts",
        "sessions_dir": sessions_dir,
        "learning_dir": learning_dir,
        "claude_md": claude_md,
        "project_state_file": project_state_file,
        "transcript": transcript,
        "context_usage_file": context_usage_file,
        "journal": learning_dir / "routing.jsonl",
    }


# ---------------------------------------------------------------------------
# Full lifecycle test
# ---------------------------------------------------------------------------


def test_mmu_full_lifecycle(tmp_path: Path) -> None:
    """Exercise all MMU lifecycle steps end-to-end in a single test."""
    ws = _make_workspace(tmp_path)
    session_id = "test-session-001"

    # ------------------------------------------------------------------
    # Step 1: Seed domains from CLAUDE.md
    # ------------------------------------------------------------------
    created_domains = seed_domains_from_claude_md(ws["claude_md"], ws["domains_dir"])

    # The CLAUDE.md mentions postgres/sql (database), clerk/jwt (auth),
    # graphql/apollo (graphql), jest/playwright (testing), terraform/docker (infrastructure)
    assert len(created_domains) >= 1, (
        f"Expected at least 1 domain to be seeded, got: {created_domains}"
    )
    assert ws["domains_dir"].exists()
    domain_files = list(ws["domains_dir"].glob("*.md"))
    assert len(domain_files) >= 1

    # ------------------------------------------------------------------
    # Step 2: SessionStart build_session_context
    # ------------------------------------------------------------------
    context = build_session_context(
        mode="startup",
        reading_room=ws["reading_room"],
        sessions_dir=ws["sessions_dir"],
    )

    assert isinstance(context, str)
    assert "SevenBelow Compliance OS" in context, (
        "Project name should appear in session context"
    )
    assert "TASK-10" in context, "Active task should appear in session context"
    assert len(context) < 4000, (
        f"Context must be under 4000 chars, got {len(context)}"
    )

    # ------------------------------------------------------------------
    # Step 3: UserPromptSubmit process_prompt with matching keyword
    # ------------------------------------------------------------------
    # "postgres" matches the database domain (seeded in step 1 if CLAUDE.md
    # content triggered it; fall back to the first seeded domain's keywords)
    first_domain_name = created_domains[0]
    first_domain_file = ws["domains_dir"] / f"{first_domain_name}.md"
    first_domain_content = first_domain_file.read_text(encoding="utf-8")

    # Extract a keyword from the domain file to guarantee a match
    test_keyword = None
    for line in first_domain_content.splitlines():
        line = line.strip()
        if line.startswith("- ") and not line.startswith("- []"):
            candidate = line[2:].strip()
            if candidate and len(candidate) > 2:
                test_keyword = candidate
                break

    assert test_keyword is not None, "Could not find a keyword in seeded domain file"

    prompt_result = process_prompt(
        prompt=f"How do I configure {test_keyword} correctly?",
        session_id=session_id,
        domains_dir=ws["domains_dir"],
        dedup_dir=ws["sessions_dir"],
        journal_path=ws["journal"],
    )

    assert prompt_result is not None, (
        f"Expected a match for keyword '{test_keyword}' in prompt"
    )
    assert "domain" in prompt_result
    assert prompt_result["domain"] == first_domain_name, (
        f"Expected domain '{first_domain_name}', got '{prompt_result['domain']}'"
    )

    # ------------------------------------------------------------------
    # Step 4: Create SESSION.md, then Stop process_stop
    # ------------------------------------------------------------------
    session_data = SessionStateData(
        session_id=session_id,
        task="TASK-10 — Integration test",
        doing="Running MMU lifecycle",
        branch="feat/mmu-integration",
        resume_instructions=["Continue from lifecycle test"],
        decisions=[],
        files_touched=[],
        domains_loaded=[first_domain_name],
        turns=1,
        context_usage=0.10,
        started="2026-04-11T09:00:00Z",
        last_updated="2026-04-11T09:30:00Z",
    )
    session_file = ws["sessions_dir"] / "SESSION.md"
    session_file.write_text(render_session_state(session_data), encoding="utf-8")

    stop_result = process_stop(
        sessions_dir=ws["sessions_dir"],
        transcript_path=ws["transcript"],
        context_usage_path=ws["context_usage_file"],
        journal_path=ws["journal"],
        warn_pct=50,
        checkpoint_pct=60,
    )

    assert isinstance(stop_result, dict)
    assert "warning" in stop_result

    # Verify SESSION.md was updated (turns incremented)
    updated_session = parse_session_state(session_file)
    assert updated_session.turns == 2, (
        f"Expected turns to be incremented to 2, got {updated_session.turns}"
    )

    # Verify files were extracted from transcript
    assert len(updated_session.files_touched) >= 1, (
        "Expected at least one file to be extracted from transcript"
    )

    # ------------------------------------------------------------------
    # Step 5: PreCompact process_pre_compact
    # ------------------------------------------------------------------
    compact_result = process_pre_compact(
        transcript_path=ws["transcript"],
        vault_transcripts_dir=ws["vault_transcripts_dir"],
        sessions_dir=ws["sessions_dir"],
        session_id=session_id,
    )

    assert compact_result["saved"] is True, "Transcript should be archived to vault"
    archived_transcript = Path(compact_result["archive_path"])
    assert archived_transcript.exists(), (
        f"Archived transcript not found at {archived_transcript}"
    )
    assert archived_transcript.parent == ws["vault_transcripts_dir"]

    # ------------------------------------------------------------------
    # Step 6: SessionEnd process_session_end
    # ------------------------------------------------------------------
    # session_end reads SESSION.md from reading_room, so move a copy there
    session_file_in_reading_room = ws["reading_room"] / "SESSION.md"
    session_file_in_reading_room.write_text(
        render_session_state(updated_session), encoding="utf-8"
    )

    # Read current session_count before
    project_state_before = parse_project_state(ws["project_state_file"])
    session_count_before = project_state_before.session_count

    end_result = process_session_end(
        reading_room=ws["reading_room"],
        sessions_dir=ws["sessions_dir"],
        vault_sessions_dir=ws["vault_sessions_dir"],
        session_id=session_id,
    )

    assert end_result["archived"] is True, "SESSION.md should be archived"
    archived_sessions = list(ws["vault_sessions_dir"].iterdir())
    assert len(archived_sessions) >= 1, "At least one archived session should exist"

    # Verify session_count was incremented in PROJECT-STATE.md
    project_state_after = parse_project_state(ws["project_state_file"])
    assert project_state_after.session_count == session_count_before + 1, (
        f"session_count should increment from {session_count_before} to "
        f"{session_count_before + 1}, got {project_state_after.session_count}"
    )

    # ------------------------------------------------------------------
    # Step 7: Verify routing journal has entries
    # ------------------------------------------------------------------
    journal_entries = read_journal(ws["journal"])

    # At minimum, step 3 should have logged a routing decision
    assert len(journal_entries) >= 1, (
        "Routing journal should have at least one entry from prompt_scan"
    )

    # The first hit entry should record the matched domain
    first_entry = journal_entries[0]
    assert "session_id" in first_entry
    assert "matched_domain" in first_entry
    assert first_entry["matched_domain"] == first_domain_name
    assert first_entry["match_type"] == "first_hit"
