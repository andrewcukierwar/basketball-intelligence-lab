"""Chronological lineage for margin-calibration examples (#136).

The #39 margin calibrator was fit on 2021–23 games scored with #35 snapshots whose penalties were
selected on those same seasons, so a later outcome could change an earlier calibration example.
This module implements the registered post-freeze construction in
``docs/research/calibration-lineage-protocol.md``. Each example records its parent fit and
selection and the date through which that selection read outcomes. The calibration may use an
example only when the selection froze before the example's snapshot, the snapshot precedes the
game, and the game is final before the calibration's fit cutoff. ``load_calibration`` re-checks
every example against the registered parents, so a late-selected parent is refused at the
consumer boundary.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray

from bil.data.pilot_sources import sha256_file
from bil.features.box_build import TEAM_LOG
from bil.models.expected_impact_outer import ADDENDUM, parse_config
from bil.models.rapm.multiseason import REPO_ROOT, SEASON_PINS, _git_head, _versions, _write_json
from bil.models.rapm.targets import verify_protocol
from bil.models.spm_build import checked_file, read_json
from bil.models.team_outcomes import (
    RATING_RUNS,
    Game,
    fit_calibration,
    metrics,
    normal_cdf,
    paired,
    team_games,
)

FloatArray = NDArray[np.float64]
VERSION = "issue-136-v1"
PROTOCOL = REPO_ROOT / "docs/research/calibration-lineage-protocol.md"
CONSTRUCTION = "post_freeze"
TEAM_RUN = "issue-39-v1"
TEAM_MANIFEST = "8486bf8c42a30c708b12717c4955617d43aef044c4cf0cbc5b6da5fa8b1b1cee"
SOURCES = ("ei", "team_rating")


class LineageError(ValueError):
    """A calibration example or artifact fails the chronological lineage contract."""


@dataclass(frozen=True)
class Parent:
    """A fitted, selected model whose outputs feed calibration examples."""

    parent_id: str
    run: str
    manifest_sha256: str
    selection_id: str
    # Latest outcome date any fit or selection of this parent read. Inclusive.
    outcomes_through: date


# Registered parents (protocol §2). #35 read rows and box lines from seasons ending in June 2023
# and selected its penalties on 2021–23 blocks; #36 reuses those penalties with the final SPM fit
# (origin 2023-06-13). #39 chose the team-rating grid on 2021–23 regular-season margins.
PARENTS = {
    parent.parent_id: parent
    for parent in (
        Parent(
            "ei:issue-36-v1",
            "issue-36-v1",
            RATING_RUNS["issue-36-v1"],
            "issue-35-v1:W2:offense=8000:defense=8000",
            date(2023, 6, 30),
        ),
        Parent(
            "ei:issue-35-v1",
            "issue-35-v1",
            RATING_RUNS["issue-35-v1"],
            "issue-35-v1:W2:offense=8000:defense=8000",
            date(2023, 6, 30),
        ),
        Parent(
            "team_rating:issue-39-v1",
            TEAM_RUN,
            TEAM_MANIFEST,
            "issue-39-v1:half_life=60:ridge=4",
            date(2023, 6, 30),
        ),
    )
}


@dataclass(frozen=True)
class Example:
    """One game's raw model input and realized margin, with its lineage."""

    source: str  # "ei" or "team_rating"
    game_id: str
    game_day: date
    raw: float
    margin: float
    parent_id: str
    snapshot_as_of: date  # the rating snapshot or team fit date used for this game
    snapshot_id: str
    source_view: str  # digest of the file the raw input was read from


def check_example(example: Example, parents: Mapping[str, Parent], fit_cutoff: date) -> None:
    """Refuse an example whose parent, snapshot or label is not eligible at ``fit_cutoff``."""
    parent = parents.get(example.parent_id)
    where = f"{example.source} {example.game_id}"
    if parent is None:
        raise LineageError(f"{where}: parent {example.parent_id} is not registered")
    if not example.parent_id.startswith(f"{example.source}:"):
        raise LineageError(f"{where}: parent {example.parent_id} is not a {example.source} parent")
    if not parent.outcomes_through < example.snapshot_as_of:
        raise LineageError(
            f"{where}: parent {parent.parent_id} read outcomes through "
            f"{parent.outcomes_through}, not before its snapshot {example.snapshot_as_of}"
        )
    if not example.snapshot_as_of <= example.game_day:
        raise LineageError(f"{where}: snapshot {example.snapshot_as_of} follows the game")
    if not example.game_day < fit_cutoff:
        raise LineageError(f"{where}: label on {example.game_day} is not final by {fit_cutoff}")


