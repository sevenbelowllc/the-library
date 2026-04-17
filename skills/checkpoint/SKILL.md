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

### Step 6: Confirm

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

## MCP Tools Used

- `library:checkpoint:write` — write structured checkpoint file
- `library:checkpoint:list` — list recent checkpoints (for resume flow)
- `library:checkpoint:read` — read a specific checkpoint (for resume flow)
- `library:pm:update` — comment on PM tasks (if PM configured)
- `library:pm:sync` — check for orphaned work (if PM configured)
