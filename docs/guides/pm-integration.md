# PM Integration Guide

End-to-end guide for managing projects and tickets through The Library's PM adapter layer.

## Architecture

The Library routes all PM operations through a provider-agnostic adapter. MCP tools call the adapter; the adapter dispatches to the concrete provider client.

```
Claude Code / MCP Tools
        |
        v
   PMAdapter (abstract interface)
        |
   +---------+-----------+
   |                     |
JiraAdapter         LinearAdapter
   |
JiraClient (HTTP — Basic Auth, REST v3)
   |
Jira Cloud REST API
```

The `JiraClient` is a standalone async HTTP client. It owns all authentication, pagination, and error handling. The `JiraAdapter` is a thin mapping layer that converts raw API responses into Library types (`TaskResult`, `EpicResult`, `ProjectResult`).

The Linear adapter uses the Linear GraphQL API and follows the same interface, with a subset of operations implemented.

## Capabilities Matrix

| Capability | Jira | Linear |
|-----------|------|--------|
| Create task | Yes | Yes |
| Create epic | Yes | Yes |
| Update task | Yes | Yes |
| Query tasks (JQL / filter) | Yes | Yes |
| Sync PM state to SESSION.md | Yes | Yes |
| Create project | Yes | No |
| List projects | Yes | No |
| Get project details | Yes | No |
| Update project | Yes | No |
| Assign task to user | Yes | No |
| Link issues | Yes | No |
| List link types | Yes | No |

## MCP Tools Reference

### Project Management (4 tools)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `library_pm_create_project` | `name`, `key`, `description?`, `project_type_key?` | Create a new Jira project |
| `library_pm_list_projects` | (none) | List all visible projects |
| `library_pm_get_project` | `project_key` | Get project details |
| `library_pm_update_project` | `project_key`, `name?`, `description?` | Update project name or description |

### Ticket Management (5 tools)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `library_pm_create_task` | `project_key`, `summary`, `description?`, `labels?` | Create a task/story/bug |
| `library_pm_create_epic` | `project_key`, `name`, `description?` | Create an epic |
| `library_pm_update` | `task_id`, `fields` | Update any issue fields |
| `library_pm_query` | `jql?`, `project_key?`, `status?` | Search issues |
| `library_pm_sync` | (none) | Pull PM state into SESSION.md |

### Assignment and Linking (3 tools)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `library_pm_assign_task` | `task_id`, `account_id` | Assign an issue to a user |
| `library_pm_link_issues` | `type_name`, `inward_key`, `outward_key` | Link two issues |
| `library_pm_get_link_types` | (none) | List available link types (e.g., "blocks", "relates to") |

## Configuration

### Jira

```yaml
pm:
  provider: jira
  site_url: https://your-org.atlassian.net
  workflow_scheme: "SevenBelow Standard SDLC Workflow"
  projects:
    - key: MYPROJECT
      name: My Project
```

#### Workflow Configuration and Project Creation
When AI creates a new Jira project using the `library_pm_create_project` MCP tool, the project will automatically inherit the custom workflow scheme specified by the `workflow_scheme` key in your `library-config.yaml` file.

> [!WARNING]
> **Workflow vs. Workflow Scheme**  
> Jira's architecture explicitly forbids directly assigning a *Workflow* to a Project. You must assign a **Workflow Scheme** to a project instead (a Scheme is a bucket that maps different issue types like Epics/Bugs/Stories to specific Workflows). You must supply the exact name of a *Workflow Scheme* to your `library-config.yaml` file, or the AI's Atlassian API call will fail with a 404 Not Found error.

**How to Configure Custom Workflows:**
If you require custom or strict review gates (for example, enforcing a transition from "In Progress" -> "In Review" -> "Done"):
1. In Jira Administration Settings, navigate to **Issues > Workflow Schemes**.
2. Click **Add Workflow Scheme** and explicitly name it (e.g., `SevenBelow Standard SDLC Workflow Scheme`).
3. Inside your new Scheme, map your custom workflow (e.g., `SevenBelow Standard SDLC Workflow`) to your desired Issue Types.
4. Update `library-config.yaml` so the `workflow_scheme` value matches the **Scheme's exact string** verbatim.
5. The next time `library_pm_create_project` runs, it will systematically auto-resolve the Scheme ID via the Jira REST API to irreversibly bind your new projects!

> [!CAUTION]
> **The Jira Trash Gotcha**  
> If the `library_pm_create_project` tool successfully creates the Jira project but crashes on the workflow binding step (e.g., due to a typo in the Scheme name), the project *actually exists* on your Jira dashboard. If you attempt to delete the project manually to try again, Jira moves the project into the "Trash" bin and permanently locks the project key (e.g., `PLT`, `SEC`). Future creation attempts will crash with a `Project uses this key` error. To retry the automation, you must navigate to the Jira Trash and securely "Permanently Delete" the project to free up the key!

Environment variables required:

```bash
export ATLASSIAN_EMAIL=you@example.com
export JIRA_API_TOKEN=your_api_token
```

See [jira-setup.md](../setup/jira-setup.md) for token creation steps.

### Linear

```yaml
pm:
  provider: linear
  api_key: lin_api_xxx    # or set LINEAR_API_KEY env var
```

