---
name: checkpoint
description: "Capture session state at the end of a work session. Writes structured checkpoint file, updates memory, and comments on PM tasks with progress."
---

# library:checkpoint — Session State Capture

Capture everything the next session needs to resume without context loss.

## When to Use

- End of a work session
- Before switching to a different task or project
- When the user says "checkpoint", "save state", "wrap up"
- Before context window is likely to expire

## Process

### Step 1: Gather State

Review the conversation and recent tool calls to collect:

1. **Accomplished** — concrete deliverables (files created, features implemented, bugs fixed)
2. **Changes** — run `git status` and `git diff --stat` for file-level changes
3. **Next Actions** — specific, actionable items (not "continue working on X")
4. **Open Decisions** — unresolved questions with options and impact
5. **Key Context** — non-obvious information (error messages, gotchas, constraints)
6. **Memory Updates** — what was saved to Claude memory this session

### Step 2: Write Checkpoint

Call `library:checkpoint:write` with gathered data:

- **topic**: kebab-case summary (e.g., "auth-middleware-refactor")
- **status**: current state in one line
- **next_session**: what to do first next time
- **accomplished**: semicolon-separated list
- **next_actions**: semicolon-separated list
- **key_context**: semicolon-separated list

### Step 3: Update Memory

Save a project-type memory pointing to the checkpoint:

```
name: <Topic> Session Checkpoint
description: <one-line summary>
type: project
```

Content: path to checkpoint file, resume point, key decisions.

### Step 4: Update PM Tasks (if PM configured)

For each PM task touched this session:
- Call `library:pm:update` with a comment summarizing progress
- If task is complete, transition status (but only if verified — evidence before claims)

### Step 5: Check for Orphaned Work

Call `library:pm:sync` for active projects. Compare accomplished work against open tasks.
Flag any session work that doesn't match a PM task (orphaned work — should it be tracked?).

### Step 6: Detect gaps + auto-file follow-up tickets

A session almost always discovers follow-ups that are NOT in PM yet — orphaned commits, side-fixes mid-merge, skipped tests with TODOs, drift between spec + code, manual workarounds, deferred validations. These die in operator memory if not filed.

Step 5's orphaned-work check compares accomplished vs open tickets. Step 6 goes further: it scans the session transcript + checkpoint for **signals of untracked follow-ups** that may not even be visible as "accomplished work" yet.

#### Procedure

1. **Inventory candidate gaps** by re-reading the session transcript + the checkpoint just written. Categories to look for:

   | Category | Signal |
   |---|---|
   | Test skipped with TODO | `describe.skip(.*TODO\|skip.*FIXME` in committed diff |
   | Migration number collision | two files with same NNN_ prefix in `src/db/migrations/` |
   | Hot-fix mid-merge | commit titled `fix(*): ...` against own session's merges |
   | Spec not updated for shipped code | new migration / endpoint / schema change without matching B-spec edit |
   | Config corrected without audit | `account_id` / `project_id` / `region` value flipped without consumer audit |
   | Deferred validation | "smoke test pending after X applies" / "blocked on operator click" |
   | Pre-existing bug papered over | shipped fix with `# pre-existing, not introduced here` note |
   | Manual cleanup left for operator | `<dir>.old-pre-cleanup` / `<file>.bak` style preserved artifacts |
   | Secrets near-miss | gitleaks fired on session content (worktree .env, etc.) |
   | Dep bump that violates pin policy | edited HARD-pin requirement file |

2. **Cross-check each candidate against open PM:**
   - Call `library:pm:query` with `status=To Do` + `In Progress` for active project key
   - For each candidate, grep summaries + descriptions for keyword overlap (table name, file path, ticket-ID reference)
   - If candidate maps to existing ticket → skip (tracked)
   - If candidate has no match → it's a gap

3. **Surface the gap list to operator BEFORE filing.** Format:

   ```
   ## Gap detection — N untracked items
   | # | Gap | Suggested ticket title | Labels |
   |---|---|---|---|
   | 1 | <symptom> | <imperative title> | follow-up,<area> |
   ```

   Ask: "File these N tickets in `<PROJECT_KEY>`? (yes / cherry-pick: 1,3,5 / no)"

4. **On operator yes / cherry-pick:** call `library:pm:create_task` for each accepted gap. Description must include:
   - **Detected during:** `<this checkpoint slug>` YYYY-MM-DD
   - **Source signal:** the literal grep / commit / file that triggered detection
   - **Action:** specific repair steps
   - **Labels:** always include `follow-up` + 1-2 area tags (e.g. `db-migration`, `tf-audit`, `test-cleanup`, `security-audit`)

5. **Append filed ticket IDs to the checkpoint file** under a new section `## Gap follow-ups filed` so the next session sees them at the same level as accomplished/blockers.

#### Hard rules for gap detection

- Never silently skip surfacing a gap. If unsure, surface it + let operator decide.
- Never auto-file without operator approval (default `no`-on-empty).
- Cherry-pick mode allowed: operator types `1,3,5` to file a subset.
- One ticket per gap — do not stack multiple unrelated fixes in one ticket body.
- If the gap lacks a clear repair path, file it anyway with `## Open question:` block — better tracked than forgotten.

### Step 7: Confirm

Report to user:
> "Checkpoint written to `<path>`. Memory updated. [N PM tasks updated.] The next session should start by reading that file. Anything to add?"

Wait for user confirmation.

## Resume from Checkpoint

When invoked with "resume" intent or when starting a new session:

### Step R1: List Checkpoints

Call `library_checkpoint_list` to show recent checkpoints with dates and status.

### Step R2: Select Checkpoint

Present the list and let user pick one to load. If only one recent checkpoint exists, offer to load it directly.

### Step R3: Load Checkpoint

Call `library_checkpoint_read(path)` to display checkpoint content.

### Step R4: Resume

Resume from the checkpoint's "What's Next" section. Read referenced files and re-establish context before proceeding with the next actions.

## Quality Gates

- **No vague actions.** "Continue working on X" is not valid. Be specific.
- **No assumed context.** Write as if the next reader has zero memory.
- **Fresh git state.** Run `git status` now, don't reuse earlier observations.
- **Absolute paths.** No ambiguous references.
- **Decisions include rationale.** Not just "chose X" but "chose X because Y."

## Token Budget

**Weight:** Medium
**Estimated context cost:** ~1500 tokens
**Subagent delegation:** No

## Storage Location (Hard Rule)

Checkpoints **always** live under the Reading Room. By default the file is written to `<reading_room.path>/checkpoints/`. An explicit `checkpoints.path` in `library-config.yaml` is allowed but must resolve under `reading_room.path` — anything else is rejected with an error. There is no silent fallback to the MCP server's CWD.

## MCP Tools Used

- `library:checkpoint:write` — write structured checkpoint file
- `library:checkpoint:list` — list recent checkpoints (for resume flow)
- `library:checkpoint:read` — read a specific checkpoint (for resume flow)
- `library:pm:update` — comment on PM tasks (if PM configured)
- `library:pm:sync` — check for orphaned work (if PM configured)
- `library:pm:query` — find existing tickets to cross-check candidate gaps (Step 6)
- `library:pm:create_task` — file new tickets for accepted gaps (Step 6)
