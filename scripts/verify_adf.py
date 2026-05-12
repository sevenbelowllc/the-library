"""GET a ticket and dump its description ADF tree to verify shape."""
import asyncio
import json
import sys

from library_server.pm.jira_client import JiraClient


async def main() -> int:
    key = sys.argv[1] if len(sys.argv) > 1 else "PARKLOT-78"
    client = JiraClient(site_url="https://sevenbelow.atlassian.net")
    issue = await client.get_issue(key, fields="summary,description")
    desc = issue.get("fields", {}).get("description")
    print(f"Summary: {issue.get('fields', {}).get('summary')}")
    print(f"Description top-level type: {desc.get('type') if desc else 'NULL'}")
    print(f"Top-level children count: {len(desc.get('content', [])) if desc else 0}")
    print(f"Child types: {[c.get('type') for c in (desc.get('content', []) if desc else [])]}")
    print("---FULL ADF---")
    print(json.dumps(desc, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
