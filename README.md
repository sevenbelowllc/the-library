# The Library

Open-source meta-system for AI-assisted project management. Session continuity, knowledge management, and PM tracking through a Claude Code skill suite backed by an MCP server.

## What It Does

| Component | What It Is |
|-----------|-----------|
| **The Library** | The system — 11 skills + MCP server + config |
| **The Reading Room** | Your project's working area — specs, plans, checkpoints, project assets (repo or directory) |
| **The Vault** | Knowledge base — Obsidian-native (wikilinks, tags), Karpathy 3-layer pattern |
| **Graphify** | Card catalog — cross-document relationship queries (optional) |
| **PM Adapter** | Circulation desk — configurable Jira or Linear integration |

## Install

```bash
pip install the-library
```

Optional dependencies:
```bash
pip install the-library[linear]    # Linear PM adapter
pip install the-library[graphify]  # Graphify knowledge graph
pip install the-library[all]       # Everything
```

## Quick Start

```bash
# Install the Claude Code plugin
claude plugins install sevenbelowllc/the-library

# Configure (interactive setup)
# In Claude Code, run:
library:config
```

The config wizard asks 5 questions:
1. Where is your Reading Room? (repo or directory for specs, plans, checkpoints)
2. Where are your specs?
3. Where is your knowledge vault?
4. What PM tool do you use?
5. Do you want Graphify?

### Reading Room Setup

The Reading Room is where your project's "books" live — canonical specs, implementation plans, session checkpoints, and project assets. It can be:

- **A dedicated repo** — for multi-repo projects where specs span multiple codebases
- **A directory at the repo root** — for monorepos (e.g., `reading-room/` or `.library/`)

## Skills

| Skill | Purpose |
|-------|---------|
| `library:config` | Setup and configuration |
| `library:ingest` | Add source material to the vault |
| `library:compile` | Compile wiki articles from sources |
| `library:query` | Ask the Librarian questions |
| `library:memory` | Memory lifecycle management |
| `library:sync` | PM state sync |
| `library:triage` | Turn vault tags into PM tasks |
| `library:plan` | Convert specs into PM epics/tasks |
| `library:audit` | Spec vs code gap analysis |
| `library:review` | Completion validation |
| `library:checkpoint` | Session state capture |

## MCP Server

The Library runs as an MCP server exposing 20 tools across 6 modules:

| Module | Tools |
|--------|-------|
| Config | `library_config_get`, `library_config_set` |
| Vault | `library_vault_init`, `library_vault_validate`, `library_vault_parse`, `library_vault_ingest` |
| PM | `library_pm_create_task`, `library_pm_create_epic`, `library_pm_sync`, `library_pm_update`, `library_pm_query` |
| Memory | `library_memory_scan`, `library_memory_aggregate`, `library_memory_prune` |
| Checkpoint | `library_checkpoint_write`, `library_checkpoint_read`, `library_checkpoint_list` |
| Graph | `library_graph_rebuild`, `library_graph_query`, `library_graph_path` |

```bash
# Run standalone
library-server

# Or configure in Claude Code settings
```

## Configuration

See `library-config.example.yaml` for all options.

## Memory Management Unit (v0.2.0)

The Library includes a Memory Management Unit (MMU) that prevents contextual drift across AI-assisted development sessions.

### How It Works

- **800 token baseline** — Injects minimal project context at session start (PROJECT-STATE.md + SESSION.md)
- **Demand-paged** — Domain-specific context loaded only when keyword patterns match your prompts
- **Zero-token hooks** — 6 lifecycle hooks run programmatically, never consuming LLM tokens
- **Auto-learning** — Observes which context injections help and which are noise, proposes improvements over time
- **Crash recovery** — Stop hook heartbeat updates SESSION.md every turn, max 1 turn lost on crash

### Architecture

```
Context Window (RAM)          Hooks (Interrupt Handlers)       Vault (Disk)
├─ CRITICAL ~300 tokens       ├─ SessionStart (boot)           ├─ domains/
├─ FRESH ~500 tokens          ├─ UserPromptSubmit (page fault)  ├─ decisions/
├─ MODERATE 0-1500 tokens     ├─ Stop (heartbeat)              ├─ sessions/
└─ DEEP 0-unlimited           ├─ PreCompact (emergency save)   ├─ sources/raw/
                               ├─ SessionEnd (shutdown)         └─ wiki/
                               └─ StatusLine (monitor)
```

### Setup

The MMU is configured automatically during `library-config` setup. Two questions:
1. Where is your Reading Room?
2. Do you use Jira, Linear, or neither?

Everything else uses smart defaults. Run `/library-config` to customize.

### Spec

Full specification: [MEMORY-MANAGEMENT.md](../library-reading-room/specs/MEMORY-MANAGEMENT.md)

## License

MIT - SevenBelow LLC
