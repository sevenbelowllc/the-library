# v0.3.2 Stabilization & Reconnect Pass — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the seven confirmed bugs, make every documented vault-builder config key honest, reconnect built-but-unwired code, and ship as v0.3.2.

**Architecture:** Three tracks executed in order: bug fixes (Tasks 1–8, independent of each other), reconnects (Tasks 9–15, some touch the same files as the bug fixes), release hygiene last (Tasks 16–17, docs/versions describe the final state). Task 18 is final verification.

**Tech Stack:** Python 3.10–3.12, pytest (+pytest-asyncio for `async def` tests), httpx, FastMCP, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-08-02-stabilization-0.3.2-design.md`

## Global Constraints

- Work on branch `chore/stabilization-0.3.2` (already created; spec + leaked-file removal already committed on it).
- Every module starts with `from __future__ import annotations`.
- MCP tool names use underscores (`library_pm_autodetect_workflow`), registered in `src/library_server/server.py` with **lazy local imports** inside the tool function.
- No hardcoded paths outside the `~/.library/` convention.
- Async adapter/extractor tests need `@pytest.mark.asyncio` (already configured in the repo — copy the idiom from neighboring tests in the same file).
- Test commands: `pytest tests/<file>.py::<test> -v` for single tests. Full-suite gate is Task 18 (`pytest --ignore=tests/test_jira_integration.py`, `bin/library-coverage-ratchet`, `ruff check .`, `mypy`).
- Commit after every task, message style `fix:`/`feat:`/`docs:`/`chore:` as shown per task, each ending with:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- Do NOT touch `src/library_server/vault_builder/extractors/axon_bridge.py` or the `axon:` config block — they are retired wholesale by the next push (see `docs/superpowers/specs/2026-08-02-graphify-code-extractor-design.md`).

---

### Task 1: Fix init data-loss — CLI templates must round-trip through the state parsers

**Files:**
- Modify: `src/library_server/cli.py:526-576` (`_create_session_md`, `_create_project_state`)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `render_session_state(SessionStateData)` from `src/library_server/state/session_state.py:12`, `render_project_state(ProjectStateData)` from `src/library_server/state/project_state.py:14`, dataclasses from `src/library_server/types.py`.
- Produces: `_create_session_md(path)` / `_create_project_state(path, project_name)` unchanged signatures — but output now parses losslessly.

**Background:** The current templates emit `- task: ...` bullets, but `parse_session_state` matches `**Task:** ...` bold fields (`session_state.py:98-100`) and `parse_project_state` matches `**Project:**` etc. (`project_state.py:115-117`). The first `session_end` round-trips PROJECT-STATE.md through parse→render and blanks the user's project/focus/task. Fix: stop hand-writing markdown — build the dataclass and call the canonical renderer, which guarantees round-trip by construction.

- [ ] **Step 1: Write the failing round-trip test**

Append to `tests/test_cli.py`:

```python
class TestBootstrapStateRoundTrip:
    """CLI-generated state files must survive parse -> render without data loss.

    Regression: pre-0.3.2 templates used '- task:' bullets that the bold-field
    parsers could not read, so the first session_end blanked project/focus/task.
    """

    def test_session_md_round_trips(self, tmp_path):
        from library_server.cli import _create_session_md
        from library_server.state.session_state import parse_session_state

        path = tmp_path / "SESSION.md"
        _create_session_md(path)
        data = parse_session_state(path)
        assert data.task == "Initial setup"
        assert data.doing == "Library initialization"
        assert data.branch == "main"
        assert data.session_id == "init"
        assert data.resume_instructions  # non-empty

    def test_project_state_round_trips(self, tmp_path):
        from library_server.cli import _create_project_state
        from library_server.state.project_state import parse_project_state

        path = tmp_path / "PROJECT-STATE.md"
        _create_project_state(path, "my-project")
        data = parse_project_state(path)
        assert data.project == "my-project"
        assert data.focus == "Initial setup"
        assert data.active_task != ""
        assert data.session_count == 0

    def test_project_state_survives_session_count_update(self, tmp_path):
        """The exact data-loss scenario: session_end's field update must not blank fields."""
        from library_server.cli import _create_project_state
        from library_server.state.project_state import (
            parse_project_state,
            update_project_state_field,
        )

        path = tmp_path / "PROJECT-STATE.md"
        _create_project_state(path, "my-project")
        update_project_state_field(path, "session_count", 1)
        data = parse_project_state(path)
        assert data.project == "my-project"
        assert data.session_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py::TestBootstrapStateRoundTrip -v`
Expected: FAIL — `data.task == "Initial setup"` assertion fails (parser returns `""`).

- [ ] **Step 3: Rewrite the two template functions to use the canonical renderers**

Replace the bodies of `_create_session_md` and `_create_project_state` in `src/library_server/cli.py` (keep signatures):

```python
def _create_session_md(path: Path) -> None:
    """Create a fresh SESSION.md via the canonical renderer (round-trip safe)."""
    from library_server.state.session_state import render_session_state
    from library_server.types import SessionStateData

    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = SessionStateData(
        session_id="init",
        task="Initial setup",
        doing="Library initialization",
        branch="main",
        resume_instructions=[
            "Fresh session — The Library has been initialized. "
            "Run library:config for interactive setup."
        ],
        started=now,
        last_updated=now,
    )
    path.write_text(render_session_state(data), encoding="utf-8")


def _create_project_state(path: Path, project_name: str) -> None:
    """Create a starter PROJECT-STATE.md via the canonical renderer (round-trip safe)."""
    from library_server.state.project_state import render_project_state
    from library_server.types import ProjectStateData

    path.parent.mkdir(parents=True, exist_ok=True)
    data = ProjectStateData(
        project=project_name,
        focus="Initial setup",
        active_task="Run library:config for interactive configuration",
    )
    path.write_text(render_project_state(data), encoding="utf-8")
```

Note: if `SessionStateData`/`ProjectStateData` require positional args beyond these (check `src/library_server/types.py` — both dataclasses default everything else), pass only the fields shown; defaults cover the rest.

- [ ] **Step 4: Run the new tests and the existing CLI suite**

Run: `pytest tests/test_cli.py -v`
Expected: PASS. If an existing test asserted the *old* template text (e.g. substring `- task:`), update that assertion to the new bold-field format (`**Task:** Initial setup`) — the old format is the bug.

- [ ] **Step 5: Commit**

```bash
git add src/library_server/cli.py tests/test_cli.py
git commit -m "fix(cli): bootstrap SESSION.md/PROJECT-STATE.md via canonical renderers

The hand-written templates used '- task:' bullets the state parsers cannot
read, so the first session_end round-trip blanked project/focus/task.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Fix routing-journal path mismatch — one shared helper, server reads what hooks write

**Files:**
- Modify: `src/library_server/hooks/config_loader.py` (add helper)
- Modify: `src/library_server/server.py:448-449,474-475` (`library_memory_health`, `library_memory_learn`)
- Modify: `src/library_server/cli.py:405` (`_cmd_doctor` journal fix) and `cli.py` init's journal-touch step (search for `routing.jsonl` in `_cmd_init`)
- Test: `tests/test_server.py`, `tests/test_hooks/test_config_loader.py` (create class if the file lacks one)

**Interfaces:**
- Produces: `routing_journal_path() -> Path` in `library_server.hooks.config_loader` returning `Path("~/.library/routing.jsonl").expanduser()`. All non-hook-wrapper code referencing the journal path MUST call this.
- Consumes: nothing new.

**Background:** Hooks write `~/.library/routing.jsonl` (the generated wrappers default `journal_path` to exactly that — `cli.py:627,635`), but `server.py` computes `~/.library/learning/routing-journal.jsonl` from `memory.session_dir` — a file nothing ever writes, so `library_memory_health`/`library_memory_learn` are permanently empty. The existing `tests/test_server.py` learning tests (around lines 423-437) write directly to the wrong path, masking the bug.

- [ ] **Step 1: Write the failing test**

In `tests/test_hooks/test_config_loader.py` add:

```python
class TestRoutingJournalPath:
    def test_matches_hook_wrapper_default(self, monkeypatch, tmp_path):
        """server-side readers must read the exact file the hook wrappers write."""
        from pathlib import Path
        from library_server.hooks.config_loader import routing_journal_path

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert routing_journal_path() == tmp_path / ".library" / "routing.jsonl"
```

In `tests/test_server.py`, find the existing `library_memory_health`/`library_memory_learn` tests that create `learning/routing-journal.jsonl` under a fake session dir, and add this new test alongside them:

```python
def test_memory_learn_reads_hook_journal_path(monkeypatch, tmp_path):
    """Regression: server must read ~/.library/routing.jsonl (what hooks write),
    not ~/.library/learning/routing-journal.jsonl (which nothing writes)."""
    import json
    from pathlib import Path
    from library_server.server import library_memory_learn

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.chdir(tmp_path)  # no library-config.yaml -> defaults
    journal = tmp_path / ".library" / "routing.jsonl"
    journal.parent.mkdir(parents=True)
    entry = {
        "ts": "2026-08-02T00:00:00Z", "session_id": "s1", "prompt_keywords": ["auth"],
        "matched_domain": "auth", "action": "injected", "outcome": "hit",
        "outcome_signal": "test",
    }
    journal.write_text("\n".join([json.dumps(entry)] * 12) + "\n")

    result = library_memory_learn()
    assert result["status"] == "analyzed"
```

