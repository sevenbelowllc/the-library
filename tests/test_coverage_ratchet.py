"""Tests for bin/library-coverage-ratchet.

Exercises the pure comparison logic and negative (drop) cases without
actually running pytest under coverage.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "library-coverage-ratchet"


def _load():
    loader = importlib.machinery.SourceFileLoader("_cov_ratchet", str(_SCRIPT))
    spec = importlib.util.spec_from_loader("_cov_ratchet", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_cov_ratchet"] = mod
    loader.exec_module(mod)
    return mod


mod = _load()


class TestRatchet:
    def test_no_change_passes(self, tmp_path, monkeypatch, capsys):
        baseline = tmp_path / "coverage-baseline.txt"
        baseline.write_text("93.46\n")
        monkeypatch.setattr(mod, "BASELINE", baseline)
        rc = mod.main(["--current", "93.46"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "delta=+0.00pp" in out

    def test_improvement_passes(self, tmp_path, monkeypatch):
        baseline = tmp_path / "coverage-baseline.txt"
        baseline.write_text("93.00\n")
        monkeypatch.setattr(mod, "BASELINE", baseline)
        assert mod.main(["--current", "95.00"]) == 0

    def test_drop_fails(self, tmp_path, monkeypatch, capsys):
        """Negative test: coverage drop must fail the ratchet."""
        baseline = tmp_path / "coverage-baseline.txt"
        baseline.write_text("93.46\n")
        monkeypatch.setattr(mod, "BASELINE", baseline)
        rc = mod.main(["--current", "90.00"])
        err = capsys.readouterr().err
        assert rc == 1
        assert "dropped" in err

    def test_tolerance_allows_small_drop(self, tmp_path, monkeypatch):
        baseline = tmp_path / "coverage-baseline.txt"
        baseline.write_text("93.46\n")
        monkeypatch.setattr(mod, "BASELINE", baseline)
        # 93.40 is 0.06pp below; tolerance 0.1 allows it.
        assert mod.main(["--current", "93.40", "--tolerance", "0.1"]) == 0

    def test_bump_writes_baseline(self, tmp_path, monkeypatch):
        baseline = tmp_path / "coverage-baseline.txt"
        baseline.write_text("93.46\n")
        monkeypatch.setattr(mod, "BASELINE", baseline)
        assert mod.main(["--bump", "--current", "95.12"]) == 0
        assert baseline.read_text().strip() == "95.12"

    def test_missing_baseline_raises(self, tmp_path, monkeypatch):
        baseline = tmp_path / "does-not-exist.txt"
        monkeypatch.setattr(mod, "BASELINE", baseline)
        with pytest.raises(SystemExit, match="baseline file missing"):
            mod.main(["--current", "93.46"])
