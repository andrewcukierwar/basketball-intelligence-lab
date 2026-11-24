"""Compare two multi-season RAPM run directories under the replay protocol's tolerances.

Example:
    uv run python scripts/compare_rapm_runs.py dev \
        data/processed/multiseason/issue-26-dev-v1 \
        data/processed/multiseason/issue-27-replay-dev-v1

Rules (docs/research/rapm-replay-protocol.md): strings, integers, booleans, nulls, digests, row
counts, solver iteration counts and the selected configuration must match exactly. Other floats
pass when |a - b| <= ATOL + RTOL * max(|a|, |b|). Timing, memory, commit and clean-tree fields
are ignored. Exit status is 0 only if every group passes.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

RTOL = 1e-8
ATOL = 1e-10
IGNORED_KEYS = frozenset(
    {
        "generated_at",
        "runtime_seconds",
        "peak_memory_mib",
        "seconds",
        "fit_seconds",
        "median_fit_seconds",
        "total_fit_seconds",
        "_assemble_seconds",
        "code_commit",
        "head_commit",
        "working_tree_clean",
        "working_tree_clean_at_end",
        "outputs",  # file digests: results.json and fit_log.json embed timings
    }
)
REPORTED_KEYS = frozenset({"versions"})
EXACT_FLOAT_KEYS = frozenset({"iterations", "stop", "rows"})


@dataclass
class Group:
    name: str
    leaves: int = 0
    failures: list[str] = field(default_factory=list)
    max_abs: float = 0.0
    max_rel: float = 0.0
    worst: str = ""

    @property
    def passed(self) -> bool:
        return not self.failures


def floats_close(a: float, b: float) -> bool:
    if math.isnan(a) or math.isnan(b):
        return math.isnan(a) and math.isnan(b)
    if math.isinf(a) or math.isinf(b):
        return a == b
    return abs(a - b) <= ATOL + RTOL * max(abs(a), abs(b))


def _note(group: Group, path: str, a: float, b: float) -> None:
    if math.isfinite(a) and math.isfinite(b):
        diff = abs(a - b)
        rel = diff / max(abs(a), abs(b), 1e-300)
        if diff > group.max_abs:
            group.max_abs = diff
            group.worst = path
        group.max_rel = max(group.max_rel, rel)


def _fail(group: Group, path: str, message: str) -> None:
    if len(group.failures) < 25:
        group.failures.append(f"{path}: {message}")
    elif len(group.failures) == 25:
        group.failures.append("... further failures omitted")


def compare_values(a: Any, b: Any, group: Group, path: str = "", key: str = "") -> None:
    """Recursively compare two parsed JSON values, recording every leaf in the group."""
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k in IGNORED_KEYS or k in REPORTED_KEYS:
                continue
            if k not in a or k not in b:
                _fail(group, f"{path}/{k}", "present on one side only")
                continue
            compare_values(a[k], b[k], group, f"{path}/{k}", k)
        return
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            _fail(group, path, f"length {len(a)} != {len(b)}")
            return
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            compare_values(x, y, group, f"{path}[{i}]", key)
        return
    group.leaves += 1
    both_numbers = (
        isinstance(a, (int, float))
        and isinstance(b, (int, float))
        and not isinstance(a, bool)
        and not isinstance(b, bool)
    )
    if both_numbers and (isinstance(a, float) or isinstance(b, float)):
        x, y = float(a), float(b)
        _note(group, path, x, y)
        if key in EXACT_FLOAT_KEYS:
            if x != y:
                _fail(group, path, f"{x!r} != {y!r} (exact)")
        elif not floats_close(x, y):
            _fail(group, path, f"{x!r} vs {y!r}")
        return
    if type(a) is not type(b) or a != b:
        _fail(group, path, f"{a!r} != {b!r} (exact)")


def compare_arrays(
    a: np.ndarray[Any, Any], b: np.ndarray[Any, Any], group: Group, path: str
) -> None:
    group.leaves += 1
    if a.shape != b.shape:
        _fail(group, path, f"shape {a.shape} != {b.shape}")
        return
    if a.dtype.kind != b.dtype.kind:
        _fail(group, path, f"dtype {a.dtype} != {b.dtype}")
        return
    if a.dtype.kind != "f":
        if not np.array_equal(a, b):
            _fail(group, path, f"{int((a != b).sum())} elements differ (exact)")
        return
    nan_a, nan_b = np.isnan(a), np.isnan(b)
    if not np.array_equal(nan_a, nan_b):
        _fail(group, path, "NaN positions differ")
        return
    keep = ~nan_a
    if not keep.any():
        return
    x, y = a[keep], b[keep]
    diff = np.abs(x - y)
    bad = diff > ATOL + RTOL * np.maximum(np.abs(x), np.abs(y))
    if diff.size and float(diff.max()) > group.max_abs:
        group.max_abs = float(diff.max())
        group.worst = path
    scale = np.maximum(np.maximum(np.abs(x), np.abs(y)), 1e-300)
    group.max_rel = max(group.max_rel, float((diff / scale).max()))
    if bad.any():
        _fail(group, path, f"{int(bad.sum())} of {bad.size} elements outside tolerance")


def compare_csv(a: Path, b: Path, group: Group) -> None:
    """Player estimates: ids, order and exposure exact; estimates within tolerance."""
    with a.open(newline="") as fa, b.open(newline="") as fb:
        rows_a, rows_b = list(csv.DictReader(fa)), list(csv.DictReader(fb))
    if len(rows_a) != len(rows_b):
        _fail(group, a.name, f"row count {len(rows_a)} != {len(rows_b)}")
        return
    for i, (ra, rb) in enumerate(zip(rows_a, rows_b, strict=True)):
        if list(ra) != list(rb):
            _fail(group, f"{a.name}[{i}]", "columns differ")
            return
        for col in ra:
            group.leaves += 1
            path = f"{a.name}[{i}].{col}"
            if col in ("player_id", "on_court_possessions"):
                if ra[col] != rb[col]:
                    _fail(group, path, f"{ra[col]!r} != {rb[col]!r} (exact)")
                continue
            x, y = float(ra[col]), float(rb[col])
            _note(group, path, x, y)
            if not floats_close(x, y):
                _fail(group, path, f"{x!r} vs {y!r}")


def _load(path: Path) -> Any:
    return json.loads(path.read_text())


def _json_group(name: str, a: Any, b: Any, section: str | None = None) -> Group:
    group = Group(name)
    if section is not None:
        a, b = a.get(section), b.get(section)
        if a is None or b is None:
            _fail(group, section, "missing on one side")
            return group
    compare_values(a, b, group)
    return group


def compare_dev(orig: Path, new: Path) -> list[Group]:
    ra, rb = _load(orig / "results.json"), _load(new / "results.json")
    ma, mb = _load(orig / "manifest.json"), _load(new / "manifest.json")
    groups = [
        _json_group("input lineage and digests (manifest.inputs)", ma, mb, "inputs"),
        _json_group("row counts (results.rows)", ra, rb, "rows"),
        _json_group("blocks (results.blocks)", ra, rb, "blocks"),
        _json_group("selected configuration (results.selected)", ra, rb, "selected"),
        _json_group("selected configuration (manifest.selected)", ma, mb, "selected"),
        _json_group("protocol digest (manifest.protocol)", ma, mb, "protocol"),
        _json_group("candidate MSEs and deltas (scenarios)", ra, rb, "scenarios"),
        _json_group("sensitivity summary", ra, rb, "sensitivity_summary"),
        _json_group("solver summary", ra, rb, "solver"),
        _json_group("temporal candidates", ra, rb, "temporal_candidates"),
        _json_group("fit log", _load(orig / "fit_log.json"), _load(new / "fit_log.json")),
    ]
    covered = {"rows", "blocks", "selected", "scenarios", "sensitivity_summary", "solver"}
    covered |= {"temporal_candidates"}
    rest = Group("other results keys")
    compare_values(
        {k: v for k, v in ra.items() if k not in covered},
        {k: v for k, v in rb.items() if k not in covered},
        rest,
    )
    csv_group = Group("coefficients (player_estimates.csv)")
    compare_csv(orig / "player_estimates.csv", new / "player_estimates.csv", csv_group)
    return [*groups, rest, csv_group]


def compare_outer(orig: Path, new: Path) -> list[Group]:
    ra, rb = _load(orig / "results.json"), _load(new / "results.json")
    ma, mb = _load(orig / "manifest.json"), _load(new / "manifest.json")
    groups = [
        _json_group("input lineage and digests (manifest.inputs)", ma, mb, "inputs"),
        _json_group("outcome digests and counts (manifest.outcomes)", ma, mb, "outcomes"),
        _json_group("addendum and dev-manifest lineage", ma, mb, "addendum"),
        _json_group("frozen configuration", ma, mb, "frozen_configuration"),
        _json_group("dev manifest digest", ma["dev_manifest_sha256"], mb["dev_manifest_sha256"]),
        _json_group("configuration (results.configuration)", ra, rb, "configuration"),
        _json_group("outcomes (results.outcomes)", ra, rb, "outcomes"),
        _json_group("pooled and per-season sets with deltas and CIs", ra, rb, "sets"),
        _json_group("per-block results", ra, rb, "per_block"),
        _json_group("refit volatility", ra, rb, "refit_volatility"),
        _json_group("solver summary", ra, rb, "solver"),
        _json_group("fit log", _load(orig / "fit_log.json"), _load(new / "fit_log.json")),
    ]
    pred = Group("predictions (predictions.npz)")
    with np.load(orig / "predictions.npz") as za, np.load(new / "predictions.npz") as zb:
        if sorted(za.files) != sorted(zb.files):
            _fail(pred, "keys", f"{sorted(za.files)} != {sorted(zb.files)}")
        else:
            for name in sorted(za.files):
                compare_arrays(za[name], zb[name], pred, name)
    return [*groups, pred]


def versions(orig: Path, new: Path) -> dict[str, Any]:
    return {
        "original": _load(orig / "manifest.json").get("versions"),
        "replay": _load(new / "manifest.json").get("versions"),
    }


def report(phase: str, orig: Path, new: Path) -> tuple[bool, dict[str, Any]]:
    groups = compare_dev(orig, new) if phase == "dev" else compare_outer(orig, new)
    ok = all(g.passed for g in groups)
    out = {
        "phase": phase,
        "original": str(orig),
        "replay": str(new),
        "passed": ok,
        "tolerance": {"rtol": RTOL, "atol": ATOL},
        "versions": versions(orig, new),
        "groups": [
            {
                "name": g.name,
                "passed": g.passed,
                "leaves": g.leaves,
                "max_abs_deviation": g.max_abs,
                "max_rel_deviation": g.max_rel,
                "worst_leaf": g.worst,
                "failures": g.failures,
            }
            for g in groups
        ],
    }
    return ok, out


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    cli.add_argument("phase", choices=["dev", "outer"])
    cli.add_argument("original", type=Path)
    cli.add_argument("replay", type=Path)
    cli.add_argument("--json", type=Path, help="write the full report here")
    args = cli.parse_args(argv)
    ok, out = report(args.phase, args.original, args.replay)
    for g in out["groups"]:
        status = "PASS" if g["passed"] else "FAIL"
        print(
            f"{status}  {g['name']}: {g['leaves']} leaves, max abs {g['max_abs_deviation']:.3g},"
            f" max rel {g['max_rel_deviation']:.3g}"
        )
        for failure in g["failures"]:
            print(f"      {failure}")
    print(f"versions: {out['versions']}")
    print("OVERALL", "PASS" if ok else "FAIL")
    if args.json:
        args.json.write_text(json.dumps(out, indent=2) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
