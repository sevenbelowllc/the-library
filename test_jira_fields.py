import asyncio
from library_server.pm.jira_client import JiraClient
async def main():
    client = JiraClient(site_url='https://sevenbelow.atlassian.net')
    fields = await client.get_fields()
    for f in fields:
        if 'epic' in f.get('name', '').lower() or 'name' in f.get('name', '').lower():
            print(f"ID: {f.get('id')}, Name: {f.get('name')}")
asyncio.run(main())
