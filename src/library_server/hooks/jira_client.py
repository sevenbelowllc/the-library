"""Direct Jira REST API client for zero-token task fetching.

Uses the shared JiraClient for HTTP. Preserves the fetch_issue_summary
function signature for backward compatibility with hook callers.
"""

from library_server.pm.jira_client import JiraClient, JiraApiError


async def fetch_issue_summary(
    base_url: str,
    api_token: str,
    email: str,
    issue_key: str,
) -> dict | None:
    """Fetch a Jira issue's summary and status.

    Args:
        base_url: The Jira instance base URL, e.g. "https://example.atlassian.net".
        api_token: Jira API token (unused — reads from env, kept for backward compat).
        email: Email address (unused — reads from env, kept for backward compat).
        issue_key: The issue key, e.g. "COS-42".

    Returns:
        A dict with keys ``key``, ``summary``, and ``status``, or ``None`` if
        the issue is not found or a network error occurs.
    """
    try:
        client = JiraClient(site_url=base_url)
        data = await client.get_issue(issue_key, fields=["summary", "status"])
        return {
            "key": data["key"],
            "summary": data["fields"]["summary"],
            "status": data["fields"]["status"]["name"],
        }
    except (JiraApiError, ValueError, KeyError):
        return None
    except Exception:
        return None
