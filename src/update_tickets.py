import asyncio
from library_server.pm.jira_client import JiraClient, _to_adf

async def main():
    try:
        client = JiraClient("https://sevenbelow.atlassian.net")
        
        # Update COS-2
        cos2_desc = """
h3. Context
User is working in the Document Edit view (which requires an initial Document Name + Objective).

h3. Expected Behavior
Because the excerpt was set as an "Activity Run" type in the parent view, the child modal ("Create Activity Run") that auto-launches should have its Activity Type dropdown automatically pre-populated with "Activity Run", saving the user from selecting it again.

h3. Actual Behavior
The Activity Run type is not set automatically in the "Create Activity Run" modal window. The field remains empty/unset and does not populate.

h3. Steps to Reproduce
1. Create a Document (set name and objective minimum).
2. Enter the Document Edit view.
3. Type `/excerpt` into the body to launch the Create Excerpt window.
4. Select Excerpt Type: "Activity Run".
5. Click Save. This auto-launches the "Create Activity Run" modal window.
6. Observe that the Activity Type in the second modal is blank and not pre-populated.

h3. Technical Context
- The initial `/excerpt` window successfully records the type, but that state/prop is not surviving the transition or being passed correctly into the auto-launched "Create Activity Run" React modal. It involves user-created content (Activity Run type excerpt dictating a secondary action).
"""
        await client.update_issue("COS-2", fields={"description": _to_adf(cos2_desc)})
        print("Updated COS-2")

        # Update COS-3
        cos3_desc = """
h3. Context
User is attempting to create a new Control from the "Create New Control" modal. 

h3. Expected Behavior
Filling out the required fields and clicking "Create Control" should invoke the GraphQL mutation and succeed.

h3. Actual Behavior
The backend rejects the payload resulting in a 400 Bad Request error. The UI toast shows "Failed to create control. Response not successful: Received status code 400".

h3. Technical Logs / Context
The following exact console logs were captured concurrently with the failure:
{code:javascript}
resolveExtensions.ts:17 [tiptap warn]: Duplicate extension names found: ['link', 'underline']. This can lead to issues.
invariant.ts:42 An error occurred! For more details, see the full error text at https://go.apollo.dev/c/err#%7B%22version%22%3A%223.14.0%22%2C%22message%22%3A43%2C%22args%22%3A%5B%22GetRecentExcerpts%22%5D%7D
:4000/graphql:1 Failed to load resource: the server responded with a status of 400 (Bad Request)
:4000/graphql:1 Failed to load resource: the server responded with a status of 400 (Bad Request)
page.tsx:288 [DocumentEdit] Failed to sync document references
:4000/graphql:1 Failed to load resource: the server responded with a status of 400 (Bad Request)
{code}
Key Indicators for AI:
- `GetRecentExcerpts` is throwing an Apollo cache/network invariant invariant.
- Multiple 400 Bad Requests are hitting `:4000/graphql`.
- `page.tsx:288` indicates a failure to sync document references, which might be bleeding over into or triggering the Control creation failure. AI should check the GraphQL schema for `CreateControl` vs the submitted payload on the network layer.
"""
        await client.update_issue("COS-3", fields={"description": _to_adf(cos3_desc)})
        print("Updated COS-3")

    except Exception as e:
        print("Failed:", repr(e))

asyncio.run(main())
