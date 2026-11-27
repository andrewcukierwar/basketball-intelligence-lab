"""Warm and cold equality, capacity and a late-revision drill for the local refresh (#144).

The workload, passes and budget are registered in ``docs/refresh.md`` (Capacity budget) before
the run. Usage::

    uv run python -m bil.refresh_capacity RAW PROCESSED OUT

``OUT`` must be a new directory under ``data/``. It receives the artifact roots, the checkpoint
store and ``results.json``.
"""

from __future__ import annotations

import argparse
import json
import resource
import subprocess
import sys
import time
from dataclasses import replace
from datetime import date
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

import numpy as np

from bil.models.rapm.multiseason import _git_head, season_blocks
from bil.models.refresh_cadence import cutoffs
from bil.refresh import (
    CHECKPOINT_RETENTION,
    RATINGS,
    REVISIONS,
    Inputs,
    RevisionConflict,
    load_inputs,
    refresh_origin,
)
from bil.refresh_sources import GameRecord

SEASON = 2024
DAILY = [date(2025, 1, d) for d in range(1, 32)]
DAILY_JOB = date(2025, 2, 3)
DRILL = date(2025, 1, 15)
BUDGET = {
    "peak_rss_gib": 4.0,
    "max_refresh_seconds": 5.0,
    "daily_job_seconds": 120.0,
    "checkpoint_store_mb": 500.0,
}


def _rss_gib(who: int) -> float:
    peak = resource.getrusage(who).ru_maxrss
    return peak / (1 << 30) if sys.platform == "darwin" else peak / (1 << 20)


def workload(inputs: Inputs) -> dict[str, list[date]]:
    rows = inputs.analysis.rows
    days = sorted(date.fromordinal(int(d)) for d in np.unique(rows.day[rows.season == SEASON]))
    blocks = [b.cutoff for b in season_blocks(rows, SEASON)]
    return {"daily": DAILY, "weekly": cutoffs("weekly", SEASON, blocks, days)}


