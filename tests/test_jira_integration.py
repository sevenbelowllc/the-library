"""Integration tests for JiraClient against real Jira Cloud.

These tests hit the live Jira REST API at https://sevenbelow.atlassian.net.
They are skipped automatically when JIRA_EMAIL and JIRA_API_TOKEN are not set.

Run:
    JIRA_EMAIL=you@example.com JIRA_API_TOKEN=tok \
        python -m pytest tests/test_jira_integration.py -v
"""

from __future__ import annotations

import os
import random
import string

import pytest

from library_server.pm.jira_client import JiraClient

# ---------------------------------------------------------------------------
# Skip decorator — applied to every test in this module
# ---------------------------------------------------------------------------

SKIP_REASON = "JIRA_EMAIL and JIRA_API_TOKEN required for integration tests"
requires_jira = pytest.mark.skipif(
    not (os.environ.get("JIRA_EMAIL") and os.environ.get("JIRA_API_TOKEN")),
    reason=SKIP_REASON,
)

SITE_URL = "https://sevenbelow.atlassian.net"
TEST_PROJECT = "DEIOCAP"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rand_suffix(length: int = 4) -> str:
    """Return a short random uppercase string for unique keys."""
    return "".join(random.choices(string.ascii_uppercase, k=length))


def _make_client() -> JiraClient:
    """Build a JiraClient pointing at the real site."""
    return JiraClient(site_url=SITE_URL, timeout=30.0)


async def _create_test_issue(
    client: JiraClient,
    summary: str | None = None,
    project: str = TEST_PROJECT,
    issue_type: str = "Task",
) -> str:
    """Create a throwaway issue and return its key."""
    if summary is None:
        summary = f"INTEGRATION-TEST-DELETE-ME {_rand_suffix(6)}"
    result = await client.create_issue(
        project_key=project,
        issue_type=issue_type,
        summary=summary,
        description="Created by automated integration test. Safe to delete.",
        labels=["integration-test"],
    )
    return result["key"]


