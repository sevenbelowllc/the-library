"""The Library — MCP server entry point."""

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from library_server.config import load_config, LibraryConfig

mcp = FastMCP(
    "library",
    json_response=True,
)


def get_config() -> LibraryConfig:
    """Load config from library-config.yaml in current working directory."""
    return load_config()


# --- Config tools ---

@mcp.tool(name="library_config_get")
def library_config_get(section: str = "") -> dict:
    """Read current library configuration. Pass a section name (e.g. 'vault', 'pm') or empty for all."""
    config = get_config()
    if section:
        return config.get_section(section)
    return config.to_dict()


@mcp.tool(name="library_config_set")
def library_config_set(section: str, key: str, value: str) -> dict:
    """Update a configuration value. Example: section='pm', key='provider', value='linear'."""
    config = get_config()
    config.set_value(section, key, value)
    config.save()
    return {"status": "updated", "section": section, "key": key, "value": value}


# --- Checkpoint tools ---

@mcp.tool(name="library_checkpoint_write")
def library_checkpoint_write(
    topic: str,
    status: str,
    next_session: str,
    accomplished: str = "",
    next_actions: str = "",
    key_context: str = "",
) -> dict:
    """Write a session checkpoint. Lists are semicolon-separated strings."""
    from library_server.checkpoint.checkpoint import write_checkpoint
    from library_server.types import CheckpointData
    from datetime import date

    data = CheckpointData(
        topic=topic,
        date=date.today().isoformat(),
        status=status,
        next_session=next_session,
        accomplished=[s.strip() for s in accomplished.split(";") if s.strip()] if accomplished else [],
        next_actions=[s.strip() for s in next_actions.split(";") if s.strip()] if next_actions else [],
        key_context=[s.strip() for s in key_context.split(";") if s.strip()] if key_context else [],
    )
    checkpoint_path = get_config().get_section("checkpoints").get("path", "./checkpoints")
    return write_checkpoint(checkpoint_path, data)


@mcp.tool(name="library_checkpoint_read")
def library_checkpoint_read(checkpoint_path: str) -> dict:
    """Read and parse a checkpoint file. Returns structured session state."""
    from library_server.checkpoint.checkpoint import read_checkpoint
    return read_checkpoint(checkpoint_path)


@mcp.tool(name="library_checkpoint_list")
def library_checkpoint_list(checkpoint_dir: str = "") -> dict:
    """List all checkpoint files. Uses config path if no directory specified."""
    from library_server.checkpoint.checkpoint import list_checkpoints
    if not checkpoint_dir:
        checkpoint_dir = get_config().get_section("checkpoints").get("path", "./checkpoints")
    return list_checkpoints(checkpoint_dir)


# --- Memory tools ---

@mcp.tool(name="library_memory_scan")
def library_memory_scan(memory_path: str = "", stale_threshold_days: int = 30) -> dict:
    """Scan memory files for staleness and metadata. Returns entries with stale flags."""
    from library_server.memory.scan import scan_memories
    path = memory_path or get_config().get_section("memory").get("path", "./.library/memory")
    threshold = stale_threshold_days or get_config().get_section("memory").get("stale_threshold_days", 30)
    return scan_memories(path, threshold)


@mcp.tool(name="library_memory_aggregate")
def library_memory_aggregate(memory_path: str = "", dry_run: bool = True) -> dict:
    """Find merge opportunities for related memories. Set dry_run=False to apply."""
    from library_server.memory.aggregate import aggregate_memories
    path = memory_path or get_config().get_section("memory").get("path", "./.library/memory")
    return aggregate_memories(path, dry_run)


@mcp.tool(name="library_memory_prune")
def library_memory_prune(memory_path: str = "", stale_threshold_days: int = 30, dry_run: bool = True) -> dict:
    """Remove stale memory files. Set dry_run=False to delete. Updates MEMORY.md index."""
    from library_server.memory.prune import prune_stale
    path = memory_path or get_config().get_section("memory").get("path", "./.library/memory")
    threshold = stale_threshold_days or get_config().get_section("memory").get("stale_threshold_days", 30)
    return prune_stale(path, threshold, dry_run)


# --- Vault tools ---