Note: match the journal-entry dict shape to whatever the existing passing tests in `tests/test_server.py` use (copy their entry template verbatim — field names must match what `analyze_routing_accuracy` reads in `src/library_server/hooks/learning.py:118-174`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_hooks/test_config_loader.py::TestRoutingJournalPath tests/test_server.py::test_memory_learn_reads_hook_journal_path -v`
Expected: FAIL — `routing_journal_path` does not exist; learn test returns `{"status": "no_data", ...}`.

- [ ] **Step 3: Add the helper and rewire all readers**

Append to `src/library_server/hooks/config_loader.py`:

```python
def routing_journal_path() -> Path:
    """Canonical routing-journal location.

    Must stay in lockstep with the hook wrappers generated by
    ``cli._ensure_hook_scripts`` (prompt_scan/stop_capture default
    ``journal_path`` to ``~/.library/routing.jsonl``). Every non-hook reader
    or writer of the journal must use this helper instead of building the
    path itself — the 0.3.1-era divergence made the learning tools read a
    file nothing wrote.
    """
    return Path("~/.library/routing.jsonl").expanduser()
```

In `src/library_server/server.py`, inside `library_memory_health` replace:

```python
    learning_dir = Path(config.get("memory", {}).get("session_dir", "~/.library/sessions")).expanduser().parent / "learning"
    journal_path = learning_dir / "routing-journal.jsonl"
```

with:

```python
    from library_server.hooks.config_loader import routing_journal_path
    journal_path = routing_journal_path()
```

Make the identical replacement inside `library_memory_learn` (it has its own copy of the two lines; `load_hook_config` is already imported there — add `routing_journal_path` to that import instead of a second import line).

In `src/library_server/cli.py`, `_cmd_doctor` (line 405) and the `_cmd_init` journal-touch step: replace `Path.home() / ".library" / "routing.jsonl"` with `routing_journal_path()` (import at top of function: `from library_server.hooks.config_loader import routing_journal_path`).

- [ ] **Step 4: Fix the masking tests and run**

In `tests/test_server.py`, rewrite the existing health/learn tests that build `.../learning/routing-journal.jsonl`: point them at `~/.library/routing.jsonl` via the same `monkeypatch.setattr(Path, "home", lambda: tmp_path)` pattern.

Run: `pytest tests/test_server.py tests/test_hooks/test_config_loader.py tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/library_server/hooks/config_loader.py src/library_server/server.py src/library_server/cli.py tests/
git commit -m "fix(mmu): memory health/learn read the journal the hooks actually write

Adds routing_journal_path() as the single source of truth. Previously
server.py derived ~/.library/learning/routing-journal.jsonl while hooks
wrote ~/.library/routing.jsonl, so learning tools were permanently empty.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Redact transcript archival in pre_compact

**Files:**
- Modify: `src/library_server/hooks/scripts/pre_compact.py:52` (`process_pre_compact`)
- Test: `tests/test_hooks_scripts/test_pre_compact.py` (add to it; if it does not exist, create it with this class only)

**Interfaces:**
- Consumes: `redact(text: str) -> str` from `library_server.redaction` (`redaction.py:74`).
- Produces: `process_pre_compact` signature unchanged; archived file content is now redacted line-by-line.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the PreCompact hook script."""
from __future__ import annotations

import json
from pathlib import Path

from library_server.hooks.scripts.pre_compact import process_pre_compact


class TestPreCompactRedaction:
    def test_archived_transcript_is_redacted(self, tmp_path):
        transcript = tmp_path / "transcript.jsonl"
        # Assembled at runtime so no secret-shaped literal exists in the repo
        # (gitleaks pre-commit); redact() still sees a real-shaped token.
        secret = "ATATT3" + "xFfGF0" + "a" * 20
        transcript.write_text(
            json.dumps({"role": "user", "content": f"my token is {secret}"}) + "\n"
            + json.dumps({"role": "assistant", "content": "ok"}) + "\n"
        )
        dest_dir = tmp_path / "vault" / "transcripts"

        result = process_pre_compact(
            transcript_path=transcript,
            vault_transcripts_dir=dest_dir,
            sessions_dir=tmp_path,
            session_id="s1",
        )

        assert result["saved"] is True
        archived = Path(result["archive_path"]).read_text()
        assert secret not in archived
        assert "[REDACTED]" in archived
        # Structure preserved: still one JSON object per line
        lines = [ln for ln in archived.splitlines() if ln.strip()]
        assert len(lines) == 2
        json.loads(lines[0])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_hooks_scripts/test_pre_compact.py::TestPreCompactRedaction -v`
Expected: FAIL — `secret not in archived` fails (raw `shutil.copy2`).

- [ ] **Step 3: Replace the copy with a redacting line-by-line write**

In `src/library_server/hooks/scripts/pre_compact.py`, add `from library_server.redaction import redact` to the imports, delete the `import shutil` line (no longer used), and replace `shutil.copy2(transcript_path, dest)` with:

```python
    # Redact line-by-line: transcripts may contain pasted secrets, and the
    # vault is a long-lived, ingested store. redact() preserves line structure
    # (JSONL stays one object per line) since patterns never match newlines.
    with open(transcript_path, encoding="utf-8", errors="replace") as src, \
            open(dest, "w", encoding="utf-8") as out:
        for line in src:
            out.write(redact(line))
```

- [ ] **Step 4: Run the script's full test file**

Run: `pytest tests/test_hooks_scripts/test_pre_compact.py -v`
Expected: PASS (existing tests assert `saved`/`archive_path` behavior, which is unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/library_server/hooks/scripts/pre_compact.py tests/test_hooks_scripts/test_pre_compact.py
git commit -m "fix(hooks): redact transcript content when archiving in pre_compact

Raw shutil.copy2 bypassed the write-time redaction chokepoint, landing
pasted secrets verbatim in the vault.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Redact SESSION.md archival and exception logging in session_end

**Files:**
- Modify: `src/library_server/hooks/scripts/session_end.py:67,78`
- Test: `tests/test_hooks_scripts/test_session_end.py` (add; create the file with this class if absent)

**Interfaces:**
- Consumes: `redact`, `redact_exception` from `library_server.redaction`.
- Produces: `process_session_end` signature unchanged.

- [ ] **Step 1: Write the failing test**

```python
class TestSessionEndRedaction:
    def test_archived_session_md_is_redacted(self, tmp_path):
        from library_server.hooks.scripts.session_end import process_session_end

        reading_room = tmp_path / "rr"
        reading_room.mkdir()
        # Assembled at runtime — see Task 3's note on gitleaks-safe fixtures.
        secret = "ATATT3" + "xFfGF0" + "a" * 20
        (reading_room / "SESSION.md").write_text(
            "---\nsession_id: s1\nstarted: 2026-08-02T00:00:00Z\n---\n\n"
            "## Current\n\n"
            f"**Task:** debug auth with token {secret}\n"
            "**Doing:** \n**Branch:** main\n"
        )
        dest_dir = tmp_path / "vault" / "sessions"

        result = process_session_end(
            reading_room=reading_room,
            sessions_dir=tmp_path,
            vault_sessions_dir=dest_dir,
            session_id="s1",
        )

        assert result["archived"] is True
        archived_files = list(dest_dir.glob("*-s1-session.md"))
        assert len(archived_files) == 1
        content = archived_files[0].read_text()
        assert secret not in content
        assert "[REDACTED]" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_hooks_scripts/test_session_end.py::TestSessionEndRedaction -v`
Expected: FAIL — secret survives the raw copy.

- [ ] **Step 3: Redact on archive; redact the stderr path**

In `src/library_server/hooks/scripts/session_end.py`:

1. Imports: add `from library_server.redaction import redact, redact_exception`; delete `import shutil` (no longer used).
2. Replace `shutil.copy2(session_file, dest)` (line 67) with:

```python
    dest.write_text(
        redact(session_file.read_text(encoding="utf-8", errors="replace")),
        encoding="utf-8",
    )
```

3. Replace the except-clause print (line 78) with:

```python
        except Exception as exc:
            print(
                f"[library] session_end: failed to update PROJECT-STATE.md: {redact_exception(exc)}",
                file=sys.stderr,
            )
```

- [ ] **Step 4: Run the file's full test suite**

Run: `pytest tests/test_hooks_scripts/test_session_end.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/library_server/hooks/scripts/session_end.py tests/test_hooks_scripts/test_session_end.py
git commit -m "fix(hooks): redact SESSION.md archival and exception text in session_end

Matches stop_capture's redact_exception pattern and closes the second
raw-copy bypass of the redaction chokepoint.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Linear adapter must not silently drop status changes

**Files:**
- Modify: `src/library_server/pm/linear.py:130-163` (`update_task`)
- Test: `tests/test_pm_adapter.py`

**Interfaces:**
- Consumes: `TransitionNotAvailableError(task_id, requested_status, current_status, available_transitions)` from `library_server.pm.adapter:17-48`.
- Produces: `LinearAdapter.update_task(task_id, status=...)` now raises `TransitionNotAvailableError`; comment-only calls behave exactly as before.

- [ ] **Step 1: Write the failing test**

Add to the Linear test class in `tests/test_pm_adapter.py` (match the file's existing mock idiom — Linear tests patch `adapter._graphql` with an `AsyncMock`; copy the setup from `test_update_task_with_comment`):

```python
    @pytest.mark.asyncio
    async def test_update_task_with_status_raises_transition_error(self):
        """Regression: status= was silently ignored — the exact no-op bug class
        TransitionNotAvailableError exists to prevent."""
        from library_server.pm.adapter import TransitionNotAvailableError

        adapter = self._make_adapter()  # use this file's existing Linear fixture/helper
        adapter._graphql = AsyncMock(return_value={
            "data": {"issue": {
                "id": "x", "identifier": "ENG-1", "title": "t",
                "state": {"name": "Todo"}, "url": "",
            }}
        })

        with pytest.raises(TransitionNotAvailableError) as exc_info:
            await adapter.update_task("ENG-1", status="Done")

        assert exc_info.value.task_id == "ENG-1"
        assert exc_info.value.requested_status == "Done"
        assert exc_info.value.current_status == "Todo"
        assert exc_info.value.available_transitions == []

    @pytest.mark.asyncio
    async def test_update_task_status_error_precedes_comment(self):
        """When both status and comment are passed, no comment is posted before raising."""
        from library_server.pm.adapter import TransitionNotAvailableError

        adapter = self._make_adapter()
        calls: list[str] = []

        async def fake_graphql(query, variables=None):
            calls.append(query)
            return {"data": {"issue": {
                "id": "x", "identifier": "ENG-1", "title": "t",
                "state": {"name": "Todo"}, "url": "",
            }}}

        adapter._graphql = fake_graphql
        with pytest.raises(TransitionNotAvailableError):
            await adapter.update_task("ENG-1", status="Done", comment="hello")
        assert not any("commentCreate" in q for q in calls)
```

(If the Linear test class constructs adapters inline rather than via a helper, replicate that construction — the assertion bodies stay identical.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pm_adapter.py -k "transition_error or precedes_comment" -v`
Expected: FAIL — no exception raised (status silently dropped).

- [ ] **Step 3: Implement the guard at the top of `LinearAdapter.update_task`**

In `src/library_server/pm/linear.py`, change the import at line 12 to `from library_server.pm.adapter import PMAdapter, TransitionNotAvailableError`, then insert at the top of `update_task` (before the `if comment:` block):

```python
        if status is not None:
            # Status transitions are not implemented for Linear yet (needs a
            # workflowState id lookup + issueUpdate mutation). Raising keeps the
            # documented invariant: an unhonored status change must never be a
            # silent no-op (2026-04-17 audit failure class).
            current_status = ""
            try:
                current = await self._graphql(
                    """
                    query($id: String!) {
                        issue(id: $id) {
                            id identifier title state { name } url
                        }
                    }
                    """,
                    {"id": task_id},
                )
                current_status = current["data"]["issue"]["state"]["name"]
            except Exception:
                pass
            raise TransitionNotAvailableError(
                task_id=task_id,
                requested_status=status,
                current_status=current_status,
                available_transitions=[],
            )
```

- [ ] **Step 4: Run the PM adapter suite**

Run: `pytest tests/test_pm_adapter.py -v`
Expected: PASS — including the pre-existing `test_update_task_with_comment`/`test_update_task_no_comment` (they never pass `status`).

- [ ] **Step 5: Commit**

```bash
git add src/library_server/pm/linear.py tests/test_pm_adapter.py
git commit -m "fix(pm): Linear update_task raises TransitionNotAvailableError on status

Previously status= was silently ignored — the exact silent no-op class the
error type exists to prevent. Real Linear transitions remain future work.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Shared ADF→text helper; Jira extractor stops dumping ADF dicts

**Files:**
- Create: `src/library_server/pm/adf.py`
- Modify: `src/library_server/pm/jira.py:323-339` (move `_adf_to_text` out, import instead)
- Modify: `src/library_server/vault_builder/extractors/jira.py:117,144`
- Test: `tests/vault_builder/extractors/test_jira.py`, `tests/pm/test_adf.py` (create)

**Interfaces:**
- Produces: `adf_to_text(node: dict | str | None) -> str` in `library_server.pm.adf` — exact behavior of the current `jira.py:_adf_to_text` (text nodes concatenated; paragraph/heading nodes append `\n`; str passes through; None/non-dict → `""`).
- Consumes: nothing new.

- [ ] **Step 1: Write the failing tests**

Create `tests/pm/test_adf.py`:

```python
"""Tests for the shared ADF -> plain text helper."""
from __future__ import annotations

from library_server.pm.adf import adf_to_text


ADF_DOC = {
    "type": "doc", "version": 1,
    "content": [
        {"type": "heading", "attrs": {"level": 1},
         "content": [{"type": "text", "text": "Title"}]},
        {"type": "paragraph",
         "content": [
             {"type": "text", "text": "Hello "},
             {"type": "text", "text": "world", "marks": [{"type": "strong"}]},
         ]},
    ],
}


def test_flattens_document():
    assert adf_to_text(ADF_DOC) == "Title\nHello world\n"


def test_passes_through_plain_string():
    assert adf_to_text("already text") == "already text"


def test_none_and_non_dict_return_empty():
    assert adf_to_text(None) == ""
    assert adf_to_text(42) == ""
```

Add to `tests/vault_builder/extractors/test_jira.py` (inside the existing test class, reusing that file's existing mocked-issue fixture pattern — the existing tests build issue dicts with plain-string descriptions and mock `_fetch_issues`; copy that setup):

```python
    @pytest.mark.asyncio
    async def test_extract_renders_adf_description_as_text(self, tmp_path):
        """Regression: ADF dict descriptions were str()-dumped as Python reprs."""
        issue = {
            "key": "PROJ-1",
            "fields": {
                "summary": "ADF issue",
                "description": {
                    "type": "doc", "version": 1,
                    "content": [{"type": "paragraph",
                                 "content": [{"type": "text", "text": "Rich body"}]}],
                },
                "issuetype": {"name": "Task"},
                "status": {"name": "Done"},
                "assignee": None,
                "labels": [],
            },
        }
        extractor = self._make_extractor()  # this file's existing construction helper/idiom
        extractor._fetch_issues = AsyncMock(return_value=[issue])

        result = await extractor.extract(tmp_path / "jira")

        assert result.success
        written = (tmp_path / "jira" / "PROJ" / "PROJ-1.md").read_text()
        assert "Rich body" in written
        assert "'type': 'doc'" not in written  # no Python-repr blob
```

(Adjust the written-file path assertion to match how the existing tests in that file locate output — they configure `projects: ["PROJ"]` on the extractor config and files land under `<output_dir>/<project>/<key>.md`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/pm/test_adf.py tests/vault_builder/extractors/test_jira.py -v`
Expected: `test_adf.py` FAILS with ImportError (module doesn't exist); the extractor test FAILS on `'type': 'doc'` appearing in output.

- [ ] **Step 3: Create the module and rewire both consumers**

Create `src/library_server/pm/adf.py` — move the function body verbatim from `jira.py:323-339`, renamed:

```python
"""Atlassian Document Format helpers shared by the PM adapter and extractors."""

from __future__ import annotations


def adf_to_text(node: dict | str | None) -> str:
    """Flatten Atlassian Document Format to plain text. Tolerates str input."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return node.get("text", "")
    parts: list[str] = []
    for child in node.get("content", []) or []:
        parts.append(adf_to_text(child))
    text = "".join(parts)
    if node.get("type") in ("paragraph", "heading"):
        return text + "\n"
    return text
```

In `src/library_server/pm/jira.py`: delete the `_adf_to_text` function (lines 323-339) and add near the other imports:

```python
from library_server.pm.adf import adf_to_text as _adf_to_text
```

(The alias keeps every internal call site and any test referencing `jira._adf_to_text` working unchanged.)

In `src/library_server/vault_builder/extractors/jira.py`: add `from library_server.pm.adf import adf_to_text` to the imports, then replace line 117:

```python
                        description = fields.get("description") or "No description."
```

with:

```python
                        raw_description = fields.get("description")
                        if isinstance(raw_description, dict):
                            description = adf_to_text(raw_description).rstrip("\n") or "No description."
                        else:
                            description = raw_description or "No description."
```

Also fix the comment bodies loop (line 150) the same way — Jira v3 comment bodies are ADF too:

```python
                            for c in comments:
                                body_parts.append(f"- {adf_to_text(c.get('body', '')).rstrip(chr(10))}")
```

- [ ] **Step 4: Run all touched suites**

Run: `pytest tests/pm/ tests/test_pm_adapter.py tests/vault_builder/extractors/test_jira.py -v`
Expected: PASS (adapter tests still pass because of the `_adf_to_text` alias).

- [ ] **Step 5: Commit**

```bash
git add src/library_server/pm/adf.py src/library_server/pm/jira.py src/library_server/vault_builder/extractors/jira.py tests/
git commit -m "fix(vault-builder): render Jira ADF descriptions/comments as text

Extracts the adapter's ADF flattener into pm/adf.py and uses it in the
Jira extractor, which previously str()-dumped ADF dicts as Python reprs.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Safety gate for `library_vault_builder_extract`

**Files:**
- Modify: `src/library_server/server.py:568-582`
- Test: `tests/test_server.py`

**Interfaces:**
- Produces: `library_vault_builder_extract(extractor: str, dry_run: bool = False, force: bool = False)` — same return shapes, plus the `{"status": "blocked", "message": ...}` shape `library_vault_builder_build` already uses.
- Consumes: `detect_vault_state`, `check_safety_gate` from `library_server.vault_builder.orchestrator:16,35`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_server.py`, following the file's existing pattern for vault-builder tool tests (they patch `library_server.server._get_vault_orchestrator`):

```python
@pytest.mark.asyncio
async def test_vault_builder_extract_blocked_by_safety_gate(monkeypatch, tmp_path):
    """Single-extractor builds must respect the same gate as full builds."""
    from library_server.server import library_vault_builder_extract

    # An existing non-vault directory + create mode => gate blocks
    (tmp_path / "somefile.txt").write_text("existing content")

    orch = MagicMock()
    orch.output_vault = tmp_path
    orch.mode = "create"
    orch.build = AsyncMock()
    monkeypatch.setattr("library_server.server._get_vault_orchestrator", lambda: orch)

    result = await library_vault_builder_extract("specs")

    assert result["status"] == "blocked"
    orch.build.assert_not_called()


@pytest.mark.asyncio
async def test_vault_builder_extract_force_overrides_gate(monkeypatch, tmp_path):
    from library_server.server import library_vault_builder_extract

    (tmp_path / "somefile.txt").write_text("existing content")

    orch = MagicMock()
    orch.output_vault = tmp_path
    orch.mode = "create"
    build_result = MagicMock(status="completed", extract_results=[])
    orch.build = AsyncMock(return_value=build_result)
    monkeypatch.setattr("library_server.server._get_vault_orchestrator", lambda: orch)

    result = await library_vault_builder_extract("specs", force=True)

    assert result["status"] == "completed"
    orch.build.assert_awaited_once_with(["specs"], True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py -k "safety_gate or overrides_gate" -v`
Expected: FAIL — first test gets a build result, not `blocked`; second fails on the awaited-args assertion.

- [ ] **Step 3: Implement — mirror the gate block from `library_vault_builder_build`**

Replace the body of `library_vault_builder_extract` in `src/library_server/server.py`:

```python
@mcp.tool(name="library_vault_builder_extract")
async def library_vault_builder_extract(extractor: str, dry_run: bool = False, force: bool = False) -> dict:
    """Run a single extractor by name. Set dry_run=True for preview only.

    Applies the same create-mode safety gate as library_vault_builder_build;
    pass force=True to overwrite an existing vault.
    """
    orch = _get_vault_orchestrator()
    if dry_run:
        previews = await orch.preview([extractor])
        return {"mode": "preview", "sources": previews}

    if orch.output_vault:
        from library_server.vault_builder.orchestrator import detect_vault_state, check_safety_gate
        vault_state = detect_vault_state(orch.output_vault)
        gate = check_safety_gate(orch.mode, vault_state, force)
        if gate["blocked"]:
            return {"status": "blocked", "message": gate["message"]}

    result = await orch.build([extractor], force)
    return {
        "status": result.status,
        "extract_results": [
            {"source": r.source_name, "success": r.success, "files": len(r.files_written), "errors": r.errors}
            for r in result.extract_results
        ],
    }
```

- [ ] **Step 4: Run the server suite**

Run: `pytest tests/test_server.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/library_server/server.py tests/test_server.py
git commit -m "fix(vault-builder): single-extractor tool respects the create-mode safety gate

library_vault_builder_extract could silently overwrite an existing vault;
it now runs the same detect_vault_state/check_safety_gate as full builds.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Thread `project_type_key` through create_project

**Files:**
- Modify: `src/library_server/pm/adapter.py:109-117`, `src/library_server/pm/jira.py:215-245`, `src/library_server/pm/linear.py:221-229`, `src/library_server/server.py:264-275`
- Test: `tests/test_pm_adapter.py`, `tests/test_server.py`

**Interfaces:**
- Produces: `PMAdapter.create_project(name, key, description="", lead_account_id="", workflow_scheme="", project_type_key="software")` — new trailing keyword param on the ABC and both implementations. `JiraClient.create_project` already accepts `project_type_key` (`jira_client.py:156-164`) — no client change.

- [ ] **Step 1: Write the failing tests**

In `tests/test_pm_adapter.py`, next to the existing Jira `create_project` tests (which mock `adapter.client` methods):

```python
    @pytest.mark.asyncio
    async def test_create_project_forwards_project_type_key(self):
        adapter = self._make_jira_adapter()  # the file's existing mocked-client setup
        adapter.client.get_myself = AsyncMock(return_value={"accountId": "acct-1"})
        adapter.client.create_project = AsyncMock(return_value={"id": 1, "key": "OPS", "self": ""})

        await adapter.create_project("Ops", "OPS", project_type_key="business")

        _, kwargs = adapter.client.create_project.call_args
        assert kwargs["project_type_key"] == "business"
```

In `tests/test_server.py`, next to the existing PM tool tests (which patch `_get_pm_adapter`):

```python
@pytest.mark.asyncio
async def test_pm_create_project_forwards_project_type_key(monkeypatch):
    from library_server.server import library_pm_create_project

    adapter = MagicMock()
    adapter.create_project = AsyncMock(
        return_value=MagicMock(project_key="OPS", name="Ops", url="")
    )
    monkeypatch.setattr("library_server.server._get_pm_adapter", lambda: adapter)

    await library_pm_create_project(name="Ops", key="OPS", project_type_key="business")

    _, kwargs = adapter.create_project.call_args
    assert kwargs["project_type_key"] == "business"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pm_adapter.py -k project_type_key -v && pytest tests/test_server.py -k project_type_key -v`
Expected: FAIL — adapter test with `TypeError: unexpected keyword argument`; server test with missing kwarg.

- [ ] **Step 3: Add the parameter at all four layers**

1. `src/library_server/pm/adapter.py` — ABC `create_project` signature becomes:

```python
    @abstractmethod
    async def create_project(
        self,
        name: str,
        key: str,
        description: str = "",
        lead_account_id: str = "",
        workflow_scheme: str = "",
        project_type_key: str = "software",
    ) -> ProjectResult:
        ...
```

2. `src/library_server/pm/jira.py` — same signature change on `JiraAdapter.create_project`; pass it through in the client call:

```python
        result = await self.client.create_project(
            name=name,
            key=key,
            description=description,
            lead_account_id=lead_account_id,
            project_type_key=project_type_key,
        )
```

3. `src/library_server/pm/linear.py` — same signature change on the stub (body stays `raise NotImplementedError("Not supported by Linear adapter")`).
4. `src/library_server/server.py` `library_pm_create_project` — forward it:

```python
    result = await adapter.create_project(
        name, key, description,
        workflow_scheme=actual_scheme,
        project_type_key=project_type_key,
    )
```

- [ ] **Step 4: Run both suites**

Run: `pytest tests/test_pm_adapter.py tests/test_server.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/library_server/pm/adapter.py src/library_server/pm/jira.py src/library_server/pm/linear.py src/library_server/server.py tests/
git commit -m "fix(pm): honor project_type_key in library_pm_create_project

The tool accepted the parameter but dropped it before the adapter; every
project was created as type 'software' regardless.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: New MCP tool `library_pm_autodetect_workflow` (wires dead `autodetect_jira_workflow`)

**Files:**
- Modify: `src/library_server/pm/jira_client.py` (add `get_project_statuses`)
- Modify: `src/library_server/server.py` (new tool, after `library_pm_get_link_types`)
- Test: `tests/test_jira_client.py`, `tests/test_server.py`

**Interfaces:**
- Produces: `JiraClient.get_project_statuses(project_key: str) -> list[dict]` (`GET /rest/api/3/project/{key}/statuses`); MCP tool `library_pm_autodetect_workflow(project_key: str) -> dict` returning `{"status": "detected", "project_key": ..., "workflow": {states, in_progress, in_review, closed}}` or `{"status": "error", "error": ...}`.
- Consumes: `autodetect_jira_workflow(statuses_response) -> dict` from `library_server.config:88-123` (exists, tested, previously uncalled).

- [ ] **Step 1: Write the failing tests**

In `tests/test_jira_client.py` (follow the file's `_request`-mocking idiom used by e.g. the `get_project` test):

```python
    @pytest.mark.asyncio
    async def test_get_project_statuses(self):
        client = self._make_client()
        client._request = AsyncMock(return_value=[{"name": "Task", "statuses": [{"name": "To Do"}]}])

        result = await client.get_project_statuses("PROJ")

        client._request.assert_awaited_once_with("GET", "/rest/api/3/project/PROJ/statuses")
        assert result[0]["statuses"][0]["name"] == "To Do"
```

In `tests/test_server.py`:

```python
@pytest.mark.asyncio
async def test_pm_autodetect_workflow(monkeypatch):
    from library_server.server import library_pm_autodetect_workflow

    adapter = MagicMock()
    adapter.client.get_project_statuses = AsyncMock(return_value=[
        {"name": "Task", "statuses": [
            {"name": "To Do"}, {"name": "In Progress"},
            {"name": "In Review"}, {"name": "Done"},
        ]}
    ])
    monkeypatch.setattr("library_server.server._get_pm_adapter", lambda: adapter)

    result = await library_pm_autodetect_workflow("PROJ")

    assert result["status"] == "detected"
    assert result["workflow"]["closed"] == "Done"
    assert result["workflow"]["in_progress"] == "In Progress"
    assert result["workflow"]["states"] == ["To Do", "In Progress", "In Review", "Done"]


@pytest.mark.asyncio
async def test_pm_autodetect_workflow_requires_jira(monkeypatch):
    from library_server.server import library_pm_autodetect_workflow

    adapter = MagicMock(spec=[])  # no .client attribute — Linear-shaped
    monkeypatch.setattr("library_server.server._get_pm_adapter", lambda: adapter)

    result = await library_pm_autodetect_workflow("PROJ")

    assert result["status"] == "error"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_jira_client.py -k project_statuses -v && pytest tests/test_server.py -k autodetect -v`
Expected: FAIL — `get_project_statuses` and the tool don't exist (ImportError/AttributeError).

- [ ] **Step 3: Implement client method and tool**

In `src/library_server/pm/jira_client.py`, next to `get_project` (after line 197):

```python
    async def get_project_statuses(self, project_key: str) -> list[dict]:
        """GET /rest/api/3/project/{key}/statuses — issue types with their statuses."""
        return await self._request("GET", f"/rest/api/3/project/{project_key}/statuses")
```

In `src/library_server/server.py`, after `library_pm_get_link_types` (line 336):

```python
@mcp.tool(name="library_pm_autodetect_workflow")
async def library_pm_autodetect_workflow(project_key: str) -> dict:
    """Detect a pm.workflow block from a live Jira project's statuses.

    Returns {states, in_progress, in_review, closed} derived from
    GET /project/{key}/statuses. Review the proposal, then persist it by
    editing the pm.workflow section of library-config.yaml. Jira only.
    """
    from library_server.config import autodetect_jira_workflow

    adapter = _get_pm_adapter()
    client = getattr(adapter, "client", None)
    if client is None:
        return {"status": "error", "error": "Workflow autodetection requires pm.provider=jira."}
    statuses = await client.get_project_statuses(project_key)
    try:
        workflow = autodetect_jira_workflow(statuses)
    except ValueError as e:
        return {"status": "error", "error": str(e)}
    return {"status": "detected", "project_key": project_key, "workflow": workflow}
```

- [ ] **Step 4: Run both suites**

Run: `pytest tests/test_jira_client.py tests/test_server.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/library_server/pm/jira_client.py src/library_server/server.py tests/
git commit -m "feat(pm): library_pm_autodetect_workflow tool wires autodetect_jira_workflow

config.autodetect_jira_workflow was fully implemented and tested but had
zero production callers. Tool count is now 37 (docs sync in Task 17).

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: Honest vault-builder concurrency config — implement `parallel`/`max_parallel_extractors`/`fail_fast`, remove `preserve`, delete dead code

**Files:**
- Modify: `src/library_server/vault_builder/orchestrator.py:55-131`
- Modify: `src/library_server/vault_builder/config.py:13-50` (remove `preserve`)
- Modify: `src/library_server/server.py:621-626` (`_get_vault_orchestrator` passes the new params)
- Test: `tests/vault_builder/test_orchestrator.py`, `tests/vault_builder/test_config.py`

**Interfaces:**
- Produces: `VaultBuildOrchestrator(registry, graphify_runner, output_vault, mode="create", parallel=True, max_parallel_extractors=8, fail_fast=False)`. `VaultBuilderConfig` loses the `preserve` field.
- Behavior contract: `parallel=False` ⇒ concurrency limit 1; `fail_fast=True` ⇒ after the first extractor returns `success=False` (or raises), extractors that have not yet started return `ExtractResult(success=False, errors=["Skipped: fail_fast after '<name>' failed"])`; already-running extractors finish normally.

- [ ] **Step 1: Write the failing tests**

Add to `tests/vault_builder/test_orchestrator.py` (reuse that file's existing fake-extractor helpers/fixtures where present; otherwise these self-contained fakes):

```python
class _CountingExtractor(BaseExtractor):
    """Records max concurrent extract() calls via a shared tracker dict."""
    def __init__(self, name, tracker, delay=0.02, fail=False):
        super().__init__(config={"enabled": True})
        self.name = name
        self.output_subdir = name
        self._tracker = tracker
        self._delay = delay
        self._fail = fail

    def validate_config(self):
        return []

    async def survey(self):
        raise NotImplementedError

    async def preview(self):
        raise NotImplementedError

    async def extract(self, output_dir):
        self._tracker["running"] += 1
        self._tracker["max"] = max(self._tracker["max"], self._tracker["running"])
        await asyncio.sleep(self._delay)
        self._tracker["running"] -= 1
        if self._fail:
            return ExtractResult(source_name=self.name, errors=["boom"], success=False)
        return ExtractResult(source_name=self.name, files_written=["f.md"], success=True)


@pytest.mark.asyncio
async def test_max_parallel_extractors_limits_concurrency(tmp_path):
    tracker = {"running": 0, "max": 0}
    registry = PluginRegistry()
    for i in range(4):
        registry.register(_CountingExtractor(f"e{i}", tracker))
    orch = VaultBuildOrchestrator(
        registry=registry, graphify_runner=GraphifyRunner(config={}),
        output_vault=tmp_path, mode="enrich",
        parallel=True, max_parallel_extractors=2,
    )
    await orch.build()
    assert tracker["max"] <= 2


@pytest.mark.asyncio
async def test_parallel_false_runs_sequentially(tmp_path):
    tracker = {"running": 0, "max": 0}
    registry = PluginRegistry()
    for i in range(3):
        registry.register(_CountingExtractor(f"e{i}", tracker))
    orch = VaultBuildOrchestrator(
        registry=registry, graphify_runner=GraphifyRunner(config={}),
        output_vault=tmp_path, mode="enrich",
        parallel=False,
    )
    await orch.build()
    assert tracker["max"] == 1


@pytest.mark.asyncio
async def test_fail_fast_skips_undispatched_extractors(tmp_path):
    tracker = {"running": 0, "max": 0}
    registry = PluginRegistry()
    registry.register(_CountingExtractor("failer", tracker, fail=True))
    for i in range(3):
        registry.register(_CountingExtractor(f"e{i}", tracker))
    orch = VaultBuildOrchestrator(
        registry=registry, graphify_runner=GraphifyRunner(config={}),
        output_vault=tmp_path, mode="enrich",
        parallel=False, fail_fast=True,  # sequential => deterministic ordering
    )
    result = await orch.build()
    skipped = [r for r in result.extract_results if r.errors and "Skipped: fail_fast" in r.errors[0]]
    assert len(skipped) == 3
    assert result.status in ("failed", "completed_with_warnings")
```

Add to `tests/vault_builder/test_config.py`:

```python
def test_preserve_key_is_gone():
    """preserve was documented-but-inert; removed in 0.3.2 pending incrementality."""
    from library_server.vault_builder.config import VaultBuilderConfig
    assert not hasattr(VaultBuilderConfig(), "preserve")
```

(Match import style to the top of each test file — they already import `PluginRegistry`, `VaultBuildOrchestrator`, `GraphifyRunner`, `ExtractResult`, `BaseExtractor`, `asyncio`, `pytest`; add any missing ones.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/vault_builder/test_orchestrator.py -k "max_parallel or sequentially or fail_fast" tests/vault_builder/test_config.py::test_preserve_key_is_gone -v`
Expected: FAIL — `__init__` rejects the new kwargs; `preserve` still exists.

- [ ] **Step 3: Implement in orchestrator + config + server**

`src/library_server/vault_builder/orchestrator.py`:

1. Extend `__init__`:

```python
    def __init__(
        self,
        registry: PluginRegistry,
        graphify_runner: GraphifyRunner,
        output_vault: Path,
        mode: str = "create",
        parallel: bool = True,
        max_parallel_extractors: int = 8,
        fail_fast: bool = False,
    ) -> None:
        self.registry = registry
        self.graphify_runner = graphify_runner
        self.output_vault = output_vault
        self.mode = mode
        self.parallel = parallel
        self.max_parallel_extractors = max_parallel_extractors
        self.fail_fast = fail_fast
```

2. In `build()`, replace the extract block (lines 106-118: the `tasks = [...]` / `gather` / exception-conversion loop) with:

```python
        # Run extractors under a concurrency limit. parallel=False degrades to
        # a limit of 1 (sequential). fail_fast skips extractors that have not
        # started once any extractor has failed; in-flight ones finish.
        limit = self.max_parallel_extractors if self.parallel else 1
        semaphore = asyncio.Semaphore(max(1, limit))
        failed_first: list[str] = []  # single-element list as a mutable flag

        async def _run_one(ext) -> ExtractResult:
            async with semaphore:
                if self.fail_fast and failed_first:
                    return ExtractResult(
                        source_name=ext.name,
                        errors=[f"Skipped: fail_fast after '{failed_first[0]}' failed"],
                        success=False,
                    )
                try:
                    result = await ext.extract(raw_dir / ext.output_subdir)
                except BaseException as exc:
                    result = ExtractResult(source_name=ext.name, errors=[str(exc)], success=False)
                if not result.success and not failed_first:
                    failed_first.append(ext.name)
                return result

        extract_results = list(
            await asyncio.gather(*[_run_one(ext) for ext in extractors])
        )
```

3. Delete the two dead discarded expressions and their misleading comment (lines 125-131). Keep only:

```python
        all_failed = all(not r.success for r in extract_results)
```

`src/library_server/vault_builder/config.py`: delete the `preserve: list[str] = field(default_factory=list)` dataclass field and the `preserve=vb.get("preserve", [])` kwarg in `load_vault_builder_config`.

`src/library_server/vault_builder/graphify_runner.py`: delete the `is_available()` method (lines 69-74) — it checks `shutil.which` for a CLI that neither build path ever shells out to (both call the Python API), so its answer is unrelated to whether a build succeeds. Delete its tests in `tests/vault_builder/test_graphify_runner.py` (the `is_available` test methods around lines 32-52). Remove the now-unused `import shutil` from `graphify_runner.py` if nothing else uses it.

`src/library_server/server.py` `_get_vault_orchestrator` return:

```python
    return VaultBuildOrchestrator(
        registry=registry,
        graphify_runner=graphify,
        output_vault=vb_cfg.output_vault or Path.cwd() / "vault-output",
        mode=vb_cfg.mode,
        parallel=vb_cfg.parallel,
        max_parallel_extractors=vb_cfg.max_parallel_extractors,
        fail_fast=vb_cfg.fail_fast,
    )
```

- [ ] **Step 4: Run the vault-builder suites (unit + integration)**

Run: `pytest tests/vault_builder/ -v`
Expected: PASS — the existing 23 orchestrator tests must still pass (default kwargs preserve old behavior). If a config test asserted the `preserve` field loads, delete that assertion — the field is gone by design.

- [ ] **Step 5: Commit**

```bash
git add src/library_server/vault_builder/orchestrator.py src/library_server/vault_builder/config.py src/library_server/server.py tests/vault_builder/
git add src/library_server/vault_builder/graphify_runner.py tests/vault_builder/test_graphify_runner.py
git commit -m "feat(vault-builder): honor parallel/max_parallel_extractors/fail_fast; drop preserve

Concurrency keys were loaded but never consulted — builds always ran fully
parallel with no fail-fast. preserve is removed until incremental builds
exist. Also deletes the discarded quality-gate expressions and the dead
GraphifyRunner.is_available() (checked a CLI no build path shells out to).

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 11: Validate `pm.workflow.blocked`

**Files:**
- Modify: `src/library_server/config.py:239-253` (`validate_config`)
- Modify: `library-config.example.yaml` (workflow comment block, lines ~51-55)
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `validate_config` warns when `pm.workflow.blocked` is set but absent from `pm.workflow.states`. `blocked` stays optional — no warning when unset (unlike `in_progress`/`in_review`/`closed`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py` beside the existing `pm.workflow` validation tests (copy their config-construction idiom — they build a `LibraryConfig(raw={...}, path=...)` directly):

```python
def test_validate_warns_on_blocked_not_in_states(tmp_path):
    from library_server.config import LibraryConfig, validate_config

    config = LibraryConfig(raw={
        "library": {"version": "0.3.2"},
        "pm": {"provider": "jira", "workflow": {
            "states": ["To Do", "In Progress", "In Review", "Done"],
            "in_progress": "In Progress", "in_review": "In Review",
            "closed": "Done", "blocked": "Stuck",
        }},
    }, path=tmp_path / "library-config.yaml")

    result = validate_config(config)

    assert any("blocked" in w and "Stuck" in w for w in result["warnings"])


def test_validate_blocked_unset_is_fine(tmp_path):
    from library_server.config import LibraryConfig, validate_config

    config = LibraryConfig(raw={
        "library": {"version": "0.3.2"},
        "pm": {"provider": "jira", "workflow": {
            "states": ["To Do", "Done"],
            "in_progress": "To Do", "in_review": "To Do", "closed": "Done",
        }},
    }, path=tmp_path / "library-config.yaml")

    result = validate_config(config)

    assert not any("blocked" in w for w in result["warnings"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -k blocked -v`
Expected: first test FAILS (no warning produced).

- [ ] **Step 3: Implement**

In `src/library_server/config.py`, inside the `else:` branch of the workflow check (after the `for key in ("in_progress", "in_review", "closed"):` loop), add:

```python
            # blocked is optional (sync_state bucketing works without it), but
            # if set it must name a real state — it is consumed by
            # server._get_pm_adapter and silently misclassifies otherwise.
            blocked_val = workflow.get("blocked")
            if blocked_val is not None and blocked_val not in states:
                warnings.append(
                    f"pm.workflow.blocked={blocked_val!r} is not present in pm.workflow.states {states}"
                )
```

In `library-config.example.yaml`, extend the commented workflow block (after the `in_review` line) with:

```yaml
  #   blocked: "Blocked"                    # optional — status bucketed as blocked by pm sync
```

- [ ] **Step 4: Run the config suite**

Run: `pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/library_server/config.py library-config.example.yaml tests/test_config.py
git commit -m "feat(config): validate and document pm.workflow.blocked

The key was load-bearing (consumed by _get_pm_adapter) but unvalidated
and undocumented.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 12: Expose the three unreachable checkpoint fields

**Files:**
- Modify: `src/library_server/server.py:46-73` (`library_checkpoint_write`)
- Test: `tests/test_server.py`

**Interfaces:**
- Produces: `library_checkpoint_write(..., changes: str = "", open_decisions: str = "", memory_updates: str = "")`. Formats: `changes` is semicolon-separated like the other list params; `open_decisions` entries are `question|options|impact` joined by `;`; `memory_updates` entries are `file|type|content` joined by `;`. Missing `|` segments become `""`.
- Consumes: `CheckpointData` (`types.py:114-125`) — `changes: list[str]`, `open_decisions: list[dict]` (keys `question/options/impact`, see `checkpoint.py:116-127`), `memory_updates: list[dict]` (keys `file/type/content`, see `checkpoint.py:136-147`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_server.py` beside the existing checkpoint tool tests (they monkeypatch config/`resolve_checkpoint_dir` — reuse that fixture idiom):

```python
def test_checkpoint_write_renders_changes_decisions_memory(monkeypatch, tmp_path):
    from library_server.server import library_checkpoint_write

    rr = tmp_path / "rr"
    (rr / "checkpoints").mkdir(parents=True)
    monkeypatch.setattr(
        "library_server.server.resolve_checkpoint_dir", lambda cfg: rr / "checkpoints"
    )

    result = library_checkpoint_write(
        topic="pipeline",
        status="in progress",
        next_session="continue",
        changes="Added retry logic; Removed dead code",
        open_decisions="Use Redis?|redis,memcached|caching layer",
        memory_updates="auth-notes.md|project|JWT rotation policy",
    )

    content = Path(result["path"]).read_text()
    assert "## 2. What Changed" in content
    assert "Added retry logic" in content
    assert "## 4. Open Decisions" in content
    assert "Use Redis?" in content
    assert "## 6. Memory Updates" in content
    assert "auth-notes.md" in content
```

(Check the return-key name for the written path against `write_checkpoint`'s return in `src/library_server/checkpoint/checkpoint.py` — if it returns `checkpoint_path` instead of `path`, use that key.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_server.py -k renders_changes -v`
Expected: FAIL — `TypeError: unexpected keyword argument 'changes'`.

- [ ] **Step 3: Extend the tool**

Replace `library_checkpoint_write` in `src/library_server/server.py`:

```python
@mcp.tool(name="library_checkpoint_write")
def library_checkpoint_write(
    topic: str,
    status: str,
    next_session: str,
    accomplished: str = "",
    next_actions: str = "",
    key_context: str = "",
    changes: str = "",
    open_decisions: str = "",
    memory_updates: str = "",
) -> dict:
    """Write a session checkpoint. List params are semicolon-separated strings.

    Structured params use pipe-separated fields within each semicolon-separated
    entry: open_decisions entries are "question|options|impact";
    memory_updates entries are "file|type|content".
    """
    from library_server.checkpoint.checkpoint import write_checkpoint
    from library_server.types import CheckpointData
    from datetime import date

    def _split(raw: str) -> list[str]:
        return [s.strip() for s in raw.split(";") if s.strip()] if raw else []

    def _split_records(raw: str, keys: tuple[str, ...]) -> list[dict]:
        records = []
        for entry in _split(raw):
            parts = [p.strip() for p in entry.split("|")]
            records.append({k: (parts[i] if i < len(parts) else "") for i, k in enumerate(keys)})
        return records

    data = CheckpointData(
        topic=topic,
        date=date.today().isoformat(),
        status=status,
        next_session=next_session,
        accomplished=_split(accomplished),
        changes=_split(changes),
        next_actions=_split(next_actions),
        open_decisions=_split_records(open_decisions, ("question", "options", "impact")),
        key_context=_split(key_context),
        memory_updates=_split_records(memory_updates, ("file", "type", "content")),
    )
    try:
        checkpoint_dir = resolve_checkpoint_dir(get_config())
    except ValueError as e:
        return {"status": "error", "error": str(e)}
    return write_checkpoint(str(checkpoint_dir), data)
```

- [ ] **Step 4: Run the checkpoint-related server tests**

Run: `pytest tests/test_server.py -k checkpoint -v`
Expected: PASS — existing tests pass because the new params default to empty.

- [ ] **Step 5: Commit**

```bash
git add src/library_server/server.py tests/test_server.py
git commit -m "feat(checkpoint): expose changes/open_decisions/memory_updates on the write tool

The renderer supported all three sections but the MCP surface could never
populate them.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 13: `doctor` repairs hooks; hook-wrapper writes become change-aware

**Files:**
- Modify: `src/library_server/cli.py:383-422` (`_cmd_doctor`), `cli.py:662-665` (`_ensure_hook_scripts` overwrite logic)
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `_ensure_hook_scripts` returns the count of wrapper files **written or changed** (identical existing content is skipped — this both removes the `and not True` dead conditional and makes `doctor` idempotent). `_cmd_doctor` additionally registers hooks in `.claude/settings.json` and (re)writes wrapper scripts under the CWD.
- Consumes: `_install_hooks(settings_path, project_dir)` (`cli.py:579-593`), `_ensure_hook_scripts(hooks_dir, project_dir)` (`cli.py:596`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli.py`:

```python
class TestDoctorHookRepair:
    def test_doctor_installs_missing_hooks(self, monkeypatch, tmp_path, capsys):
        import json
        from library_server.cli import _cmd_doctor

        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        monkeypatch.chdir(tmp_path)

        _cmd_doctor()

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert "SessionStart" in settings.get("hooks", {})
        wrappers = list((tmp_path / ".claude" / "hooks").glob("*.py"))
        assert len(wrappers) >= 6

    def test_doctor_is_idempotent(self, monkeypatch, tmp_path, capsys):
        from library_server.cli import _cmd_doctor

        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        monkeypatch.chdir(tmp_path)

        _cmd_doctor()
        capsys.readouterr()
        _cmd_doctor()
        out = capsys.readouterr().out
        assert "No issues found" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py::TestDoctorHookRepair -v`
Expected: FAIL — no `.claude/settings.json` created by doctor.

- [ ] **Step 3: Implement**

1. In `_ensure_hook_scripts` (`cli.py`), delete the dead conditional:

```python
        if script_path.exists() and not True:  # always overwrite hook wrappers
            continue
```

and instead, immediately before each `script_path.write_text(content)` call at the end of the per-script loop (there are two content branches; the write is shared or duplicated — put this before the write in both paths if needed):

```python
        if script_path.exists() and script_path.read_text() == content:
            continue  # unchanged — don't count as created/fixed
```

then keep `script_path.write_text(content)` + `created += 1` (and the chmod line if present) for the changed/new case.

2. In `_cmd_doctor`, after the context-usage fix block (line 417), add:

```python
    # Fix hook registration + wrapper scripts (what `validate` flags)
    project_dir = Path.cwd()
    settings_path = project_dir / ".claude" / "settings.json"
    if _install_hooks(settings_path, project_dir):
        print("  [fix] Registered hooks in .claude/settings.json")
        fixes += 1
    wrappers_written = _ensure_hook_scripts(project_dir / ".claude" / "hooks", project_dir)
    if wrappers_written:
        print(f"  [fix] Wrote {wrappers_written} hook wrapper script(s)")
        fixes += wrappers_written
```

- [ ] **Step 4: Run the CLI suite**

Run: `pytest tests/test_cli.py -v`
Expected: PASS — including existing `_ensure_hook_scripts` tests. If one asserted wrappers are always rewritten/counted, update it to the new contract (unchanged content ⇒ not counted).

- [ ] **Step 5: Commit**

```bash
git add src/library_server/cli.py tests/test_cli.py
git commit -m "feat(cli): doctor repairs hook registration and wrapper scripts

Everything `library validate` can flag, `library doctor` can now fix.
Wrapper writes are change-aware (removes the `and not True` leftover),
keeping doctor idempotent.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 14: `aggregate_memories` stops claiming it applied merges

**Files:**
- Modify: `src/library_server/memory/aggregate.py:11-54`, `src/library_server/server.py:106-111`
- Test: `tests/test_memory_mmu/` (the file containing the existing `aggregate_memories` tests — locate with `grep -rl aggregate_memories tests/`)

**Interfaces:**
- Produces: `aggregate_memories(memory_path, dry_run=True) -> {"suggestions": [...], "applied": False}` — `applied` is now always `False`; `dry_run` is accepted for backward compatibility but has no effect.

- [ ] **Step 1: Write the failing test**

In the test file found via `grep -rl aggregate_memories tests/`, add:

```python
def test_aggregate_never_claims_applied(tmp_path):
    """Regression: dry_run=False used to report applied=True with no merge performed."""
    from library_server.memory.aggregate import aggregate_memories

    for name in ("auth-flow", "auth-flow-notes"):
        (tmp_path / f"{name}.md").write_text(
            f"---\nname: {name}\ndescription: d\nmetadata:\n  type: project\n---\nbody\n"
        )
    before = sorted(p.name for p in tmp_path.glob("*.md"))

    result = aggregate_memories(str(tmp_path), dry_run=False)

    assert result["suggestions"], "related files should still be suggested"
    assert result["applied"] is False
    assert sorted(p.name for p in tmp_path.glob("*.md")) == before  # nothing touched
```

(If the frontmatter shape above doesn't yield a `type` for grouping — `_parse_frontmatter` returns the whole YAML dict, and grouping reads `frontmatter.get("type")` — flatten it: use `---\nname: auth-flow\ntype: project\n---\n`. Check `tests/` for the shape the existing aggregate tests use and copy it.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest $(grep -rl aggregate_memories tests/ | head -1) -k never_claims -v`
Expected: FAIL — `applied` is `True`.

- [ ] **Step 3: Implement honesty**

In `src/library_server/memory/aggregate.py`: change the return (line 54) to:

```python
    # Merging is not implemented — this function only analyzes. Reporting
    # applied=True on dry_run=False was a lie that made callers believe
    # files had been consolidated.
    return {"suggestions": suggestions, "applied": False}
```

and update the docstring's Returns section: `"applied": always False — analysis only; merging is not implemented.` Also note in the `dry_run` description that the flag is accepted for compatibility and has no effect.

In `src/library_server/server.py`, update `library_memory_aggregate`'s docstring:

```python
    """Find merge opportunities for related memories. Analysis only — returns
    suggestions; no files are modified regardless of dry_run."""
```

- [ ] **Step 4: Run the memory suite**

Run: `pytest tests/test_memory_mmu/ tests/test_server.py -v`
Expected: PASS. If an existing test asserted `applied is True` for `dry_run=False`, invert it — that behavior was the bug.

- [ ] **Step 5: Commit**

```bash
git add src/library_server/memory/aggregate.py src/library_server/server.py tests/
git commit -m "fix(memory): aggregate_memories reports applied=False — it never merges

The applied flag claimed success for an operation that does not exist.
Real merging is deferred to the learning-loop push.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 15: Remove out-of-domain clerk-pollution-scan tooling

**Files:**
- Delete: `bin/library-clerk-pollution-scan`, `tests/test_clerk_pollution_scan.py`

- [ ] **Step 1: Verify nothing references it**

Run: `grep -rn "clerk-pollution\|clerk_pollution" --include="*.py" --include="*.md" --include="*.toml" --include="*.yml" --include="*.yaml" . | grep -v test_clerk_pollution_scan | grep -v "bin/library-clerk"`
Expected: no output (the redaction *pattern* for Clerk keys in `redaction.py` mentions "clerk" but not this script — it stays).

- [ ] **Step 2: Delete and verify the suite**

```bash
git rm bin/library-clerk-pollution-scan tests/test_clerk_pollution_scan.py
```

Run: `pytest --ignore=tests/test_jira_integration.py -q`
Expected: PASS, with the clerk test file simply gone.

- [ ] **Step 3: Commit**

```bash
git commit -m "chore: remove clerk-pollution-scan tooling

Out-of-domain carry-over from a sibling project; referenced by no doc or
workflow in this repo.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 16: Version bump + CHANGELOG + packaging JSON sync

**Files:**
- Modify: `pyproject.toml:3`, `CHANGELOG.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `skills/plugin.json`

- [ ] **Step 1: Bump versions and counts**

1. `pyproject.toml:3`: `version = "0.3.1"` → `version = "0.3.2"`.
2. `.claude-plugin/plugin.json`: `"version": "0.3.0"` → `"0.3.2"`; in `"description"`, replace `via 11 skills backed by an MCP server with 27 tools` → `via 12 skills backed by an MCP server with 37 tools`.
3. `.claude-plugin/marketplace.json`: plugin entry `"version": "0.3.0"` → `"0.3.2"`; same description fix (`11 skills`→`12 skills`, `27 tools`→`37 tools`).
4. `skills/plugin.json`: `"version": "0.1.0"` → `"0.3.2"` (its description already says 12 skills — leave it).

- [ ] **Step 2: Write the CHANGELOG entry**

Insert directly under the `Format follows...` line in `CHANGELOG.md` (above `## [0.3.1]`):

```markdown
## [0.3.2] - 2026-08-02

### Added
- `library_pm_autodetect_workflow` MCP tool — derives a `pm.workflow` block from a live Jira project's statuses (wires the previously uncalled `autodetect_jira_workflow`). Tool count is now 37.
- `library_checkpoint_write` accepts `changes`, `open_decisions` ("question|options|impact"), and `memory_updates` ("file|type|content") — the renderer supported these sections but the tool could never populate them.
- `library doctor` now repairs hook registration in `.claude/settings.json` and rewrites hook wrapper scripts — everything `library validate` flags, `doctor` can fix.
- Vault builder honors `parallel`, `max_parallel_extractors`, and `fail_fast`.
- `pm.workflow.blocked` is validated and documented.
- `library-config.example.yaml` documents the `vault_builder` section.

### Fixed
- `library init` wrote SESSION.md/PROJECT-STATE.md in a bullet format the state parsers could not read; the first session-end round-trip blanked project/focus/task. Bootstrap now uses the canonical renderers.
- `library_memory_health`/`library_memory_learn` read `~/.library/learning/routing-journal.jsonl` while hooks write `~/.library/routing.jsonl`; both now use the shared `routing_journal_path()` helper.
- PreCompact transcript archival and SessionEnd SESSION.md archival bypassed redaction (raw file copies into the vault); both now redact at write time. `session_end` stderr uses `redact_exception`.
- Linear `update_task(status=...)` silently ignored the status; it now raises `TransitionNotAvailableError` (real Linear transitions remain unimplemented).
- Jira vault-builder extractor dumped ADF description/comment dicts as Python reprs; ADF is now flattened to text via the shared `pm/adf.py` helper.
- `library_vault_builder_extract` bypassed the create-mode safety gate; it now applies the same gate as full builds and accepts `force`.
- `library_pm_create_project` dropped its `project_type_key` parameter; it is now threaded through to Jira.
- `aggregate_memories` claimed `applied: true` without performing any merge; it now always reports `applied: false` (analysis only).

### Changed
- Removed the inert `vault_builder.preserve` config key (deferred to the incrementality push) and the out-of-domain `bin/library-clerk-pollution-scan` tooling.
- Docs: added `library_pm_get_issue` to the MCP tool reference and Linear capability docs; corrected CONTRIBUTING's stale colon-form tool naming; corrected the test plan's stale coverage-floor description (the ratchet against `coverage-baseline.txt` is the only floor).

### Performance (previously unreleased, mid-2026 merges)
- JiraClient: HTTP connection reuse plus retry/backoff on 429/502/503/504 honoring `Retry-After`; config loading cached on `(mtime_ns, size)`.
- Stop hook emits `systemMessage` instead of `hookSpecificOutput` (Stop event schema fix).
```

- [ ] **Step 3: Verify and commit**

Run: `python -c "import json; [json.load(open(p)) for p in ('.claude-plugin/plugin.json', '.claude-plugin/marketplace.json', 'skills/plugin.json')]" && grep -c "0.3.2" pyproject.toml CHANGELOG.md`
Expected: no JSON errors; both files contain `0.3.2`.

```bash
git add pyproject.toml CHANGELOG.md .claude-plugin/ skills/plugin.json
git commit -m "chore(release): v0.3.2 — changelog, version bump, packaging sync

plugin.json/marketplace.json said 0.3.0 with '27 tools/11 skills';
skills/plugin.json said 0.1.0. All now 0.3.2 / 37 tools / 12 skills.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 17: Docs drift fixes

**Files:**
- Modify: `docs/reference/mcp-tools.md`, `docs/guides/pm-integration.md`, `docs/setup/linear-setup.md`, `library-config.example.yaml`, `CONTRIBUTING.md`, `docs/reference/test-plan.md`, `docs/reference/vault-builder-api.md`, `README.md`

No code — verification is grep-based. Make each edit, then run the checks in Step 9.

- [ ] **Step 1: `docs/reference/mcp-tools.md`**

- Quick Reference table (lines ~9-19): add `library_pm_get_issue` and `library_pm_autodetect_workflow` to the PM row; change the PM tool count 12→14 and the stated total 35→37.
- Full PM section (~lines 356-628): add entries for both tools. For `library_pm_get_issue`, document parameters (`task_id`) and the return shape from `server.py:217-245` (id, summary, description, status, labels, parent, assignee, comments[{author, created, body}] up to 20 most recent, available_transitions[{name, to_status}], url). For `library_pm_autodetect_workflow`, document parameters (`project_key`), the `{"status": "detected", "project_key", "workflow": {states, in_progress, in_review, closed}}` return, the `{"status": "error", "error"}` shape for non-Jira providers, and that results are applied by editing `pm.workflow` in `library-config.yaml`.
- In the `library_pm_create_project` entry: note `project_type_key` is now honored (default `software`).
- In the `library_vault_builder_extract` entry: document the new `force` parameter and the `blocked` status.
- In the `library_checkpoint_write` entry: document `changes`, `open_decisions` (`question|options|impact` entries), `memory_updates` (`file|type|content` entries).

- [ ] **Step 2: `docs/guides/pm-integration.md`**

In the capability matrix (~lines 30-43) add two rows: `Get issue detail` (Jira ✅ / Linear ❌) and `Autodetect workflow` (Jira ✅ / Linear ❌).

- [ ] **Step 3: `docs/setup/linear-setup.md`**

In the "Not Yet Supported" list (~lines 50-58): add `get_issue` (the 8th `NotImplementedError` method, previously undocumented) and `library_pm_autodetect_workflow` (Jira-only). Also add: "Status transitions via `library_pm_update` raise a structured `transition_not_available` error rather than silently ignoring the request."

- [ ] **Step 4: `library-config.example.yaml`**

Append this commented section at the end of the file (matching the file's comment style):

```yaml
# Vault Builder — multi-source extraction pipeline (see docs/guides/vault-builder.md)
# A source block must be present (non-empty) for its extractor to be registered.
# vault_builder:
#   mode: create                    # create | enrich (enrich never touches .obsidian/ or wiki/)
#   output_vault: ./vault-output
#   parallel: true                  # run extractors concurrently
#   max_parallel_extractors: 8      # concurrency cap when parallel: true
#   fail_fast: false                # skip not-yet-started extractors after the first failure
#   graphify:
#     enabled: false                # build knowledge graph + wiki stubs from extracted frontmatter
#   sources:
#     specs:
#       source_path: ./library-reading-room/specs
#     claude_memory:
#       source_path: ~/.claude/projects/<project>/memory
#     session_context:
#       source_path: ./library-reading-room/sessions
#     notebooklm:
#       source_path: ./notebooklm-exports
#     obsidian_vault:
#       source_path: ~/ObsidianVault    # read-only source
#     jira:
#       instance: https://your-site.atlassian.net   # auth via ATLASSIAN_EMAIL + JIRA_API_TOKEN env vars
#       projects: [PROJ1]
#     axon_bridge:                      # being replaced by a graphify-based extractor (see specs/)
#       repos:
#         - {name: my-repo, path: ../my-repo, language: python}
```

- [ ] **Step 5: `CONTRIBUTING.md`**

In the tool-naming sections (~lines 64-99): replace the `library:<module>:<action>` convention text and the `@mcp.tool(name="library:<module>:<action>")` example with the underscore form actually used: convention `library_<module>_<action>`, example `@mcp.tool(name="library_pm_create_task")`. Note that skills (`library:config`) and CLI subcommands (`library init`) keep their colon/space forms.

- [ ] **Step 6: `docs/reference/test-plan.md`**

Replace every claim (lines ~9-13, ~68, ~165, ~174) that an "88% floor" is "enforced via pytest-cov in pyproject.toml" with: "Coverage floor: the ratchet — `bin/library-coverage-ratchet` fails CI on any drop versus `coverage-baseline.txt` (currently 94.35). There is no static threshold in pyproject.toml." Update the header's test count/coverage snapshot to state it is a historical snapshot from 2026-04-16 and that `coverage-baseline.txt` is authoritative.

- [ ] **Step 7: `docs/reference/vault-builder-api.md`**

- Fix the stale registration pointer (line ~328): `server.py` lines 489-530 → "`server.py::_get_vault_orchestrator`" (name, not line numbers — they drift).
- In the config-reference section (~lines 253-312): delete the `preserve` row; delete `graphify.flags`, `graphify.auto_rebuild`, `graphify.incremental` rows (never read — only `graphify.enabled` is consumed by the runner); delete the Jira `cloud_id` and `auth: mcp` rows (feature does not exist — auth is via `ATLASSIAN_EMAIL`/`JIRA_API_TOKEN` env vars); note that `parallel`/`max_parallel_extractors`/`fail_fast` are now enforced by the orchestrator.
- Make the matching deletions in `docs/guides/vault-builder.md` (~lines 149-231): same keys, same reasons.

- [ ] **Step 8: `README.md`**

Tool table (~lines 84-96): add `library_pm_get_issue` and `library_pm_autodetect_workflow` to the PM row's tool enumeration; update the "36 tools" total to 37.

- [ ] **Step 9: Verify with grep**

```bash
grep -c "pm_get_issue" docs/reference/mcp-tools.md          # expect >= 2
grep -c "pm_autodetect_workflow" docs/reference/mcp-tools.md README.md  # expect >= 1 each
grep -rn "37 tools" README.md docs/reference/mcp-tools.md   # expect hits
grep -n "vault_builder" library-config.example.yaml | head -1  # expect a hit
grep -n 'library:<module>:<action>' CONTRIBUTING.md            # expect NO hits
grep -n "88%" docs/reference/test-plan.md                      # expect NO floor claims left
grep -n "preserve\|auto_rebuild\|cloud_id" docs/reference/vault-builder-api.md  # expect no config-claim hits
```

- [ ] **Step 10: Commit**

```bash
git add docs/ library-config.example.yaml CONTRIBUTING.md README.md
git commit -m "docs: sync references with code — pm_get_issue, autodetect tool, vault_builder config

Removes claims for config keys that never existed (preserve, graphify
flags/auto_rebuild/incremental, jira cloud_id/auth:mcp), fixes the stale
colon-form tool naming in CONTRIBUTING, and corrects the coverage-floor
description to the ratchet mechanism.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 18: Final verification

- [ ] **Step 1: Full test suite**

Run: `pytest --ignore=tests/test_jira_integration.py`
Expected: PASS (live-Jira suite self-skips anyway without `ATLASSIAN_EMAIL`/`JIRA_API_TOKEN`; the explicit ignore keeps CI parity).

- [ ] **Step 2: Coverage ratchet**

Run: `bin/library-coverage-ratchet`
Expected: PASS — no drop vs `coverage-baseline.txt` (94.35). If coverage *improved* meaningfully, do NOT bump the baseline in this pass (keep the diff reviewable); note it in the PR body instead.

- [ ] **Step 3: Lint + types**

Run: `ruff check . && mypy`
Expected: both clean. Fix any findings in the files this plan touched (annotate new functions; unused imports from deleted `shutil` usages are the likely offenders).

- [ ] **Step 4: Mutation smoke (PM layer was touched)**

Run: `bin/library-mutation-smoke`
Expected: PASS (CI runs this; catching it locally is cheaper).

- [ ] **Step 5: Review the full diff**

Run: `git diff main...HEAD --stat && git log --oneline main..HEAD`
Check: no unintended file appears; every commit maps to a task; `axon_bridge.py` and the `axon:` config block are untouched (deferred to the next push).

- [ ] **Step 6: Report**

State what was verified (suite, ratchet, ruff, mypy, mutation smoke) and what could not be verified locally (live Jira integration tests; the 3.10/3.11 matrix runs in CI).
