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
  projects:
    - key: MYPROJECT
      name: My Project
```

Environment variables required:

```bash
export JIRA_EMAIL=you@example.com
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