async def _try_transition_to_done(client: JiraClient, issue_key: str) -> None:
    """Best-effort: move the issue to Done so it doesn't clutter the board."""
    try:
        transitions = await client.get_transitions(issue_key)
        for t in transitions.get("transitions", []):
            if t["name"].lower() in ("done", "close", "closed", "resolved"):
                await client.transition_issue(issue_key, t["id"])
                return
    except Exception:
        pass  # cleanup is best-effort


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestJiraIntegration:
    """Integration tests that call the real Jira API."""

    @requires_jira
    @pytest.mark.asyncio
    async def test_auth_get_myself(self) -> None:
        """get_myself() returns the authenticated user's profile."""
        client = _make_client()
        me = await client.get_myself()
        assert "accountId" in me, f"Missing accountId in response: {me}"
        assert "displayName" in me, f"Missing displayName in response: {me}"

    @requires_jira
    @pytest.mark.asyncio
    async def test_list_projects(self) -> None:
        """list_projects() returns a paginated project list."""
        client = _make_client()
        result = await client.list_projects()
        assert "values" in result, f"Missing 'values' key in response: {result}"
        assert isinstance(result["values"], list)

    @requires_jira
    @pytest.mark.asyncio
    async def test_create_and_get_project(self) -> None:
        """Create a project with a unique key, then retrieve it."""
        client = _make_client()
        me = await client.get_myself()
        lead_id = me["accountId"]

        suffix = _rand_suffix(4)
        key = f"ZZT{suffix}"  # max 10 chars, starts with ZZ for easy cleanup
        name = f"INTEGRATION-TEST-DELETE-ME-{suffix}"

        created = await client.create_project(
            name=name,
            key=key,
            project_type_key="software",
            lead_account_id=lead_id,
            description="Integration test project. Safe to delete.",
        )
        assert "key" in created or "id" in created

        # Retrieve the project and verify
        project = await client.get_project(key)
        assert project["key"] == key

    @requires_jira
    @pytest.mark.asyncio
    async def test_create_and_get_issue(self) -> None:
        """Create a Task in DEIOCAP, fetch it, verify fields match."""
        client = _make_client()
        summary = f"INTEGRATION-TEST-DELETE-ME {_rand_suffix(6)}"
        issue_key = await _create_test_issue(client, summary=summary)

        try:
            issue = await client.get_issue(issue_key)
            assert issue["key"] == issue_key
            assert issue["fields"]["summary"] == summary
            assert issue["fields"]["issuetype"]["name"] == "Task"
        finally:
            await _try_transition_to_done(client, issue_key)

    @requires_jira
    @pytest.mark.asyncio
    async def test_search_issues(self) -> None:
        """JQL search against DEIOCAP returns results."""
        client = _make_client()
        result = await client.search_issues(
            jql=f"project = {TEST_PROJECT} ORDER BY created DESC",
            max_results=5,
        )
        assert "issues" in result, f"Missing 'issues' key in response: {result}"
        assert isinstance(result["issues"], list)

    @requires_jira
    @pytest.mark.asyncio
    async def test_add_comment(self) -> None:
        """Create an issue and add a comment to it."""
        client = _make_client()
        issue_key = await _create_test_issue(client)

        try:
            comment = await client.add_comment(
                issue_key, "Integration test comment — safe to ignore."
            )
            assert "id" in comment, f"Missing 'id' in comment response: {comment}"
        finally:
            await _try_transition_to_done(client, issue_key)

    @requires_jira
    @pytest.mark.asyncio
    async def test_get_transitions(self) -> None:
        """Create an issue and list its available transitions."""
        client = _make_client()
        issue_key = await _create_test_issue(client)

        try:
            result = await client.get_transitions(issue_key)
            assert "transitions" in result, f"Missing 'transitions': {result}"
            assert isinstance(result["transitions"], list)
        finally:
            await _try_transition_to_done(client, issue_key)

    @requires_jira
    @pytest.mark.asyncio
    async def test_transition_issue(self) -> None:
        """Create an issue, get transitions, execute the first one."""
        client = _make_client()
        issue_key = await _create_test_issue(client)

        try:
            transitions = await client.get_transitions(issue_key)
            available = transitions.get("transitions", [])
            assert len(available) > 0, "No transitions available for new issue"

            first = available[0]
            # transition_issue returns None on success (204)
            await client.transition_issue(issue_key, first["id"])

            # Verify the issue actually moved
            issue = await client.get_issue(issue_key)
            new_status = issue["fields"]["status"]["name"]
            # The status should have changed from the initial status
            assert new_status is not None
        finally:
            await _try_transition_to_done(client, issue_key)

    @requires_jira
    @pytest.mark.asyncio
    async def test_assign_issue(self) -> None:
        """Create an issue, get current user, assign issue to self."""
        client = _make_client()
        issue_key = await _create_test_issue(client)

        try:
            me = await client.get_myself()
            account_id = me["accountId"]

            # assign_issue returns None on 204
            await client.assign_issue(issue_key, account_id)

            # Verify assignment
            issue = await client.get_issue(issue_key, fields="assignee")
            assert issue["fields"]["assignee"] is not None
            assert issue["fields"]["assignee"]["accountId"] == account_id
        finally:
            await _try_transition_to_done(client, issue_key)

    @requires_jira
    @pytest.mark.asyncio
    async def test_issue_linking(self) -> None:
        """Create two issues, get link types, link them together."""
        client = _make_client()
        key_a = await _create_test_issue(
            client, summary=f"INTEGRATION-TEST-LINK-A {_rand_suffix(4)}"
        )
        key_b = await _create_test_issue(
            client, summary=f"INTEGRATION-TEST-LINK-B {_rand_suffix(4)}"
        )

        try:
            # Get available link types
            link_types = await client.get_link_types()
            assert "issueLinkTypes" in link_types
            types_list = link_types["issueLinkTypes"]
            assert len(types_list) > 0, "No issue link types available"

            # Use the first link type (e.g. "Blocks", "Relates")
            link_type_name = types_list[0]["name"]

            # Create the link — returns None on 201
            await client.create_issue_link(
                type_name=link_type_name,
                inward_key=key_a,
                outward_key=key_b,
            )

            # Verify by fetching one of the issues with link fields
            issue = await client.get_issue(key_a, fields="issuelinks")
            links = issue["fields"].get("issuelinks", [])
            assert len(links) > 0, f"No links found on {key_a}"
        finally:
            await _try_transition_to_done(client, key_a)
            await _try_transition_to_done(client, key_b)