@mcp.tool(name="library_vault_init")
def library_vault_init(vault_path: str) -> dict:
    """Bootstrap a new vault with Karpathy 3-layer structure (_schema/, sources/, wiki/, archive/)."""
    from library_server.vault.init import init_vault
    return init_vault(vault_path)


@mcp.tool(name="library_vault_validate")
def library_vault_validate(vault_path: str) -> dict:
    """Validate vault structure against schema. Returns {valid: bool, issues: list}."""
    from library_server.vault.validate import validate_vault
    return validate_vault(vault_path)


@mcp.tool(name="library_vault_parse")
def library_vault_parse(vault_path: str) -> dict:
    """Parse vault wiki articles. Returns tags ([VERIFY]/[CONFLICT]/[PLANNED]), frontmatter, headings."""
    from library_server.vault.parse import parse_vault
    return parse_vault(vault_path)


@mcp.tool(name="library_vault_ingest")
def library_vault_ingest(vault_path: str, source_path: str, tier: str, category: str) -> dict:
    """Ingest a file or directory into vault sources/<tier>/<category>/. Updates kb.yaml."""
    from library_server.vault.ingest import ingest_source
    return ingest_source(vault_path, source_path, tier, category)


# --- PM tools ---

@mcp.tool(name="library_pm_create_task")
async def library_pm_create_task(
    project_key: str, summary: str, description: str, labels: str = ""
) -> dict:
    """Create a task in the configured PM tool (Jira or Linear)."""
    adapter = _get_pm_adapter()
    label_list = [l.strip() for l in labels.split(",") if l.strip()] if labels else []
    result = await adapter.create_task(project_key, summary, description, label_list)
    return {"task_id": result.task_id, "summary": result.summary, "url": result.url}


@mcp.tool(name="library_pm_create_epic")
async def library_pm_create_epic(project_key: str, summary: str, description: str) -> dict:
    """Create an epic in the configured PM tool."""
    adapter = _get_pm_adapter()
    result = await adapter.create_epic(project_key, summary, description)
    return {"epic_id": result.epic_id, "summary": result.summary, "url": result.url}


@mcp.tool(name="library_pm_sync")
async def library_pm_sync(project_key: str) -> dict:
    """Pull current state from PM tool. Returns open, stale, blocked, recently closed tasks."""
    adapter = _get_pm_adapter()
    state = await adapter.sync_state(project_key)
    return {
        "project_key": state.project_key,
        "open": len(state.open_tasks),
        "blocked": len(state.blocked_tasks),
        "recently_closed": len(state.recently_closed),
        "tasks": [{"id": t.task_id, "summary": t.summary, "status": t.status.value} for t in state.open_tasks],
    }


@mcp.tool(name="library_pm_update")
async def library_pm_update(task_id: str, status: str = "", comment: str = "") -> dict:
    """Update a task's status or add a comment."""
    adapter = _get_pm_adapter()
    result = await adapter.update_task(task_id, status or None, comment or None)
    return {"task_id": result.task_id, "status": result.status.value}


@mcp.tool(name="library_pm_query")
async def library_pm_query(project_key: str, status: str = "", labels: str = "") -> dict:
    """Query tasks by filter. Returns matching tasks."""
    adapter = _get_pm_adapter()
    filters = {}
    if status:
        filters["status"] = status
    if labels:
        filters["labels"] = [l.strip() for l in labels.split(",")]
    results = await adapter.query_tasks(project_key, filters if filters else None)
    return {
        "count": len(results),
        "tasks": [{"id": t.task_id, "summary": t.summary, "status": t.status.value} for t in results],
    }


@mcp.tool(name="library_pm_create_project")
async def library_pm_create_project(
    name: str, key: str, description: str = "", project_type_key: str = "software", workflow_scheme: str = "",
) -> dict:
    """Create a Jira project. Requires admin access."""
    config = get_config()
    default_scheme = config.get_section("pm").get("workflow_scheme", "SevenBelow Standard SDLC Workflow")
    actual_scheme = workflow_scheme if workflow_scheme else default_scheme

    adapter = _get_pm_adapter()
    result = await adapter.create_project(name, key, description, workflow_scheme=actual_scheme)
    return {"project_key": result.project_key, "name": result.name, "url": result.url}


