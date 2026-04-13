import asyncio
from library_server.pm.jira_client import JiraClient

async def main():
    try:
        client = JiraClient("https://sevenbelow.atlassian.net")
        # Try to get the current user for lead
        me = await client.get_myself()
        lead_account_id = me["accountId"]
        
        # Test creating a project with a scrum template
        payload = {
            "name": "Scrum Test Template",
            "key": "STT",
            "projectTypeKey": "software",
            "projectTemplateKey": "com.pyxis.greenhopper.jira:gh-simplified-scrum-classic",
            "leadAccountId": lead_account_id,
            "description": "Test project with scrum template",
            "assigneeType": "PROJECT_LEAD"
        }
        res = await client._request("POST", "/rest/api/3/project", json=payload)
        print("Success:", res)
        
        # Check if it has Epics
        proj = await client.get_project("STT")
        issue_types = proj.get("issueTypes", [])
        names = [it.get("name") for it in issue_types]
        print(f"Project STT issue types: {', '.join(names)}")
        
    except Exception as e:
        print("Failed:", repr(e))
        if hasattr(e, "message"):
            print("Message:", e.message)

asyncio.run(main())
