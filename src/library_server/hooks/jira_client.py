"""Direct Jira REST API client for zero-token task fetching."""
import base64

import httpx


async def fetch_issue_summary(
    base_url: str,
    api_token: str,
    email: str,
    issue_key: str,
) -> dict | None:
    """Fetch a Jira issue's summary and status without going through MCP.

    Args:
        base_url: The Jira instance base URL, e.g. "https://example.atlassian.net".
        api_token: Jira API token.
        email: The email address associated with the API token.
        issue_key: The issue key, e.g. "COS-42".

    Returns:
        A dict with keys ``key``, ``summary``, and ``status``, or ``None`` if
        the issue is not found or a network error occurs.
    """
    credentials = base64.b64encode(f"{email}:{api_token}".encode()).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "Accept": "application/json",
    }
    url = f"{base_url}/rest/api/3/issue/{issue_key}?fields=summary,status"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, headers=headers)
    except httpx.RequestError:
        return None

    if response.status_code != 200:
        return None

    data = response.json()
    return {
        "key": data["key"],
        "summary": data["fields"]["summary"],
        "status": data["fields"]["status"]["name"],
    }
