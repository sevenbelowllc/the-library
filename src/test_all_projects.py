import asyncio
from library_server.pm.jira_client import JiraClient

async def main():
    try:
        client = JiraClient("https://sevenbelow.atlassian.net")
        projects = await client.list_projects()
        for p in projects.get("values", []):
            proj = await client.get_project(p["key"])
            issue_types = proj.get("issueTypes", [])
            names = [it.get("name") for it in issue_types]
            print(f"Project {p['key']}: {', '.join(names)}")
    except Exception as e:
        print("Failed:", repr(e))

asyncio.run(main())
