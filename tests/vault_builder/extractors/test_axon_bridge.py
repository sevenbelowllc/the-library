"""Tests for Axon Bridge extractor.

IMPORTANT: Mocks in this file reflect the REAL output format of axon CLI commands.
axon query  → plain numbered text (NOT JSON)
axon cypher → pipe-separated rows (NOT JSON)
axon status → key: value text (NOT JSON)

The previous test suite used JSON mocks which hid the real failure mode.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest
import yaml


# ── Real axon CLI output formats ──────────────────────────────────────────────

AXON_ANALYZE_SUCCESS = """\
Indexing /some/repo

Indexing complete.
  Files:          288
  Symbols:        1882
  Relationships:  5526
  Clusters:       58
  Flows:          30
  Dead code:      556
  Coupled pairs:  26
  Duration:       6.83s
"""

AXON_STATUS_OUTPUT = """\
Index status for /some/repo
  Version:        1.0.1
  Last indexed:   2026-04-13T08:16:33.015549+00:00
  Files:          288
  Symbols:        1882
  Relationships:  5526
  Clusters:       58
  Flows:          30
  Dead code:      556
  Coupled pairs:  26
"""

AXON_CYPHER_COMMUNITIES = """\
Results (3 rows):

  1. Services+graphql | 0.010516 | {"symbol_count": 125}
  2. Application+approval | 0.014653 | {"symbol_count": 101}
  3. Auth+middleware | 0.027137 | {"symbol_count": 42}
"""

AXON_CYPHER_MEMBERS = """\
Results (3 rows):

  1. requireAuth | src/middleware/auth.ts
  2. verifyJWT | src/middleware/auth.ts
  3. setTenantContext | src/middleware/tenant.ts