@mcp.tool(name="library_pm_list_projects")
async def library_pm_list_projects() -> dict:
    """List all visible projects."""
    adapter = _get_pm_adapter()
    results = await adapter.list_projects()
    return {
        "count": len(results),
        "projects": [
            {"key": p.project_key, "name": p.name, "description": p.description}
            for p in results
        ],
    }


@mcp.tool(name="library_pm_get_project")
async def library_pm_get_project(project_key: str) -> dict:
    """Get project details."""
    adapter = _get_pm_adapter()
    result = await adapter.get_project(project_key)
    return {
        "project_key": result.project_key, "name": result.name,
        "description": result.description, "lead": result.lead, "url": result.url,
    }


@mcp.tool(name="library_pm_update_project")
async def library_pm_update_project(
    project_key: str, name: str = "", description: str = "",
) -> dict:
    """Update project name or description."""
    adapter = _get_pm_adapter()
    result = await adapter.update_project(project_key, name, description)
    return {"project_key": result.project_key, "name": result.name, "url": result.url}


@mcp.tool(name="library_pm_assign_task")
async def library_pm_assign_task(task_id: str, account_id: str) -> dict:
    """Assign a task to a user by account ID."""
    adapter = _get_pm_adapter()
    result = await adapter.assign_task(task_id, account_id)
    return {"task_id": result.task_id, "status": result.status.value}


@mcp.tool(name="library_pm_link_issues")
async def library_pm_link_issues(
    type_name: str, inward_key: str, outward_key: str,
) -> dict:
    """Link two issues (e.g., 'Blocks', 'Relates')."""
    adapter = _get_pm_adapter()
    await adapter.link_issues(type_name, inward_key, outward_key)
    return {"status": "linked", "type": type_name, "inward": inward_key, "outward": outward_key}


@mcp.tool(name="library_pm_get_link_types")
async def library_pm_get_link_types() -> dict:
    """List available issue link types."""
    adapter = _get_pm_adapter()
    types = await adapter.get_link_types()
    return {"types": types}


def _get_pm_adapter() -> "PMAdapter":
    """Get the configured PM adapter."""
    from library_server.pm.adapter import PMAdapter
    config = get_config()
    pm_config = config.get_section("pm")
    provider = pm_config.get("provider", "none")

    if provider == "jira":
        from library_server.pm.jira import JiraAdapter
        return JiraAdapter(site_url=pm_config.get("site_url", ""))
    elif provider == "linear":
        from library_server.pm.linear import LinearAdapter
        return LinearAdapter(api_key=pm_config.get("api_key", ""))
    else:
        raise ValueError(f"PM provider '{provider}' not configured. Run library:config to set up.")


# --- Graph tools ---

@mcp.tool(name="library_graph_rebuild")
def library_graph_rebuild() -> dict:
    """Trigger Graphify to rebuild the knowledge graph from vault sources."""
    from library_server.graph.orchestrator import rebuild_graph
    config = get_config()
    vault_config = config.get_section("vault")
    graph_config = config.get_section("graphify")
    return rebuild_graph(
        vault_path=vault_config.get("path", ""),
        graph_path=graph_config.get("graph_path", ""),
        mode=graph_config.get("mode", "deep"),
        enabled=graph_config.get("enabled", False),
    )


@mcp.tool(name="library_graph_query")
def library_graph_query(query: str) -> dict:
    """Query the knowledge graph. Falls back gracefully if Graphify is disabled."""
    from library_server.graph.orchestrator import query_graph
    config = get_config()
    graph_config = config.get_section("graphify")
    return query_graph(
        query=query,
        graph_path=graph_config.get("graph_path", ""),
        enabled=graph_config.get("enabled", False),
    )


@mcp.tool(name="library_graph_path")
def library_graph_path(node_a: str, node_b: str) -> dict:
    """Trace shortest path between two nodes in the knowledge graph."""
    from library_server.graph.orchestrator import trace_path
    config = get_config()
    graph_config = config.get_section("graphify")
    return trace_path(
        node_a=node_a,
        node_b=node_b,
        graph_path=graph_config.get("graph_path", ""),
        enabled=graph_config.get("enabled", False),
    )


