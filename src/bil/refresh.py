"""Replayable origin refresh with cutoff enforcement and atomic publication (#142).

One origin `D` produces one Expected Impact snapshot under the #36 configuration, as a #135
as-of rating artifact. The refresh is replay-only on pinned 2023–25 inputs: no live capture and no
2025–26 date.

- **Cutoff.** The snapshot reads only possessions and box lines dated strictly before `D`, which
  `expected_impact.prepare` enforces.
- **Identity.** The artifact ID is a content hash of the origin, the input digests, the parent
  fit and selection IDs, and the configuration. The code commit is recorded but is not part of
  the identity.
- **Idempotence.** If `ROOT/D/<id>` exists and its manifest names the same ID, the refresh is a
  no-op and nothing is fitted or rewritten. Changed inputs give a new ID in a new directory.
- **Atomicity.** The artifact is written into a staging directory inside `ROOT` and renamed into
  place. A run interrupted by an exception removes its staging directory. A killed process or
  power loss can leave a dot-prefixed staging directory, which is never read as an artifact.
  Files are fsynced before the rename.
- **Code changes.** The identity covers ``VERSION``, not the model code. A code change that
  changes outputs must bump ``VERSION``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

import numpy as np

from bil.data.pilot_sources import sha256_file
from bil.features.box import Appearance, snapshot_instant
from bil.features.box_build import PLAYER_LOG, TEAM_LOG
from bil.models.expected_impact import (
    SPM_MANIFEST,
    SPM_RUN,
    SpmFit,
    as_of_ratings,
    fit_informed,
    prepare,
    spm_fit,
    write_ratings,
)
from bil.models.expected_impact_outer import (
    ADDENDUM,
    FINAL_CUTOFF,
    OUTER_SEASONS,
    ROW_SEASONS,
    outer_logs,
    parse_config,
)
from bil.models.rapm.multiseason import (
    SEASON_PINS,
    TEMPORAL_BY_NAME,
    Analysis,
    Scenario,
    _git_head,
    _prepare,
    season_blocks,
)
from bil.models.spm_build import checked_file, read_json
from bil.refresh_sources import (
    Capture,
    Mode,
    Resolution,
    box_capture,
    possession_captures,
    resolve,
)

VERSION = "origin-refresh-issue-143-v2"
MANIFEST = "manifest.json"
RATINGS = "ratings.csv"
SOURCES = "sources.json"
FROZEN_TOLERANCE = 1e-6


class RefreshError(ValueError):
    """An origin cannot be refreshed or an existing artifact is inconsistent."""


@dataclass(frozen=True)
class Inputs:
    """Everything one origin refresh reads, already verified against its pins."""

    analysis: Analysis
    spm: SpmFit
    logs: Mapping[int, Sequence[Appearance]]
    config: Mapping[str, Any]  # window and penalties
    input_ids: Mapping[str, Any]  # digests of row sets, box logs, SPM fit, configuration source
    parents: Mapping[str, str]  # parent fit and selection IDs
    seasons: tuple[int, ...] = OUTER_SEASONS  # replay scope
    captures: tuple[Capture, ...] = ()  # per-game source captures; derived from the inputs if empty
    mode: Mode = "retrospective"  # pinned replay snapshots carry only post-season capture times


@dataclass(frozen=True)
class Published:
    path: Path
    artifact_id: str
    created: bool


def season_of(origin: date) -> int:
    return origin.year if origin.month >= 8 else origin.year - 1


def artifact_id(
    origin: date,
    input_ids: Mapping[str, Any],
    parents: Mapping[str, str],
    config: Mapping[str, Any],
) -> str:
    body = {
        "version": VERSION,
        "origin": origin.isoformat(),
        "inputs": input_ids,
        "parents": parents,
        "config": config,
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def check_origin(origin: date, seasons: Sequence[int] = OUTER_SEASONS) -> int:
    """Replay scope: an origin inside a pinned replay season and before the holdout."""
    season = season_of(origin)
    if origin >= FINAL_CUTOFF or season not in seasons:
        raise RefreshError(f"origin {origin} is outside the replay seasons {list(seasons)}")
    return season


def existing(root: Path, origin: date, aid: str) -> Path | None:
    target = root / origin.isoformat() / aid
    if not target.exists():
        return None
    manifest = target / MANIFEST
    if not manifest.is_file():
        raise RefreshError(f"{target} exists without a manifest")
    try:
        record = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RefreshError(f"{target} has an unreadable manifest") from error
    if not isinstance(record, dict) or not isinstance(record.get("outputs"), dict):
        raise RefreshError(f"{target} has a malformed manifest")
    if record.get("artifact_id") != aid or record.get("origin") != origin.isoformat():
        raise RefreshError(f"{target} holds a different artifact")
    ratings = target / RATINGS
    if not ratings.is_file() or sha256_file(ratings) != record["outputs"].get(RATINGS):
        raise RefreshError(f"{target} ratings do not match their manifest")
    return target


def publish(
    root: Path, origin: date, aid: str, write: Callable[[Path], Mapping[str, Any]]
) -> Published:
    """Run ``write`` into a staging directory and rename it into place, unless already there."""
    found = existing(root, origin, aid)
    if found is not None:
        return Published(found, aid, False)
    parent = root / origin.isoformat()
    parent.mkdir(parents=True, exist_ok=True)
    stage = Path(mkdtemp(prefix=f".{aid[:12]}.staging-", dir=parent))
    try:
        extra = dict(write(stage))
        outputs = {p.name: sha256_file(p) for p in sorted(stage.iterdir()) if p.is_file()}
        manifest = {
            "schema_version": 1,
            "version": VERSION,
            "artifact_id": aid,
            "origin": origin.isoformat(),
            **extra,
            "outputs": outputs,
        }
        (stage / MANIFEST).write_text(
            json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )
        _fsync(stage)
        target = parent / aid
        try:
            os.rename(stage, target)
        except OSError:
            # Another run published the same ID first. Accept it only if it is consistent.
            if existing(root, origin, aid) is None:
                raise
            return Published(target, aid, False)
        _fsync_dir(parent)
        return Published(target, aid, True)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _fsync(directory: Path) -> None:
    for path in directory.iterdir():
        if path.is_file():
            with path.open("rb") as handle:
                os.fsync(handle.fileno())
    _fsync_dir(directory)


def _fsync_dir(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def replay_captures(
    inputs: Inputs, retrieved: Mapping[str, Any] | None = None
) -> tuple[Capture, ...]:
    """One capture per pinned box-log snapshot and per pinned possession row-set season."""
    retrieved = retrieved or {}
    boxes = [
        box_capture(
            f"box_logs/{season}",
            inputs.input_ids["box_logs"].get(str(season), "unpinned"),
            retrieved.get(str(season)),
            logs,
        )
        for season, logs in sorted(inputs.logs.items())
    ]
    rows = possession_captures(inputs.analysis.rows, inputs.input_ids["rows"])
    return (*boxes, *rows)


def resolution_for(origin: date, inputs: Inputs) -> Resolution:
    """The per-game source revisions this origin reads (#143)."""
    if inputs.mode != "retrospective":
        raise RefreshError(
            "the replay refresh reads one pinned capture per source; strict resolution needs the "
            "live captures that the rest of #43 adds"
        )
    return resolve(inputs.captures or replay_captures(inputs), origin, inputs.mode)


def refresh_origin(root: Path, origin: date, inputs: Inputs) -> Published:
    """Build and publish the snapshot for ``origin``; a no-op when it already exists."""
    season = check_origin(origin, inputs.seasons)
    resolution = resolution_for(origin, inputs)
    input_ids = {**inputs.input_ids, "source_resolution": resolution.digest()}
    aid = artifact_id(origin, input_ids, inputs.parents, inputs.config)
    if existing(root, origin, aid) is not None:
        return Published(root / origin.isoformat() / aid, aid, False)

    def write(stage: Path) -> Mapping[str, Any]:
        analysis = inputs.analysis
        prepared = prepare(
            analysis, origin, inputs.spm, inputs.logs[season - 1], inputs.logs[season]
        )
        offense, defense = inputs.config["offense_ridge"], inputs.config["defense_ridge"]
        fit = fit_informed(analysis, prepared, offense, defense, f"refresh:{origin}")
        snap = as_of_ratings(
            prepared,
            fit,
            analysis.design,
            {**inputs.config, "cutoff": origin, "spm": inputs.spm.fit_id},
        )
        write_ratings(stage / RATINGS, [snap])
        (stage / SOURCES).write_text(
            json.dumps(resolution.record(), sort_keys=True) + "\n", encoding="utf-8"
        )
        head, clean = _git_head()
        return {
            "inputs": input_ids,
            "source_resolution": resolution.summary(),
            "parents": inputs.parents,
            "config": inputs.config,
            "snapshot_id": snap.snapshot_id,
            "coverage": snap.coverage,
            "eligibility": prepared.audit,
            "code_commit": head,
            "working_tree_clean": clean,
        }

    return publish(root, origin, aid, write)


# --- pinned replay inputs --------------------------------------------------------------


def load_inputs(raw: Path, processed: Path, scratch: Path) -> Inputs:
    """The #36 configuration, locked SPM fit, outer row sets and pinned box logs."""
    config = parse_config(ADDENDUM.read_text(encoding="utf-8"))
    ei = config["models"]["ei"]
    if ei["window"] != "W2" or TEMPORAL_BY_NAME[ei["window"]].name != "W2":
        raise RefreshError("the #36 EI window is not W2")
    spm_dir = processed / "spm" / SPM_RUN
    checked_file(spm_dir / "manifest.json", SPM_MANIFEST)
    spm = spm_fit(read_json(checked_file(spm_dir / config["spm_fit"], config["spm_fit_sha256"])))
    logs, log_ids, retrieved = {}, {}, {}
    for key, pin in config["box_logs"].items():
        logs[int(key)], _ = outer_logs(raw, int(key), pin)
        log_ids[key] = pin["sha256"]
        snapshot = raw / SEASON_PINS[int(key)].label / pin["snapshot"] / "snapshot.json"
        assets = read_json(checked_file(snapshot, pin["sha256"]))["artifacts"]
        retrieved[key] = max(
            snapshot_instant(a["retrieved_at"])
            for a in assets
            if a["name"] in (PLAYER_LOG, TEAM_LOG)
        )
    _, rows, design, row_inputs = _prepare(processed, ROW_SEASONS, ROW_SEASONS, scratch)
    analysis = Analysis(rows, design, Scenario("primary", np.ones(len(rows), dtype=bool)), [], [])
    row_ids = {
        label: entry["row_manifest_sha256"]
        for label, entry in row_inputs.items()
        if not label.startswith("_")
    }
    inputs = Inputs(
        analysis,
        spm,
        logs,
        {
            "window": ei["window"],
            "offense_ridge": ei["offense_ridge"],
            "defense_ridge": ei["defense_ridge"],
        },
        {
            "rows": row_ids,
            "box_logs": log_ids,
            "spm_fit_sha256": config["spm_fit_sha256"],
            "addendum_sha256": sha256_file(ADDENDUM),
        },
        {"spm": spm.fit_id, "penalty_selection": "issue-35-v1 W2 8000/8000"},
    )
    return replace(inputs, captures=replay_captures(inputs, retrieved))


Pair = tuple[float, float]


def compare_ratings(
    ours: Mapping[int, Pair], theirs: Mapping[int, Pair], cold: Pair | None
) -> dict[str, Any]:
    """Compare a refreshed v2 roster with a published legacy (#36) export of the same cutoff.

    The legacy export lists every globally indexed player. The v2 roster keeps only players
    eligible at the cutoff, and every other indexed player scores at the explicit ``cold`` prior
    (#135). So each refreshed player must match its published value, no refreshed player may be
    missing from the export, and each published player off the roster must equal the cold prior.
    """
    common = sorted(set(ours) & set(theirs))
    dropped = sorted(set(theirs) - set(ours))
    gaps = [abs(a - b) for p in common for a, b in zip(ours[p], theirs[p], strict=True)]
    cold_gaps = [
        abs(a - b)
        for p in dropped
        for a, b in zip(theirs[p], cold or (float("inf"),) * 2, strict=True)
    ]
    report: dict[str, Any] = {
        "players": len(ours),
        "missing_from_published": len(set(ours) - set(theirs)),
        "off_roster_at_cold_prior": len(dropped),
        "max_abs_rating_gap": max(gaps, default=float("inf")),
        "max_abs_cold_gap": max(cold_gaps, default=0.0),
        "non_finite": sum(not math.isfinite(g) for g in gaps + cold_gaps),
    }
    # Python's max skips a NaN that is not first, so every gap is checked, not only the max.
    report["reproduced"] = (
        bool(common)
        and report["missing_from_published"] == 0
        and all(g <= FROZEN_TOLERANCE for g in gaps + cold_gaps)
    )
    return report


def verify_frozen(root: Path, processed: Path, inputs: Inputs) -> dict[str, Any]:
    """Refresh at the #36 block cutoffs and compare with the published `issue-36-v1` ratings."""
    directory = processed / "expected_impact" / "issue-36-v1"
    manifest = read_json(directory / "manifest.json")
    path = checked_file(directory / RATINGS, manifest["outputs"][RATINGS])
    published: dict[str, dict[int, tuple[float, float]]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            published.setdefault(row["as_of"], {})[int(row["player_id"])] = (
                float(row["rating_offense"]),
                float(row["rating_defense"]),
            )
    report: dict[str, Any] = {}
    rows = inputs.analysis.rows
    for season in OUTER_SEASONS:
        for block in season_blocks(rows, season):
            done = refresh_origin(root, block.cutoff, inputs)
            with (done.path / RATINGS).open(newline="", encoding="utf-8") as handle:
                records = list(csv.DictReader(handle))
            ours = {
                int(r["player_id"]): (float(r["rating_offense"]), float(r["rating_defense"]))
                for r in records
            }
            colds = {(float(r["cold_offense"]), float(r["cold_defense"])) for r in records}
            if len(colds) != 1:
                raise RefreshError(f"{done.path} does not carry one cold prior")
            theirs = published.get(block.cutoff.isoformat(), {})
            report[block.cutoff.isoformat()] = {
                "artifact_id": done.artifact_id,
                **compare_ratings(ours, theirs, colds.pop()),
            }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "verify-frozen"):
        p = sub.add_parser(name)
        p.add_argument("raw", type=Path)
        p.add_argument("processed", type=Path)
        p.add_argument("root", type=Path)
        if name == "build":
            p.add_argument("--origin", type=date.fromisoformat, required=True, action="append")
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    scratch = Path(mkdtemp(prefix=".inputs-", dir=args.root))
    try:
        inputs = load_inputs(args.raw, args.processed, scratch)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    if args.command == "build":
        for origin in args.origin:
            done = refresh_origin(args.root, origin, inputs)
            print(
                json.dumps(
                    {
                        "origin": origin.isoformat(),
                        "artifact_id": done.artifact_id,
                        "created": done.created,
                        "path": str(done.path),
                    }
                )
            )
    else:
        report = verify_frozen(args.root, args.processed, inputs)
        print(json.dumps(report, indent=2))
        failed = sorted(cutoff for cutoff, entry in report.items() if not entry["reproduced"])
        if failed or not report:
            raise SystemExit(f"frozen rebuild did not reproduce issue-36-v1 at {failed}")


if __name__ == "__main__":
    main()
