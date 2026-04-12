"""Tests for Axon Bridge extractor."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

SAMPLE_AXON_QUERY_RESULT = json.dumps({
    "results": [
        {"id": "auth.ts", "type": "module", "community": "auth-middleware", "symbols": ["requireAuth", "verifyJWT"]},
        {"id": "rls.ts", "type": "module", "community": "tenant-context", "symbols": ["setTenantContext"]},
    ]
})


def _parse_frontmatter(content: str) -> dict:
    parts = content.split("---\n", 2)
    if len(parts) < 3:
        return {}
    return yaml.safe_load(parts[1]) or {}


@pytest.fixture
def sample_ts_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "compliance-core"
    repo.mkdir()
    (repo / "package.json").write_text('{"name": "compliance-core"}')
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
        'resource "google_project" "main" {\n'
        '  name = "compliance-os"\n'
        '}\n\n'
        'module "network" {\n'
        '  source = "./modules/network"\n'
        '}\n\n'
        'variable "region" {\n'
        '  default = "us-central1"\n'
        '}\n'
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


async def test_survey_returns_correct_counts(axon_extractor):
    result = await axon_extractor.survey()
    assert result.source_name == "axon_bridge"
    assert result.file_count == 2


async def test_terraform_fallback_extracts(axon_extractor, output_dir: Path):
    mock_run = MagicMock()
    mock_run.returncode = 1
    mock_run.stderr = "Unsupported language"
    with patch("subprocess.run", return_value=mock_run):
        result = await axon_extractor.extract(output_dir / "repos")
    tf_dir = output_dir / "repos" / "terraform-metadata"
    assert tf_dir.exists()
    tf_files = list(tf_dir.rglob("*.md"))
    assert len(tf_files) >= 1


async def test_terraform_fallback_extracts_resources(axon_extractor, output_dir: Path):
    mock_run = MagicMock()
    mock_run.returncode = 1
    mock_run.stderr = "Unsupported"
    with patch("subprocess.run", return_value=mock_run):
        await axon_extractor.extract(output_dir / "repos")
    summary = output_dir / "repos" / "terraform-metadata" / "repo-summary.md"
    assert summary.exists()
    content = summary.read_text()
    assert "google_project" in content


async def test_extract_trust_values(axon_extractor, output_dir: Path):
    mock_run = MagicMock()
    mock_run.returncode = 0
    mock_run.stdout = SAMPLE_AXON_QUERY_RESULT
    with patch("subprocess.run", return_value=mock_run):
        await axon_extractor.extract(output_dir / "repos")
    for md in (output_dir / "repos").rglob("*.md"):
        fm = _parse_frontmatter(md.read_text())
        assert fm["trust"] == 1.0


async def test_extract_frontmatter_valid(axon_extractor, output_dir: Path):
    mock_run = MagicMock()
    mock_run.returncode = 0
    mock_run.stdout = SAMPLE_AXON_QUERY_RESULT
    with patch("subprocess.run", return_value=mock_run):
        await axon_extractor.extract(output_dir / "repos")
    for md in (output_dir / "repos").rglob("*.md"):
        fm = _parse_frontmatter(md.read_text())
        assert fm["extractor"] == "axon_bridge"
        assert "source/code" in fm["tags"]
        assert "trust/high" in fm["tags"]