@mcp.tool(name="library_memory_health")
def library_memory_health(memory_path: str = "", vault_path: str = "") -> dict:
    """Get memory system health report — keyword accuracy, vault stats, CLAUDE.md lines."""
    from library_server.hooks.config_loader import load_hook_config
    config = load_hook_config(Path.cwd())

    v_path = Path(vault_path) if vault_path else Path(config.get("vault", {}).get("path", "./vault"))
    domains_dir = v_path / "domains"
    decisions_dir = v_path / "decisions"

    domain_count = len(list(domains_dir.glob("*.md"))) if domains_dir.exists() else 0
    decision_count = len(list(decisions_dir.glob("*.md"))) if decisions_dir.exists() else 0
    vault_file_count = len(list(v_path.rglob("*.md"))) if v_path.exists() else 0

    learning_dir = Path(config.get("memory", {}).get("session_dir", "~/.library/sessions")).expanduser().parent / "learning"
    journal_path = learning_dir / "routing-journal.jsonl"

    accuracy_report = {}
    if journal_path.exists():
        from library_server.hooks.learning import analyze_routing_accuracy
        accuracy_report = analyze_routing_accuracy(journal_path, min_observations=5)

    return {
        "vault_file_count": vault_file_count,
        "domain_count": domain_count,
        "decision_count": decision_count,
        "keyword_accuracy": accuracy_report,
        "status": "healthy",
    }


@mcp.tool(name="library_memory_learn")
def library_memory_learn(vault_path: str = "") -> dict:
    """Analyze routing journal and propose keyword improvements."""
    from library_server.hooks.config_loader import load_hook_config
    from library_server.hooks.learning import analyze_routing_accuracy, detect_drift

    config = load_hook_config(Path.cwd())
    learning_cfg = config.get("memory", {}).get("keyword_learning", {})

    learning_dir = Path(config.get("memory", {}).get("session_dir", "~/.library/sessions")).expanduser().parent / "learning"
    journal_path = learning_dir / "routing-journal.jsonl"

    if not journal_path.exists():
        return {"status": "no_data", "message": "No routing journal found. Use The Library for a few sessions first."}

    accuracy = analyze_routing_accuracy(
        journal_path,
        min_observations=learning_cfg.get("min_observations", 10),
    )
    drifts = detect_drift(
        journal_path,
        window_entries=learning_cfg.get("drift_window_days", 30),
        drop_threshold=learning_cfg.get("drift_drop_threshold", 0.4),
    )

    return {
        "accuracy": accuracy,
        "drifts": drifts,
        "status": "analyzed",
    }


# --- Vault Builder tools ---

@mcp.tool(name="library_vault_builder_config")
def library_vault_builder_config(section: str = "") -> dict:
    """Show current Vault Builder configuration and validation status."""
    from library_server.vault_builder.config import load_vault_builder_config, validate_vault_builder_config
    cfg = load_vault_builder_config(get_config().path)
    errors = validate_vault_builder_config(cfg)
    result = {
        "mode": cfg.mode,
        "output_vault": str(cfg.output_vault) if cfg.output_vault else None,
        "parallel": cfg.parallel,
        "sources": list(cfg.sources.keys()),
        "graphify_enabled": cfg.graphify.get("enabled", False),
        "axon_enabled": cfg.axon.get("enabled", False),
        "validation_errors": errors,
        "valid": len(errors) == 0,
    }
    if section and section in cfg.sources:
        result["source_detail"] = cfg.sources[section]
    return result


@mcp.tool(name="library_vault_builder_survey")
async def library_vault_builder_survey(sources: str = "") -> dict:
    """Survey all or specific vault builder sources. Returns file counts and health."""
    source_list = [s.strip() for s in sources.split(",") if s.strip()] if sources else None
    orch = _get_vault_orchestrator()
    surveys = await orch.survey(source_list)
    vault_state = None
    if orch.output_vault:
        from library_server.vault_builder.orchestrator import detect_vault_state
        vault_state = detect_vault_state(orch.output_vault).value
    return {"vault_state": vault_state, "sources": surveys}


