"""Compare K0 agreement with disjoint repeat estimates and held-out outcomes (#137)."""

from __future__ import annotations

import argparse
import hashlib
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from itertools import combinations
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import numpy as np
from numpy.typing import NDArray

from bil.data.pilot_sources import sha256_file
from bil.models.rapm.multiseason import (
    REPO_ROOT,
    Design,
    Rows,
    _git_head,
    _prepare,
    _versions,
    _write_json,
    fit_context,
    paired_delta,
    week_clusters,
)
from bil.models.rapm.targets import (
    TARGET_PINS,
    fit_joint,
    input_digest,
    subset_rows,
    team_codes,
    verify_protocol,
)
from bil.models.spm_build import Labels, load_labels, target_inputs

VERSION = "issue-137-v1"
PROTOCOL = REPO_ROOT / "docs/research/k0-player-support-protocol.md"
SEASONS = tuple(range(2019, 2023))
RIDGES = (1000, 4000, 16000, 64000)
REFERENCE = "ridge_16000"
MIN_EXPOSURE = 250
MIN_MATCHED_GAMES = 2
MIN_MATCHED_POSSESSIONS = 15
ROLES = ("offense", "defense")
Indices = NDArray[np.int64]
Values = NDArray[np.float64]


def schedule_blocks(rows: Rows, season: int) -> dict[str, Indices]:
    regular = (rows.season == season) & ~rows.playoff
    days = np.unique(rows.day[regular])
    if len(days) < 4:
        raise ValueError(f"insufficient played dates in {season}")
    middle, repeat_end = days[len(days) // 2], days[3 * len(days) // 4]
    candidate_games = np.asarray(
        [
            hashlib.sha256(f"{VERSION}:{gid}".encode()).digest()[-1] % 2 == 0
            for gid in rows.game_ids
        ],
        dtype=np.bool_,
    )
    calibration = regular & (rows.day < middle)
    blocks = {
        "candidate": np.flatnonzero(calibration & candidate_games[rows.game]),
        "proxy": np.flatnonzero(calibration & ~candidate_games[rows.game]),
        "repeat": np.flatnonzero(regular & (rows.day >= middle) & (rows.day < repeat_end)),
        "outcome": np.flatnonzero(regular & (rows.day >= repeat_end)),
    }
    games: set[int] = set()
    for name, index in blocks.items():
        block_games = set(rows.game[index].tolist())
        if not block_games or games & block_games:
            raise ValueError(f"empty or overlapping game block {name} in {season}")
        games.update(block_games)
    return blocks


def role_counts(design: Design, index: Indices) -> Values:
    return np.asarray(design.on_court[index].sum(axis=0), dtype=np.float64).ravel()


def role_overlap(design: Design, index: Indices, side: int) -> Values:
    start = side * design.size
    presence = design.on_court[index, start : start + design.size]
    both = np.asarray((presence.T @ presence).toarray(), dtype=np.float64)
    counts = np.diag(both).copy()
    union = counts[:, None] + counts[None, :] - both
    np.fill_diagonal(both, 0)
    both[:, counts < MIN_EXPOSURE] = 0
    overlap: Values = np.divide(both, union, out=np.zeros_like(both), where=union > 0).max(axis=1)
    return overlap


def ridge(
    rows: Rows, design: Design, index: Indices, penalty: int
) -> tuple[Values, float, Values, dict[str, float]]:
    response, context = rows.y[index], rows.context[index]
    fit, coefficients = fit_joint(
        design, index, response, np.ones(index.size), context, penalty, penalty
    )
    if not fit.info["converged"]:
        raise ValueError(f"ridge solve failed at penalty {penalty}")
    return fit.effects, fit.intercept, coefficients, dict(fit.info)


def block_metadata(rows: Rows, teams: Indices, index: Indices) -> dict[str, Any]:
    mask = np.zeros(len(rows), dtype=np.bool_)
    mask[index] = True
    sub = subset_rows(rows, mask)
    return {
        "games": int(np.unique(rows.game[index]).size),
        "possessions": int(index.size),
        "first": date.fromordinal(int(np.min(sub.day))).isoformat(),
        "last": date.fromordinal(int(np.max(sub.day))).isoformat(),
        "input_digest": input_digest(sub, teams[index]),
    }


@dataclass
class Slot:
    games: set[int] = field(default_factory=set)
    positions: list[int] = field(default_factory=list)

    def supported(self) -> bool:
        return (
            len(self.games) >= MIN_MATCHED_GAMES and len(self.positions) >= MIN_MATCHED_POSSESSIONS
        )


def lineup_slots(
    teammates: Indices, opponents: Indices, games: Indices
) -> dict[tuple[int, ...], dict[int, Slot]]:
    slots: dict[tuple[int, ...], dict[int, Slot]] = defaultdict(dict)
    own = np.sort(teammates, axis=1).tolist()
    other = np.sort(opponents, axis=1).tolist()
    for i, (five, opposing, game) in enumerate(zip(own, other, games.tolist(), strict=True)):
        for position, player in enumerate(five):
            key = tuple(five[:position] + five[position + 1 :] + opposing)
            players = slots[key]
            if player not in players:
                players[player] = Slot()
            players[player].games.add(game)
            players[player].positions.append(i)
    return slots


def supported_contrasts(
    candidate: Mapping[tuple[int, ...], Mapping[int, Slot]],
    outcome: Mapping[tuple[int, ...], Mapping[int, Slot]],
) -> list[tuple[int, int, Slot, Slot]]:
    comparisons: list[tuple[int, int, Slot, Slot]] = []
    for key in sorted(candidate.keys() & outcome.keys()):
        fitted, observed = candidate[key], outcome[key]
        common = sorted(
            p
            for p in fitted.keys() & observed.keys()
            if fitted[p].supported() and observed[p].supported()
        )
        comparisons.extend((p, q, observed[p], observed[q]) for p, q in combinations(common, 2))
    return comparisons


@dataclass
class RatingScores:
    players: Indices
    weights: Values
    ratings: dict[str, Values]
    proxy: Values
    repeat: Values
    overlap: Values


def rating_cohort(
    ids: Indices, counts: Values, effects: Mapping[str, Values], overlap: Values
) -> RatingScores:
    eligible = (counts >= MIN_EXPOSURE).all(axis=0)
    weights = counts[0, eligible]
    centered = (
        {
            name: values[eligible] - np.average(values[eligible], weights=weights)
            for name, values in effects.items()
        }
        if eligible.any()
        else {name: np.empty(0) for name in effects}
    )
    proxy, repeat = centered.pop("proxy"), centered.pop("repeat")
    return RatingScores(ids[eligible], weights, centered, proxy, repeat, overlap[eligible])


def agreement(cohort: RatingScores, keep: NDArray[np.bool_]) -> dict[str, Any]:
    if not keep.any():
        return {"players": 0, "status": "unavailable"}
    return {
        "players": int(keep.sum()),
        "metrics": {
            name: {
                "proxy_rmse": float(np.sqrt(np.mean((values[keep] - cohort.proxy[keep]) ** 2))),
                "repeat_rmse": float(np.sqrt(np.mean((values[keep] - cohort.repeat[keep]) ** 2))),
                "weighted_sd": float(
                    np.sqrt(
                        np.average(
                            (values[keep] - np.average(values[keep], weights=cohort.weights[keep]))
                            ** 2,
                            weights=cohort.weights[keep],
                        )
                    )
                ),
            }
            for name, values in cohort.ratings.items()
        },
    }


def outcome_scores(
    rows: Rows, index: Indices, teams: Indices, predictions: Mapping[str, Values]
) -> dict[str, Any]:
    if not index.size:
        return {"possessions": 0, "status": "unavailable"}
    outcomes = rows.y[index]
    games = rows.game[index]
    clusters = {"game": games, "week": week_clusters(rows.day[index])}
    reference = predictions[REFERENCE]
    scores = {}
    for name, model in predictions.items():
        delta = (model - outcomes) ** 2 - (reference - outcomes) ** 2
        without_franchise = []
        for franchise in np.unique(teams):
            keep = np.all(teams != franchise, axis=1)
            if keep.any():
                without_franchise.append(float(delta[keep].mean()))
        scores[name] = {
            "mse": float(np.mean((model - outcomes) ** 2)),
            "vs_ridge_16000": paired_delta(outcomes, model, reference, clusters),
            "delta_without_one_franchise": [min(without_franchise), max(without_franchise)]
            if without_franchise
            else None,
        }
    return {"possessions": int(index.size), "games": int(np.unique(games).size), "scores": scores}


def outcome_slices(
    rows: Rows, index: Indices, teams: Indices, predictions: Mapping[str, Values], minimum: Indices
) -> dict[str, Any]:
    coverage = {
        "all": np.ones(index.size, dtype=np.bool_),
        "all_ten_250": minimum >= MIN_EXPOSURE,
        "any_unseen": minimum == 0,
        "any_below_250": minimum < MIN_EXPOSURE,
    }
    return {
        name: outcome_scores(
            rows,
            index[keep],
            teams[index[keep]],
            {model: p[keep] for model, p in predictions.items()},
        )
        for name, keep in coverage.items()
    }


def fit_season(
    rows: Rows, design: Design, teams: Indices, season: int, stage: Path
) -> tuple[dict[str, Any], Indices, dict[str, Values], dict[str, RatingScores], Indices]:
    blocks = schedule_blocks(rows, season)
    train, proxy, repeat, outcome = (
        blocks[name] for name in ("candidate", "proxy", "repeat", "outcome")
    )
    counts = np.vstack([role_counts(design, index) for index in (train, proxy, repeat)])
    intercept, gamma = fit_context(rows.context[train], rows.y[train], np.ones(train.size))
    baseline = intercept + rows.context[outcome] @ gamma
    effects = {"zero": np.zeros(2 * design.size)}
    predictions = {"zero": baseline}
    fits = {}
    for penalty in RIDGES:
        name = f"ridge_{penalty}"
        effects[name], level, context, fits[name] = ridge(rows, design, train, penalty)
        predictions[name] = (
            level + rows.context[outcome] @ context + design.players[outcome] @ effects[name]
        )
    for name, index in (("proxy", proxy), ("repeat", repeat)):
        effects[name], _, _, fits[name] = ridge(rows, design, index, 16000)
    if not all(np.isfinite(prediction).all() for prediction in predictions.values()):
        raise ValueError(f"nonfinite predictions in {season}")
    ids = np.asarray(design.player_ids, dtype=np.int64)
    prediction_path = stage / f"predictions_{season}.npz"
    np.savez_compressed(
        prediction_path,
        candidates=list(predictions),
        game_id=np.asarray(rows.game_ids)[rows.game[outcome]],
        possession_seq=rows.possession_seq[outcome],
        points_per_100=np.column_stack(list(predictions.values())),
        player_id=ids,
        rating_names=list(effects),
        offense_effects=np.stack([effect[: design.size] for effect in effects.values()]),
        defense_effects=np.stack([effect[design.size :] for effect in effects.values()]),
    )
    prediction_digest = sha256_file(prediction_path)

    role_scores = {}
    outcome_minimum = np.full(outcome.size, np.iinfo(np.int64).max, dtype=np.int64)
    report: dict[str, Any] = {
        "inputs": {n: block_metadata(rows, teams, i) for n, i in blocks.items()},
        "fits": fits,
        "predictions_sha256": prediction_digest,
        "roles": {},
    }
    for side, (role, own, other) in enumerate(
        (("offense", rows.offense, rows.defense), ("defense", rows.defense, rows.offense))
    ):
        columns = slice(side * design.size, (side + 1) * design.size)
        cohort = rating_cohort(
            ids,
            counts[:, columns],
            {n: e[columns] for n, e in effects.items()},
            role_overlap(design, train, side),
        )
        role_scores[role] = cohort
        bands = {
            "all": np.ones(cohort.players.size, dtype=np.bool_),
            "250_to_999": cohort.weights < 1000,
            "1000_plus": cohort.weights >= 1000,
            "overlap_low": cohort.overlap < 0.5,
            "overlap_high": cohort.overlap >= 0.5,
        }
        role_report = {name: agreement(cohort, keep) for name, keep in bands.items()}
        minimum = (
            counts[0, columns][np.searchsorted(ids, own[outcome])].min(axis=1).astype(np.int64)
        )
        outcome_minimum = np.minimum(outcome_minimum, minimum)
        train_slots = lineup_slots(own[train], other[train], rows.game[train])
        test_slots = lineup_slots(own[outcome], other[outcome], rows.game[outcome])
        matches = supported_contrasts(train_slots, test_slots)
        contrast_report: dict[str, Any] = {
            "matched_contrasts": len(matches),
            "candidate_configurations": len(train_slots),
            "outcome_configurations": len(test_slots),
            "status": "scored" if matches else "unavailable",
        }
        if matches:
            residual = (rows.y[outcome] - baseline) * (1 if side == 0 else -1)
            truth = np.asarray(
                [
                    residual[a.positions].mean() - residual[b.positions].mean()
                    for _, _, a, b in matches
                ]
            )
            left = np.searchsorted(ids, [p for p, _, _, _ in matches])
            right = np.searchsorted(ids, [q for _, q, _, _ in matches])
            contrast_report["rmse"] = {
                n: float(np.sqrt(np.mean((e[columns][left] - e[columns][right] - truth) ** 2)))
                for n, e in effects.items()
                if n in predictions
            }
        role_report["matched_outcome_contrasts"] = contrast_report
        report["roles"][role] = role_report
    return report, outcome, predictions, role_scores, outcome_minimum


def pooled_ratings(cohorts: Sequence[RatingScores]) -> dict[str, Any]:
    ids = np.concatenate([cohort.players for cohort in cohorts])
    if not ids.size:
        return {"player_seasons": 0, "status": "unavailable"}
    reference = np.concatenate([cohort.ratings[REFERENCE] for cohort in cohorts])
    truth = {
        "proxy": np.concatenate([c.proxy for c in cohorts]),
        "repeat": np.concatenate([c.repeat for c in cohorts]),
    }
    report = {}
    for name in cohorts[0].ratings:
        model = np.concatenate([cohort.ratings[name] for cohort in cohorts])
        report[name] = {
            label: {
                "rmse": float(np.sqrt(np.mean((actual - model) ** 2))),
                "vs_ridge_16000": paired_delta(actual, model, reference, {"player": ids}),
            }
            for label, actual in truth.items()
        }
    return {
        "player_seasons": int(ids.size),
        "distinct_players": int(np.unique(ids).size),
        "scores": report,
    }


def published_agreement(
    cohort: RatingScores, labels: Labels, season: int, side: int
) -> dict[str, Any]:
    lookup = {
        player: label.values[side]
        for (y, player), label in labels.items()
        if y == season and label.enough()
    }
    keep = np.asarray([int(p) in lookup for p in cohort.players], dtype=np.bool_)
    if not keep.any():
        return {"players": 0, "status": "unavailable"}
    weights = cohort.weights[keep]
    truth = np.asarray([lookup[int(p)] for p in cohort.players[keep]])
    truth -= np.average(truth, weights=weights)
    return {
        "players": int(keep.sum()),
        "rmse": {
            name: float(
                np.sqrt(np.mean((fit[keep] - np.average(fit[keep], weights=weights) - truth) ** 2))
            )
            for name, fit in cohort.ratings.items()
        },
    }


def run(processed: Path, output: Path, protocol_sha256: str) -> dict[str, Any]:
    start = time.perf_counter()
    protocol = verify_protocol(PROTOCOL, protocol_sha256)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite a run: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".k0-support-", dir=output.parent) as directory:
        stage = Path(directory) / "results"
        stage.mkdir()
        loads, rows, design, sources = _prepare(processed, SEASONS, SEASONS, stage, TARGET_PINS)
        teams = team_codes(
            np.concatenate([load.data["offense_team_id"] for load in loads]), rows.game
        )
        seasons = {season: fit_season(rows, design, teams, season, stage) for season in SEASONS}
        target_dir, registration, _, _, target_digests = target_inputs(processed)
        frozen = registration["contiguous"]["outer_seasons_use"]
        published = load_labels(target_dir / "evaluation_labels.csv", evaluation=True)[frozen]
        results: dict[str, Any] = {"seasons": {}, "pooled": {"ratings": {}}}
        for season, (report, index, predictions, ratings, minimum) in seasons.items():
            report["outcomes"] = outcome_slices(rows, index, teams, predictions, minimum)
            for side, role in enumerate(ROLES):
                report["roles"][role]["published_k0_descriptive"] = published_agreement(
                    ratings[role], published, season, side
                )
            results["seasons"][str(season)] = report
        index = np.concatenate([s[1] for s in seasons.values()])
        predictions = {
            name: np.concatenate([s[2][name] for s in seasons.values()])
            for name in seasons[SEASONS[0]][2]
        }
        minimum = np.concatenate([s[4] for s in seasons.values()])
        results["pooled"].update(outcome_slices(rows, index, teams, predictions, minimum))
        for role in ROLES:
            results["pooled"]["ratings"][role] = pooled_ratings(
                [s[3][role] for s in seasons.values()]
            )
        _write_json(stage / "results.json", results)
        head, clean = _git_head()
        outputs = {path.name: sha256_file(path) for path in sorted(stage.iterdir())}
        for season, (report, _, _, _, _) in seasons.items():
            if outputs[f"predictions_{season}.npz"] != report["predictions_sha256"]:
                raise ValueError(f"predictions for {season} changed after scoring")
        manifest = {
            "version": VERSION,
            "evidence_tier": "retrospective_capture_bound",
            "protocol": protocol,
            "code_commit": head,
            "working_tree_clean": clean,
            "rows": sources,
            "target_digests": target_digests,
            "versions": _versions(),
            "runtime_seconds": time.perf_counter() - start,
            "outputs": outputs,
        }
        _write_json(stage / "manifest.json", manifest)
        stage.rename(output)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("processed", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--protocol-sha256", required=True)
    args = parser.parse_args()
    print(run(args.processed, args.output, args.protocol_sha256)["outputs"])


if __name__ == "__main__":
    main()
