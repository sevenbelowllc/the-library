# The Library -- Test Plan

## Overview

This document covers the test strategy for The Library's PM integration layer,
focusing on the Jira Cloud REST API client, adapter, and supporting modules.

---

## Unit Tests (existing -- all mocked)

| Module | File | Tests | Coverage |
|--------|------|-------|----------|
| JiraClient | `tests/test_jira_client.py` | 27 | Auth, all 16 API methods, error handling, URL normalisation |
| JiraAdapter | `tests/test_pm_adapter.py` | 16 | Type mapping, JQL construction, status categorisation |
| LinearAdapter | `tests/test_pm_adapter.py` | 4 (stubs) | Interface compliance, placeholder tests |
| Vault builder extractor | `tests/vault_builder/` | 13 | Extraction, trust scores, frontmatter generation |
| Hooks client | `tests/test_hooks/` | 3 | Wrapper, error handling, missing env vars |

**Total unit tests: ~594 (all pass, fully mocked)**

Run all unit tests:

```bash
python -m pytest tests/ -v --ignore=tests/test_jira_integration.py
```

---

## Integration Tests (new)

**File:** `tests/test_jira_integration.py`

These tests call the real Jira Cloud REST API at `https://sevenbelow.atlassian.net`.
They are automatically skipped when credentials are not set.

### Prerequisites

- `JIRA_EMAIL` -- Atlassian account email with access to the sevenbelow site
- `JIRA_API_TOKEN` -- API token generated at https://id.atlassian.com/manage-profile/security/api-tokens
- Project `DEIOCAP` must exist on the Jira site

### Skip condition

Tests are skipped unless both `JIRA_EMAIL` and `JIRA_API_TOKEN` are set in the
environment.

### Run command

```bash
JIRA_EMAIL=you@example.com JIRA_API_TOKEN=tok \
    python -m pytest tests/test_jira_integration.py -v
```

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
       /  Unit (mocked) \      <- 594 tests (fast, always run)
      ---------------------
```

### CI behaviour

- **Unit tests** run on every push (no credentials required)
- **Integration tests** skipped in CI by default (no `JIRA_EMAIL`/`JIRA_API_TOKEN`)
- To run integration tests in CI, add the secrets to the pipeline environment

---

## Adding new tests

1. **Unit test** every new JiraClient method in `tests/test_jira_client.py`
2. **Adapter test** for type mapping/JQL in `tests/test_pm_adapter.py`
3. **Integration test** for end-to-end API verification in `tests/test_jira_integration.py`
4. Update this plan if the test inventory changes significantly