@mcp.tool(name="library_vault_builder_preview")
async def library_vault_builder_preview(sources: str = "") -> dict:
    """Dry run — show what would be extracted without writing."""
    source_list = [s.strip() for s in sources.split(",") if s.strip()] if sources else None
    orch = _get_vault_orchestrator()
    previews = await orch.preview(source_list)
    return {"sources": previews}


@mcp.tool(name="library_vault_builder_build")
async def library_vault_builder_build(sources: str = "", force: bool = False) -> dict:
    """Full parallel extraction + Graphify build. Pass force=True to overwrite existing vault."""
    source_list = [s.strip() for s in sources.split(",") if s.strip()] if sources else None
    orch = _get_vault_orchestrator()

    if orch.output_vault:
        from library_server.vault_builder.orchestrator import detect_vault_state, check_safety_gate
        vault_state = detect_vault_state(orch.output_vault)
        gate = check_safety_gate(orch.mode, vault_state, force)
        if gate["blocked"]:
            return {"status": "blocked", "message": gate["message"]}

    result = await orch.build(source_list, force)
    return {
        "status": result.status,
        "extract_results": [
            {"source": r.source_name, "success": r.success, "files": len(r.files_written), "errors": r.errors}
            for r in result.extract_results
        ],
        "graphify_status": result.graphify_status,
        "duration_seconds": round(result.duration_seconds, 1),
        "manifest_path": result.manifest_path,
    }


@mcp.tool(name="library_vault_builder_extract")
async def library_vault_builder_extract(extractor: str, dry_run: bool = False) -> dict:
    """Run a single extractor by name. Set dry_run=True for preview only."""
    orch = _get_vault_orchestrator()
    if dry_run:
        previews = await orch.preview([extractor])
        return {"mode": "preview", "sources": previews}
    result = await orch.build([extractor])
    return {
        "status": result.status,
        "extract_results": [
            {"source": r.source_name, "success": r.success, "files": len(r.files_written), "errors": r.errors}
            for r in result.extract_results
        ],
    }


def _get_vault_orchestrator():
    """Build a VaultBuildOrchestrator from config."""
    from library_server.vault_builder.config import load_vault_builder_config
    from library_server.vault_builder.registry import PluginRegistry
    from library_server.vault_builder.graphify_runner import GraphifyRunner
    from library_server.vault_builder.orchestrator import VaultBuildOrchestrator
    from library_server.vault_builder.extractors.specs import SpecsExtractor
    from library_server.vault_builder.extractors.claude_memory import ClaudeMemoryExtractor
    from library_server.vault_builder.extractors.session_context import SessionContextExtractor
    from library_server.vault_builder.extractors.notebooklm import NotebookLMExtractor
    from library_server.vault_builder.extractors.obsidian_vault import ObsidianVaultExtractor
    from library_server.vault_builder.extractors.jira import JiraExtractor
    from library_server.vault_builder.extractors.axon_bridge import AxonBridgeExtractor

    config = get_config()
    vb_cfg = load_vault_builder_config(config.path)

    registry = PluginRegistry()

    extractor_map = {
        "specs": SpecsExtractor,
        "claude_memory": ClaudeMemoryExtractor,
        "session_context": SessionContextExtractor,
        "notebooklm": NotebookLMExtractor,
        "obsidian_vault": ObsidianVaultExtractor,
        "jira": JiraExtractor,
        "axon_bridge": AxonBridgeExtractor,
    }

    for name, cls in extractor_map.items():
        source_cfg = vb_cfg.sources.get(name, {})
        if source_cfg:
            registry.register(cls(config=source_cfg))

    graphify = GraphifyRunner(config=vb_cfg.graphify)

    return VaultBuildOrchestrator(
        registry=registry,
        graphify_runner=graphify,
        output_vault=vb_cfg.output_vault or Path.cwd() / "vault-output",
        mode=vb_cfg.mode,
    )


@mcp.tool(name="library_dev_token_report")
def library_dev_token_report() -> dict:
    """Show per-component token usage for the current session (dev mode)."""
    from library_server.hooks.scripts.token_tracker import aggregate_usage
    state_path = Path("~/.library/state/token-usage.json").expanduser()
    return aggregate_usage(state_path)


def main():
    """Run the MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