def run_pass(
    root: Path, origins: list[date], inputs: Inputs, store: Path, reuse: bool
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for origin in origins:
        started = time.perf_counter()
        done = refresh_origin(
            root, origin, inputs, checkpoints=store, reuse=reuse, retention=len(origins)
        )
        out[origin.isoformat()] = {
            "artifact_id": done.artifact_id,
            "checkpoint": done.checkpoint,
            "seconds": time.perf_counter() - started,
            "ratings": (done.path / RATINGS).read_bytes(),
        }
    return out


def drill(root: Path, inputs: Inputs) -> dict[str, Any]:
    """Alter one pre-origin game's captured content at a published origin."""
    before = sorted(p.name for p in (root / DRILL.isoformat()).iterdir())
    captures = list(inputs.captures)
    index = next(i for i, c in enumerate(captures) if c.source == f"box_logs/{SEASON}")
    capture = captures[index]
    game = min(g for g, r in capture.games.items() if r.game_date and r.game_date < DRILL)
    record = capture.games[game]
    games = {**capture.games, game: GameRecord(record.game_date, "f" * 64, record.finalized_at)}
    captures[index] = replace(capture, games=games)
    try:
        refresh_origin(root, DRILL, replace(inputs, captures=tuple(captures)))
    except RevisionConflict as error:
        refused = str(error)
    else:
        refused = ""
    log = [json.loads(line) for line in (root / DRILL.isoformat() / REVISIONS).open()]
    after = sorted(p.name for p in (root / DRILL.isoformat()).iterdir())
    return {
        "game": game,
        "refused": bool(refused),
        "record": log[-1],
        "artifacts_unchanged": [n for n in before if n != REVISIONS]
        == [n for n in after if n != REVISIONS],
        "passed": bool(refused)
        and log[-1]["examples"]["changed"] == [f"box_logs/{SEASON}:{game}"]
        and log[-1]["action"] == "refused",
    }


def daily_job(raw: Path, processed: Path, root: Path) -> dict[str, Any]:
    started = time.perf_counter()
    command = [sys.executable, "-m", "bil.refresh", "build", str(raw), str(processed), str(root)]
    done = subprocess.run(
        [*command, "--origin", DAILY_JOB.isoformat()],
        capture_output=True,
        text=True,
        check=True,
    )
    return {
        "origin": DAILY_JOB.isoformat(),
        "seconds": time.perf_counter() - started,
        "peak_rss_gib": _rss_gib(resource.RUSAGE_CHILDREN),
        "output": json.loads(done.stdout.strip().splitlines()[-1]),
    }


def _dir_mb(path: Path) -> float:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) / 1e6


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("processed", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    head, clean = _git_head()
    started = time.perf_counter()
    scratch = Path(mkdtemp(prefix=".inputs-", dir=args.out))
    inputs = load_inputs(args.raw, args.processed, scratch)
    load_seconds = time.perf_counter() - started
    plan = workload(inputs)
    origins = sorted({*plan["daily"], *plan["weekly"]})
    store = args.out / "checkpoints"
    cold = run_pass(args.out / "cold", origins, inputs, store, reuse=False)
    warm = run_pass(args.out / "warm", origins, inputs, store, reuse=True)
    mismatched = [
        o
        for o in cold
        if cold[o]["artifact_id"] != warm[o]["artifact_id"]
        or cold[o]["ratings"] != warm[o]["ratings"]
    ]
    checkpoint_files = list(store.glob("*.npz"))
    mean_mb = _dir_mb(store) / max(len(checkpoint_files), 1)
    # The store at default retention, measured: the files of the latest retained origins.
    latest = sorted({p.name[:10] for p in checkpoint_files})[-CHECKPOINT_RETENTION:]
    retained_mb = (
        sum(p.stat().st_size for p in store.iterdir() if p.is_file() and p.name[:10] in latest)
        / 1e6
    )
    revision = drill(args.out / "cold", inputs)
    job = daily_job(args.raw, args.processed, args.out / "daily")
    seconds = {
        name: [p["seconds"] for p in run.values()] for name, run in (("cold", cold), ("warm", warm))
    }

    def stats(values: list[float]) -> dict[str, float]:
        return {
            "mean": float(np.mean(values)),
            "max": float(np.max(values)),
            "total": float(np.sum(values)),
        }

    peak = _rss_gib(resource.RUSAGE_SELF)
    measured = {
        "peak_rss_gib": max(peak, job["peak_rss_gib"]),
        "max_refresh_seconds": max(max(seconds["cold"]), max(seconds["warm"])),
        "daily_job_seconds": job["seconds"],
        "checkpoint_store_mb": retained_mb,
    }
    checks = {name: measured[name] <= BUDGET[name] for name in BUDGET}
    checks["warm_cold_equality"] = not mismatched
    # The warm pass must really reuse every checkpoint, and the cold pass compute every one.
    checks["warm_reused_cold_computed"] = {p["checkpoint"] for p in warm.values()} == {
        "reused"
    } and {p["checkpoint"] for p in cold.values()} == {"computed"}
    checks["late_revision_drill"] = revision["passed"] and revision["artifacts_unchanged"]
    results = {
        "code_commit": head,
        "working_tree_clean": clean,
        "workload": {k: [d.isoformat() for d in v] for k, v in plan.items()},
        "origins": len(origins),
        "load_seconds": load_seconds,
        "refresh_seconds": {k: stats(v) for k, v in seconds.items()},
        "checkpoint_states": {
            name: sorted({p["checkpoint"] for p in run.values()})
            for name, run in (("cold", cold), ("warm", warm))
        },
        "checkpoint_mean_mb": mean_mb,
        "checkpoints_retained_in_run": len(checkpoint_files),
        "mismatched_origins": mismatched,
        "daily_job": job,
        "late_revision_drill": revision,
        "peak_rss_gib_capacity_process": peak,
        "budget": BUDGET,
        "measured": measured,
        "checks": checks,
        "supported_cadence": "daily" if all(checks.values()) else "not supported within budget",
    }
    (args.out / "results.json").write_text(json.dumps(results, indent=2, default=str) + "\n")
    print(
        json.dumps({k: results[k] for k in ("measured", "checks", "supported_cadence")}, indent=2)
    )


if __name__ == "__main__":
    main()
