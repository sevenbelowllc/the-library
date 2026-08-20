"""Real-API (no mocks) compatibility tests against the installed graphify.

These exist because GraphifyRunner/code_repo tests mock the graphify
functions — a graphify upgrade that changes signatures or return shapes
would otherwise only fail in production. No LLM calls: AST extraction,
clustering, and labeling are fully deterministic and offline.
"""
from __future__ import annotations

from pathlib import Path

import pytest

graphify = pytest.importorskip("graphify")

from graphify.build import build_from_json  # noqa: E402
from graphify.cluster import cluster, label_communities_by_hub, score_all  # noqa: E402
from graphify.extract import collect_files, extract  # noqa: E402


@pytest.fixture()
def cache_root(tmp_path: Path) -> Path:
    """A per-test graphify AST cache.

    graphify caches extractions by content hash under `<cache_root>/graphify-out`
    and defaults that to the CWD — a warm cache from an earlier run would let
    these tests pass even with a grammar uninstalled (and would litter the repo
    root). An empty per-test dir forces a real extraction every time.
    """
    d = tmp_path / "graphify-cache"
    d.mkdir()
    return d


@pytest.fixture()
def tiny_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "tiny-repo"
    repo.mkdir()
    (repo / "auth.py").write_text(
        "def login(user):\n    return check_token(user)\n\n"
        "def check_token(user):\n    return True\n"
    )
    (repo / "db.py").write_text(
        "from auth import login\n\n"
        "def connect():\n    return login('svc')\n"
    )
    # A second language, so the suite would notice graphify losing a grammar
    # that ships in the base install (tree-sitter-javascript is a hard dep).
    (repo / "client.js").write_text(
        "function fetchUser(id) {\n  return requestJson('/users/' + id);\n}\n\n"
        "function requestJson(url) {\n  return fetch(url).then(r => r.json());\n}\n"
    )
    return repo


@pytest.fixture()
def terraform_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "tf-repo"
    repo.mkdir()
    (repo / "main.tf").write_text(
        'resource "google_storage_bucket" "artifacts" {\n'
        '  name     = "artifacts"\n'
        '  location = "US"\n'
        "}\n\n"
        'variable "project_id" {\n  type = string\n}\n\n'
        'output "bucket_name" {\n  value = google_storage_bucket.artifacts.name\n}\n'
    )
    return repo


def test_full_code_pipeline_on_real_api(tiny_repo, cache_root):
    files = collect_files(tiny_repo, root=tiny_repo)
    assert files, "collect_files found no python files"

    extraction = extract(files, cache_root, root=tiny_repo, parallel=False)
    assert isinstance(extraction, dict)
    assert extraction["nodes"], "extract produced no nodes"
    node = extraction["nodes"][0]
    assert "id" in node and "label" in node and "source_file" in node

    graph = build_from_json(extraction, root=tiny_repo)
    assert graph.number_of_nodes() > 0
    # code_repo reads label/source_file off the *graph nodes*, not the raw
    # extraction dict. A release that stopped copying them across would render
    # every community member as "`` — ``" with this suite otherwise green.
    assert all(
        "label" in graph.nodes[n] and "source_file" in graph.nodes[n] for n in graph.nodes
    )

    communities = cluster(graph)
    assert communities, "cluster found no communities on a connected graph"
    for cid, members in communities.items():
        assert isinstance(cid, int) and isinstance(members, list)

    labels = label_communities_by_hub(graph, communities)
    assert set(labels) == set(communities)
    assert all(isinstance(v, str) and v for v in labels.values())

    cohesion = score_all(graph, communities)
    assert set(cohesion) == set(communities)
    assert all(isinstance(v, float) for v in cohesion.values())


def test_javascript_symbols_are_extracted(tiny_repo, cache_root):
    """Non-Python input must produce symbols too — the extractor advertises
    multi-language support, and only Python was ever covered."""
    files = collect_files(tiny_repo, root=tiny_repo)
    assert any(f.suffix == ".js" for f in files)

    extraction = extract(files, cache_root, root=tiny_repo, parallel=False)
    js_labels = {
        n["label"] for n in extraction["nodes"] if n.get("source_file", "").endswith(".js")
    }
    assert any("fetchUser" in label for label in js_labels), js_labels
    assert any("requestJson" in label for label in js_labels), js_labels


def test_terraform_symbols_are_extracted(terraform_repo, cache_root):
    """Guards the `graphifyy[terraform]` pin: without the terraform extra
    (tree_sitter_hcl) a .tf-only repo yields zero symbols silently."""
    files = collect_files(terraform_repo, root=terraform_repo)
    assert any(f.suffix == ".tf" for f in files), "collect_files skipped .tf"

    extraction = extract(files, cache_root, root=terraform_repo, parallel=False)
    labels = {n["label"] for n in extraction["nodes"]}
    assert any("google_storage_bucket.artifacts" in label for label in labels), labels

    graph = build_from_json(extraction, root=terraform_repo)
    assert graph.number_of_nodes() > 1, "terraform grammar missing — install the [graphify] extra"


def test_runner_imports_still_resolve():
    """Every symbol graphify_runner.py imports must exist in this graphify."""
    from graphify.detect import detect  # noqa: F401
    from graphify.extract import extract, collect_files  # noqa: F401
    from graphify.build import build_from_json  # noqa: F401
    from graphify.cluster import cluster, score_all  # noqa: F401
    from graphify.analyze import god_nodes, surprising_connections  # noqa: F401
    from graphify.report import generate  # noqa: F401
    from graphify.export import to_json, to_html  # noqa: F401
    from graphify.wiki import to_wiki  # noqa: F401
    from graphify.cache import check_semantic_cache  # noqa: F401
