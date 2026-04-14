import asyncio
from library_server.pm.jira_client import JiraClient, _to_adf

async def main():
    try:
        client = JiraClient("https://sevenbelow.atlassian.net")
        
        # Update COS-4 (Bonus/Safety)
        cos4_desc = """
h3. Context
User expects Frameworks (e.g., SOC 2, ASSURE) to populate inside the system so they can be mapped to Controls.

h3. Expected Behavior
Canonical framework criteria (Level 0, 1, and leaf nodes) should be successfully ingested and displayed on the Frameworks page / dropdown menus.

h3. Actual Behavior
No framework criteria data is loaded into the platform.

h3. Technical Context
- Investigate the backend database seed scripts (`compliance-core`) to verify if the initial Framework JSON import logic is failing, incomplete, or if the database is starting entirely empty instead of with the canonical definitions.
"""
        # Update COS-5
        cos5_desc = """
h3. Context
User is accessing the "Control Mapping" page from the main UI navigation.

h3. Expected Behavior
The Control Mapping Matrix (as defined in `DOMAINS.md`) should visualize the Document -> Control -> Framework Criteria mapping chain with heatmaps, gaps, and coverage analytics.

h3. Actual Behavior
The Control Mapping page is completely empty. No matrices render, no analytical data displays.

h3. Steps to Reproduce
1. Log into Compliance OS UI.
2. Click "Control Mapping" in the sidebar navigation.
3. Observe empty state or missing visual components.

h3. Technical Context
- Check if the React component for the Control Mapping Matrix is still stubbed out or failing to mount.
- Monitor the network tab for the GraphQL query fetching mappings. If data is an empty array `[]`, the UI might be failing to show an "Empty State" UI.
"""
        await client.update_issue("COS-5", fields={"description": _to_adf(cos5_desc)})
        print("Updated COS-5")

        # Update COS-6
        cos6_desc = """
h3. Context
User is accessing the distinct "SevenBelow Admin panel / CS Portal" used for internal engineering and customer support.

h3. Expected Behavior
Dashboard cards showing system health, active tenants, billing status, or system-wide metrics should dynamically load and be interactive.

h3. Actual Behavior
Zero cards work. They are either blank, unclickable, or frozen.

h3. Steps to Reproduce
1. Navigate to the SevenBelow Admin panel URL.
2. Attempt to interact with or view any of the metric/action cards.
3. Observe failure.

h3. Technical Context
- Check console logs for `401 Unauthorized` or `403 Forbidden` API rejections. The Clerk authentication roles might not be passing the correct `sysadmin` claims down to the backend.
- Alternatively, the admin GraphQL queries might be fundamentally broken or unimplemented in `compliance-core`.
"""
        await client.update_issue("COS-6", fields={"description": _to_adf(cos6_desc)})
        print("Updated COS-6")

        # Update COS-7
        cos7_desc = """
h3. Context
To maintain strict Test-Driven Development (TDD) invariants, the project requires automated end-to-end (E2E) testing.

h3. Expected Behavior
A testing framework (Playwright/Cypress) should exist in the repository. It should automatically seed a local PostgreSQL database with tenant metadata, frameworks, and controls, and execute critical path workflows (e.g., creating a document, approving an excerpt) headlessly.

h3. Actual Behavior
No automated E2E tests exist, and there is no automated seed data routine coupled with the test runner.

h3. Action Items / Technical Context
1. Introduce Playwright to the `compliance-ui` space.
2. Write a database seeding utility in `compliance-core` specifically for test environments.
3. Write 1-2 foundational E2E tests asserting that basic routing and login work with seed data.
"""
        await client.update_issue("COS-7", fields={"description": _to_adf(cos7_desc)})
        print("Updated COS-7")

        # Try updating COS-4 just in case it wasn't done
        await client.update_issue("COS-4", fields={"description": _to_adf(cos4_desc)})
        print("Updated COS-4")

    except Exception as e:
        print("Failed:", repr(e))

asyncio.run(main())
