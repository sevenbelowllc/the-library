"""Tests for bin/library-mutation-smoke — mutation discovery logic.

We exercise the pure mutation-generator on hand-crafted source lines to
prove each strategy fires on the lines it should and stays silent on the
lines it shouldn't. The subprocess test-runner path is intentionally not
exercised here — that's validated by running the tool on the real tree.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "library-mutation-smoke"


def _load():
    loader = importlib.machinery.SourceFileLoader("_mut_smoke", str(_SCRIPT))
    spec = importlib.util.spec_from_loader("_mut_smoke", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_mut_smoke"] = mod
    loader.exec_module(mod)
    return mod


mod = _load()


class TestFlipConditional:
    def test_flips_equals_to_not_equals(self):
        muts = mod._mutations_for_line(Path("x.py"), 1, 'if a == b:\n')
        assert any(m.strategy == "flip_eq" for m in muts)
        flip = next(m for m in muts if m.strategy == "flip_eq")
        assert "!=" in flip.new_line

    def test_flips_not_equals_to_equals(self):
        muts = mod._mutations_for_line(Path("x.py"), 1, 'if a != b:\n')
        assert any(m.strategy == "flip_neq" for m in muts)

    def test_line_without_comparison_yields_no_flip(self):
        """Negative: plain assignment generates no flip_eq mutation."""
        muts = mod._mutations_for_line(Path("x.py"), 1, "x = 1\n")
        assert not any(m.strategy in ("flip_eq", "flip_neq") for m in muts)


class TestRemoveAssertRaise:
    def test_removes_raise(self):
        muts = mod._mutations_for_line(Path("x.py"), 1, '    raise ValueError("nope")\n')
        assert any(m.strategy == "remove_raise" for m in muts)
        rem = next(m for m in muts if m.strategy == "remove_raise")
        assert "pass" in rem.new_line
        # Indentation preserved.
        assert rem.new_line.startswith("    ")

    def test_removes_assert(self):
        muts = mod._mutations_for_line(Path("x.py"), 1, "    assert x > 0\n")
        assert any(m.strategy == "remove_assert" for m in muts)

    def test_does_not_match_raising_method(self):
        """Negative: ``self.raiseEvent()`` is not a raise statement."""
        muts = mod._mutations_for_line(Path("x.py"), 1, "    self.raiseEvent()\n")
        assert not any(m.strategy.startswith("remove_") for m in muts)


class TestFlipBoolean:
    def test_flips_true_to_false(self):
        muts = mod._mutations_for_line(Path("x.py"), 1, "x = True\n")
        assert any(m.strategy == "flip_true" for m in muts)

    def test_flips_false_to_true(self):
        muts = mod._mutations_for_line(Path("x.py"), 1, "x = False\n")
        assert any(m.strategy == "flip_false" for m in muts)

    def test_does_not_match_true_substring(self):
        """Negative: ``truthy`` is not the bool literal True."""
        muts = mod._mutations_for_line(Path("x.py"), 1, "truthy = 1\n")
        assert not any(m.strategy in ("flip_true", "flip_false") for m in muts)


class TestDiscovery:
    def test_discover_returns_mutations(self):
        """Integration: the real pm/ tree yields a non-empty mutation list."""
        mutations = mod._discover_mutations()
        assert len(mutations) > 0
        strategies = {m.strategy for m in mutations}
        # We expect at least a flip_eq and a remove_raise somewhere in pm/.
        assert "flip_eq" in strategies
        assert "remove_raise" in strategies

    def test_max_per_file_caps_output(self):
        capped = mod._discover_mutations(max_per_file=1)
        # One mutation per file at most.
        files = [m.file for m in capped]
        assert len(files) == len(set(files))


class TestMutationDescribe:
    def test_describe_includes_strategy(self):
        m = mod.Mutation(
            file=Path(mod.ROOT / "src" / "library_server" / "pm" / "jira.py"),
            line_no=42,
            old_line="if a == b:\n",
            new_line="if a != b:\n",
            strategy="flip_eq",
        )
        desc = m.describe()
        assert "flip_eq" in desc
        assert ":42" in desc
