"""Integration tests for JiraClient against real Jira Cloud.

These tests hit the live Jira REST API at https://sevenbelow.atlassian.net.
They are skipped automatically when ATLASSIAN_EMAIL and JIRA_API_TOKEN are not set.

Cleanup contract (LIBRARY-7):
    Every test that creates external state (issues, projects, links) registers
    its artefact with the ``jira_cleanup`` fixture. The fixture's ``finally``
    block deletes every registered artefact on pass, fail, timeout or SIGINT.

    Best-effort: cleanup errors are logged but do not mask the original test
    failure. See TESTING-STANDARD.md §4.

Run:
    ATLASSIAN_EMAIL=you@example.com JIRA_API_TOKEN=tok \\
        python -m pytest tests/test_jira_integration.py -v
"""

from __future__ import annotations

import logging
import os
import random
import string
from dataclasses import dataclass, field
from typing import AsyncIterator

import pytest

from library_server.pm.jira_client import JiraApiError, JiraClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Skip decorator — applied to every test in this module
# ---------------------------------------------------------------------------

SKIP_REASON = "ATLASSIAN_EMAIL and JIRA_API_TOKEN required for integration tests"
requires_jira = pytest.mark.skipif(
    not (os.environ.get("ATLASSIAN_EMAIL") and os.environ.get("JIRA_API_TOKEN")),
    reason=SKIP_REASON,
)

SITE_URL = "https://sevenbelow.atlassian.net"
TEST_PROJECT = "DEIOCAP"


# ---------------------------------------------------------------------------
# Cleanup registry
# ---------------------------------------------------------------------------


