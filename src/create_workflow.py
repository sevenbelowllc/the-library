import asyncio
import os
from library_server.pm.jira import JiraAdapter

async def main():
    try:
        adapter = JiraAdapter("https://sevenbelow.atlassian.net")
        
        # 1. Create the COS project
        print("Creating project...")
        proj = await adapter.create_project(
            name="Compliance OS Core",
            key="COS",
            description="Compliance OS core project for managing issues and gaps."
        )
        print("Project Created:", proj)
        await asyncio.sleep(2) # Give Jira API a moment to propagate project schema
        
        # 2. Create the epic
        print("Creating Epic...")
        epic = await adapter.create_epic(
            project_key="COS",
            summary="mvp-gaps-bugs",
            description="Epic tracking the core 6 MVP bugs required before release."
        )
        print("Epic Created:", epic)
        
        # 3. Create the 6 tasks
        bugs = [
            "Activity Run Excerpts don't populate",
            "Document Properties — can't create a Control",
            "No framework criteria data loaded",
            "Control Mapping page is empty",
            "SevenBelow Admin panel — zero cards work",
            "No automated E2E tests with seed data"
        ]
        
        for bug in bugs:
            print(f"Creating task for bug: {bug}")
            task = await adapter.client.create_issue(
                project_key="COS",
                issue_type="Task",
                summary=bug,
                description="Fix the critical MVP issue.",
                parent_key=epic.epic_id
            )
            print(f"Task created: {task['key']}")
            
        print("Workflow complete!")
        
    except Exception as e:
        print("Failed:", repr(e))

asyncio.run(main())
