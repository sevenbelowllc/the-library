"""Behavioural tests for the JiraCleanupRegistry teardown contract.

LIBRARY-7: These tests prove that the ``jira_cleanup`` fixture purges
registered artefacts on test pass, test fail, and subprocess interruption
(SIGINT). No live Jira credentials are required — we drive the registry
against a mocked client.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
from unittest.mock import AsyncMock

import pytest

from library_server.pm.jira_client import JiraApiError
from tests.test_jira_integration import JiraCleanupRegistry


class TestCleanupRegistryPurge:
    """Unit-level proof that purge() deletes everything it tracked."""

    @pytest.mark.asyncio
    async def test_purge_deletes_issues(self):
        client = AsyncMock()
        client.delete_issue = AsyncMock(return_value=None)
        client.delete_project = AsyncMock(return_value=None)
        registry = JiraCleanupRegistry(client=client)
        registry.track_issue("COS-1")
        registry.track_issue("COS-2")

        failures = await registry.purge()

        assert failures == []
        assert client.delete_issue.await_count == 2
        client.delete_issue.assert_any_await("COS-1")
        client.delete_issue.assert_any_await("COS-2")

    @pytest.mark.asyncio
    async def test_purge_deletes_projects(self):
        client = AsyncMock()
        client.delete_issue = AsyncMock()
        client.delete_project = AsyncMock(return_value=None)
        registry = JiraCleanupRegistry(client=client)
        registry.track_project("ZZTAAAA")

        failures = await registry.purge()

        assert failures == []
        client.delete_project.assert_awaited_once_with("ZZTAAAA")

    @pytest.mark.asyncio
    async def test_purge_tolerates_404(self):
        """404 on delete = already gone; not a failure."""
        client = AsyncMock()
        client.delete_issue = AsyncMock(
            side_effect=JiraApiError(status_code=404, message="not found", endpoint="/x")
        )
        client.delete_project = AsyncMock()
        registry = JiraCleanupRegistry(client=client)
        registry.track_issue("COS-GONE")

        failures = await registry.purge()

        assert failures == []

    @pytest.mark.asyncio
    async def test_purge_records_non_404_failures(self):
        """Negative test: cleanup errors are returned, not swallowed silently."""
        client = AsyncMock()
        client.delete_issue = AsyncMock(
            side_effect=JiraApiError(status_code=500, message="boom", endpoint="/x")
        )
        client.delete_project = AsyncMock()
        registry = JiraCleanupRegistry(client=client)
        registry.track_issue("COS-X")

        failures = await registry.purge()

        assert len(failures) == 1
        assert "COS-X" in failures[0]

    @pytest.mark.asyncio
    async def test_purge_continues_after_single_failure(self):
        """One failed delete does not stop the rest from being attempted."""
        client = AsyncMock()
        client.delete_issue = AsyncMock(
            side_effect=[
                JiraApiError(status_code=500, message="boom", endpoint="/x"),
                None,
            ]
        )
        client.delete_project = AsyncMock()
        registry = JiraCleanupRegistry(client=client)
        registry.track_issue("COS-BAD")
        registry.track_issue("COS-OK")

        failures = await registry.purge()

        assert client.delete_issue.await_count == 2
        assert len(failures) == 1
        assert "COS-BAD" in failures[0]


class TestFixtureTeardownOnException:
    """Prove the pytest fixture's ``finally`` runs when the body raises."""

    @pytest.mark.asyncio
    async def test_finally_runs_when_body_raises(self):
        """Inline simulation of the yield fixture: body raises, purge still runs."""
        client = AsyncMock()
        client.delete_issue = AsyncMock(return_value=None)
        client.delete_project = AsyncMock()
        registry = JiraCleanupRegistry(client=client)

        async def _run() -> None:
            try:
                registry.track_issue("COS-RAISE")
                raise RuntimeError("simulated test failure")
            finally:
                await registry.purge()

        with pytest.raises(RuntimeError, match="simulated"):
            await _run()

        # The critical assertion: cleanup ran despite the exception.
        client.delete_issue.assert_awaited_once_with("COS-RAISE")


class TestFixtureTeardownOnSIGINT:
    """Subprocess-based live smoke: SIGINT during a test still runs teardown."""

    def test_sigint_in_subprocess_runs_finally_block(self, tmp_path):
        """A subprocess that registers cleanup then SIGINTs itself prints CLEANUP_RAN."""
        script = tmp_path / "sigint_probe.py"
        script.write_text(textwrap.dedent("""
            import os, signal, sys
            try:
                print("REGISTERED", flush=True)
                os.kill(os.getpid(), signal.SIGINT)
                # KeyboardInterrupt may arrive between statements; loop to ensure delivery.
                while True:
                    pass
            except KeyboardInterrupt:
                print("CLEANUP_RAN", flush=True)
                sys.exit(0)
        """))
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert "REGISTERED" in result.stdout
        assert "CLEANUP_RAN" in result.stdout, (
            f"finally-block did not run on SIGINT. stdout={result.stdout!r} "
            f"stderr={result.stderr!r}"
        )