def examples_digest(examples: Iterable[Example]) -> str:
    """Content hash of examples, independent of input order."""
    records = sorted(
        json.dumps(asdict(example), sort_keys=True, default=str) for example in examples
    )
    return hashlib.sha256("\n".join(records).encode()).hexdigest()


def fit_post_freeze(
    examples: Sequence[Example], parents: Mapping[str, Parent], fit_cutoff: date
) -> dict[str, Any]:
    """Fit each source's margin calibration on the examples final before ``fit_cutoff``.

    Examples on or after the cutoff are dropped before anything is computed, so later outcomes
    cannot change the fit or its digest. Every kept example must pass ``check_example``.
    """
    # Sorted, so the fit does not depend on input order even in floating point.
    kept = sorted(
        (e for e in examples if e.game_day < fit_cutoff),
        key=lambda e: (e.source, e.game_day, e.game_id),
    )
    for example in kept:
        check_example(example, parents, fit_cutoff)
    out: dict[str, Any] = {
        "version": VERSION,
        "construction": CONSTRUCTION,
        "fit_cutoff": fit_cutoff.isoformat(),
        "examples_sha256": examples_digest(kept),
        "parents": {pid: asdict(parents[pid]) for pid in sorted({e.parent_id for e in kept})},
        "sources": {},
    }
    for source in SOURCES:
        chosen = [e for e in kept if e.source == source]
        if not chosen:
            raise LineageError(f"no eligible {source} examples before {fit_cutoff}")
        raw = np.asarray([e.raw for e in chosen])
        margin = np.asarray([e.margin for e in chosen])
        out["sources"][source] = {
            **fit_calibration(raw, margin),
            "examples": len(chosen),
            "first_game": min(e.game_day for e in chosen).isoformat(),
            "last_game": max(e.game_day for e in chosen).isoformat(),
        }
    margins = {e.game_id: e.margin for e in kept}
    values = np.asarray(list(margins.values()))
    out["sources"]["hca"] = {
        "a": float(values.mean()),
        "b": 0.0,
        "sigma": float(values.std()),
        "examples": len(values),
    }
    return cast(dict[str, Any], json.loads(json.dumps(out, default=str)))


def write_examples(path: Path, examples: Iterable[Example]) -> None:
    rows = sorted(examples, key=lambda e: (e.source, e.game_day, e.game_id))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(list(Example.__dataclass_fields__))
        for e in rows:
            writer.writerow([*(str(v) for v in asdict(e).values())])


def read_examples(path: Path) -> list[Example]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            Example(
                row["source"],
                row["game_id"],
                date.fromisoformat(row["game_day"]),
                float(row["raw"]),
                float(row["margin"]),
                row["parent_id"],
                date.fromisoformat(row["snapshot_as_of"]),
                row["snapshot_id"],
                row["source_view"],
            )
            for row in csv.DictReader(handle)
        ]


def load_calibration(
    directory: Path, origin: date, parents: Mapping[str, Parent] = PARENTS
) -> dict[str, Any]:
    """Load a calibration for forecasts made at ``origin``, re-checking its whole lineage.

    The recorded parents must equal the registered ones, every example must pass
    ``check_example`` at the recorded cutoff, the examples must hash to the recorded digest and
    refit to the recorded coefficients, and the cutoff must not follow ``origin``.
    """
    artifact = cast(dict[str, Any], read_json(directory / "calibration.json"))
    if artifact.get("construction") != CONSTRUCTION:
        raise LineageError("calibration was not built with the registered construction")
    cutoff = date.fromisoformat(artifact["fit_cutoff"])
    if cutoff > origin:
        raise LineageError(f"calibration fit cutoff {cutoff} follows the origin {origin}")
    for pid, recorded in artifact["parents"].items():
        registered = parents.get(pid)
        if registered is None or recorded != json.loads(
            json.dumps(asdict(registered), default=str)
        ):
            raise LineageError(f"parent {pid} differs from its registration")
    examples = read_examples(directory / "examples.csv")
    late = [e for e in examples if e.game_day >= cutoff]
    if late:
        raise LineageError(f"{len(late)} examples are not final by the fit cutoff {cutoff}")
    refit = fit_post_freeze(examples, parents, cutoff)
    if refit["examples_sha256"] != artifact["examples_sha256"]:
        raise LineageError("examples differ from the recorded digest")
    if refit["parents"] != artifact["parents"]:
        raise LineageError("recorded parents differ from the parents its examples cite")
    if not _same(refit["sources"], artifact["sources"]):
        raise LineageError("examples do not reproduce the recorded coefficients")
    return artifact


