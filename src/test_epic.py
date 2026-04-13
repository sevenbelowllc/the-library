import asyncio
import os
import sys
from library_server.pm.jira_client import JiraClient
from library_server.pm.jira import JiraAdapter, _parse_issue

async def main():
    try:
        adapter = JiraAdapter("https://sevenbelow.atlassian.net")
        res = await adapter.create_epic(
            project_key="ZZTJPJA",
            summary="Test Epic - Validating Epic Creation Functionality",
            description="Testing via python script"
        )
        print("Success:", res)
    except Exception as e:
        print("Failed:", repr(e))

asyncio.run(main())
