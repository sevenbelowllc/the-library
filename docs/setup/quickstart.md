# Quickstart

Get The Library running in under five minutes.

## 1. Install

```bash
pip install the-library
```

Optional extras:

```bash
pip install the-library[linear]    # Linear PM adapter
pip install the-library[graphify]  # Graphify knowledge graph
pip install the-library[all]       # Everything
```

## 2. Initialize Your Project

```bash
cd your-project
library init
```

`library init` creates everything in one step:

| What | Where |
|------|-------|
| Config file | `library-config.yaml` |
| Reading Room | `reading-room/` (specs, plans, checkpoints) |
| Vault | `vault/` (Obsidian-native knowledge base) |
| Domain manifests | `vault/domains/` |
| Session files | `SESSION.md`, `PROJECT-STATE.md` |
| Lifecycle hooks | `.claude/settings.json` hooks block |

No manual steps. Run it once.

## 3. Install the Claude Code Plugin (Optional)

For the full skill suite inside Claude Code:

```bash
claude plugins install sevenbelowllc/the-library
```

This installs 11 skills (`library:config`, `library:ingest`, `library:compile`, etc.) and wires the MCP server into your Claude Code session.

## 4. Configure PM Integration (Optional)

If you use Jira or Linear, configure the PM adapter:

**Interactive (recommended):**

```bash
# In Claude Code
library:config
```

**Manual:**

Edit `library-config.yaml` directly:

```yaml
pm:
  provider: jira          # or: linear
  site_url: https://your-org.atlassian.net
  projects:
    - key: MYPROJECT
      name: My Project
```

- Jira setup: see [jira-setup.md](jira-setup.md)
- Linear setup: see [linear-setup.md](linear-setup.md)

## 5. Verify

```bash
# Check config and structure
library validate

# Auto-fix common issues
library doctor
```

`library validate` checks your config schema, vault structure, and hook wiring. `library doctor` detects and repairs common problems (missing directories, stale hooks, missing env vars).

## Next Steps

- Run `library:ingest` to add source material to the vault
- Run `library:compile` to build wiki articles from sources
- Run `library:query` to ask the Librarian questions
- Run `library:sync` to pull PM state from Jira or Linear
