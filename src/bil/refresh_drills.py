"""Failure drills and recovery on the pinned replay inputs (#145).

Usage::

    uv run python -m bil.refresh_drills RAW PROCESSED OUT

``OUT`` must be a new directory under ``data/``. Each drill runs in its own artifact root.

**Refusal drills.** Each must leave an outcome record with the refused origin, stage, reason and
inputs, and no artifact or staging directory. They cover:

- a mismatched pin digest;
- a missing pin;
- a late parent fit;
- a failed row-set check;
- an ineligible calibration, through ``load_calibration``;
- an interrupted publish.

**Recovery drills.** Resume after an interruption, roll back an accepted revision, and rebuild
cold with the same artifact ID.
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import date
from pathlib import Path
from tempfile import mkdtemp
from typing import Any
from unittest import mock

import bil.refresh as refresh
from bil.models.expected_impact_outer import ADDENDUM
from bil.models.rapm.multiseason import FROZEN_BLOCK, SEASON_PINS, _git_head
from bil.refresh import (
    CHECKPOINTS,
    OUTCOMES,
    RATINGS,
    Inputs,
    build,
    current,
    load_inputs,
    refresh_origin,
    requested_inputs,
    retire,
)

ORIGIN = date(2025, 1, 15)  # after the #136 calibration fit cutoff (2024-07-01)
EARLY = date(2024, 1, 15)  # before it


def _addendum(out: Path, change: Callable[[dict[str, Any]], None]) -> Path:
    """A copy of the #36 addendum whose frozen block has one pin altered."""
    text = ADDENDUM.read_text(encoding="utf-8")
    match = FROZEN_BLOCK.search(text)
    assert match is not None
    config = json.loads(match.group(1))
    change(config)
    altered = text[: match.start(1)] + json.dumps(config, indent=2) + text[match.end(1) :]
    path = Path(mkdtemp(prefix="addendum-", dir=out)) / ADDENDUM.name
    path.write_text(altered, encoding="utf-8")
    return path


def _loader(raw: Path, processed: Path, root: Path, **options: Any) -> Callable[[], Inputs]:
    def load() -> Inputs:
        root.mkdir(parents=True, exist_ok=True)
        scratch = Path(mkdtemp(prefix=".inputs-", dir=root))
        try:
            return load_inputs(raw, processed, scratch, **options)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    return load


def _outcomes(root: Path) -> list[dict[str, Any]]:
    path = root / OUTCOMES
    return [json.loads(line) for line in path.open()] if path.is_file() else []


def _leftovers(root: Path) -> list[str]:
    """Artifact or staging directories under any origin of ``root``."""
    return sorted(
        str(p.relative_to(root))
        for origin in root.iterdir()
        if origin.is_dir() and origin.name[:2] == "20"
        for p in origin.iterdir()
        if p.is_dir()
    )


def _refusal(root: Path, stage: str, expect: str) -> dict[str, Any]:
    records = _outcomes(root)
    record = records[-1] if records else {}
    left = _leftovers(root) if root.exists() else []
    return {
        "record": record,
        "leftovers": left,
        "passed": record.get("outcome") == "refused"
        and record.get("stage") == stage
        and expect in str(record.get("reason", ""))
        and bool(record.get("origin"))
        and bool(record.get("inputs"))
        and not left,
    }


