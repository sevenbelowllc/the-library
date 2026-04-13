# Linear Setup

> **Status:** The Linear adapter supports issue and epic management. Project management (creating, listing, and updating Linear projects/teams) is not yet supported.

## Prerequisites

- Linear workspace with member or admin access
- A Linear API key (personal or service)

## Create an API Key

1. Open [linear.app](https://linear.app) and sign in.
2. Go to **Settings** > **API** (or navigate to `https://linear.app/settings/api`).
3. Under **Personal API Keys**, click **Create new API key**.
4. Name the key (e.g., `the-library`).
5. Copy the generated key — it starts with `lin_api_`. You will not see it again.

## Configure The Library

Set the API key as an environment variable:

```bash
export LINEAR_API_KEY=lin_api_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Add it to your shell profile (`.zshrc`, `.bashrc`, etc.) or a `.env` file loaded by your project.

Update `library-config.yaml`:

```yaml
pm:
  provider: linear
  api_key: lin_api_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx   # or omit to use env var
```

## Supported Operations

The following operations work with the Linear adapter:

| Operation | MCP Tool | Notes |
|-----------|----------|-------|
| Create task | `library_pm_create_task` | Creates a Linear issue |
| Create epic | `library_pm_create_epic` | Creates a Linear project/milestone |
| Update task | `library_pm_update` | Updates title, status, description |
| Query tasks | `library_pm_query` | JQL-equivalent filter by project or status |
| Sync state | `library_pm_sync` | Pulls open/closed counts into SESSION.md |

## Not Yet Supported

The following operations raise `NotImplementedError` on the Linear adapter:

- `library_pm_create_project` — project creation
- `library_pm_list_projects` — listing teams/projects
- `library_pm_get_project` — project detail lookup
- `library_pm_update_project` — project updates
- `library_pm_assign_task` — explicit issue assignment
- `library_pm_link_issues` — issue linking
- `library_pm_get_link_types` — link type enumeration

These capabilities are on the roadmap. Track progress at the [LIBRARY Jira project](https://sevenbelow.atlassian.net/jira/software/projects/LIBRARY/boards).

## Verify

```bash
library validate
```

The validator checks that `LINEAR_API_KEY` is set when `provider: linear` is configured.
