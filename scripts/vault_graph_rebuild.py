"""Rebuild the knowledge graph from the entire vault via frontmatter (free).

Uses GraphifyRunner.build_from_vault() which reads YAML frontmatter
`related:` + `domain:` and emits graph edges — no LLM call.

Scans the vault ROOT so both raw/vault/** AND wiki/** contribute nodes
and cross-link edges. This is what the library:compile skill's Step 4
intends, ungated by graphify.auto_rebuild.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from library_server.vault_builder.graphify_runner import GraphifyRunner  # noqa: E402


VAULT = Path("/Users/pollucts/workdir/sevenbelow/complyos-kb")
GRAPH_OUT = VAULT / "graphify-out"
GRAPH_JSON = GRAPH_OUT / "graph.json"


async def main() -> int:
    if not VAULT.is_dir():
        print(f"ERROR: vault not found at {VAULT}")
        return 1

    baseline_nodes = 0
    if GRAPH_JSON.exists():
        baseline = json.loads(GRAPH_JSON.read_text())
        baseline_nodes = len(baseline.get("nodes", []))
        print(f"baseline nodes: {baseline_nodes}")

    # Generate a wiki-only frontmatter graph at a FRESH output dir to avoid
    # the runner's safety guard against overwriting a larger existing graph.
    # Then we merge it into the main graph via `graphify merge-graphs`.
    import subprocess

    wiki_only_out = Path("/tmp/wiki-only-graph")
    if wiki_only_out.exists():
        import shutil
        shutil.rmtree(wiki_only_out)
    wiki_only_out.mkdir()

    # SAFETY: snapshot real wiki/ before any graphify call (to_wiki() in
    # build_from_vault otherwise overwrites user-compiled articles with
    # auto-stubs). Discovered 2026-05-22 — clobbered 15 articles.
    real_wiki = VAULT / "wiki"
    import shutil
    snapshot_dir = Path(f"/tmp/wiki-snapshot-pre-rebuild")
    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)
    if real_wiki.exists():
        shutil.copytree(real_wiki, snapshot_dir)
        snapshot_count = len(list(snapshot_dir.rglob("*.md")))
        snapshot_loc = sum(p.read_text().count("\n") for p in snapshot_dir.rglob("*.md"))
        print(f"snapshot: {snapshot_count} wiki files, {snapshot_loc} lines -> {snapshot_dir}")

    # Use a THROWAWAY wiki_dir so to_wiki() writes its stubs to /tmp, not
    # over the real wiki/. The real wiki/ stays untouched.
    throwaway_wiki = Path("/tmp/graphify-to-wiki-throwaway")
    if throwaway_wiki.exists():
        shutil.rmtree(throwaway_wiki)
    throwaway_wiki.mkdir()

    runner = GraphifyRunner(config={"enabled": True})
    print(f"scanning vault root, redirecting to_wiki -> {throwaway_wiki}")
    result = await runner.build_from_vault(
        raw_dir=VAULT,
        output_dir=wiki_only_out,
        wiki_dir=throwaway_wiki,  # safety: divert to_wiki stubs
    )
    print(f"frontmatter build status: {result.get('status')}")
    if result.get("message"):
        print(f"message: {result['message']}")

    wiki_only_json = wiki_only_out / "graph.json"
    if not wiki_only_json.exists():
        print(f"ERROR: frontmatter graph not written at {wiki_only_json}")
        return 1

    # Merge frontmatter graph INTO existing LLM-extracted graph.
    merged_out = GRAPH_OUT / "merged.json"
    print(f"merging existing graph with frontmatter graph -> {merged_out}")
    merge_cmd = [
        "graphify", "merge-graphs",
        str(GRAPH_JSON),
        str(wiki_only_json),
        "--out", str(merged_out),
    ]
    proc = subprocess.run(merge_cmd, capture_output=True, text=True, timeout=120)
    print(proc.stdout)
    if proc.returncode != 0:
        print(f"ERROR: merge-graphs failed: {proc.stderr}")
        return 1

    # Replace primary graph with merged result.
    shutil.copy2(merged_out, GRAPH_JSON)
    print(f"replaced {GRAPH_JSON} with merged graph")

    # POST-CHECK: did real wiki/ change? It must not.
    if real_wiki.exists() and snapshot_dir.exists():
        post_count = len(list(real_wiki.rglob("*.md")))
        post_loc = sum(p.read_text().count("\n") for p in real_wiki.rglob("*.md"))
        if post_count != snapshot_count or post_loc != snapshot_loc:
            print(f"!! ALARM: wiki/ changed during rebuild ({snapshot_count}/{snapshot_loc} -> "
                  f"{post_count}/{post_loc}). Restoring from snapshot.")
            shutil.rmtree(real_wiki)
            shutil.copytree(snapshot_dir, real_wiki)
            print("wiki/ restored from snapshot")
            return 1
        print(f"verified wiki/ untouched: {post_count} files, {post_loc} lines")

    if not GRAPH_JSON.exists():
        print(f"ERROR: graph.json not written at {GRAPH_JSON}")
        return 1

    new_graph = json.loads(GRAPH_JSON.read_text())
    nodes = new_graph.get("nodes", [])
    edges = new_graph.get("links", new_graph.get("edges", []))
    print(f"new nodes: {len(nodes)}  edges: {len(edges)}")

    # Verification: did wiki nodes appear?
    wiki_node_titles = {
        "glossary", "scope", "frameworks", "architecture", "operational-specs",
        "security-model", "tenant-isolation", "domains", "decisions",
        "the-library-design", "standards", "plans-overview", "test-strategy",
        "research-index", "gap-summary",
    }
    labels = {n.get("label", "").lower().replace(".md", "") for n in nodes}
    wiki_in_graph = wiki_node_titles & labels
    print(f"wiki nodes found in graph: {len(wiki_in_graph)} / {len(wiki_node_titles)}")
    if wiki_in_graph:
        print(f"sample: {sorted(wiki_in_graph)[:5]}")

    if len(wiki_in_graph) < 10:
        print(f"WARN: expected ≥10 wiki nodes, got {len(wiki_in_graph)}")
        return 2
    if len(nodes) <= baseline_nodes:
        print(f"WARN: node count did not grow ({baseline_nodes} -> {len(nodes)})")
        return 2

    print(f"OK: graph rebuilt, wiki layer present")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