def run(raw: Path, processed: Path, out: Path) -> dict[str, Any]:
    calibration = processed / "team_outcomes" / "issue-136-v1"
    results: dict[str, Any] = {}
    started = time.perf_counter()
    base_root = out / "baseline"
    inputs = _loader(raw, processed, base_root, calibration=calibration)()
    load_seconds = time.perf_counter() - started
    records, failures = build(base_root, [ORIGIN], lambda: inputs)
    baseline = records[0]
    results["baseline"] = {"record": baseline, "passed": failures == 0}

    # 1. A mismatched pin digest refuses at load.
    def flip(config: dict[str, Any]) -> None:
        pin = config["box_logs"]["2024"]
        pin["sha256"] = pin["sha256"][::-1]

    root = out / "pin_digest_mismatch"
    bad = _addendum(out, flip)
    build(
        root,
        [ORIGIN],
        _loader(raw, processed, root, addendum=bad),
        requested_inputs(raw, processed, bad),
    )
    results["pin_digest_mismatch"] = _refusal(root, "load", "")

    # 2. A missing pinned snapshot refuses at load.
    def missing(config: dict[str, Any]) -> None:
        config["box_logs"]["2024"]["snapshot"] = "snapshot-that-does-not-exist"

    root = out / "pin_missing"
    gone = _addendum(out, missing)
    build(
        root,
        [ORIGIN],
        _loader(raw, processed, root, addendum=gone),
        requested_inputs(raw, processed, gone),
    )
    results["pin_missing"] = _refusal(root, "load", "snapshot-that-does-not-exist")

    # 3. A parent fit dated at the origin refuses before fitting.
    root = out / "late_parent"
    late = replace(inputs, spm=replace(inputs.spm, origin=f"contiguous@{ORIGIN.isoformat()}"))
    build(root, [ORIGIN], lambda: late)
    results["late_parent"] = _refusal(root, "parent", "late parent")

    # 4. A failed row-set check (a pinned row-manifest digest that does not match) refuses.
    root = out / "row_set_check"
    pins: Mapping[int, Any] = {
        **SEASON_PINS,
        2024: replace(SEASON_PINS[2024], row_manifest_sha256="0" * 64),
    }
    build(
        root,
        [ORIGIN],
        _loader(raw, processed, root, pins=pins),
        requested_inputs(raw, processed, pins=pins),
    )
    results["row_set_check"] = _refusal(root, "load", "")

    # 5. The #136 calibration is ineligible before its fit cutoff; load_calibration refuses.
    root = out / "ineligible_calibration"
    build(root, [EARLY], lambda: inputs)
    results["ineligible_calibration"] = _refusal(root, "calibration", "follows the origin")

    # 6. An interrupted publish leaves nothing; a rerun resumes and publishes.
    root = out / "interrupted_publish"

    def crash(path: Path, snapshots: object) -> None:
        path.write_text("partial", encoding="utf-8")
        raise OSError("drill: interrupted while writing ratings")

    with mock.patch.object(refresh, "write_ratings", crash):
        build(root, [ORIGIN], lambda: inputs)
    refused = _refusal(root, "publish", "interrupted")
    resumed, failures = build(root, [ORIGIN], lambda: inputs)
    refused["resume"] = resumed[0]
    refused["passed"] = (
        refused["passed"]
        and failures == 0
        and resumed[0]["outcome"] == "published"
        and resumed[0]["artifact_id"] == baseline["artifact_id"]
    )
    results["interrupted_publish"] = refused

    # 7. Roll back an accepted revision to the last good artifact.
    root = out / "rollback"
    good = refresh_origin(root, ORIGIN, inputs)
    changed = replace(inputs, config={**inputs.config, "offense_ridge": 9000.0})
    revised = refresh_origin(root, ORIGIN, changed, accept_revision=True)
    after_accept = current(root, ORIGIN)
    retire(root, ORIGIN, revised.artifact_id, "drill: rejected revision")
    restored = current(root, ORIGIN)
    results["rollback"] = {
        "good": good.artifact_id,
        "revised": revised.artifact_id,
        "passed": after_accept == revised.path
        and restored == good.path
        and (restored / RATINGS).read_bytes()
        == (base_root / ORIGIN.isoformat() / baseline["artifact_id"] / RATINGS).read_bytes(),
    }

    # 8. A cold rebuild (new root, no checkpoints) reproduces the baseline artifact.
    root = out / "cold_rebuild"
    cold, failures = build(root, [ORIGIN], lambda: inputs, checkpoints=None)
    baseline_checkpoints = base_root / CHECKPOINTS
    results["cold_rebuild"] = {
        "record": cold[0],
        "passed": failures == 0
        and cold[0]["artifact_id"] == baseline["artifact_id"]
        and (Path(cold[0]["path"]) / RATINGS).read_bytes()
        == (base_root / ORIGIN.isoformat() / baseline["artifact_id"] / RATINGS).read_bytes(),
        "baseline_had_checkpoints": baseline_checkpoints.exists(),
    }
    head, clean = _git_head()
    return {
        "code_commit": head,
        "working_tree_clean": clean,
        "load_seconds": load_seconds,
        "seconds": time.perf_counter() - started,
        "drills": results,
        "passed": all(d["passed"] for d in results.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("processed", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    report = run(args.raw, args.processed, args.out)
    (args.out / "results.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps({k: v["passed"] for k, v in report["drills"].items()}, indent=2))
    if not report["passed"]:
        raise SystemExit("a drill failed")


if __name__ == "__main__":
    main()