def _same(left: Any, right: Any, tol: float = 1e-9) -> bool:
    """Structural equality with a relative tolerance on floats (refits differ in the last bit)."""
    if isinstance(left, dict) and isinstance(right, dict):
        return bool(left.keys() == right.keys()) and all(
            _same(left[k], right[k], tol) for k in left
        )
    if isinstance(left, float) or isinstance(right, float):
        if not isinstance(left, int | float) or not isinstance(right, int | float):
            return False
        return math.isclose(left, right, rel_tol=tol, abs_tol=tol)
    return bool(left == right)


# --- development comparison runner (protocol §5) ---------------------------------------


def _predict(calib: Mapping[str, float], raw: FloatArray) -> tuple[FloatArray, FloatArray]:
    margin = calib["a"] + calib["b"] * raw
    return margin, normal_cdf(margin / calib["sigma"])


def development_examples(
    raw_dir: Path, processed: Path
) -> tuple[list[Example], dict[str, Game], dict[str, Any], dict[str, Any]]:
    """Examples for 2023–24 and 2024–25 from the frozen #39 predictions.

    #39 wrote each model's calibrated margin ``a + b * raw`` to six decimals, so the raw input
    is recovered by inverting its frozen calibration. The recovery error is below 1e-5.
    """
    directory = processed / "team_outcomes" / TEAM_RUN
    manifest = read_json(checked_file(directory / "manifest.json", TEAM_MANIFEST))
    results = read_json(
        checked_file(directory / "results.json", manifest["outputs"]["results.json"])
    )
    path = checked_file(directory / "predictions.csv", manifest["outputs"]["predictions.csv"])
    view = sha256_file(path)
    frozen = results["calibration"]
    addendum = parse_config(ADDENDUM.read_text(encoding="utf-8"))
    games: dict[str, Game] = {}
    logs: dict[str, Any] = {}
    for season in (2023, 2024):
        pin = addendum["box_logs"][str(season)]
        season_dir = raw_dir / SEASON_PINS[season].label / pin["snapshot"]
        logs[str(season)] = {
            "snapshot": pin["snapshot"],
            "team_log": sha256_file(season_dir / TEAM_LOG),
        }
        for game in team_games(season_dir, season)[0]:
            games[game.game_id] = game
    examples: list[Example] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            found = games.get(row["game_id"])
            if found is None or row["playoff"] != "False" or found.margin is None:
                continue
            day = date.fromisoformat(row["date"])
            for source, parent_id, as_of, snapshot_id in (
                ("ei", "ei:issue-36-v1", row["as_of"], row["snapshot_id"]),
                # The team rating is refit on each game day from earlier games only.
                ("team_rating", "team_rating:issue-39-v1", row["date"], "daily-ridge"),
            ):
                c = frozen[source]
                examples.append(
                    Example(
                        source,
                        row["game_id"],
                        day,
                        round((float(row[f"{source}_margin"]) - c["a"]) / c["b"], 6),
                        float(found.margin),
                        parent_id,
                        date.fromisoformat(as_of),
                        snapshot_id,
                        view,
                    )
                )
    return examples, games, frozen, {"team_outcomes": TEAM_MANIFEST, "box_logs": logs}


