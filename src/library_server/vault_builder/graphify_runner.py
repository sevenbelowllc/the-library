"""GraphifyRunner — triggers Graphify Python API to build knowledge graph and wiki.

Uses detect() to find ALL file types (code, docs, papers, images, video),
then routes code files through AST extraction and merges with any pre-existing
semantic extraction results before building the graph.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

try:
    from graphify.detect import detect as graphify_detect
    from graphify.extract import extract, collect_files
    from graphify.build import build_from_json
    from graphify.cluster import cluster, score_all
    from graphify.analyze import god_nodes, surprising_connections
    from graphify.report import generate
    from graphify.export import to_json, to_html
    from graphify.wiki import to_wiki
    from graphify.cache import check_semantic_cache
except ImportError:  # pragma: no cover
    graphify_detect = None  # type: ignore[assignment]
    extract = None  # type: ignore[assignment]
    collect_files = None  # type: ignore[assignment]
    build_from_json = None  # type: ignore[assignment]
    cluster = None  # type: ignore[assignment]
    score_all = None  # type: ignore[assignment]
    god_nodes = None  # type: ignore[assignment]
    surprising_connections = None  # type: ignore[assignment]
    generate = None  # type: ignore[assignment]
    to_json = None  # type: ignore[assignment]
    to_html = None  # type: ignore[assignment]
    to_wiki = None  # type: ignore[assignment]
    check_semantic_cache = None  # type: ignore[assignment]


class GraphifyRunner:
    """Runs Graphify to build knowledge graph and Obsidian wiki from raw/ content.

    The build pipeline:
    1. detect() — scans for all file types (code, docs, papers, images, video)
    2. AST extract() — structural extraction for code files (deterministic, free)
    3. Semantic cache — loads previously-extracted doc/paper/image results
    4. build_from_json() — builds the graph from merged extraction results
    5. cluster() + analyze — community detection, god nodes, surprises
    6. Export — graph.json, graph.html, wiki articles, GRAPH_REPORT.md

    Note: Semantic extraction of documents requires the /graphify skill
    (Claude subagents). This runner uses cached semantic results when available.
    If no semantic cache exists for documents, it builds the graph from code
    files only and reports how many documents need semantic extraction.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def is_available(self) -> bool:
        if not self.config.get("enabled", False):
            return False
        if graphify_detect is None:
            return False
        return shutil.which(self.config.get("command", "graphify")) is not None

    async def build(
        self,
        raw_dir: Path,
        output_dir: Path,
        wiki_dir: Path,
    ) -> dict[str, Any]:
        """Run the full Graphify pipeline: detect → extract → build → cluster → export → wiki."""
        if not self.config.get("enabled", False):
            return {"status": "disabled", "message": "Graphify is not enabled in config."}

        if graphify_detect is None:
            return {
                "status": "error",
                "message": "Graphify is not installed. Run: pip install 'the-library[graphify]'",
            }

        output_dir.mkdir(parents=True, exist_ok=True)
        wiki_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Step 1: Detect all files (code, docs, papers, images, video)
            detection = graphify_detect(raw_dir)
            file_groups = detection.get("files", {})
            total_files = detection.get("total_files", 0)

            if total_files == 0:
                return {"status": "error", "message": f"No supported files found in {raw_dir}"}

            # Save detection results for the /graphify skill and other tools
            detect_path = output_dir / ".graphify_detect.json"
            detect_path.write_text(json.dumps(detection, indent=2))

            # Step 2: AST extraction for code files
            code_file_paths = file_groups.get("code", [])
            ast_nodes: list[dict] = []
            ast_edges: list[dict] = []

            if code_file_paths:
                all_code = []
                for f in code_file_paths:
                    p = Path(f)
                    if p.is_dir():
                        all_code.extend(collect_files(p))
                    else:
                        all_code.append(p)
                if all_code:
                    ast_result = extract(all_code)
                    ast_nodes = ast_result.get("nodes", [])
                    ast_edges = ast_result.get("edges", [])

            # Step 3: Check semantic cache for docs/papers/images
            non_code_files = (
                file_groups.get("document", [])
                + file_groups.get("paper", [])
                + file_groups.get("image", [])
            )
            sem_nodes: list[dict] = []
            sem_edges: list[dict] = []
            sem_hyperedges: list[dict] = []
            uncached_count = 0

            if non_code_files and check_semantic_cache is not None:
                cached_nodes, cached_edges, cached_hyperedges, uncached = check_semantic_cache(
                    non_code_files, root=raw_dir,
                )
                sem_nodes = cached_nodes
                sem_edges = cached_edges
                sem_hyperedges = cached_hyperedges
                uncached_count = len(uncached)

            # Step 4: Merge AST + semantic extraction results
            seen_ids = {n["id"] for n in ast_nodes}
            merged_nodes = list(ast_nodes)
            for n in sem_nodes:
                if n["id"] not in seen_ids:
                    merged_nodes.append(n)
                    seen_ids.add(n["id"])

            merged_edges = ast_edges + sem_edges
            extraction = {
                "nodes": merged_nodes,
                "edges": merged_edges,
                "hyperedges": sem_hyperedges,
                "input_tokens": 0,
                "output_tokens": 0,
            }

            # Save merged extraction for /graphify skill compatibility
            (output_dir / ".graphify_extract.json").write_text(json.dumps(extraction, indent=2))

            if not merged_nodes:
                message = f"No nodes extracted from {total_files} files."
                if uncached_count > 0:
                    message += (
                        f" {uncached_count} document(s) need semantic extraction. "
                        "Run '/graphify <path>' to extract entities from documents."
                    )
                return {"status": "error", "message": message}

            # Step 5: Build graph, cluster, analyze
            graph = build_from_json(extraction)
            communities = cluster(graph)
            cohesion = score_all(graph, communities)
            gods = god_nodes(graph)
            surprises = surprising_connections(graph, communities)

            # Step 6: Generate outputs
            report_md = generate(
                graph, communities, cohesion,
                community_labels={},
                god_node_list=gods,
                surprise_list=surprises,
                detection_result=detection,
                token_cost={"input": 0, "output": 0},
                root=str(raw_dir),
            )
            (output_dir / "GRAPH_REPORT.md").write_text(report_md)

            to_json(graph, communities, str(output_dir / "graph.json"))

            if graph.number_of_nodes() <= 5000:
                to_html(graph, communities, str(output_dir / "graph.html"))

            wiki_count = to_wiki(
                graph, communities, wiki_dir, cohesion=cohesion, god_nodes_data=gods,
            )

            # Save analysis for downstream tools
            analysis = {
                "communities": {str(k): v for k, v in communities.items()},
                "cohesion": {str(k): v for k, v in cohesion.items()},
                "gods": gods,
                "surprises": surprises,
            }
            (output_dir / ".graphify_analysis.json").write_text(json.dumps(analysis, indent=2))

            result: dict[str, Any] = {
                "status": "success",
                "nodes": graph.number_of_nodes(),
                "edges": graph.number_of_edges(),
                "communities": len(communities),
                "wiki_articles": wiki_count,
                "output_dir": str(output_dir),
                "wiki_dir": str(wiki_dir),
                "detection": {
                    "total_files": total_files,
                    "code_files": len(code_file_paths),
                    "doc_files": len(non_code_files),
                    "uncached_docs": uncached_count,
                },
            }

            if uncached_count > 0:
                result["message"] = (
                    f"{uncached_count} document(s) lack semantic extraction and were not "
                    "included in the graph. Run '/graphify <path>' to extract them."
                )

            return result

        except Exception as e:
            return {"status": "error", "message": str(e)}
