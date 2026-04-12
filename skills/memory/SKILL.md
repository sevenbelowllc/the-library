---
name: memory
description: "Memory lifecycle management. Prune stale entries, validate references, aggregate related memories, detect conflicts, track age. Garbage collection for the knowledge layer."
---

# library:memory — Memory Lifecycle

Maintain memory health across sessions.

## When to Use

- Periodically (every few sessions) to prevent memory rot
- When memory index is getting long (approaching 200 lines)
- When you suspect stale or conflicting memories
- After major project changes (renames, restructuring)

## Operations

### Scan
Call `library:memory:scan` to get full report:
- All memory entries with metadata
- Stale entries (not modified in >N days)
- Total count

Present report to user.

### Validate
For each memory entry:
1. If it references a file path → check the file exists (use Glob/Read)
2. If it references a function or flag → grep for it
3. If it references a project decision → check if decision still holds in specs

Flag entries that reference nonexistent things.

### Aggregate
Call `library:memory:aggregate` with `dry_run=True` first:
- Review merge suggestions
- Present to user for approval
- If approved, call with `dry_run=False`

### Prune
Call `library:memory:prune` with `dry_run=True` first:
- Review candidates for deletion
- Present to user for approval
- If approved, call with `dry_run=False`

### Conflict Detection
Compare memory entries against:
- Each other (two memories saying different things about same topic)
- Current code state (memory says X, code shows Y)
- Canonical specs (memory says X, spec says Z)

Report conflicts for manual resolution.

### Health Report
Call `library:memory:health` to get:
- Vault stats (file count, domain count, decision count)
- Keyword accuracy per domain
- CLAUDE.md line count
- Present as formatted report to user

### Learning Report
Call `library:memory:learn` to get:
- Per-domain accuracy with hit/miss/noise counts
- Drift detection results
- Propose keyword changes to user (HITL — user approves each change)
- Apply approved changes by editing domain file frontmatter

### Optimize
Call `library:memory:scan` on ~/.claude/projects/*/memory/:
- Identify stale Claude auto-memories (>30 days, low reference)
- Propose offloading to vault wiki articles (HITL per entry)
- Remove migrated entries from Claude memory, keep pointer in MEMORY.md

## Safety

- **Always dry_run first.** Never delete without showing candidates.
- **User confirms destructive operations.** Prune and aggregate require explicit approval.
- **Archive, don't destroy.** Move pruned memories to an archive section rather than deleting.

## MCP Tools Used

- `library:memory:scan` — scan all memories
- `library:memory:aggregate` — find merge opportunities
- `library:memory:prune` — remove stale entries
- `library:config:get` — memory path and thresholds
- `library:memory:health`
- `library:memory:learn`
