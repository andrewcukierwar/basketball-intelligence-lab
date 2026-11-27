"""Game-held-out retrospective test of preseason anchors and playoff emphasis (#41)."""

from __future__ import annotations

import argparse
import time
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import numpy as np
from numpy.typing import NDArray

from bil.data.pilot_sources import sha256_file
from bil.models.expected_impact import as_of_ratings, fit_informed, prepare
from bil.models.expected_impact_outer import ADDENDUM, OUTER_SEASONS
from bil.models.rapm.multiseason import (
    REPO_ROOT,
    Design,
    Rows,
    _git_head,
    _versions,
    _write_json,
    fit_context,
    paired_delta,
    week_clusters,
)
from bil.models.rapm.targets import fit_joint, game_folds, verify_protocol
from bil.models.spm_build import checked_file
from bil.refresh import Inputs, check_parents, load_inputs

VERSION = "issue-41-v1"
PROTOCOL = REPO_ROOT / "docs/research/actual-impact-protocol.md"
OUTER_ADDENDUM_PIN = "1076ab0bcfd022f39b68e99eaf9398ce7bec6d99985933821bf8f8bd68762d7c"
FOLDS = 5
RIDGE = 8000.0
Values = NDArray[np.float64]
Indices = NDArray[np.int64]


def preseason(inputs: Inputs, season: int, output: Path) -> tuple[Values, dict[str, Any]]:
    cutoff = date(season, 10, 1)
    check_parents(cutoff, inputs)
    analysis = inputs.analysis
    if not cutoff.toordinal() < np.min(analysis.rows.day[analysis.rows.season == season]):
        raise ValueError(f"preseason anchor follows the first eligible game of {season}")
    p = prepare(analysis, cutoff, inputs.spm, inputs.logs[season - 1], inputs.logs[season])
    fit = fit_informed(
        analysis,
        p,
        inputs.config["offense_ridge"],
        inputs.config["defense_ridge"],
        f"anchor:{season}",
    )
    if fit.info["stop"] not in {0, 1, 2, 4, 5}:
        raise ValueError(f"preseason anchor failed to converge for {season}")
    snap = as_of_ratings(
        p, fit, analysis.design, {**inputs.config, "cutoff": cutoff, "spm": inputs.spm.fit_id}
    )
    if snap.cold is None:
        raise ValueError("expected an as-of preseason anchor with an explicit cold prior")
    if not np.isfinite(snap.rating).all() or not np.isfinite(snap.cold).all():
        raise ValueError(f"preseason anchor supplied nonfinite rates for {season}")
    path = output / f"anchor_{season}.npz"
    np.savez_compressed(path, player_id=snap.player_ids, rates=snap.rating, cold=snap.cold)
    ids = np.asarray(analysis.design.player_ids, dtype=np.int64)
    positions = np.searchsorted(snap.player_ids, ids)
    known = np.append(snap.player_ids, 0)[positions] == ids
    by_player = np.tile(snap.cold, (ids.size, 1))
    by_player[known] = snap.rating[positions[known]]
    return np.concatenate((by_player[:, 0], by_player[:, 1])), {
        "cutoff": cutoff.isoformat(),
        "snapshot_id": snap.snapshot_id,
        "parents": inputs.parents,
        "coverage": snap.coverage,
        "eligibility": p.audit,
        "sha256": sha256_file(path),
    }


def heldout_predictions(
    rows: Rows, design: Design, season: int, anchor: Values
) -> tuple[Indices, dict[str, Values], list[dict[str, Any]]]:
    index = np.flatnonzero(rows.season == season)
    if not index.size or anchor.shape != (2 * design.size,) or not np.isfinite(anchor).all():
        raise ValueError("season rows and finite preseason player effects are required")
    fold = game_folds(rows.game_ids, FOLDS, VERSION)[rows.game[index]]
    level = np.column_stack((rows.context, rows.playoff))
    anchor_offset = np.asarray(design.players @ anchor, dtype=np.float64)
    candidates = {
        "season_only": (False, RIDGE, 1.0),
        "uniform_anchor": (True, RIDGE, 1.0),
        "weaker_anchor": (True, RIDGE / 2, 1.0),
        "playoff_emphasis": (True, RIDGE, 4.0),
    }
    predictions = {name: np.full(index.size, np.nan) for name in ("preseason_only", *candidates)}
    audit = []
    for group in range(FOLDS):
        mask = fold == group
        train, test = index[~mask], index[mask]
        if (
            not train.size
            or not test.size
            or np.intersect1d(rows.game[train], rows.game[test]).size
        ):
            raise ValueError(f"invalid whole-game split for {season} fold {group}")
        if np.unique(rows.playoff[train]).size != 2:
            raise ValueError(f"both season types must appear in the fit for {season} fold {group}")
        x, y = level[train], rows.y[train]
        intercept, beta = fit_context(x, y - anchor_offset[train], np.ones(train.size))
        predictions["preseason_only"][mask] = intercept + level[test] @ beta + anchor_offset[test]
        fits = {}
        for name, (anchored, penalty, playoff_weight) in candidates.items():
            fit_response = y - anchor_offset[train] if anchored else y
            weights = np.where(rows.playoff[train], playoff_weight, 1.0)
            fit, beta = fit_joint(design, train, fit_response, weights, x, penalty, penalty)
            if not fit.info["converged"]:
                raise ValueError(f"{season} fold {group} failed to converge for {name}")
            effects = fit.effects + anchor if anchored else fit.effects
            predictions[name][mask] = (
                fit.intercept + level[test] @ beta + design.players[test] @ effects
            )
            fits[name] = fit.info
        audit.append(
            {
                "fold": group,
                "fit_games": int(np.unique(rows.game[train]).size),
                "scored_games": int(np.unique(rows.game[test]).size),
                "fits": fits,
            }
        )
    if not all(np.isfinite(values).all() for values in predictions.values()):
        raise ValueError(f"{season} has unscored or nonfinite predictions")
    return index, predictions, audit


