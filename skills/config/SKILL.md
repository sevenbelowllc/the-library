---
name: config
description: "Set up and configure The Library. Run on first use or to update settings. Handles Reading Room setup, vault initialization, PM provider selection, Graphify toggle, branding, and MCP registration."
---

# library:config — Setup & Configuration

Configure The Library for your project. Run this first.

## When to Use

- First time using The Library in a project
- Managing a specific domain: `library:config branding`, `library:config vault`, `library:config pm`, `library:config graphify`, `library:config mcp`
- After installing optional dependencies

## Conventions (not configurable)

The Library enforces a standard Reading Room structure. These are conventions, not user choices:

- `specs/` — canonical spec files, always at Reading Room root
- `plans/` — implementation plans, always at Reading Room root
- `checkpoints/` — session checkpoints, always at Reading Room root
- Checkpoint format: `YYYY-MM-DD-HH-MM-SS-<topic>-checkpoint.md`
- Memory index: `MEMORY.md` with 200-line max, 30-day stale threshold

## First-Run Flow

If no `library-config.yaml` exists in the project root, walk through setup:

### Step 1: Reading Room

Ask: "Where is your Reading Room? (path to existing repo/directory, or 'create' to scaffold one)"

- The Reading Room is the centralized home for your project's canonical documents — specs, plans, checkpoints, and optionally branding. All repos in your project reference this one location.
- **Recommend a dedicated repo** — "We recommend creating a dedicated repo for your Reading Room. This keeps canonical documents versioned independently from your application code, and works best for multi-repo projects."
- If existing path: validate it exists, check for `specs/` directory
- If "create": ask for path, scaffold: `specs/`, `plans/`, `checkpoints/`
- Set `reading_room.path` and `reading_room.type` ("repo" or "directory")

### Step 2: Branding

Ask: "Do you want a centralized branding location in your Reading Room? This gives all your repos a single source of truth for brand kit, logos, colors, and design tokens. (yes / later / no)"

- If **yes** + they have existing assets: ask for the path, copy into `branding/`
- If **yes** + they want to create one now: scaffold `branding/` with a starter brand kit. Ask: "What's your brand name?", "Primary brand color (hex)?", "Do you have a logo file? (path or skip)". Generate a baseline `brandkit.html`.
- If **later**: scaffold empty `branding/` with a `README.md` explaining how to create a brand kit using `ui-ux-pro-max` or `frontend-design` skills. "Run `library:config branding` when you're ready."
- If **no**: skip entirely
- In all "yes/later" cases: set `reading_room.branding` to `"branding"`

### Step 3: Vault

Ask: "Where is (or should be) your knowledge vault? (path, or 'create new')"

- If existing path: validate structure with `library:vault:validate`
- If "create new": ask for path, run `library:vault:init`
- After vault init, ask: "Want to ingest sources now?" If yes, enter batch ingest loop (see `library:ingest --batch`)

### Step 4: PM Provider

Ask: "What PM tool do you use? (jira / linear / none)"

- If jira: verify Atlassian MCP is connected. Ask for project keys.
- If linear: ask for API key. Ask for team IDs.
- If none: skip PM setup

### Step 5: Graphify

Ask: "Do you want Graphify for cross-document relationship queries? (yes / no)"

- If yes: check `graphifyy` is installed. If not, suggest `pip install the-library[graphify]`
- Set port, mode, auto_rebuild defaults

### Step 5.5: Memory Management (automatic — no user input needed)
- Seed domain files from CLAUDE.md using domain seeder
- Create PROJECT-STATE.md in Reading Room
- Create SESSION.md directory at ~/.library/sessions/
- Install hooks in .claude/settings.json
- Configure status line
- Initialize routing journal
- Display: "Memory management active. Auto-learning enabled."

### Step 6: Write Config & Register MCP

- Write `library-config.yaml` to project root
- Register `library` in Claude Code MCP settings
- If Graphify enabled, add `graphify` sidecar to MCP settings
- Run validation, display any warnings
- Display final config summary

## Subcommands

Each subcommand manages a specific domain independently. The base `library:config` (no args) runs the full wizard. Subcommands let you revisit any area without re-running everything.

### `library:config branding`

1. **Report current state:**
   - If `branding/` exists with files: list contents, note whether `brandkit.html` is present
   - If `branding/` exists but empty: "Branding directory scaffolded but not populated yet"
   - If no branding configured: "Branding is not set up"

2. **Offer options:**
   - **A) Add existing assets** — "Have brand assets to add? (path to files or directory)" → copy into `branding/`
   - **B) Create a brand kit** — Ask brand name, primary color, logo file. Generate baseline `brandkit.html`. Recommend `ui-ux-pro-max` for full design systems and `frontend-design` for component-level design.
   - **C) Come back later** — Scaffold empty `branding/` with a README. "Run `library:config branding` again when ready."

### `library:config vault`

1. **Report current state:**
   - If vault exists: run `library:vault:validate`, report structure health, source count, wiki article count
   - If no vault configured: "No vault configured"

2. **Offer options:**
   - **A) Validate** — run `library:vault:validate`, display results
   - **B) Ingest sources** — chain into `library:ingest --batch`
   - **C) Create new vault** — ask for path, run `library:vault:init`
   - **D) Change vault path** — update config to point at a different vault

### `library:config pm`

1. **Report current state:**
   - Show current provider and project keys
   - If Jira: verify Atlassian MCP connection is working
   - If Linear: verify API key is valid
   - If none: "No PM provider configured"

2. **Offer options:**
   - **A) Switch provider** — walk through new provider setup (jira / linear / none)
   - **B) Add/remove project keys** — modify the project list
   - **C) Test connection** — verify MCP or API connectivity

### `library:config graphify`

1. **Report current state:**
   - Enabled/disabled, whether `graphifyy` CLI is installed
   - If enabled: show graph path, mode, port, last rebuild time

2. **Offer options:**
   - **A) Enable** — check installation, set defaults, add MCP sidecar
   - **B) Disable** — remove MCP sidecar, set `enabled: false`
   - **C) Rebuild graph** — trigger `library:graph:rebuild`
   - **D) Change settings** — mode (deep/shallow), port, auto_rebuild

### `library:config mcp`

1. **Report current state:**
   - Check if `library` is registered in Claude Code MCP settings
   - Check if Graphify sidecar is registered (if enabled)
   - Show server command and any environment variables

2. **Offer options:**
   - **A) Register** — add `library` to MCP settings
   - **B) Unregister** — remove from MCP settings
   - **C) Re-register** — remove and re-add (useful after upgrades)
   - **D) Status check** — verify server can start, test tool availability

## Update Flow

If `library-config.yaml` exists and no subcommand is given, show current config and ask what to change:
- "Current config loaded. What would you like to update?"
- Use `library:config:set` for individual changes
- Re-run validation after changes

## MCP Tools Used

- `library:config:get` — read current config
- `library:config:set` — update values
- `library:vault:init` — scaffold vault (if creating new)
- `library:vault:validate` — check existing vault
- `library:graph:rebuild` — rebuild Graphify graph
