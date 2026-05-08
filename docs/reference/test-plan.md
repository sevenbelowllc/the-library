# The Library -- Test Plan

## Overview

This document covers the test strategy for The Library MCP server, including
all modules: vault builder, PM integration (Jira and Linear), knowledge graph,
memory management, checkpoint system, and supporting utilities.

**Current stats (as of 2026-04-16):**

- **Total tests:** 746
- **Overall coverage:** 94.11%
- **Coverage floor:** 88% (enforced via `pytest-cov` -- builds fail below this threshold)

---

## Running Tests

Coverage is configured automatically via `pyproject.toml`. A single command runs
all tests with coverage reporting:

```bash
python -m pytest
```

This runs all unit tests with coverage collection enabled. No extra flags needed.

For verbose output:

```bash
python -m pytest -v
```

To run a single test file:

```bash
python -m pytest tests/test_jira_client.py -v
```

To run integration tests (requires credentials):

```bash
ATLASSIAN_EMAIL=you@example.com JIRA_API_TOKEN=tok \
    python -m pytest tests/test_jira_integration.py -v
```

---

## Coverage Summary

### Module-by-Module Highlights

| Module Area | Key Files | Approximate Coverage |
|-------------|-----------|---------------------|
| PM / Jira Client | `pm/jira_client.py`, `pm/jira.py` | 96%+ |
| PM / Linear Adapter | `pm/linear.py` | 90%+ |
| Vault Builder Core | `vault_builder/orchestrator.py`, `vault_builder/output.py` | 95%+ |
| Vault Builder Extractors | `vault_builder/extractors/*.py` | 93%+ |
| Vault Builder Config | `vault_builder/config.py`, `vault_builder/registry.py` | 97%+ |
| Knowledge Graph | `graph/` | 92%+ |
| Memory Management | `memory/` | 94%+ |
| Checkpoint System | `checkpoint/` | 93%+ |
| MCP Server / Tools | `server.py`, `tools/` | 90%+ |
| Config Loading | `config.py`, `types.py` | 96%+ |

### Coverage Floor Enforcement

The 88% coverage floor is configured in `pyproject.toml` via `pytest-cov`. Any
PR or local test run that drops coverage below 88% will fail. The project
currently sits at 94.11%, well above the floor.

---

## Unit Tests (all mocked)

| Module | File | Tests | Coverage Notes |
|--------|------|-------|----------------|
| JiraClient | `tests/test_jira_client.py` | 27 | Auth, all 16 API methods, error handling, URL normalisation |
| JiraAdapter | `tests/test_pm_adapter.py` | 16 | Type mapping, JQL construction, status categorisation |
| LinearAdapter | `tests/test_pm_adapter.py` | 4 (stubs) | Interface compliance, placeholder tests |
| Vault builder extractors | `tests/vault_builder/` | 13 | Extraction, trust scores, frontmatter generation |
| Hooks client | `tests/test_hooks/` | 3 | Wrapper, error handling, missing env vars |
| All other modules | `tests/` | 683+ | Server tools, config, memory, graph, checkpoint, types |

**Total unit tests: 746 (all pass, fully mocked)**

---

## Integration Tests

**File:** `tests/test_jira_integration.py`

These tests call the real Jira Cloud REST API at `https://sevenbelow.atlassian.net`.
They are automatically skipped when credentials are not set.

### Prerequisites

- `ATLASSIAN_EMAIL` -- Atlassian account email with access to the sevenbelow site
- `JIRA_API_TOKEN` -- API token generated at https://id.atlassian.com/manage-profile/security/api-tokens
- Project `DEIOCAP` must exist on the Jira site

### Skip condition

Tests are skipped unless both `ATLASSIAN_EMAIL` and `JIRA_API_TOKEN` are set in the
environment.

### Test inventory

| # | Test | What it verifies |
|---|------|-----------------|
| 1 | `test_auth_get_myself` | Auth works; response contains `accountId` and `displayName` |
| 2 | `test_list_projects` | `list_projects()` returns a `values` list |
| 3 | `test_create_and_get_project` | Creates project with `ZZT*` key, retrieves it, key matches |
| 4 | `test_create_and_get_issue` | Creates Task in DEIOCAP, fetches it, fields match |
| 5 | `test_search_issues` | JQL `project = DEIOCAP` returns `issues` list |
| 6 | `test_add_comment` | Creates issue, adds comment, comment has `id` |
| 7 | `test_get_transitions` | Creates issue, lists transitions, `transitions` is a list |
| 8 | `test_transition_issue` | Creates issue, executes first available transition |
| 9 | `test_assign_issue` | Creates issue, assigns to self via `get_myself` |
| 10 | `test_issue_linking` | Creates two issues, gets link types, links them |

### Cleanup strategy

- Issues are labelled `integration-test` and prefixed `INTEGRATION-TEST-DELETE-ME`
- Each test attempts to transition its issues to Done in a `finally` block
- Projects created use key prefix `ZZT` and name prefix `INTEGRATION-TEST-DELETE-ME`
- Periodic manual cleanup: JQL `labels = integration-test AND status != Done`

---

## Manual Verification Checklist

Use this when validating the full flow end-to-end after a release or
significant refactor.

- [ ] **Auth:** `get_myself()` returns account info
- [ ] **List projects:** returns existing DEIOCAP
- [ ] **Create project:** creates a new project with correct key
- [ ] **Create issue:** Task created in correct project
- [ ] **Create epic:** Epic created with correct type
- [ ] **Search:** JQL returns results
- [ ] **Transition:** issue moves to new status
- [ ] **Comment:** comment appears on issue
- [ ] **Assign:** issue assigned to user
- [ ] **Link:** two issues linked
- [ ] **Vault builder:** extractor fetches issues via JiraClient
- [ ] **MCP tools:** `library_pm_list_projects` returns data

---

## Test Pyramid

```
         /  Manual  \          <- 12 checklist items (as needed)
        / Integration \        <- 10 tests (real API, skipped in CI)
       /  Unit (mocked) \      <- 746 tests (fast, always run)
      ---------------------
```

### CI behaviour

- **Unit tests** run on every push (no credentials required)
- **Integration tests** skipped in CI by default (no `ATLASSIAN_EMAIL`/`JIRA_API_TOKEN`)
- To run integration tests in CI, add the secrets to the pipeline environment
- **Coverage gate:** 88% minimum enforced by `pytest-cov` in `pyproject.toml`

---

## Adding new tests

1. **Unit test** every new method in the relevant test file
2. **Adapter test** for type mapping/JQL in `tests/test_pm_adapter.py`
3. **Integration test** for end-to-end API verification in `tests/test_jira_integration.py`
4. Maintain the 88% coverage floor -- check with `python -m pytest` before committing
5. Update this plan if the test inventory changes significantly
