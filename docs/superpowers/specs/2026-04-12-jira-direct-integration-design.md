# Jira Direct Integration — Design Spec

**Date:** 2026-04-12
**Status:** Approved
**Scope:** The Library MCP server — Jira REST API integration

## Problem

The Library's Jira integration currently routes all API calls through the Atlassian MCP server via `_call_mcp()`, which:

1. **Cannot create Jira projects** — the Atlassian MCP's OAuth scopes (`read:jira-work`, `write:jira-work`) don't include project administration
2. **Cannot execute without an LLM agent** — `_call_mcp()` raises `NotImplementedError` because MCP tool invocation requires the Claude Code agent to mediate each call
3. **Duplicates HTTP logic** — the vault builder extractor and hooks client each roll their own Basic Auth + httpx calls to the Jira REST API, separate from the PM adapter
4. **Limits automation** — any background process, hook, or scheduled job that needs Jira data must go through the LLM context window

## Decision

Replace the MCP-mediated approach with a standalone `JiraClient` class that makes direct REST API calls using Basic Auth. All Jira HTTP communication — PM adapter, vault builder extractor, hooks client — consolidates into this single client.

### Why Not the Atlassian MCP?

The Atlassian MCP server is useful for ad-hoc exploration via Claude Code, but is insufficient as a programmatic integration layer:

- **OAuth scope limitations** — no project creation, no admin operations, scopes are fixed by the MCP server author
- **Agent-in-the-loop** — every API call requires the LLM to mediate, consuming tokens and preventing background automation
- **No consolidation** — each consumer (PM adapter, vault builder, hooks) would need its own MCP call wiring
- **Basic Auth is sufficient** — Jira Cloud's REST API v3 works with email + API token, giving full access to all endpoints The Library needs

## Architecture

```
JiraClient (HTTP layer — auth, requests, pagination, errors)
    ├── JiraAdapter (PMAdapter — maps responses to Library types)
    │       ↑
    │   server.py (MCP tools — exposes to Claude Code)
    │
    ├── JiraExtractor (vault builder — issue ingestion)
    │
    └── hooks/jira_client.py (zero-token task lookups)
```

All three consumers share one client class. Auth configured once via env vars.

## Component Design

### 1. `JiraClient` — `src/library_server/pm/jira_client.py`

Standalone async HTTP client. No dependency on Library types or PMAdapter.

**Constructor:**

```python
class JiraClient:
    def __init__(self, site_url: str):
        # Reads JIRA_EMAIL and JIRA_API_TOKEN from env vars
        # Builds Basic Auth header
        # Creates httpx.AsyncClient with base_url and timeout
```

**Error handling:**

```python
class JiraApiError(Exception):
    def __init__(self, status_code: int, message: str, endpoint: str): ...
```

Raised on any non-2xx response. Includes status code, Jira error message, and the endpoint that failed.

**Methods — Projects:**

| Method | REST Endpoint | Purpose |
|--------|--------------|---------|
| `create_project(name, key, project_type_key, lead_account_id, description?)` | `POST /rest/api/3/project` | Create a Jira project |
| `list_projects()` | `GET /rest/api/3/project/search` | List all visible projects |
| `get_project(project_key)` | `GET /rest/api/3/project/{key}` | Get project details |
| `update_project(project_key, **fields)` | `PUT /rest/api/3/project/{key}` | Update project name/description/lead |

**Methods — Issues:**

| Method | REST Endpoint | Purpose |
|--------|--------------|---------|
| `create_issue(project_key, issue_type, summary, description, labels?, parent?, assignee?)` | `POST /rest/api/3/issue` | Create task/epic/bug/story |
| `get_issue(issue_key, fields?)` | `GET /rest/api/3/issue/{key}` | Get issue details |
| `update_issue(issue_key, fields)` | `PUT /rest/api/3/issue/{key}` | Update issue fields |
| `search_issues(jql, fields?, max_results?, start_at?)` | `GET /rest/api/3/search` | JQL search with pagination |
| `assign_issue(issue_key, account_id)` | `PUT /rest/api/3/issue/{key}/assignee` | Assign/reassign |

