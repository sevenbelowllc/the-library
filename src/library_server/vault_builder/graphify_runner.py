"""GraphifyRunner — triggers Graphify Python API to build knowledge graph and wiki."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

try:
    from graphify.extract import extract, collect_files
    from graphify.build import build_from_json
    from graphify.cluster import cluster, score_all
    from graphify.analyze import god_nodes, surprising_connections
    from graphify.report import generate
    from graphify.export import to_json, to_html
    from graphify.wiki import to_wiki
except ImportError:
    extract = None  # type: ignore[assignment]
    build_from_json = None  # type: ignore[assignment]
    cluster = None  # type: ignore[assignment]
    score_all = None  # type: ignore[assignment]
    god_nodes = None  # type: ignore[assignment]
    surprising_connections = None  # type: ignore[assignment]
    generate = None  # type: ignore[assignment]
    to_json = None  # type: ignore[assignment]
    to_html = None  # type: ignore[assignment]
    to_wiki = None  # type: ignore[assignment]


class GraphifyRunner:
    """Runs Graphify to build knowledge graph and Obsidian wiki from raw/ content."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def is_available(self) -> bool:
        if not self.config.get("enabled", False):
            return False
        return shutil.which(self.config.get("command", "graphify")) is not None

    async def build(
        self,
        raw_dir: Path,
        output_dir: Path,
        wiki_dir: Path,
    ) -> dict[str, Any]:
        """Run the full Graphify pipeline: extract → build → cluster → export → wiki."""
        if not self.config.get("enabled", False):
            return {"status": "disabled", "message": "Graphify is not enabled in config."}

        output_dir.mkdir(parents=True, exist_ok=True)
        wiki_dir.mkdir(parents=True, exist_ok=True)

        try:
            files = collect_files(raw_dir)
            extraction = extract(files)
            graph = build_from_json(extraction)
            communities = cluster(graph)
            cohesion = score_all(graph, communities)
            gods = god_nodes(graph)
            surprises = surprising_connections(graph, communities)

            report_md = generate(
                graph, communities, cohesion,
                community_labels={},
                god_node_list=gods,
                surprise_list=surprises,
                detection_result={},
                token_cost=extraction.get("input_tokens", 0) if isinstance(extraction, dict) else {},
                root=str(raw_dir),
            )
            (output_dir / "GRAPH_REPORT.md").write_text(report_md)

            to_json(graph, communities, str(output_dir / "graph.json"))
            to_html(graph, communities, str(output_dir / "graph.html"))
            wiki_count = to_wiki(graph, communities, wiki_dir, cohesion=cohesion, god_nodes_data=gods)

            return {
                "status": "success",
                "nodes": graph.number_of_nodes(),
                "edges": graph.number_of_edges(),
                "communities": len(communities),
                "wiki_articles": wiki_count,
                "output_dir": str(output_dir),
                "wiki_dir": str(wiki_dir),
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}
