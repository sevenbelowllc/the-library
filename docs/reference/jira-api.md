# Jira API Reference

Reference documentation for The Library's `JiraClient` — the direct REST API integration layer introduced in v0.4.0.

## Authentication

The Library uses HTTP Basic Authentication with a Jira Cloud API token.

**Header format:**

```
Authorization: Basic <base64(email:api_token)>
```

**Construction:**

```python
import base64, os

credentials = base64.b64encode(
    f"{os.environ['ATLASSIAN_EMAIL']}:{os.environ['JIRA_API_TOKEN']}".encode()
).decode()
headers = {"Authorization": f"Basic {credentials}"}
```

**Required environment variables:**

| Variable | Description |
|----------|-------------|
| `ATLASSIAN_EMAIL` | The email address of the Jira account that owns the API token |
| `JIRA_API_TOKEN` | API token from [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens) |

The `JiraClient` reads these variables at construction time. They are never written to disk or logs.

## Endpoints

### Projects

| Method | REST Endpoint | `JiraClient` Method |
|--------|--------------|---------------------|
| `POST` | `/rest/api/3/project` | `create_project(name, key, project_type_key, lead_account_id, description?)` |
| `GET` | `/rest/api/3/project/search` | `list_projects()` |
| `GET` | `/rest/api/3/project/{key}` | `get_project(project_key)` |
| `PUT` | `/rest/api/3/project/{key}` | `update_project(project_key, **fields)` |

### Issues

| Method | REST Endpoint | `JiraClient` Method |
|--------|--------------|---------------------|
| `POST` | `/rest/api/3/issue` | `create_issue(project_key, issue_type, summary, description, labels?, parent?, assignee?)` |
| `GET` | `/rest/api/3/issue/{key}` | `get_issue(issue_key, fields?)` |
| `PUT` | `/rest/api/3/issue/{key}` | `update_issue(issue_key, fields)` |
| `GET` | `/rest/api/3/search` | `search_issues(jql, fields?, max_results?, start_at?)` |
| `PUT` | `/rest/api/3/issue/{key}/assignee` | `assign_issue(issue_key, account_id)` |

### Transitions

| Method | REST Endpoint | `JiraClient` Method |
|--------|--------------|---------------------|
| `GET` | `/rest/api/3/issue/{key}/transitions` | `get_transitions(issue_key)` |
| `POST` | `/rest/api/3/issue/{key}/transitions` | `transition_issue(issue_key, transition_id)` |

### Comments

| Method | REST Endpoint | `JiraClient` Method |
|--------|--------------|---------------------|
| `POST` | `/rest/api/3/issue/{key}/comment` | `add_comment(issue_key, body)` |

### Links

| Method | REST Endpoint | `JiraClient` Method |
|--------|--------------|---------------------|
| `POST` | `/rest/api/3/issueLink` | `create_issue_link(type_name, inward_key, outward_key)` |
| `GET` | `/rest/api/3/issueLinkType` | `get_link_types()` |

### Users

| Method | REST Endpoint | `JiraClient` Method |
|--------|--------------|---------------------|
| `GET` | `/rest/api/3/myself` | `get_myself()` |
| `GET` | `/rest/api/3/user/search` | `find_users(query)` |

## Atlassian Document Format (ADF)

Jira Cloud's REST API v3 uses **Atlassian Document Format (ADF)** for rich-text fields — issue descriptions, comments, and panel text. ADF is a JSON tree, not a plain string.

**Minimal ADF document (plain paragraph):**

```json
{
  "version": 1,
  "type": "doc",
  "content": [
    {
      "type": "paragraph",
      "content": [
        {
          "type": "text",
          "text": "This is the description text."
        }
      ]
    }
  ]
}
```

**ADF with multiple paragraphs:**

```json
{
  "version": 1,
  "type": "doc",
  "content": [
    {
      "type": "paragraph",
      "content": [{ "type": "text", "text": "First paragraph." }]
    },
    {
      "type": "paragraph",
      "content": [{ "type": "text", "text": "Second paragraph." }]
    }
  ]
}
```

The `JiraClient` converts plain string `description` arguments to ADF automatically. You can also pass a pre-built ADF dict if you need headings, code blocks, or bullet lists.

## Error Handling

All non-2xx responses from the Jira REST API raise `JiraApiError`.

**Exception class:**

```python
class JiraApiError(Exception):
    status_code: int    # HTTP status code (e.g., 404)
    message: str        # Error message from Jira response body
    endpoint: str       # The REST path that failed (e.g., "/rest/api/3/issue/FOO-1")
```

**Common error codes:**

| Status | Meaning | Common Cause |
|--------|---------|-------------|
| `400` | Bad Request | Invalid field value, missing required field, malformed ADF, invalid project key format |
| `401` | Unauthorized | `ATLASSIAN_EMAIL` or `JIRA_API_TOKEN` missing, expired, or incorrect |
| `403` | Forbidden | Authenticated user lacks permission for the operation (e.g., project creation requires admin) |
| `404` | Not Found | Issue key, project key, or transition ID does not exist |

**Handling errors in calling code:**

```python
from library_server.pm.jira_client import JiraClient, JiraApiError

client = JiraClient(site_url="https://your-org.atlassian.net")

try:
    issue = await client.get_issue("FOO-999")
except JiraApiError as e:
    if e.status_code == 404:
        print(f"Issue not found: {e.endpoint}")
    elif e.status_code == 401:
        print("Check ATLASSIAN_EMAIL and JIRA_API_TOKEN env vars")
    else:
        raise
```
