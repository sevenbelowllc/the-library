"""The Library — MCP server entry point."""

from mcp.server.fastmcp import FastMCP

from library_server.config import load_config, LibraryConfig

mcp = FastMCP(
    "library-server",
    json_response=True,
)


def get_config() -> LibraryConfig:
    """Load config from library-config.yaml in current working directory."""
    return load_config()


# --- Config tools ---

@mcp.tool()
def library_config_get(section: str = "") -> dict:
    """Read current library configuration. Pass a section name (e.g. 'vault', 'pm') or empty for all."""
    config = get_config()
    if section:
        return config.get_section(section)
    return config.to_dict()


@mcp.tool()
def library_config_set(section: str, key: str, value: str) -> dict:
    """Update a configuration value. Example: section='pm', key='provider', value='linear'."""
    config = get_config()
    config.set_value(section, key, value)
    config.save()
    return {"status": "updated", "section": section, "key": key, "value": value}


# --- Checkpoint tools ---

@mcp.tool()
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


@mcp.tool()
def library_checkpoint_read(checkpoint_path: str) -> dict:
    """Read and parse a checkpoint file. Returns structured session state."""
    from library_server.checkpoint.checkpoint import read_checkpoint
    return read_checkpoint(checkpoint_path)


@mcp.tool()
def library_checkpoint_list(checkpoint_dir: str = "") -> dict:
    """List all checkpoint files. Uses config path if no directory specified."""
    from library_server.checkpoint.checkpoint import list_checkpoints
    if not checkpoint_dir:
        checkpoint_dir = get_config().get_section("checkpoints").get("path", "./checkpoints")
    return list_checkpoints(checkpoint_dir)


# --- Memory tools ---

@mcp.tool()
def library_memory_scan(memory_path: str = "", stale_threshold_days: int = 30) -> dict:
    """Scan memory files for staleness and metadata. Returns entries with stale flags."""
    from library_server.memory.scan import scan_memories
    path = memory_path or get_config().get_section("memory").get("path", "./.library/memory")
    threshold = stale_threshold_days or get_config().get_section("memory").get("stale_threshold_days", 30)
    return scan_memories(path, threshold)


@mcp.tool()
def library_memory_aggregate(memory_path: str = "", dry_run: bool = True) -> dict:
    """Find merge opportunities for related memories. Set dry_run=False to apply."""
    from library_server.memory.aggregate import aggregate_memories
    path = memory_path or get_config().get_section("memory").get("path", "./.library/memory")
    return aggregate_memories(path, dry_run)


@mcp.tool()
def library_memory_prune(memory_path: str = "", stale_threshold_days: int = 30, dry_run: bool = True) -> dict:
    """Remove stale memory files. Set dry_run=False to delete. Updates MEMORY.md index."""
    from library_server.memory.prune import prune_stale
    path = memory_path or get_config().get_section("memory").get("path", "./.library/memory")
    threshold = stale_threshold_days or get_config().get_section("memory").get("stale_threshold_days", 30)
    return prune_stale(path, threshold, dry_run)


# --- Vault tools ---

@mcp.tool()
def library_vault_init(vault_path: str) -> dict:
    """Bootstrap a new vault with Karpathy 3-layer structure (_schema/, sources/, wiki/, archive/)."""
    from library_server.vault.init import init_vault
    return init_vault(vault_path)


@mcp.tool()
def library_vault_validate(vault_path: str) -> dict:
    """Validate vault structure against schema. Returns {valid: bool, issues: list}."""
    from library_server.vault.validate import validate_vault
    return validate_vault(vault_path)


@mcp.tool()
def library_vault_parse(vault_path: str) -> dict:
    """Parse vault wiki articles. Returns tags ([VERIFY]/[CONFLICT]/[PLANNED]), frontmatter, headings."""
    from library_server.vault.parse import parse_vault
    return parse_vault(vault_path)


@mcp.tool()
def library_vault_ingest(vault_path: str, source_path: str, tier: str, category: str) -> dict:
    """Ingest a file or directory into vault sources/<tier>/<category>/. Updates kb.yaml."""
    from library_server.vault.ingest import ingest_source
    return ingest_source(vault_path, source_path, tier, category)


# --- PM tools ---

@mcp.tool()
async def library_pm_create_task(
    project_key: str, summary: str, description: str, labels: str = ""
) -> dict:
    """Create a task in the configured PM tool (Jira or Linear)."""
    adapter = _get_pm_adapter()
    label_list = [l.strip() for l in labels.split(",") if l.strip()] if labels else []
    result = await adapter.create_task(project_key, summary, description, label_list)
    return {"task_id": result.task_id, "summary": result.summary, "url": result.url}


@mcp.tool()
async def library_pm_create_epic(project_key: str, summary: str, description: str) -> dict:
    """Create an epic in the configured PM tool."""
    adapter = _get_pm_adapter()
    result = await adapter.create_epic(project_key, summary, description)
    return {"epic_id": result.epic_id, "summary": result.summary, "url": result.url}


@mcp.tool()
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


@mcp.tool()
async def library_pm_update(task_id: str, status: str = "", comment: str = "") -> dict:
    """Update a task's status or add a comment."""
    adapter = _get_pm_adapter()
    result = await adapter.update_task(task_id, status or None, comment or None)
    return {"task_id": result.task_id, "status": result.status.value}


@mcp.tool()
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

@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


# Tool registrations for other modules are added in Phase 1-2.
# Each module defines functions that get registered here after implementation.


def main():
    """Run the MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