"""

AXON_CYPHER_MEMBERS_EMPTY = "Query returned no results.\n"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_frontmatter(content: str) -> dict:
    parts = content.split("---\n", 2)
    if len(parts) < 3:
        return {}
    return yaml.safe_load(parts[1]) or {}


def _make_subprocess_mock(returncode: int, stdout: str, stderr: str = "") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_ts_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "compliance-core"
    repo.mkdir()
    src = repo / "src"
    src.mkdir()
    (src / "index.ts").write_text("export const app = express();")
    (src / "auth.ts").write_text("export function requireAuth() {}")
    return repo


@pytest.fixture
def sample_tf_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "terraform-metadata"
    repo.mkdir()
    (repo / "main.tf").write_text(
        'resource "google_project" "main" {\n  name = "compliance-os"\n}\n\n'
        'module "network" {\n  source = "./modules/network"\n}\n\n'
        'variable "region" {\n  default = "us-central1"\n}\n'
    )
    return repo


@pytest.fixture
def axon_extractor(sample_ts_repo: Path, sample_tf_repo: Path):
    from library_server.vault_builder.extractors.axon_bridge import AxonBridgeExtractor
    return AxonBridgeExtractor(config={
        "enabled": True,
        "repos": [
            {"name": "compliance-core", "path": str(sample_ts_repo), "type": "backend", "language": "typescript"},
            {"name": "terraform-metadata", "path": str(sample_tf_repo), "type": "infrastructure", "language": "terraform"},
        ],
    })


# ── Validate config ────────────────────────────────────────────────────────────

async def test_validate_config_valid(axon_extractor):
    with patch("shutil.which", return_value="/usr/bin/axon"):
        errors = axon_extractor.validate_config()
    assert errors == []


async def test_validate_config_missing_repos():
    from library_server.vault_builder.extractors.axon_bridge import AxonBridgeExtractor
    ext = AxonBridgeExtractor(config={"enabled": True})
    errors = ext.validate_config()
    assert any("repos" in e for e in errors)


async def test_validate_config_axon_not_found(axon_extractor):
    with patch("shutil.which", return_value=None):
        errors = axon_extractor.validate_config()
    assert any("axon" in e.lower() for e in errors)


async def test_validate_config_missing_repo_path():
    from library_server.vault_builder.extractors.axon_bridge import AxonBridgeExtractor
    ext = AxonBridgeExtractor(config={
        "enabled": True,
        "repos": [{"name": "x", "path": "/does/not/exist", "language": "typescript"}],
    })
    with patch("shutil.which", return_value="/usr/bin/axon"):
        errors = ext.validate_config()
    assert any("does not exist" in e for e in errors)


# ── Survey ────────────────────────────────────────────────────────────────────

async def test_survey_returns_correct_counts(axon_extractor):
    with patch("shutil.which", return_value="/usr/bin/axon"):
        result = await axon_extractor.survey()
    assert result.source_name == "axon_bridge"
    assert result.file_count == 2
    assert result.health == "connected"


async def test_survey_error_when_axon_not_installed(axon_extractor):
    with patch("shutil.which", return_value=None):
        result = await axon_extractor.survey()
    assert result.health == "error"
    assert "axon" in result.structure_summary.lower()
    assert result.file_count == 0


async def test_survey_error_when_repo_path_missing(tmp_path):
    from library_server.vault_builder.extractors.axon_bridge import AxonBridgeExtractor
    ext = AxonBridgeExtractor(config={
        "enabled": True,
        "repos": [{"name": "missing", "path": str(tmp_path / "nope"), "language": "typescript"}],
    })
    with patch("shutil.which", return_value="/usr/bin/axon"):
        result = await ext.survey()
    assert result.health == "error"
    assert "not found" in result.structure_summary


# ── Cypher parsing (unit tests for parsing logic) ─────────────────────────────

def test_cypher_communities_parses_real_format(sample_ts_repo):
    from library_server.vault_builder.extractors.axon_bridge import AxonBridgeExtractor
    ext = AxonBridgeExtractor(config={"enabled": True, "repos": []})

    mock = _make_subprocess_mock(0, AXON_CYPHER_COMMUNITIES)
    with patch("subprocess.run", return_value=mock):
        communities = ext._cypher_communities(str(sample_ts_repo))

    assert len(communities) == 3
    assert communities[0]["name"] == "Services+graphql"
    assert communities[0]["symbol_count"] == 125
    assert communities[1]["name"] == "Application+approval"
    assert communities[2]["name"] == "Auth+middleware"


def test_cypher_communities_returns_empty_on_failure(sample_ts_repo):
    from library_server.vault_builder.extractors.axon_bridge import AxonBridgeExtractor
    ext = AxonBridgeExtractor(config={"enabled": True, "repos": []})

    mock = _make_subprocess_mock(1, "", "Cypher query failed")
    with patch("subprocess.run", return_value=mock):
        communities = ext._cypher_communities(str(sample_ts_repo))

    assert communities == []


def test_cypher_members_parses_real_format(sample_ts_repo):
    from library_server.vault_builder.extractors.axon_bridge import AxonBridgeExtractor
    ext = AxonBridgeExtractor(config={"enabled": True, "repos": []})

    mock = _make_subprocess_mock(0, AXON_CYPHER_MEMBERS)
    with patch("subprocess.run", return_value=mock):
        members = ext._cypher_members(str(sample_ts_repo), "Auth+middleware")

    assert len(members) == 3
    assert members[0] == ("requireAuth", "src/middleware/auth.ts")
    assert members[1] == ("verifyJWT", "src/middleware/auth.ts")


def test_cypher_members_returns_empty_when_no_results(sample_ts_repo):
    from library_server.vault_builder.extractors.axon_bridge import AxonBridgeExtractor
    ext = AxonBridgeExtractor(config={"enabled": True, "repos": []})

    mock = _make_subprocess_mock(0, AXON_CYPHER_MEMBERS_EMPTY)
    with patch("subprocess.run", return_value=mock):
        members = ext._cypher_members(str(sample_ts_repo), "Empty+community")

    assert members == []


def test_axon_status_parses_real_format(sample_ts_repo):
    from library_server.vault_builder.extractors.axon_bridge import AxonBridgeExtractor
    ext = AxonBridgeExtractor(config={"enabled": True, "repos": []})

    mock = _make_subprocess_mock(0, AXON_STATUS_OUTPUT)
    with patch("subprocess.run", return_value=mock):
        status = ext._axon_status(str(sample_ts_repo))

    assert status["files"] == 288
    assert status["symbols"] == 1882
    assert status["relationships"] == 5526
    assert status["clusters"] == 58


def test_axon_status_returns_empty_on_failure(sample_ts_repo):
    from library_server.vault_builder.extractors.axon_bridge import AxonBridgeExtractor
    ext = AxonBridgeExtractor(config={"enabled": True, "repos": []})

    mock = _make_subprocess_mock(1, "", "error")
    with patch("subprocess.run", return_value=mock):
        status = ext._axon_status(str(sample_ts_repo))

    assert status == {}


# ── TypeScript extraction (full pipeline) ─────────────────────────────────────

def _make_ts_subprocess_sequence(analyze_ok=True):
    """Return side_effect list for subprocess.run matching the real call sequence:
    1. axon analyze → success/failure
    2. axon cypher communities → community rows
    3. axon cypher members (per community) → member rows
    4. axon status → status output
    """
    analyze = _make_subprocess_mock(
        0 if analyze_ok else 1,
        AXON_ANALYZE_SUCCESS if analyze_ok else "",
        "" if analyze_ok else "Analysis failed",
    )
    communities = _make_subprocess_mock(0, AXON_CYPHER_COMMUNITIES)
    # One members call per community (3 communities in fixture)
    members_auth = _make_subprocess_mock(0, AXON_CYPHER_MEMBERS)
    members_empty = _make_subprocess_mock(0, AXON_CYPHER_MEMBERS_EMPTY)
    status = _make_subprocess_mock(0, AXON_STATUS_OUTPUT)
    return [analyze, communities, members_auth, members_empty, members_empty, status]


async def test_typescript_extraction_writes_community_files(axon_extractor, output_dir: Path):
    with patch("subprocess.run", side_effect=_make_ts_subprocess_sequence()):
        result = await axon_extractor.extract(output_dir / "repos")

    community_dir = output_dir / "repos" / "compliance-core" / "communities"
    assert community_dir.exists()
    community_files = list(community_dir.glob("*.md"))
    assert len(community_files) == 3  # 3 communities in fixture


async def test_typescript_extraction_community_content(axon_extractor, output_dir: Path):
    with patch("subprocess.run", side_effect=_make_ts_subprocess_sequence()):
        await axon_extractor.extract(output_dir / "repos")

    community_dir = output_dir / "repos" / "compliance-core" / "communities"
    # Services+graphql is first community → gets the members mock with requireAuth
    services_file = community_dir / "services-graphql.md"
    assert services_file.exists()
    content = services_file.read_text()
    assert "requireAuth" in content
    assert "src/middleware/auth.ts" in content


async def test_typescript_extraction_repo_summary_has_real_stats(axon_extractor, output_dir: Path):
    """Repo summary must include axon status metrics, not just file count."""
    with patch("subprocess.run", side_effect=_make_ts_subprocess_sequence()):
        await axon_extractor.extract(output_dir / "repos")

    summary = output_dir / "repos" / "compliance-core" / "repo-summary.md"
    content = summary.read_text()
    assert "288" in content   # files
    assert "1882" in content  # symbols
    assert "5526" in content  # relationships


async def test_typescript_extraction_raises_on_analyze_failure(axon_extractor, output_dir: Path):
    """If axon analyze fails, extraction must raise — not silently fall through."""
    analyze_fail = _make_subprocess_mock(1, "", "Analysis failed: permission denied")

    with patch("subprocess.run", return_value=analyze_fail):
        result = await axon_extractor.extract(output_dir / "repos")

    # Should record an error for the typescript repo
    assert any("compliance-core" in e for e in result.errors)


async def test_typescript_extraction_analyze_uses_repo_cwd(axon_extractor, output_dir: Path, sample_ts_repo: Path):
    """axon analyze must run with cwd=repo_path, not the current working directory."""
    calls = []

    def capture_calls(*args, **kwargs):
        calls.append(kwargs.get("cwd"))
        return _make_subprocess_mock(0, AXON_ANALYZE_SUCCESS)

    with patch("subprocess.run", side_effect=_make_ts_subprocess_sequence()):
        with patch("subprocess.run", side_effect=capture_calls):
            await axon_extractor.extract(output_dir / "repos")

    # All subprocess calls should have cwd set to a repo path
    for cwd in calls:
        assert cwd is not None


# ── Terraform extraction ───────────────────────────────────────────────────────

async def test_terraform_extraction_does_not_call_axon(axon_extractor, output_dir: Path):
    """Terraform repos use static .tf parsing — axon must not be called for them."""
    calls = []

    def track_calls(*args, **kwargs):
        calls.append(args[0] if args else [])
        return _make_subprocess_mock(0, AXON_ANALYZE_SUCCESS)

    # Only mock the typescript repo's axon calls
    with patch("subprocess.run", side_effect=_make_ts_subprocess_sequence()):
        await axon_extractor.extract(output_dir / "repos")

    tf_dir = output_dir / "repos" / "terraform-metadata"
    assert tf_dir.exists()
    summary = tf_dir / "repo-summary.md"
    assert summary.exists()


async def test_terraform_extracts_resources(axon_extractor, output_dir: Path):
    with patch("subprocess.run", side_effect=_make_ts_subprocess_sequence()):
        await axon_extractor.extract(output_dir / "repos")

    summary = (output_dir / "repos" / "terraform-metadata" / "repo-summary.md").read_text()
    assert "google_project" in summary


async def test_terraform_extracts_modules(axon_extractor, output_dir: Path):
    with patch("subprocess.run", side_effect=_make_ts_subprocess_sequence()):
        await axon_extractor.extract(output_dir / "repos")

    summary = (output_dir / "repos" / "terraform-metadata" / "repo-summary.md").read_text()
    assert "network" in summary


# ── Frontmatter correctness ───────────────────────────────────────────────────

async def test_all_output_files_have_valid_frontmatter(axon_extractor, output_dir: Path):
    with patch("subprocess.run", side_effect=_make_ts_subprocess_sequence()):
        await axon_extractor.extract(output_dir / "repos")

    for md in (output_dir / "repos").rglob("*.md"):
        fm = _parse_frontmatter(md.read_text())
        assert fm.get("extractor") == "axon_bridge", f"Missing extractor in {md}"
        assert fm.get("trust") == 1.0, f"Wrong trust in {md}"
        assert "source/code" in fm.get("tags", []), f"Missing tag in {md}"
        assert "trust/high" in fm.get("tags", []), f"Missing trust tag in {md}"


# ── Domain detection ──────────────────────────────────────────────────────────

def test_domain_detection_auth():
    from library_server.vault_builder.extractors.axon_bridge import AxonBridgeExtractor
    ext = AxonBridgeExtractor(config={"enabled": True, "repos": []})
    assert ext._detect_domain("requireAuth verifyJWT clerk") == "auth"


def test_domain_detection_tenancy():
    from library_server.vault_builder.extractors.axon_bridge import AxonBridgeExtractor
    ext = AxonBridgeExtractor(config={"enabled": True, "repos": []})
    assert ext._detect_domain("setTenantContext org_id rls") == "tenancy"


def test_domain_detection_fallback():
    from library_server.vault_builder.extractors.axon_bridge import AxonBridgeExtractor
    ext = AxonBridgeExtractor(config={"enabled": True, "repos": []})
    assert ext._detect_domain("some random unmatched text") == "general"


# ── Slug deduplication ───────────────────────────────────────────────────────

async def test_duplicate_community_names_produce_unique_files(output_dir: Path):
    """Communities with the same name must NOT overwrite each other on disk."""
    from library_server.vault_builder.extractors.axon_bridge import AxonBridgeExtractor
    from library_server.vault_builder.output import OutputWriter

    # Simulate 3 communities all named "Services" (real axon output pattern)
    communities = [
        {"name": "Services", "symbol_count": 50},
        {"name": "Services", "symbol_count": 30},
        {"name": "Services", "symbol_count": 10},
    ]

    ext = AxonBridgeExtractor(config={"enabled": True, "repos": [
        {"name": "test-repo", "path": "/tmp/fake", "language": "typescript"},
    ]})
    writer = OutputWriter(base_dir=output_dir.parent)

    with patch.object(ext, "_cypher_members", return_value=[("fn1", "src/a.ts")]):
        files = ext._write_axon_results(writer, output_dir, "test-repo", communities, "/tmp/fake")

    # Should have 3 unique file paths, not 3 identical ones
    assert len(files) == 3
    assert len(set(files)) == 3, f"Duplicate filenames: {files}"

    # Verify all 3 files actually exist on disk
    for f in files:
        assert (output_dir / f).exists(), f"File not written: {f}"
