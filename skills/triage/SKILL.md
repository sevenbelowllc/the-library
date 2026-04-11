---
name: triage
description: "Scan vault for [VERIFY], [CONFLICT], [PLANNED] tags and create PM tasks from them. Deduplicates against existing tasks."
---

# library:triage — Tag-Driven Task Creation

Turn vault tags into tracked PM tasks.

## When to Use

- After `library:compile` generates new wiki articles with tags
- After `library:ingest` adds new sources that may affect wiki
- Periodically to catch any untracked tags

## Process

### Step 1: Scan Tags
Call `library_vault_parse` to get all tags.

### Step 2: Map to Projects
For each tag, determine target PM project based on:
- Wiki article domain (from frontmatter)
- Tag content keywords
- Ask user if ambiguous

### Step 3: Deduplicate
For each candidate task:
- Call `library_pm_query` to check for existing tasks with similar summary
- Skip if duplicate found

### Step 4: Draft Tasks
Present list of proposed tasks:
```
1. [VERIFY] Security — JWT validation works → COS task
2. [CONFLICT] Frameworks — Feb vs March schema status → COS task
3. [PLANNED] Notifications — scheduled for Q3 → COS task
```

### Step 5: Create (with approval)
Ask: "Create these N tasks? (yes / no / select)"
- If yes: call `library_pm_create_task` for each
- If select: let user pick which ones

### Step 6: Clear Tags
After task creation, remove the tag from the wiki article.
The tag's lifecycle: tag in vault → task in PM → tag removed.

## MCP Tools Used

- `library_vault_parse` — scan tags
- `library_pm_query` — deduplicate
- `library_pm_create_task` — create tasks
- `library_config_get` — project mapping