def compare(
    examples: Sequence[Example],
    calibrations: Mapping[str, Mapping[str, Mapping[str, float]]],
    scored_season: tuple[date, date],
) -> dict[str, Any]:
    """Score one season's regular-season games under each calibration (protocol §5)."""
    start, end = scored_season
    by_source = {
        s: sorted(
            (e for e in examples if e.source == s and start <= e.game_day < end),
            key=lambda e: e.game_id,
        )
        for s in SOURCES
    }
    ids = [e.game_id for e in by_source["ei"]]
    if ids != [e.game_id for e in by_source["team_rating"]]:
        raise ValueError("EI and team-rating examples cover different games")
    margin = np.asarray([e.margin for e in by_source["ei"]])
    days = [e.game_day for e in by_source["ei"]]
    clusters = {
        "game": np.arange(len(ids), dtype=np.int64),
        "week": np.asarray([(d.toordinal() - 1) // 7 for d in days], dtype=np.int64),
    }
    out: dict[str, Any] = {"games": len(ids)}
    predictions: dict[str, dict[str, tuple[FloatArray, FloatArray]]] = {}
    for name, calib in calibrations.items():
        predictions[name] = {
            s: _predict(calib[s], np.asarray([e.raw for e in by_source[s]])) for s in SOURCES
        }
        out[name] = {
            "metrics": {s: metrics(margin, *predictions[name][s]) for s in SOURCES},
            "ei_minus_team_rating": paired(
                margin, predictions[name]["ei"], predictions[name]["team_rating"], clusters
            ),
        }
    names = list(calibrations)
    if len(names) == 2:
        first, second = names
        out[f"{second}_minus_{first}"] = {
            s: paired(margin, predictions[second][s], predictions[first][s], clusters)
            for s in SOURCES
        }
    return out


def run(raw: Path, processed: Path, output: Path, protocol_sha256: str) -> dict[str, Any]:
    started = time.perf_counter()
    protocol = verify_protocol(PROTOCOL, protocol_sha256)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite a run: {output}")
    examples, _, frozen, inputs = development_examples(raw, processed)
    # §3: the #39 calibration's own examples (2021–23, #35 snapshots) fail the lineage check.
    refused = []
    try:
        check_example(
            Example(
                "ei",
                "probe",
                date(2022, 1, 1),
                0.0,
                0.0,
                "ei:issue-35-v1",
                date(2021, 12, 1),
                "probe",
                "probe",
            ),
            PARENTS,
            date(2023, 7, 1),
        )
    except LineageError as exc:
        refused.append(str(exc))
    fit_cutoff = date(2024, 7, 1)
    staged = output.parent / f".{output.name}.staging"
    if staged.exists():  # left by an interrupted run; the output itself is never overwritten
        shutil.rmtree(staged)
    staged.mkdir(parents=True)
    eligible = [e for e in examples if e.game_day < fit_cutoff]
    write_examples(staged / "examples.csv", eligible)
    calibration = fit_post_freeze(examples, PARENTS, fit_cutoff)
    _write_json(staged / "calibration.json", calibration)
    loaded = load_calibration(staged, date(2024, 10, 1))
    frozen_calib = {s: frozen[s] for s in ("ei", "team_rating", "hca")}
    results = {
        "construction": CONSTRUCTION,
        "fit_cutoff": fit_cutoff.isoformat(),
        "support": {s: loaded["sources"][s]["examples"] for s in (*SOURCES, "hca")},
        "frozen_39_calibration": frozen_calib,
        "post_freeze_calibration": {s: loaded["sources"][s] for s in (*SOURCES, "hca")},
        "frozen_39_examples_refused": refused,
        "scored_2024_25_regular": compare(
            examples,
            {"frozen_39": frozen_calib, "post_freeze": loaded["sources"]},
            (date(2024, 10, 1), date(2025, 7, 1)),
        ),
        "evidence": "development comparison on previously examined 2023–25 seasons",
    }
    _write_json(staged / "results.json", results)
    head, clean = _git_head()
    manifest = {
        "schema_version": 1,
        "version": VERSION,
        "protocol": protocol,
        "code_commit": head,
        "working_tree_clean_at_end": clean,
        "inputs": inputs,
        "versions": _versions(),
        "runtime_seconds": time.perf_counter() - started,
        "outputs": {p.name: sha256_file(p) for p in sorted(staged.iterdir()) if p.is_file()},
        "private_outputs": ["examples.csv"],
    }
    _write_json(staged / "manifest.json", manifest)
    staged.rename(output)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("processed", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--protocol-sha256", required=True)
    args = parser.parse_args()
    manifest = run(
        args.raw.resolve(), args.processed.resolve(), args.output.resolve(), args.protocol_sha256
    )
    print(json.dumps({"outputs": manifest["outputs"]}))


if __name__ == "__main__":
    main()