@dataclass
class JiraCleanupRegistry:
    """Tracks external-state artefacts created during a test.

    Every test that calls the live Jira API MUST register its artefacts here.
    The owning fixture guarantees deletion in a ``finally`` block — runs on
    test pass, fail, timeout, or process interruption (pytest's fixture
    finalisers run even when the test body raises or is cancelled).
    """

    client: JiraClient
    issues: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)

    def track_issue(self, issue_key: str) -> None:
        self.issues.append(issue_key)

    def track_project(self, project_key: str) -> None:
        self.projects.append(project_key)

    async def purge(self) -> list[str]:
        """Delete every registered artefact. Returns list of failures."""
        failures: list[str] = []
        # Delete issues first (projects deletion will also delete their issues,
        # but explicit is better for pollution hygiene).
        for key in self.issues:
            try:
                await self.client.delete_issue(key)
            except JiraApiError as e:
                # 404 = already gone (e.g. parent project deleted first)
                if e.status_code != 404:
                    failures.append(f"delete_issue({key}): {e}")
                    logger.error("cleanup failed for issue %s: %s", key, e)
            except Exception as e:  # noqa: BLE001
                failures.append(f"delete_issue({key}): {e}")
                logger.error("cleanup failed for issue %s: %s", key, e)

        for pkey in self.projects:
            try:
                await self.client.delete_project(pkey)
            except JiraApiError as e:
                if e.status_code != 404:
                    failures.append(f"delete_project({pkey}): {e}")
                    logger.error("cleanup failed for project %s: %s", pkey, e)
            except Exception as e:  # noqa: BLE001
                failures.append(f"delete_project({pkey}): {e}")
                logger.error("cleanup failed for project %s: %s", pkey, e)

        return failures


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def jira_cleanup() -> AsyncIterator[JiraCleanupRegistry]:
    """Yield a cleanup registry; guarantee purge on teardown.

    The ``try/finally`` ensures cleanup runs on pass, fail, or exception.
    pytest fixture finalisers also run on ``KeyboardInterrupt`` / SIGINT
    delivered to the worker, satisfying TESTING-STANDARD §4.1.
    """
    client = _make_client()
    registry = JiraCleanupRegistry(client=client)
    try:
        yield registry
    finally:
        failures = await registry.purge()
        if failures:
            # Loud log per the standard: swallowed cleanup is a CI bug.
            pytest.fail(
                "jira_cleanup teardown incurred failures:\n  "
                + "\n  ".join(failures),
                pytrace=False,
            )


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
    registry: JiraCleanupRegistry,
    summary: str | None = None,
    project: str = TEST_PROJECT,
    issue_type: str = "Task",
) -> str:
    """Create a throwaway issue, register it for cleanup, and return its key."""
    if summary is None:
        summary = f"INTEGRATION-TEST-DELETE-ME {_rand_suffix(6)}"
    result = await registry.client.create_issue(
        project_key=project,
        issue_type=issue_type,
        summary=summary,
        description="Created by automated integration test. Safe to delete.",
        labels=["integration-test"],
    )
    key = result["key"]
    registry.track_issue(key)
    return key


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestJiraIntegration:
    """Integration tests that call the real Jira API."""

    @requires_jira
    @pytest.mark.asyncio
    async def test_auth_get_myself(self, jira_cleanup: JiraCleanupRegistry) -> None:
        """get_myself() returns the authenticated user's profile."""
        me = await jira_cleanup.client.get_myself()
        assert "accountId" in me, f"Missing accountId in response: {me}"
        assert "displayName" in me, f"Missing displayName in response: {me}"

    @requires_jira
    @pytest.mark.asyncio
    async def test_list_projects(self, jira_cleanup: JiraCleanupRegistry) -> None:
        """list_projects() returns a paginated project list."""
        result = await jira_cleanup.client.list_projects()
        assert "values" in result, f"Missing 'values' key in response: {result}"
        assert isinstance(result["values"], list)

    @requires_jira
    @pytest.mark.asyncio
    async def test_create_and_get_project(self, jira_cleanup: JiraCleanupRegistry) -> None:
        """Create a project with a unique key, then retrieve it — cleanup deletes it."""
        client = jira_cleanup.client
        me = await client.get_myself()
        lead_id = me["accountId"]

        suffix = _rand_suffix(4)
        key = f"ZZT{suffix}"  # ZZ* prefix is the canonical test-project marker
        name = f"INTEGRATION-TEST-DELETE-ME-{suffix}"

        created = await client.create_project(
            name=name,
            key=key,
            project_type_key="software",
            lead_account_id=lead_id,
            description="Integration test project. Safe to delete.",
        )
        jira_cleanup.track_project(key)
        assert "key" in created or "id" in created

        project = await client.get_project(key)
        assert project["key"] == key

    @requires_jira
    @pytest.mark.asyncio
    async def test_create_and_get_issue(self, jira_cleanup: JiraCleanupRegistry) -> None:
        """Create a Task in DEIOCAP, fetch it, verify fields match — cleanup deletes it."""
        summary = f"INTEGRATION-TEST-DELETE-ME {_rand_suffix(6)}"
        issue_key = await _create_test_issue(jira_cleanup, summary=summary)

        issue = await jira_cleanup.client.get_issue(issue_key)
        assert issue["key"] == issue_key
        assert issue["fields"]["summary"] == summary
        assert issue["fields"]["issuetype"]["name"] == "Task"

    @requires_jira
    @pytest.mark.asyncio
    async def test_search_issues(self, jira_cleanup: JiraCleanupRegistry) -> None:
        """JQL search against DEIOCAP returns results."""
        result = await jira_cleanup.client.search_issues(
            jql=f"project = {TEST_PROJECT} ORDER BY created DESC",
            max_results=5,
        )
        assert "issues" in result, f"Missing 'issues' key in response: {result}"
        assert isinstance(result["issues"], list)

    @requires_jira
    @pytest.mark.asyncio
    async def test_add_comment(self, jira_cleanup: JiraCleanupRegistry) -> None:
        """Create an issue and add a comment to it."""
        issue_key = await _create_test_issue(jira_cleanup)
        comment = await jira_cleanup.client.add_comment(
            issue_key, "Integration test comment — safe to ignore."
        )
        assert "id" in comment, f"Missing 'id' in comment response: {comment}"

    @requires_jira
    @pytest.mark.asyncio
    async def test_get_transitions(self, jira_cleanup: JiraCleanupRegistry) -> None:
        """Create an issue and list its available transitions."""
        issue_key = await _create_test_issue(jira_cleanup)
        result = await jira_cleanup.client.get_transitions(issue_key)
        assert "transitions" in result, f"Missing 'transitions': {result}"
        assert isinstance(result["transitions"], list)

    @requires_jira
    @pytest.mark.asyncio
    async def test_transition_issue(self, jira_cleanup: JiraCleanupRegistry) -> None:
        """Create an issue, get transitions, execute the first one."""
        issue_key = await _create_test_issue(jira_cleanup)
        transitions = await jira_cleanup.client.get_transitions(issue_key)
        available = transitions.get("transitions", [])
        assert len(available) > 0, "No transitions available for new issue"

        first = available[0]
        await jira_cleanup.client.transition_issue(issue_key, first["id"])

        issue = await jira_cleanup.client.get_issue(issue_key)
        assert issue["fields"]["status"]["name"] is not None

    @requires_jira
    @pytest.mark.asyncio
    async def test_assign_issue(self, jira_cleanup: JiraCleanupRegistry) -> None:
        """Create an issue, get current user, assign issue to self."""
        issue_key = await _create_test_issue(jira_cleanup)
        me = await jira_cleanup.client.get_myself()
        account_id = me["accountId"]

        await jira_cleanup.client.assign_issue(issue_key, account_id)

        issue = await jira_cleanup.client.get_issue(issue_key, fields="assignee")
        assert issue["fields"]["assignee"] is not None
        assert issue["fields"]["assignee"]["accountId"] == account_id

    @requires_jira
    @pytest.mark.asyncio
    async def test_issue_linking(self, jira_cleanup: JiraCleanupRegistry) -> None:
        """Create two issues, get link types, link them together."""
        client = jira_cleanup.client
        key_a = await _create_test_issue(
            jira_cleanup, summary=f"INTEGRATION-TEST-LINK-A {_rand_suffix(4)}"
        )
        key_b = await _create_test_issue(
            jira_cleanup, summary=f"INTEGRATION-TEST-LINK-B {_rand_suffix(4)}"
        )

        link_types = await client.get_link_types()
        assert "issueLinkTypes" in link_types
        types_list = link_types["issueLinkTypes"]
        assert len(types_list) > 0, "No issue link types available"

        link_type_name = types_list[0]["name"]
        await client.create_issue_link(
            type_name=link_type_name,
            inward_key=key_a,
            outward_key=key_b,
        )

        issue = await client.get_issue(key_a, fields="issuelinks")
        links = issue["fields"].get("issuelinks", [])
        assert len(links) > 0, f"No links found on {key_a}"