def scores(rows: Rows, index: Indices, predictions: dict[str, Values]) -> dict[str, Any]:
    result = {}
    for name, mask in (("regular", ~rows.playoff[index]), ("playoffs", rows.playoff[index])):
        ix = index[mask]
        if not ix.size:
            raise ValueError(f"no eligible {name} predictions")
        response = rows.y[ix]
        clusters = {"game": rows.game[ix], "week": week_clusters(rows.day[ix])}
        result[name] = {
            "possessions": int(ix.size),
            "games": int(np.unique(rows.game[ix]).size),
            "mse": {
                model: float(np.mean((values[mask] - response) ** 2))
                for model, values in predictions.items()
            },
            "vs_uniform_anchor": {
                model: paired_delta(
                    response, values[mask], predictions["uniform_anchor"][mask], clusters
                )
                for model, values in predictions.items()
                if model != "uniform_anchor"
            },
        }
    return result


def run(raw: Path, processed: Path, output: Path, protocol_sha256: str) -> dict[str, Any]:
    start = time.perf_counter()
    protocol = verify_protocol(PROTOCOL, protocol_sha256)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite a run: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".actual-impact-", dir=output.parent) as scratch:
        stage = Path(scratch) / "results"
        stage.mkdir()
        inputs = load_inputs(
            raw, processed, Path(scratch), addendum=checked_file(ADDENDUM, OUTER_ADDENDUM_PIN)
        )
        rows, design = inputs.analysis.rows, inputs.analysis.design
        anchors = {s: preseason(inputs, s, stage) for s in OUTER_SEASONS}
        _write_json(stage / "anchors.json", {str(s): record for s, (_, record) in anchors.items()})
        outcomes = {}
        predictions_sha256 = {}
        for season in OUTER_SEASONS:
            index, predictions, audit = heldout_predictions(
                rows, design, season, anchors[season][0]
            )
            path = stage / f"predictions_{season}.npz"
            np.savez_compressed(
                path,
                game_id=np.asarray(rows.game_ids)[rows.game[index]],
                possession_seq=rows.possession_seq[index],
                playoff=rows.playoff[index],
                candidates=list(predictions),
                points_per_100=np.column_stack(list(predictions.values())),
            )
            predictions_sha256[path.name] = sha256_file(path)
            outcomes[season] = (index, predictions, audit)
        all_index = np.concatenate([r[0] for r in outcomes.values()])
        all_predictions = {
            name: np.concatenate([r[1][name] for r in outcomes.values()])
            for name in outcomes[OUTER_SEASONS[0]][1]
        }
        pooled = scores(rows, all_index, all_predictions)
        season_scores = {str(s): scores(rows, i, p) for s, (i, p, _) in outcomes.items()}
        primary = pooled["playoffs"]["vs_uniform_anchor"]["playoff_emphasis"]
        deltas = [
            r["playoffs"]["vs_uniform_anchor"]["playoff_emphasis"]["delta"]
            for r in season_scores.values()
        ]
        low, high = primary["ci95_game"]
        decision = "inconclusive"
        if high < 0 and all(delta < 0 for delta in deltas):
            decision = "playoff_emphasis_better"
        elif low > 0 and all(delta > 0 for delta in deltas):
            decision = "playoff_emphasis_worse"
        _write_json(
            stage / "results.json",
            {
                "pooled": pooled,
                "seasons": season_scores,
                "verdict": decision,
                "fit_audit": {str(s): r[2] for s, r in outcomes.items()},
            },
        )
        head, clean = _git_head()
        outputs = {path.name: sha256_file(path) for path in sorted(stage.iterdir())}
        if any(out != outputs[name] for name, out in predictions_sha256.items()):
            raise ValueError("predictions changed after scoring")
        manifest = {
            "version": VERSION,
            "evidence_tier": "retrospective_capture_bound",
            "protocol": protocol,
            "code_commit": head,
            "working_tree_clean": clean,
            "input_ids": inputs.input_ids,
            "parents": inputs.parents,
            "versions": _versions(),
            "runtime_seconds": time.perf_counter() - start,
            "outputs": outputs,
        }
        _write_json(stage / "manifest.json", manifest)
        stage.rename(output)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("processed", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--protocol-sha256", required=True)
    args = parser.parse_args()
    print(run(args.raw, args.processed, args.output, args.protocol_sha256)["outputs"])


if __name__ == "__main__":
    main()
