# Contributing to The Library

Thanks for your interest in contributing! This guide covers everything you need to get started.

## Development Setup

```bash
# Clone the repo
git clone https://github.com/sevenbelowllc/the-library.git
cd the-library

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

## Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=library_server --cov-report=term-missing

# Single test file
pytest tests/test_config.py

# Watch mode (requires pytest-watch)
ptw
```

## Project Structure

```
src/library_server/       # Main package
  cli.py                  # CLI commands (library init/validate/doctor)
  server.py               # MCP server and tool definitions
  config.py               # Configuration loading and validation
  checkpoint/             # Session checkpoint management
  graph/                  # Graphify knowledge graph orchestration
  hooks/                  # Claude Code lifecycle hooks
    scripts/              # Hook scripts (session_start, prompt_scan, etc.)
  memory/                 # Memory Management Unit (MMU)
  pm/                     # PM adapters (Jira, Linear)
  state/                  # Project and session state parsing
  vault/                  # Vault operations
  vault_builder/          # Vault builder pipeline
    extractors/           # Source extraction plugins
skills/                   # Claude Code skill definitions (11 skills)
tests/                    # Test suite
```

## Code Style

- Python 3.10+ with type hints
- Use `from __future__ import annotations` in all modules
- Follow existing patterns in the codebase
- No hardcoded paths — use config or `~/.library/` conventions

## Naming Conventions

Everything uses `library:` as the namespace:

| Layer | Convention | Example |
|-------|-----------|---------|
| Shell CLI | `library <subcommand>` | `library init` |
| Skills | `library:<skill>` | `library:config` |
| MCP tools | `library:<module>:<action>` | `library:config:get` |

## Pull Request Process

1. Fork the repo and create a feature branch from `main`
2. Write tests for new functionality
3. Ensure all tests pass: `pytest`
4. Ensure coverage doesn't drop: `pytest --cov=library_server`
5. Open a PR with a clear description of what changed and why

## Adding a New MCP Tool

1. Add the tool function in `src/library_server/server.py`
2. Use the `@mcp.tool(name="library:<module>:<action>")` decorator
3. Add tests in `tests/`
4. Update the MCP tools table in `README.md`

## Adding a New Skill

1. Create `skills/<name>/SKILL.md` with frontmatter:
   ```markdown
   ---
   name: <name>
   description: "One-line description"
   ---
   ```
2. Document: When to Use, Process, MCP Tools Used
3. Reference MCP tools by their `library:*` names

## Adding a New Extractor (Vault Builder)

1. Create `src/library_server/vault_builder/extractors/<name>.py`
2. Extend `BaseExtractor` from `extractors/base.py`
3. Register in `server.py`'s `_get_vault_orchestrator()`
4. Add tests in `tests/vault_builder/extractors/`

## Reporting Issues

Use [GitHub Issues](https://github.com/sevenbelowllc/the-library/issues). Include:
- What you expected vs. what happened
- Output of `library validate`
- Python version (`python3 --version`)
- OS

## Testing standard

This repo follows the SevenBelow Compliance OS
[Testing Standard](https://github.com/sevenbelowllc/compliance-os/blob/main/library-reading-room/standards/TESTING-STANDARD.md)
(`library-reading-room/standards/TESTING-STANDARD.md`). Highlights:

- **Line coverage floor: 90%.** Behavioural coverage is the rule — every
  error path must be asserted, every state transition walked.
- **Coverage ratchet.** CI compares current coverage to
  `coverage-baseline.txt`. Any drop fails the build.
  - Enforce: `bin/library-coverage-ratchet`
  - Bump baseline (after an intentional improvement):
    `bin/library-coverage-ratchet --bump`
- **Mutation smoke.** Critical adapters and state-machine code must pass
  mutation testing — `src/library_server/pm/` is currently in scope.
  Strategies: flip conditional (`==` <-> `!=`), remove `assert`/`raise`,
  flip boolean literal. If any mutant survives, add a negative test.
  - Run: `bin/library-mutation-smoke`
  - List candidates without running: `bin/library-mutation-smoke --list`
- **Cleanup is mandatory.** Every test that creates external state
  (Jira tickets, projects, DB rows, GCS objects) must register teardown
  that runs on pass, fail, timeout, and SIGINT. Use `try/finally` in
  `yield`-based pytest fixtures — see `tests/test_jira_integration.py`
  for the canonical `jira_cleanup` pattern.
- **Pollution scan.** `bin/library-pm-pollution-scan` (dry-run by
  default) surfaces stale `INTEGRATION-TEST` / `DELETE-ME` / `ZZT*`
  artefacts older than 24h. `--execute` requires interactive
  confirmation.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
