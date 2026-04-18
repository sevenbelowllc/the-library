"""Tests for server.py MCP tool handlers."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
import yaml

from library_server.server import (
    library_config_get,
    library_config_set,
    library_checkpoint_write,
    library_checkpoint_read,
    library_checkpoint_list,
    library_memory_scan,
    library_memory_aggregate,
    library_memory_prune,
    library_vault_init,
    library_vault_validate,
    library_vault_parse,
    library_vault_ingest,
    library_pm_create_task,
    library_pm_create_epic,
    library_pm_sync,
    library_pm_update,
    library_pm_query,
    library_graph_rebuild,
    library_graph_query,
    library_graph_path,
    library_memory_health,
    library_memory_learn,
    library_vault_builder_config,
    library_vault_builder_survey,
    library_vault_builder_preview,
    library_vault_builder_build,
    library_vault_builder_extract,
    _get_pm_adapter,
    _get_vault_orchestrator,
)
from library_server.types import TaskResult, TaskStatus, EpicResult, ProjectState


# --- Helpers ---

def _make_config_mock(sections=None):
    """Build a mock config that returns sections by name."""
    defaults = {
        "checkpoints": {"path": "/tmp/checkpoints"},
        "memory": {"path": "/tmp/memory", "stale_threshold_days": 30},
        "vault": {"path": "/tmp/vault"},
        "pm": {"provider": "none"},
        "graphify": {"enabled": False, "graph_path": "/tmp/graph.json", "mode": "deep"},
    }
    if sections:
        defaults.update(sections)

    config = MagicMock()
    config.get_section.side_effect = lambda s: defaults.get(s, {})
    config.to_dict.return_value = defaults
    config.path = Path("/tmp/library-config.yaml")
    return config


# --- Config tools ---

class TestConfigTools:

    def test_config_get_all(self):
        mock_cfg = _make_config_mock()
        with patch("library_server.server.get_config", return_value=mock_cfg):
            result = library_config_get("")
            assert "checkpoints" in result

    def test_config_get_section(self):
        mock_cfg = _make_config_mock()
        with patch("library_server.server.get_config", return_value=mock_cfg):
            result = library_config_get("memory")
            assert result["path"] == "/tmp/memory"

    def test_config_set(self):
        mock_cfg = _make_config_mock()
        with patch("library_server.server.get_config", return_value=mock_cfg):
            result = library_config_set("pm", "provider", "jira")
            assert result["status"] == "updated"
            assert result["section"] == "pm"
            mock_cfg.set_value.assert_called_once_with("pm", "provider", "jira")
            mock_cfg.save.assert_called_once()


# --- Checkpoint tools ---

class TestCheckpointTools:

    def test_checkpoint_write(self):
        mock_cfg = _make_config_mock()
        with patch("library_server.server.get_config", return_value=mock_cfg), \
             patch("library_server.server.resolve_checkpoint_dir", return_value=Path("/tmp/checkpoints")), \
             patch("library_server.checkpoint.checkpoint.write_checkpoint", return_value={"status": "written"}) as mock_write:
            result = library_checkpoint_write(
                topic="test",
                status="in_progress",
                next_session="Continue testing",
                accomplished="item1;item2",
                next_actions="action1;action2",
                key_context="ctx1",
            )
            assert result["status"] == "written"
            call_args = mock_write.call_args
            data = call_args[0][1]
            assert data.topic == "test"
            assert data.accomplished == ["item1", "item2"]
            assert data.next_actions == ["action1", "action2"]
            assert data.key_context == ["ctx1"]

    def test_checkpoint_write_empty_lists(self):
        mock_cfg = _make_config_mock()
        with patch("library_server.server.get_config", return_value=mock_cfg), \
             patch("library_server.server.resolve_checkpoint_dir", return_value=Path("/tmp/checkpoints")), \
             patch("library_server.checkpoint.checkpoint.write_checkpoint", return_value={"status": "written"}) as mock_write:
            result = library_checkpoint_write(
                topic="test",
                status="done",
                next_session="None",
            )
            data = mock_write.call_args[0][1]
            assert data.accomplished == []
            assert data.next_actions == []
            assert data.key_context == []

    def test_checkpoint_write_errors_when_misconfigured(self):
        """Hard rule: missing reading_room.path returns an error, not a silent fallback."""
        mock_cfg = _make_config_mock()
        with patch("library_server.server.get_config", return_value=mock_cfg), \
             patch("library_server.server.resolve_checkpoint_dir", side_effect=ValueError("reading_room.path is not configured")):
            result = library_checkpoint_write(topic="t", status="s", next_session="n")
            assert result["status"] == "error"
            assert "reading_room.path" in result["error"]

    def test_checkpoint_read(self):
        with patch("library_server.checkpoint.checkpoint.read_checkpoint", return_value={"topic": "test"}):
            result = library_checkpoint_read("/tmp/cp.md")
            assert result["topic"] == "test"

    def test_checkpoint_list_default_path(self):
        mock_cfg = _make_config_mock()
        with patch("library_server.server.get_config", return_value=mock_cfg), \
             patch("library_server.server.resolve_checkpoint_dir", return_value=Path("/tmp/checkpoints")), \
             patch("library_server.checkpoint.checkpoint.list_checkpoints", return_value={"checkpoints": []}) as mock_list:
            result = library_checkpoint_list()
            mock_list.assert_called_once_with("/tmp/checkpoints")

    def test_checkpoint_list_custom_path(self):
        with patch("library_server.checkpoint.checkpoint.list_checkpoints", return_value={"checkpoints": []}) as mock_list:
            library_checkpoint_list("/custom/path")
            mock_list.assert_called_once_with("/custom/path")


# --- Memory tools ---

class TestMemoryTools:

    def test_memory_scan_default_path(self):
        mock_cfg = _make_config_mock()
        with patch("library_server.server.get_config", return_value=mock_cfg), \
             patch("library_server.memory.scan.scan_memories", return_value={"entries": [], "stale_count": 0, "total_count": 0}) as mock_scan:
            result = library_memory_scan()
            mock_scan.assert_called_once_with("/tmp/memory", 30)
            assert result["total_count"] == 0

    def test_memory_scan_custom_path(self):
        mock_cfg = _make_config_mock()
        with patch("library_server.server.get_config", return_value=mock_cfg), \
             patch("library_server.memory.scan.scan_memories", return_value={"entries": [], "stale_count": 0, "total_count": 0}) as mock_scan:
            library_memory_scan(memory_path="/custom", stale_threshold_days=7)
            mock_scan.assert_called_once_with("/custom", 7)

    def test_memory_aggregate_default(self):
        mock_cfg = _make_config_mock()
        with patch("library_server.server.get_config", return_value=mock_cfg), \
             patch("library_server.memory.aggregate.aggregate_memories", return_value={"suggestions": []}) as mock_agg:
            result = library_memory_aggregate()
            mock_agg.assert_called_once_with("/tmp/memory", True)

    def test_memory_prune_default(self):
        mock_cfg = _make_config_mock()
        with patch("library_server.server.get_config", return_value=mock_cfg), \
             patch("library_server.memory.prune.prune_stale", return_value={"pruned_count": 0}) as mock_prune:
            result = library_memory_prune()
            mock_prune.assert_called_once_with("/tmp/memory", 30, True)


# --- Vault tools ---

class TestVaultTools:

    def test_vault_init(self):
        with patch("library_server.vault.init.init_vault", return_value={"status": "created"}) as mock_init:
            result = library_vault_init("/tmp/vault")
            mock_init.assert_called_once_with("/tmp/vault")
            assert result["status"] == "created"

    def test_vault_validate(self):
        with patch("library_server.vault.validate.validate_vault", return_value={"valid": True}) as mock_val:
            result = library_vault_validate("/tmp/vault")
            assert result["valid"] is True

    def test_vault_parse(self):
        with patch("library_server.vault.parse.parse_vault", return_value={"tags": []}) as mock_parse:
            result = library_vault_parse("/tmp/vault")
            assert "tags" in result

    def test_vault_ingest(self):
        with patch("library_server.vault.ingest.ingest_source", return_value={"status": "ingested"}) as mock_ingest:
            result = library_vault_ingest("/tmp/vault", "/tmp/source.md", "raw", "specs")
            mock_ingest.assert_called_once_with("/tmp/vault", "/tmp/source.md", "raw", "specs")


# --- PM tools ---

class TestPMTools:

    @pytest.mark.asyncio
    async def test_pm_create_task(self):
        mock_adapter = AsyncMock()
        mock_adapter.create_task.return_value = TaskResult(
            task_id="PROJ-1", project_key="PROJ", summary="Test", status=TaskStatus.OPEN, url="http://example.com"
        )
        with patch("library_server.server._get_pm_adapter", return_value=mock_adapter):
            result = await library_pm_create_task("PROJ", "Test", "Desc", "label1,label2")
            assert result["task_id"] == "PROJ-1"
            mock_adapter.create_task.assert_called_once_with(
                "PROJ", "Test", "Desc", ["label1", "label2"], epic_id=""
            )

    @pytest.mark.asyncio
    async def test_pm_create_task_no_labels(self):
        mock_adapter = AsyncMock()
        mock_adapter.create_task.return_value = TaskResult(
            task_id="PROJ-1", project_key="PROJ", summary="Test", status=TaskStatus.OPEN, url=""
        )
        with patch("library_server.server._get_pm_adapter", return_value=mock_adapter):
            result = await library_pm_create_task("PROJ", "Test", "Desc")
            mock_adapter.create_task.assert_called_once_with("PROJ", "Test", "Desc", [], epic_id="")

    @pytest.mark.asyncio
    async def test_pm_create_task_with_epic(self):
        mock_adapter = AsyncMock()
        mock_adapter.create_task.return_value = TaskResult(
            task_id="PROJ-5", project_key="PROJ", summary="Child", status=TaskStatus.OPEN, url=""
        )
        with patch("library_server.server._get_pm_adapter", return_value=mock_adapter):
            await library_pm_create_task("PROJ", "Child", "Desc", "", epic_id="PROJ-1")
            mock_adapter.create_task.assert_called_once_with(
                "PROJ", "Child", "Desc", [], epic_id="PROJ-1"
            )

    @pytest.mark.asyncio
    async def test_pm_create_epic(self):
        mock_adapter = AsyncMock()
        mock_adapter.create_epic.return_value = EpicResult(
            epic_id="PROJ-E1", project_key="PROJ", summary="Epic", url="http://example.com"
        )
        with patch("library_server.server._get_pm_adapter", return_value=mock_adapter):
            result = await library_pm_create_epic("PROJ", "Epic", "Desc")
            assert result["epic_id"] == "PROJ-E1"

    @pytest.mark.asyncio
    async def test_pm_sync(self):
        mock_adapter = AsyncMock()
        mock_adapter.sync_state.return_value = ProjectState(
            project_key="PROJ", project_name="PROJ",
            open_tasks=[TaskResult(task_id="PROJ-1", project_key="PROJ", summary="Open", status=TaskStatus.OPEN, url="")],
            stale_tasks=[], blocked_tasks=[], recently_closed=[],
        )
        with patch("library_server.server._get_pm_adapter", return_value=mock_adapter):
            result = await library_pm_sync("PROJ")
            assert result["open"] == 1
            assert result["blocked"] == 0

    @pytest.mark.asyncio
    async def test_pm_update(self):
        mock_adapter = AsyncMock()
        mock_adapter.update_task.return_value = TaskResult(
            task_id="PROJ-1", project_key="PROJ", summary="Done", status=TaskStatus.DONE, url=""
        )
        with patch("library_server.server._get_pm_adapter", return_value=mock_adapter):
            result = await library_pm_update("PROJ-1", status="Done", comment="Finished")
            assert result["status"] == "done"
            mock_adapter.update_task.assert_called_once_with("PROJ-1", "Done", "Finished")

    @pytest.mark.asyncio
    async def test_pm_update_empty_strings(self):
        mock_adapter = AsyncMock()
        mock_adapter.update_task.return_value = TaskResult(
            task_id="PROJ-1", project_key="PROJ", summary="T", status=TaskStatus.OPEN, url=""
        )
        with patch("library_server.server._get_pm_adapter", return_value=mock_adapter):
            await library_pm_update("PROJ-1")
            mock_adapter.update_task.assert_called_once_with("PROJ-1", None, None)

    @pytest.mark.asyncio
    async def test_pm_query(self):
        mock_adapter = AsyncMock()
        mock_adapter.query_tasks.return_value = [
            TaskResult(task_id="PROJ-1", project_key="PROJ", summary="T1", status=TaskStatus.OPEN, url=""),
        ]
        with patch("library_server.server._get_pm_adapter", return_value=mock_adapter):
            result = await library_pm_query("PROJ", status="Open", labels="bug,urgent")
            assert result["count"] == 1
            mock_adapter.query_tasks.assert_called_once_with("PROJ", {"status": "Open", "labels": ["bug", "urgent"]})

    @pytest.mark.asyncio
    async def test_pm_query_no_filters(self):
        mock_adapter = AsyncMock()
        mock_adapter.query_tasks.return_value = []
        with patch("library_server.server._get_pm_adapter", return_value=mock_adapter):
            result = await library_pm_query("PROJ")
            mock_adapter.query_tasks.assert_called_once_with("PROJ", None)


# --- _get_pm_adapter factory ---

class TestGetPMAdapter:

    def test_jira_adapter(self):
        mock_cfg = _make_config_mock({"pm": {"provider": "jira", "site_url": "https://test.atlassian.net"}})
        with patch("library_server.server.get_config", return_value=mock_cfg):
            adapter = _get_pm_adapter()
            from library_server.pm.jira import JiraAdapter
            assert isinstance(adapter, JiraAdapter)
            assert adapter.site_url == "https://test.atlassian.net"

    def test_linear_adapter(self):
        mock_cfg = _make_config_mock({"pm": {"provider": "linear", "api_key": "test-key"}})
        with patch("library_server.server.get_config", return_value=mock_cfg):
            adapter = _get_pm_adapter()
            from library_server.pm.linear import LinearAdapter
            assert isinstance(adapter, LinearAdapter)

    def test_unknown_provider_raises(self):
        mock_cfg = _make_config_mock({"pm": {"provider": "none"}})
        with patch("library_server.server.get_config", return_value=mock_cfg):
            with pytest.raises(ValueError, match="not configured"):
                _get_pm_adapter()


# --- Graph tools ---

class TestGraphTools:

    def test_graph_rebuild(self):
        mock_cfg = _make_config_mock()
        with patch("library_server.server.get_config", return_value=mock_cfg), \
             patch("library_server.graph.orchestrator.rebuild_graph", return_value={"status": "disabled"}) as mock_rebuild:
            result = library_graph_rebuild()
            assert result["status"] == "disabled"

    def test_graph_query(self):
        mock_cfg = _make_config_mock()
        with patch("library_server.server.get_config", return_value=mock_cfg), \
             patch("library_server.graph.orchestrator.query_graph", return_value={"results": []}) as mock_query:
            result = library_graph_query("test query")
            mock_query.assert_called_once_with(
                query="test query",
                graph_path="/tmp/graph.json",
                enabled=False,
            )

    def test_graph_path(self):
        mock_cfg = _make_config_mock()
        with patch("library_server.server.get_config", return_value=mock_cfg), \
             patch("library_server.graph.orchestrator.trace_path", return_value={"path": []}) as mock_trace:
            result = library_graph_path("nodeA", "nodeB")
            mock_trace.assert_called_once_with(
                node_a="nodeA",
                node_b="nodeB",
                graph_path="/tmp/graph.json",
                enabled=False,
            )


# --- Memory health & learn tools ---

class TestMemoryHealthTools:

    def test_memory_health_no_journal(self, tmp_path):
        config = {
            "vault": {"path": str(tmp_path / "vault")},
            "memory": {"session_dir": str(tmp_path / "sessions")},
        }
        with patch("library_server.hooks.config_loader.load_hook_config", return_value=config):
            result = library_memory_health()
            assert result["status"] == "healthy"
            assert result["vault_file_count"] == 0

    def test_memory_health_with_vault(self, tmp_path):
        vault = tmp_path / "vault"
        domains = vault / "domains"
        decisions = vault / "decisions"
        domains.mkdir(parents=True)
        decisions.mkdir(parents=True)
        (domains / "auth.md").write_text("# Auth")
        (decisions / "d1.md").write_text("# D1")

        config = {
            "vault": {"path": str(vault)},
            "memory": {"session_dir": str(tmp_path / "sessions")},
        }
        with patch("library_server.hooks.config_loader.load_hook_config", return_value=config):
            result = library_memory_health(vault_path=str(vault))
            assert result["domain_count"] == 1
            assert result["decision_count"] == 1

    def test_memory_learn_no_data(self, tmp_path):
        config = {
            "memory": {"session_dir": str(tmp_path / "sessions"), "keyword_learning": {}},
        }
        with patch("library_server.hooks.config_loader.load_hook_config", return_value=config):
            result = library_memory_learn()
            assert result["status"] == "no_data"

    def test_memory_learn_with_journal(self, tmp_path):
        sessions = tmp_path / "sessions"
        learning = sessions.parent / "learning"
        learning.mkdir(parents=True)
        journal = learning / "routing-journal.jsonl"
        journal.write_text('{"keyword": "test", "routed": true}\n')

        config = {
            "memory": {"session_dir": str(sessions), "keyword_learning": {}},
        }
        with patch("library_server.hooks.config_loader.load_hook_config", return_value=config), \
             patch("library_server.hooks.learning.analyze_routing_accuracy", return_value={"accuracy": 0.9}), \
             patch("library_server.hooks.learning.detect_drift", return_value=[]):
            result = library_memory_learn()
            assert result["status"] == "analyzed"


# --- Vault Builder tools ---

class TestVaultBuilderTools:

    def test_vault_builder_config(self):
        mock_cfg = _make_config_mock()
        mock_vb_cfg = MagicMock()
        mock_vb_cfg.mode = "full"
        mock_vb_cfg.output_vault = Path("/tmp/vault")
        mock_vb_cfg.parallel = True
        mock_vb_cfg.sources = {"specs": {"path": "/tmp/specs"}}
        mock_vb_cfg.graphify = {"enabled": False}
        mock_vb_cfg.axon = {"enabled": False}

        with patch("library_server.server.get_config", return_value=mock_cfg), \
             patch("library_server.vault_builder.config.load_vault_builder_config", return_value=mock_vb_cfg), \
             patch("library_server.vault_builder.config.validate_vault_builder_config", return_value=[]):
            result = library_vault_builder_config()
            assert result["valid"] is True
            assert result["mode"] == "full"

    def test_vault_builder_config_with_section(self):
        mock_cfg = _make_config_mock()
        mock_vb_cfg = MagicMock()
        mock_vb_cfg.mode = "full"
        mock_vb_cfg.output_vault = None
        mock_vb_cfg.parallel = True
        mock_vb_cfg.sources = {"specs": {"path": "/tmp/specs"}}
        mock_vb_cfg.graphify = {"enabled": False}
        mock_vb_cfg.axon = {"enabled": False}

        with patch("library_server.server.get_config", return_value=mock_cfg), \
             patch("library_server.vault_builder.config.load_vault_builder_config", return_value=mock_vb_cfg), \
             patch("library_server.vault_builder.config.validate_vault_builder_config", return_value=[]):
            result = library_vault_builder_config(section="specs")
            assert result["source_detail"] == {"path": "/tmp/specs"}
            assert result["output_vault"] is None

    @pytest.mark.asyncio
    async def test_vault_builder_survey(self):
        mock_orch = AsyncMock()
        mock_orch.output_vault = None
        mock_orch.survey.return_value = {"specs": {"file_count": 5}}
        with patch("library_server.server._get_vault_orchestrator", return_value=mock_orch):
            result = await library_vault_builder_survey("specs,jira")
            mock_orch.survey.assert_called_once_with(["specs", "jira"])
            assert result["sources"]["specs"]["file_count"] == 5

    @pytest.mark.asyncio
    async def test_vault_builder_survey_all(self):
        mock_orch = AsyncMock()
        mock_orch.output_vault = Path("/tmp/vault")
        mock_orch.survey.return_value = {}
        with patch("library_server.server._get_vault_orchestrator", return_value=mock_orch), \
             patch("library_server.vault_builder.orchestrator.detect_vault_state") as mock_detect:
            mock_detect.return_value = MagicMock(value="empty")
            result = await library_vault_builder_survey()
            mock_orch.survey.assert_called_once_with(None)
            assert result["vault_state"] == "empty"

    @pytest.mark.asyncio
    async def test_vault_builder_preview(self):
        mock_orch = AsyncMock()
        mock_orch.preview.return_value = {"specs": {"files": 3}}
        with patch("library_server.server._get_vault_orchestrator", return_value=mock_orch):
            result = await library_vault_builder_preview("specs")
            assert result["sources"]["specs"]["files"] == 3

    @pytest.mark.asyncio
    async def test_vault_builder_build(self):
        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.extract_results = []
        mock_result.graphify_status = "disabled"
        mock_result.duration_seconds = 1.234
        mock_result.manifest_path = "/tmp/manifest.yaml"

        mock_orch = AsyncMock()
        mock_orch.output_vault = None
        mock_orch.build.return_value = mock_result
        with patch("library_server.server._get_vault_orchestrator", return_value=mock_orch):
            result = await library_vault_builder_build()
            assert result["status"] == "success"
            assert result["duration_seconds"] == 1.2

    @pytest.mark.asyncio
    async def test_vault_builder_build_blocked(self):
        mock_orch = AsyncMock()
        mock_orch.output_vault = Path("/tmp/vault")
        mock_orch.mode = "full"
        with patch("library_server.server._get_vault_orchestrator", return_value=mock_orch), \
             patch("library_server.vault_builder.orchestrator.detect_vault_state") as mock_detect, \
             patch("library_server.vault_builder.orchestrator.check_safety_gate", return_value={"blocked": True, "message": "Vault exists"}):
            mock_detect.return_value = MagicMock()
            result = await library_vault_builder_build()
            assert result["status"] == "blocked"

    @pytest.mark.asyncio
    async def test_vault_builder_extract_dry_run(self):
        mock_orch = AsyncMock()
        mock_orch.preview.return_value = {"specs": {"files": 2}}
        with patch("library_server.server._get_vault_orchestrator", return_value=mock_orch):
            result = await library_vault_builder_extract("specs", dry_run=True)
            assert result["mode"] == "preview"

    @pytest.mark.asyncio
    async def test_vault_builder_extract_real(self):
        mock_result = MagicMock()
        mock_result.status = "success"
        mock_er = MagicMock()
        mock_er.source_name = "specs"
        mock_er.success = True
        mock_er.files_written = ["/tmp/f1.md"]
        mock_er.errors = []
        mock_result.extract_results = [mock_er]
        mock_orch = AsyncMock()
        mock_orch.build.return_value = mock_result
        with patch("library_server.server._get_vault_orchestrator", return_value=mock_orch):
            result = await library_vault_builder_extract("specs")
            assert result["status"] == "success"
            assert result["extract_results"][0]["files"] == 1


# --- _get_vault_orchestrator factory ---

class TestGetVaultOrchestrator:

    def test_builds_orchestrator(self):
        mock_cfg = _make_config_mock()
        mock_vb_cfg = MagicMock()
        mock_vb_cfg.sources = {}
        mock_vb_cfg.graphify = {"enabled": False}
        mock_vb_cfg.output_vault = Path("/tmp/out")
        mock_vb_cfg.mode = "full"

        with patch("library_server.server.get_config", return_value=mock_cfg), \
             patch("library_server.vault_builder.config.load_vault_builder_config", return_value=mock_vb_cfg):
            orch = _get_vault_orchestrator()
            assert orch is not None
            assert orch.mode == "full"

    def test_registers_configured_extractors(self):
        mock_cfg = _make_config_mock()
        mock_vb_cfg = MagicMock()
        mock_vb_cfg.sources = {
            "specs": {"path": "/tmp/specs"},
            "jira": {"site_url": "https://test.atlassian.net"},
        }
        mock_vb_cfg.graphify = {"enabled": False}
        mock_vb_cfg.output_vault = None
        mock_vb_cfg.mode = "incremental"

        with patch("library_server.server.get_config", return_value=mock_cfg), \
             patch("library_server.vault_builder.config.load_vault_builder_config", return_value=mock_vb_cfg):
            orch = _get_vault_orchestrator()
            # Should have registered the 2 configured extractors
            assert len(orch.registry._extractors) == 2
