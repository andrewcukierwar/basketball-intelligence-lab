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
  place. An interrupted run leaves no artifact, only a dot-prefixed staging directory that is
  removed on exit and never read as an artifact.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

import numpy as np

from bil.data.pilot_sources import sha256_file
from bil.features.box import Appearance
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
    TEMPORAL_BY_NAME,
    Analysis,
    Scenario,
    _git_head,
    _prepare,
    season_blocks,
)
from bil.models.spm_build import checked_file, read_json

VERSION = "origin-refresh-issue-142-v1"
MANIFEST = "manifest.json"
RATINGS = "ratings.csv"


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
    record = json.loads(manifest.read_text(encoding="utf-8"))
    if record.get("artifact_id") != aid or record.get("origin") != origin.isoformat():
        raise RefreshError(f"{target} holds a different artifact")
    ratings = target / RATINGS
    if not ratings.is_file() or sha256_file(ratings) != record["outputs"][RATINGS]:
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
        target = parent / aid
        try:
            os.rename(stage, target)
        except OSError:
            # Another run published the same ID first. Accept it only if it is consistent.
            if existing(root, origin, aid) is None:
                raise
            return Published(target, aid, False)
        return Published(target, aid, True)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def refresh_origin(root: Path, origin: date, inputs: Inputs) -> Published:
    """Build and publish the snapshot for ``origin``; a no-op when it already exists."""
    season = check_origin(origin, inputs.seasons)
    aid = artifact_id(origin, inputs.input_ids, inputs.parents, inputs.config)
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
        head, clean = _git_head()
        return {
            "inputs": inputs.input_ids,
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
    logs, log_ids = {}, {}
    for key, pin in config["box_logs"].items():
        logs[int(key)], _ = outer_logs(raw, int(key), pin)
        log_ids[key] = pin["sha256"]
    _, rows, design, row_inputs = _prepare(processed, ROW_SEASONS, ROW_SEASONS, scratch)
    analysis = Analysis(rows, design, Scenario("primary", np.ones(len(rows), dtype=bool)), [], [])
    row_ids = {
        label: entry["row_manifest_sha256"]
        for label, entry in row_inputs.items()
        if not label.startswith("_")
    }
    return Inputs(
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
                ours = {
                    int(r["player_id"]): (float(r["rating_offense"]), float(r["rating_defense"]))
                    for r in csv.DictReader(handle)
                }
            theirs = published[block.cutoff.isoformat()]
            missing = sorted(set(ours) - set(theirs))
            gap = max(abs(a - b) for p in ours for a, b in zip(ours[p], theirs[p], strict=True))
            report[block.cutoff.isoformat()] = {
                "artifact_id": done.artifact_id,
                "players": len(ours),
                "missing_from_published": len(missing),
                "max_abs_rating_gap": gap,
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
        print(json.dumps(verify_frozen(args.root, args.processed, inputs), indent=2))


if __name__ == "__main__":
    main()
