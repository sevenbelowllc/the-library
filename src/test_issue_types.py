import asyncio
from library_server.pm.jira_client import JiraClient

async def main():
    try:
        client = JiraClient("https://sevenbelow.atlassian.net")
        project = await client.get_project("ZZTJPJA")
        issue_types = project.get("issueTypes", [])
        for it in issue_types:
            print(f"Name: {it.get('name')}, ID: {it.get('id')}")
    except Exception as e:
        print("Failed:", repr(e))

asyncio.run(main())
