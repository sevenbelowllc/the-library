---
name: sync
description: "Sync project state from Jira or Linear. Reports open, stale, blocked, and recently closed tasks. Compares PM state against vault tags."
---

# library:sync — PM State Sync

Pull current project state from the configured PM tool.

## When to Use

- Start of a session to understand current state
- After completing work to check what's left
- Periodically to detect stale or stuck tasks

## Process

### Step 1: Pull PM State
For each project in config `pm.projects`:
- Call `library:pm:sync` with project key
- Collect: open tasks, stale tasks, blocked tasks, recently closed

### Step 2: Cross-Reference Vault
Call `library:vault:parse` for `[VERIFY]` tags.
Compare: items marked `[VERIFY]` in vault but status=closed in PM → flag as "closed without verification."

### Step 3: Detect Stale Tasks
Tasks with no update in >14 days → flag as stale.
Tasks blocked for >7 days → flag for escalation.

### Step 4: Report
Present formatted summary per project:
- Open: N tasks
- Blocked: N tasks (list them)
- Stale: N tasks (list them)
- Recently closed: N tasks
- Vault conflicts: N items closed without verification

### Step 5: Push (optional)
If vault has items not tracked in PM:
- Ask: "Found N vault items not in PM. Create draft tasks?"
- If yes, call `library:pm:create_task` for each

## MCP Tools Used

- `library:pm:sync` — pull PM state
- `library:vault:parse` — vault tag cross-reference
- `library:pm:create_task` — push untracked items (optional)
- `library:config:get` — project list