**Methods — Transitions:**

| Method | REST Endpoint | Purpose |
|--------|--------------|---------|
| `get_transitions(issue_key)` | `GET /rest/api/3/issue/{key}/transitions` | List available transitions |
| `transition_issue(issue_key, transition_id)` | `POST /rest/api/3/issue/{key}/transitions` | Execute a transition |

**Methods — Comments:**

| Method | REST Endpoint | Purpose |
|--------|--------------|---------|
| `add_comment(issue_key, body)` | `POST /rest/api/3/issue/{key}/comment` | Add a comment |

**Methods — Links:**

| Method | REST Endpoint | Purpose |
|--------|--------------|---------|
| `create_issue_link(type_name, inward_key, outward_key)` | `POST /rest/api/3/issueLink` | Link two issues |
| `get_link_types()` | `GET /rest/api/3/issueLinkType` | List available link types |

**Methods — Users:**

| Method | REST Endpoint | Purpose |
|--------|--------------|---------|
| `get_myself()` | `GET /rest/api/3/myself` | Get current user (for lead_account_id) |
| `find_users(query)` | `GET /rest/api/3/user/search` | Search users |

### 2. `JiraAdapter` Rewrite — `src/library_server/pm/jira.py`

Thin wrapper around `JiraClient` that maps responses to Library types.

**Changes from current:**
- Remove `_call_mcp()` entirely
- Constructor creates `JiraClient(site_url)`
- All methods call `self.client.<method>()` and parse into `TaskResult`/`EpicResult`/etc.
- Add new methods for project management, assignment, and linking

### 3. `PMAdapter` Interface Extensions — `src/library_server/pm/adapter.py`

New abstract methods:

```python
@abstractmethod
async def create_project(self, name: str, key: str, description: str = "", lead_account_id: str = "") -> ProjectResult: ...

@abstractmethod
async def list_projects(self) -> list[ProjectResult]: ...

@abstractmethod
async def get_project(self, project_key: str) -> ProjectResult: ...

@abstractmethod
async def update_project(self, project_key: str, name: str = "", description: str = "") -> ProjectResult: ...

@abstractmethod
async def assign_task(self, task_id: str, account_id: str) -> TaskResult: ...

@abstractmethod
async def link_issues(self, type_name: str, inward_key: str, outward_key: str) -> None: ...

@abstractmethod
async def get_link_types(self) -> list[dict]: ...
```

### 4. New Type — `src/library_server/types.py`

```python
@dataclass
class ProjectResult:
    project_id: str
    project_key: str
    name: str
    description: str = ""
    lead: str = ""
    url: str = ""
```

### 5. New MCP Tools — `src/library_server/server.py`

| Tool Name | Parameters | Returns |
|-----------|-----------|---------|
| `library_pm_create_project` | `name, key, description?, project_type_key?` | `{project_key, name, url}` |
| `library_pm_list_projects` | (none) | `{count, projects[]}` |
| `library_pm_get_project` | `project_key` | `{project_key, name, description, lead, url}` |
| `library_pm_update_project` | `project_key, name?, description?` | `{project_key, name, url}` |
| `library_pm_assign_task` | `task_id, account_id` | `{task_id, status}` |
| `library_pm_link_issues` | `type_name, inward_key, outward_key` | `{status}` |
| `library_pm_get_link_types` | (none) | `{types[]}` |

### 6. Linear Adapter Stubs — `src/library_server/pm/linear.py`

All new methods raise `NotImplementedError("Not supported by Linear adapter")`. Existing methods unchanged.

### 7. Vault Builder Consolidation — `src/library_server/vault_builder/extractors/jira.py`

- Remove `_build_auth_headers()` method
- Replace `_fetch_issues()` with `JiraClient.search_issues()`
- Import `JiraClient` from `library_server.pm.jira_client`
- `validate_config()` unchanged (still checks env vars)

