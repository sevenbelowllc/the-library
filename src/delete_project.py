import asyncio
from library_server.pm.jira_client import JiraClient

async def main():
    try:
        client = JiraClient("https://sevenbelow.atlassian.net")
        res = await client._request("DELETE", "/rest/api/3/project/COS")
        print("Success:", res)
    except Exception as e:
        print("Failed:", repr(e))

asyncio.run(main())
