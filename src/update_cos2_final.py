import asyncio
from library_server.pm.jira_client import JiraClient, _to_adf

async def main():
    try:
        client = JiraClient("https://sevenbelow.atlassian.net")
        
        # Update COS-2
        cos2_desc = """
h3. Context
User is viewing the Activity Dashboard / Activity Details page for an Activity Run that was created from a Document Excerpt (e.g., "Quarterly Backup Testing").

h3. Expected Behavior
Because this Activity Run is bound to a specific Excerpt from a Source Document, the actual content/text of that Activity Run excerpt should populate and be clearly visible on the dashboard so the user running the activity knows exactly what instructions or policies apply.

h3. Actual Behavior
The Activity Run excerpt content is entirely missing from the Activity dashboard view. The dashboard shows "Source Document" linked in the bottom right, and "Steps" says "No steps defined", but the rich text content from the parent excerpt is nowhere to be found. 

h3. Steps to Reproduce
1. Create a Document Excerpt of type "Activity Run".
2. Save and proceed to create the bound Activity Run.
3. Open the newly created Activity Run's dashboard page.
4. Observe that the excerpt content is missing.

h3. Visuals
See the attached screenshot in the system context showing the "Quarterly Backup Testing" Activity Dashboard lacking the excerpt content body.
"""
        await client.update_issue("COS-2", fields={"description": _to_adf(cos2_desc)})
        print("Updated COS-2 with correct Dashboard context")

    except Exception as e:
        print("Failed:", repr(e))

asyncio.run(main())
