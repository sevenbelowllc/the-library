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
def tiny_repo(tmp_path: Path) -> Path:
    (tmp_path / "auth.py").write_text(
        "def login(user):\n    return check_token(user)\n\n"
        "def check_token(user):\n    return True\n"
    )
    (tmp_path / "db.py").write_text(
        "from auth import login\n\n"
        "def connect():\n    return login('svc')\n"
    )
    return tmp_path


def test_full_code_pipeline_on_real_api(tiny_repo):
    files = collect_files(tiny_repo, root=tiny_repo)
    assert files, "collect_files found no python files"

    extraction = extract(files, root=tiny_repo, parallel=False)
    assert isinstance(extraction, dict)
    assert extraction["nodes"], "extract produced no nodes"
    node = extraction["nodes"][0]
    assert "id" in node and "label" in node and "source_file" in node

    graph = build_from_json(extraction, root=tiny_repo)
    assert graph.number_of_nodes() > 0

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
