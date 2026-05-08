"""Live end-to-end Jira workflow walk integration tests (LIBRARY-6).

Walks the full workflow on a real issue: create -> In Progress -> In Review
-> Done. Asserts each transition takes effect via ``JiraAdapter.get_issue``,
and asserts ``TransitionNotAvailableError`` is raised for bogus status names.

Skipped automatically when ``ATLASSIAN_EMAIL``/``JIRA_API_TOKEN`` are unset.

Test issues are created in ``JIRA_TEST_PROJECT_KEY`` (default: ``DEIOCAP`` —
the safe sandbox project). Teardown runs on pass, fail, and interrupt by
routing cleanup through ``pytest_asyncio.fixture`` yield-style finalization,
so we never leave integration-test issues behind.
"""

from __future__ import annotations

import os
import random
import string

import pytest

from library_server.pm.adapter import TransitionNotAvailableError
from library_server.pm.jira import JiraAdapter
from library_server.pm.jira_client import JiraClient

SKIP_REASON = "ATLASSIAN_EMAIL and JIRA_API_TOKEN required for workflow-walk tests"
requires_jira = pytest.mark.skipif(
    not (os.environ.get("ATLASSIAN_EMAIL") and os.environ.get("JIRA_API_TOKEN")),
    reason=SKIP_REASON,
)

SITE_URL = "https://sevenbelow.atlassian.net"
TEST_PROJECT = os.environ.get("JIRA_TEST_PROJECT_KEY", "DEIOCAP")


def _rand_suffix(length: int = 6) -> str:
    return "".join(random.choices(string.ascii_uppercase, k=length))


@pytest.fixture
async def throwaway_issue():
    """Create a throwaway issue, yield its key, delete/close it on teardown.

    Teardown runs on pass/fail/interrupt via the generator-close contract of
    pytest fixtures (TESTING-STANDARD §4.1).
    """
    adapter = JiraAdapter(site_url=SITE_URL)
    client: JiraClient = adapter.client
    summary = f"INTEGRATION-TEST-WORKFLOW-WALK {_rand_suffix()}"
    created = await client.create_issue(
        project_key=TEST_PROJECT,
        issue_type="Task",
        summary=summary,
        description="Created by test_jira_workflow_walk.py. Safe to delete.",
        labels=["integration-test", "workflow-walk"],
    )
    issue_key = created["key"]
    try:
        yield adapter, issue_key
    finally:
        # Prefer real deletion over status-close to keep the board tidy.
        try:
            await client._request("DELETE", f"/rest/api/3/issue/{issue_key}")
        except Exception:
            # Fallback: best-effort transition to Done so it doesn't linger.
            try:
                trans = await client.get_transitions(issue_key)
                for t in trans.get("transitions", []):
                    to_name = t.get("to", {}).get("name", "").lower()
                    if to_name in ("done", "closed"):
                        await client.transition_issue(issue_key, t["id"])
                        break
            except Exception:
                pass


class TestJiraWorkflowWalk:
    """Walks the LIBRARY/DEIOCAP workflow on a live issue."""

    @requires_jira
    @pytest.mark.asyncio
    async def test_initial_status_is_to_do(self, throwaway_issue) -> None:
        """Newly created issues land in the workflow's initial state ('To Do')."""
        adapter, issue_key = throwaway_issue
        detail = await adapter.get_issue(issue_key)
        assert detail.id == issue_key
        assert detail.status == "To Do", (
            f"Expected initial status 'To Do', got {detail.status!r}. "
            "If this project uses a different initial state, update the test."
        )
        # Available transitions must include In Progress as a legal next move.
        to_states = {t.to_status for t in detail.available_transitions}
        assert "In Progress" in to_states

    @requires_jira
    @pytest.mark.asyncio
    async def test_walk_to_do_in_progress_review_done(self, throwaway_issue) -> None:
        """Full happy-path walk: To Do -> In Progress -> In Review -> Done."""
        adapter, issue_key = throwaway_issue

        # To Do -> In Progress
        await adapter.update_task(issue_key, status="In Progress")
        detail = await adapter.get_issue(issue_key)
        assert detail.status == "In Progress"

        # In Progress -> In Review
        await adapter.update_task(issue_key, status="In Review")
        detail = await adapter.get_issue(issue_key)
        assert detail.status == "In Review"

        # In Review -> Done
        await adapter.update_task(issue_key, status="Done")
        detail = await adapter.get_issue(issue_key)
        assert detail.status == "Done"

    @requires_jira
    @pytest.mark.asyncio
    async def test_bogus_status_raises_transition_not_available(
        self, throwaway_issue
    ) -> None:
        """Unknown status names raise TransitionNotAvailableError, not silent no-op."""
        adapter, issue_key = throwaway_issue
        with pytest.raises(TransitionNotAvailableError) as exc_info:
            await adapter.update_task(issue_key, status="Banana")
        err = exc_info.value
        assert err.task_id == issue_key
        assert err.requested_status == "Banana"
        assert err.available_transitions, (
            "Error must expose the available transitions so callers can diagnose"
        )
        # Current status should be captured too (for the audit-log story).
        assert err.current_status != ""

    @requires_jira
    @pytest.mark.asyncio
    async def test_update_comment_still_works_on_walk(self, throwaway_issue) -> None:
        """Commenting during workflow walk coexists with status transitions."""
        adapter, issue_key = throwaway_issue
        await adapter.update_task(
            issue_key,
            status="In Progress",
            comment="workflow-walk test: moved to in progress",
        )
        detail = await adapter.get_issue(issue_key)
        assert detail.status == "In Progress"
        # Our comment should appear in the most-recent comments.
        bodies = [c.body for c in detail.comments]
        assert any("moved to in progress" in b for b in bodies)
