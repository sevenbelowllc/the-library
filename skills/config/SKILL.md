---
name: config
description: "Set up and configure The Library. Run on first use or to update settings. Handles vault initialization, PM provider selection, Graphify toggle, and dependency validation."
---

# library:config — Setup & Configuration

Configure The Library for your project. Run this first.

## When to Use

- First time using The Library in a project
- Changing PM provider (Jira/Linear)
- Enabling/disabling Graphify
- After installing optional dependencies

## First-Run Flow

If no `library-config.yaml` exists in the project root, walk through setup:

### Step 0: Reading Room
Ask: "Where is your Reading Room? (path to existing repo/directory, or 'create' to scaffold one)"
- The Reading Room is where specs, plans, and checkpoints live — it can be a dedicated repo or a directory at the project root.
- If existing path: validate it exists and contains expected structure (e.g., `docs/specs/`), set `reading_room.path`
- If "create": ask for path, scaffold the Reading Room directory structure (docs/specs/, docs/plans/, docs/checkpoints/)

### Step 1: Specs Path
Ask: "Where are your canonical spec files? (path, or 'none' to skip)"
- If path provided: validate it exists, set `specs.path`
- If "none": omit specs section

### Step 2: Vault
Ask: "Where is (or should be) your knowledge vault? (path, or 'create new')"
- If existing path: validate structure with `library_vault_validate`
- If "create new": ask for path, then run `library_vault_init`
- After vault init, ask: "Want to ingest sources now?" If yes, enter batch ingest loop (see library:ingest --batch)

### Step 3: PM Provider
Ask: "What PM tool do you use? (jira / linear / none)"
- If jira: verify Atlassian MCP is connected. Ask for project keys.
- If linear: ask for API key. Ask for team IDs.
- If none: skip PM setup

### Step 4: Graphify
Ask: "Do you want Graphify for cross-document relationship queries? (yes / no)"
- If yes: check `graphifyy` is installed. If not, suggest `pip install the-library[graphify]`
- Set port, mode, auto_rebuild defaults

### Step 5: Write Config
- Write `library-config.yaml` to project root
- Run `library_config_get` to display final config
- Run validation: `validate_config` — display any warnings

### Step 6: Register MCP Server
- Add `library-server` to Claude Code MCP settings
- If Graphify enabled, add `graphify` sidecar to MCP settings

## Update Flow

If `library-config.yaml` exists, show current config and ask what to change:
- "Current config loaded. What would you like to update?"
- Use `library_config_set` for individual changes
- Re-run validation after changes

## Vault Init Mode

When called with `--init-vault` argument:
1. Ask for vault path
2. Run `library_vault_init`
3. Chain into `library:ingest --batch`

## MCP Tools Used

- `library_config_get` — read current config
- `library_config_set` — update values
- `library_vault_init` — scaffold vault (if creating new)
- `library_vault_validate` — check existing vault