See [linear-setup.md](../setup/linear-setup.md) for setup steps and supported operations.

## Admin Tools Deep Dive

The 7 admin tools provide full project and issue lifecycle management through the Jira REST API v3. All tools go through `JiraAdapter` -> `JiraClient` -> Jira Cloud.

### create_project

**MCP tool:** `library_pm_create_project`

Creates a new Jira project and optionally assigns a workflow scheme.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Project display name |
| `key` | string | Yes | Jira project key (uppercase, 2-10 chars) |
| `description` | string | No | Project description |
| `lead_account_id` | string | No | Atlassian account ID for project lead. Defaults to the authenticated user (`get_myself()`). |
| `workflow_scheme` | string | No | Name of an existing Jira Workflow Scheme to assign. Resolved by name via the REST API. |

**Workflow scheme assignment:** When `workflow_scheme` is provided, the adapter first creates the project, then calls `assign_workflow_scheme()` which looks up the scheme ID by name from `/rest/api/3/workflowscheme` and assigns it via `PUT /rest/api/3/workflowscheme/project`. If the scheme name does not match exactly (case-insensitive), a `ValueError` is raised listing available schemes.

**Returns:** `ProjectResult` with `project_id`, `project_key`, `name`, `description`, `lead`, `url`.

**Jira endpoints:** `POST /rest/api/3/project`, `GET /rest/api/3/myself` (if no lead), `GET /rest/api/3/workflowscheme` + `PUT /rest/api/3/workflowscheme/project` (if workflow scheme specified).

### list_projects

**MCP tool:** `library_pm_list_projects`

Lists all visible Jira projects for the authenticated user.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| (none) | | | |

**Returns:** `list[ProjectResult]` -- one entry per project with `project_id`, `project_key`, `name`, `description`, `lead`, `url`.

**Jira endpoint:** `GET /rest/api/3/project/search` (paginated, default 50 results).

### get_project

**MCP tool:** `library_pm_get_project`

Fetches details for a single Jira project.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_key` | string | Yes | Jira project key (e.g., `COS`, `PLT`) |

**Returns:** `ProjectResult` with full project details.

**Jira endpoint:** `GET /rest/api/3/project/{key}`

### update_project

**MCP tool:** `library_pm_update_project`

Updates the name and/or description of an existing Jira project.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_key` | string | Yes | Jira project key |
| `name` | string | No | New project name |
| `description` | string | No | New project description |

Only non-empty fields are included in the update payload. After the update, the adapter re-fetches the project to return the current state.

**Returns:** `ProjectResult` with updated values.

**Jira endpoint:** `PUT /rest/api/3/project/{key}`

### assign_task

**MCP tool:** `library_pm_assign_task`

Assigns a Jira issue to a specific user by Atlassian account ID.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_id` | string | Yes | Jira issue key (e.g., `COS-42`) |
| `account_id` | string | Yes | Atlassian account ID of the assignee |

To find account IDs, use `JiraClient.get_myself()` (for the authenticated user) or `JiraClient.find_users(query)` (search by name/email).

**Returns:** `TaskResult` with updated issue state.

**Jira endpoint:** `PUT /rest/api/3/issue/{key}/assignee`

### link_issues

**MCP tool:** `library_pm_link_issues`

Creates a directional link between two Jira issues.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `type_name` | string | Yes | Link type name (e.g., `"Blocks"`, `"Relates"`, `"Cloners"`) |
| `inward_key` | string | Yes | Issue key for the inward side of the link |
| `outward_key` | string | Yes | Issue key for the outward side of the link |

Link directionality matters. For a "Blocks" link: the `outward_key` issue blocks the `inward_key` issue. Use `get_link_types` to discover available link types and their directional semantics.

**Returns:** `None` (Jira returns 201 with no body on success).

**Jira endpoint:** `POST /rest/api/3/issueLink`

### get_link_types

**MCP tool:** `library_pm_get_link_types`

Lists all available issue link types configured in the Jira instance.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| (none) | | | |

**Returns:** `list[dict]` -- each entry contains `id`, `name`, `inward` (inward description), `outward` (outward description). Common types include: Blocks/is blocked by, Cloners/is cloned by, Relates/relates to.

**Jira endpoint:** `GET /rest/api/3/issueLinkType`

### Error Handling

All admin tools inherit error handling from `JiraClient._request()`:

- **Non-2xx responses** raise `JiraApiError` with `status_code`, `message` (parsed from Jira's `errorMessages` and `errors` fields), and `endpoint`.
- **204 No Content** responses return `None` (used by assignment and linking).
- **201 with empty body** returns `None` (used by issue link creation).
- **Timeout** defaults to 15 seconds per request (configurable via `JiraClient.__init__`).

---

## Vault Builder Integration

When the Vault Builder's Jira extractor runs (`library_vault_builder_build`), it uses the same `JiraClient` as the PM adapter — no separate auth configuration required. Issues ingested into the vault are linked back to their Jira keys so `library:sync` and `library:query` can cross-reference vault content with live PM state.

Configure which projects the extractor scans under `vault_builder.sources` in `library-config.yaml`:

```yaml
vault_builder:
  sources:
    - type: jira
      project_keys:
        - MYPROJECT
        - ANOTHERPROJECT
```
