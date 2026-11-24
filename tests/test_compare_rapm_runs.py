"""Unit tests for the replay comparison logic in scripts/compare_rapm_runs.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compare_rapm_runs.py"
spec = importlib.util.spec_from_file_location("compare_rapm_runs", SCRIPT)
assert spec is not None and spec.loader is not None
cmp = importlib.util.module_from_spec(spec)
sys.modules["compare_rapm_runs"] = cmp
spec.loader.exec_module(cmp)


def run(a: Any, b: Any) -> Any:
    group = cmp.Group("t")
    cmp.compare_values(a, b, group)
    return group


def test_identical_trees_pass_and_count_leaves() -> None:
    tree = {"mse": 14109.76, "n": 5, "s": "W2", "ci": [1.5, 2.5], "none": None}
    group = run(tree, json.loads(json.dumps(tree)))
    assert group.passed and group.leaves == 6


def test_float_within_and_outside_tolerance() -> None:
    assert run({"x": 1000.0}, {"x": 1000.0 * (1 + 5e-9)}).passed
    bad = run({"x": 1000.0}, {"x": 1000.0 * (1 + 5e-8)})
    assert not bad.passed and "/x" in bad.failures[0]
    assert run({"x": 0.0}, {"x": 1e-12}).passed
    assert not run({"x": 0.0}, {"x": 1e-6}).passed


def test_exact_classes_never_use_tolerance() -> None:
    assert not run({"n": 100}, {"n": 101}).passed
    assert not run({"s": "W2"}, {"s": "W3"}).passed
    assert not run({"d": "abc"}, {"d": "abd"}).passed
    assert not run({"iterations": 35.0}, {"iterations": 35.0000001}).passed
    assert not run({"ok": True}, {"ok": False}).passed
    assert not run({"x": None}, {"x": 0.0}).passed


def test_nan_matches_nan_only() -> None:
    assert run({"x": float("nan")}, {"x": float("nan")}).passed
    assert not run({"x": float("nan")}, {"x": 1.0}).passed
    assert not run({"x": float("inf")}, {"x": 1e300}).passed


def test_structure_differences_fail() -> None:
    assert not run({"a": 1}, {"a": 1, "b": 2}).passed
    assert not run({"a": [1, 2]}, {"a": [1, 2, 3]}).passed


def test_ignored_keys_are_skipped() -> None:
    a = {"runtime_seconds": 1.0, "code_commit": "x", "outputs": {"f": "1"}, "v": 3.0}
    b = {"runtime_seconds": 9.0, "code_commit": "y", "outputs": {"f": "2"}, "v": 3.0}
    group = run(a, b)
    assert group.passed and group.leaves == 1


def test_max_deviation_is_recorded() -> None:
    group = run({"a": 1.0, "b": 2.0}, {"a": 1.0 + 1e-10, "b": 2.0 + 3e-10})
    assert group.passed
    assert group.worst == "/b" and abs(group.max_abs - 3e-10) < 1e-15


def test_arrays_exact_for_ints_and_tolerant_for_floats() -> None:
    group = cmp.Group("a")
    cmp.compare_arrays(np.array([1, 2]), np.array([1, 2]), group, "i")
    cmp.compare_arrays(np.array([1.0, 2.0]), np.array([1.0, 2.0 + 1e-12]), group, "f")
    assert group.passed
    cmp.compare_arrays(np.array([1, 2]), np.array([1, 3]), group, "i2")
    cmp.compare_arrays(np.array([1.0]), np.array([1.001]), group, "f2")
    cmp.compare_arrays(np.array([1.0]), np.array([1.0, 2.0]), group, "shape")
    assert len(group.failures) == 3


def test_csv_ids_exact_and_estimates_tolerant(tmp_path: Path) -> None:
    head = "player_id,offense,defense,total,on_court_possessions\n"
    (tmp_path / "a.csv").write_text(head + "1,0.5,0.25,0.75,100.0\n2,-1.0,0.0,-1.0,50.0\n")
    (tmp_path / "b.csv").write_text(head + "1,0.5,0.25,0.75,100.0\n2,-1.0,0.0,-1.0,50.0\n")
    (tmp_path / "c.csv").write_text(head + "1,0.5,0.25,0.75,100.0\n3,-1.0,0.0,-1.0,50.0\n")
    (tmp_path / "d.csv").write_text(head + "1,0.5001,0.25,0.75,100.0\n2,-1.0,0.0,-1.0,50.0\n")
    ok = cmp.Group("ok")
    cmp.compare_csv(tmp_path / "a.csv", tmp_path / "b.csv", ok)
    assert ok.passed and ok.leaves == 10
    for other in ("c.csv", "d.csv"):
        bad = cmp.Group(other)
        cmp.compare_csv(tmp_path / "a.csv", tmp_path / other, bad)
        assert not bad.passed
