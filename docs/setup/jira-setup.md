# Jira Setup Guide

This guide covers everything needed to connect The Library to Jira Cloud — from creating an API token to verifying projects through the MCP tools.

---

## Prerequisites

- A **Jira Cloud** account (not Jira Data Center or Jira Server — this guide targets the Cloud REST API v3)
- **Site admin** or **Jira admin** access on your Atlassian organization — required for project creation
- The Library v0.3.0 or later installed (`library --version`)

---

## 1. Create an API Token

Jira Cloud authenticates programmatic access with an API token tied to your Atlassian account.

1. Go to [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Click **Create API token**
3. Give it a descriptive label — e.g. `the-library-local` or `compliance-os-mcp`
4. Click **Create**, then **copy the token immediately** — it will not be shown again
5. Store it in your password manager or secrets vault before closing the dialog

The token grants the same permissions as your Atlassian account. Keep it secret and rotate it if it is ever exposed.

---

## 2. Configure Environment Variables

The Library reads Jira credentials from two environment variables:

| Variable | Value |
|----------|-------|
| `JIRA_EMAIL` | The email address of the Atlassian account that owns the token |
| `JIRA_API_TOKEN` | The API token created in step 1 |

### Shell profile (recommended for local dev)

Add to `~/.zshrc` or `~/.bashrc`:

```bash
export JIRA_EMAIL="you@example.com"
export JIRA_API_TOKEN="your-api-token-here"
```

Then reload: `source ~/.zshrc`

### `.env` file (alternative)

If you prefer a project-level `.env` file, add:

```
JIRA_EMAIL=you@example.com
JIRA_API_TOKEN=your-api-token-here
```

Never commit `.env` files containing secrets. Ensure `.env` is listed in `.gitignore`.

### How they flow through `.mcp.json`

The Library's `.mcp.json` passes these variables into the MCP server process at startup:

```json
{
  "library": {
    "command": "library",
    "env": {
      "JIRA_EMAIL": "${JIRA_EMAIL}",
      "JIRA_API_TOKEN": "${JIRA_API_TOKEN}"
    }
  }
}
```

The `${VAR}` syntax tells Claude Code to substitute the value from the host shell environment. The MCP server process receives the resolved values — it never reads the `.mcp.json` substitution syntax directly. This means you must export the variables in your shell before starting Claude Code; they are not read from `.env` at MCP startup.

---

## 3. Configure The Library

Open `library-config.yaml` and fill in the `pm` section:

```yaml
pm:
  provider: jira
  site_url: https://your-instance.atlassian.net
  projects:
    - key: PROJ
      name: My Project
    - key: DOCS
      name: Documentation
```

**Fields:**

| Field | Description |
|-------|-------------|
| `provider` | Must be `jira` to activate the Jira adapter |
| `site_url` | Your Atlassian site URL — copy from your browser's address bar on any Jira page |
| `projects` | List of projects The Library should interact with. Each entry needs a `key` (Jira project key, all caps) and a `name` (display name for reference). This list does not create projects — it scopes which projects the MCP tools query by default. |

You can also set these programmatically using `library_config_set`:

```
library_config_set  pm.site_url  "https://your-instance.atlassian.net"
library_config_set  pm.projects  '[{"key": "PROJ", "name": "My Project"}]'
```

---

## 4. Create Projects

Use the `library_pm_create_project` MCP tool to create a new Jira project. The tool calls `POST /rest/api/3/project` directly — no Jira UI required.

**Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `name` | Yes | Full project name displayed in Jira |
| `key` | Yes | Short uppercase identifier (e.g. `COS`, `PLT`) |
| `project_type_key` | No | `software` (default), `business`, or `service_desk` |
| `lead_account_id` | No | Atlassian account ID of the project lead. If omitted, defaults to the token owner. |
| `description` | No | Short description shown on the project page |

**Example:**

```
library_pm_create_project
  name: "Compliance OS"
  key: "COS"
  project_type_key: "software"
  description: "Core compliance management platform"
```

**Finding `lead_account_id`:**

If you need to assign a specific lead, use `library_pm_query` with `action: find_user` and a name or email. The response includes `accountId`, which you can pass as `lead_account_id`.

---

## 5. Verify

Confirm the connection and project list with `library_pm_list_projects`:

```
library_pm_list_projects
```

This calls `GET /rest/api/3/project/search` and returns all projects visible to your token. You should see any projects you just created, along with any existing projects your account can access.

If the tool returns an auth error:

- Confirm `JIRA_EMAIL` and `JIRA_API_TOKEN` are set in your current shell session (`echo $JIRA_EMAIL`)
- Confirm `site_url` in `library-config.yaml` matches your Atlassian site exactly (no trailing slash, correct subdomain)
- Confirm the token has not expired or been revoked at [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)

---

## 6. Vault Builder Integration

The Vault Builder's Jira extractor uses the same `JiraClient` and the same `JIRA_EMAIL` / `JIRA_API_TOKEN` credentials — no separate configuration required.

To enable Jira issue ingestion in the vault build, add a `jira` block under `vault_builder.sources` in `library-config.yaml`:

```yaml
vault_builder:
  sources:
    jira:
      enabled: true
      instance: your-instance.atlassian.net
      cloud_id: your-cloud-id-here          # from Atlassian admin console
      projects: [PROJ, DOCS]                # project keys to ingest
      auth: api_token                       # always api_token for Cloud
```

The `cloud_id` is required for certain Atlassian REST APIs. Find it at:
`https://your-instance.atlassian.net/_edge/tenant_info`

The vault builder will extract issues, epics, and labels from each listed project and write them to `vault/sources/raw/jira/`.

---

## Why Not the Atlassian MCP?

The Atlassian MCP server (the `mcp__claude_ai_Atlassian__*` tools in Claude Code) is useful for ad-hoc, conversational Jira lookups. It is not suitable as The Library's programmatic integration layer for four specific reasons:

### 1. OAuth scope limitations

The Atlassian MCP uses OAuth 2.0 with scopes fixed by the MCP server author (`read:jira-work`, `write:jira-work`). These scopes cover reading and writing issues, but **do not include project administration**. Creating a Jira project requires the `manage:jira-project` scope — which the Atlassian MCP cannot grant, regardless of your Atlassian account's permissions.

The Library's `library_pm_create_project` tool calls the REST API directly with your own credentials, which carry your full account permissions.

### 2. Agent-in-the-loop required

MCP tool calls go through the Claude Code LLM. Every API call — including background polling, hook callbacks, and vault builder extractions — would require the LLM agent to be active in the loop, consuming tokens and context window for work that should run silently in the background.

The Library's hooks (session start, stop, pre-compact) need to look up Jira task state without waking an LLM. `JiraClient` makes async HTTP calls directly, with no LLM mediation.

### 3. No consolidation across consumers

Three separate components in The Library need Jira data: the PM adapter (MCP tools), the vault builder extractor, and the hooks client. Routing all three through the Atlassian MCP would require each component to call `_call_mcp()` independently, duplicating wiring and making the integration brittle.

`JiraClient` is a single import shared by all three layers. Auth is configured once. The architecture is:

```
JiraClient (HTTP layer)
    ├── JiraAdapter → MCP tools (server.py)
    ├── JiraExtractor (vault builder)
    └── hooks/jira_client.py (zero-token task lookups)
```

### 4. Basic Auth is sufficient

Jira Cloud REST API v3 fully supports email + API token authentication for all endpoints — including project creation, issue management, transitions, comments, and user lookups. There is no capability advantage to OAuth for server-to-server automation. Basic Auth is simpler, requires no token refresh flow, and works identically across all environments (local, CI, scheduled jobs).

---

## Quick-Reference Checklist

```
[ ] API token created at id.atlassian.com
[ ] JIRA_EMAIL exported in shell
[ ] JIRA_API_TOKEN exported in shell
[ ] pm.provider: jira set in library-config.yaml
[ ] pm.site_url set to https://your-instance.atlassian.net
[ ] pm.projects list populated
[ ] library_pm_list_projects returns projects without error
[ ] vault_builder.sources.jira configured (if using vault builder)
```