### 8. Hooks Client Consolidation — `src/library_server/hooks/jira_client.py`

Replace the standalone `fetch_issue_summary()` function with a thin wrapper around `JiraClient.get_issue()`. Preserve the same return signature for backward compatibility with hook callers.

## Documentation

### New directory: `the-library/docs/`

```
docs/
├── setup/
│   ├── quickstart.md         — Install, init, first run
│   ├── jira-setup.md         — API token, env vars, project setup, why not Atlassian MCP
│   └── linear-setup.md       — Placeholder
├── guides/
│   └── pm-integration.md     — End-to-end project & ticket management
└── reference/
    └── jira-api.md           — REST endpoints, field mappings, auth details
```

### `jira-setup.md` outline:

1. **Prerequisites** — Jira Cloud account, admin access for project creation
2. **Create API Token** — Step-by-step at id.atlassian.com
3. **Configure Environment** — `JIRA_EMAIL`, `JIRA_API_TOKEN` env vars
4. **Configure The Library** — `library-config.yaml` PM section, site_url, projects list
5. **Create Projects** — Using `library_pm_create_project` tool
6. **Verify** — Using `library_pm_list_projects` to confirm
7. **Why Not the Atlassian MCP?** — OAuth scope limits, agent-in-the-loop requirement, consolidation benefits

## Config Changes

`library-config.yaml` PM section gains a `projects` list (already in the example config):

```yaml
pm:
  provider: jira
  site_url: https://sevenbelow.atlassian.net
  projects:
    - key: LIBRARY
      name: THE LIBRARY
    - key: COS
      name: COMPLIANCE-OS
    - key: PLT
      name: PLATFORM
    - key: SEC
      name: SECURITY
    - key: SB
      name: SEVENBELOW
    - key: DEIOCAP
      name: DEIO-CAPSTONE
```

## Testing Strategy

- **`JiraClient`**: Mock `httpx.AsyncClient` responses. Test auth header construction, error handling, pagination, each endpoint.
- **`JiraAdapter`**: Mock `JiraClient` methods. Test type mapping from raw dicts to `TaskResult`/`EpicResult`/`ProjectResult`.
- **Vault builder extractor**: Mock `JiraClient.search_issues()`. Existing test structure preserved.
- **Hooks client**: Mock `JiraClient.get_issue()`. Verify return signature compatibility.
- **Integration test**: Optional — hits real Jira with env vars set, skipped in CI without credentials.

## Files Changed

| File | Action |
|------|--------|
| `src/library_server/pm/jira_client.py` | **New** — standalone HTTP client |
| `src/library_server/pm/jira.py` | **Rewrite** — use JiraClient instead of _call_mcp |
| `src/library_server/pm/adapter.py` | **Extend** — new abstract methods |
| `src/library_server/types.py` | **Extend** — add ProjectResult |
| `src/library_server/server.py` | **Extend** — 7 new MCP tools |
| `src/library_server/pm/linear.py` | **Extend** — stub new methods |
| `src/library_server/vault_builder/extractors/jira.py` | **Refactor** — use JiraClient |
| `src/library_server/hooks/jira_client.py` | **Refactor** — use JiraClient |
| `tests/test_pm_adapter.py` | **Rewrite** — mock JiraClient not _call_mcp |
| `tests/test_jira_client.py` | **New** — JiraClient unit tests |
| `tests/vault_builder/extractors/test_jira.py` | **Update** — mock JiraClient |
| `tests/test_hooks/test_jira_client.py` | **Update** — mock JiraClient |
| `docs/setup/jira-setup.md` | **New** |
| `docs/setup/quickstart.md` | **New** |
| `docs/setup/linear-setup.md` | **New** (placeholder) |
| `docs/guides/pm-integration.md` | **New** |
| `docs/reference/jira-api.md` | **New** |

## Out of Scope

- Sprint/board management
- Custom field management
- Workflow scheme configuration
- Jira webhooks (inbound)
- Bulk operations API
- Attachment uploads
