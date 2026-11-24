"""Retrospective realized-lineup predictions and paired SPM scoring."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
from numpy.typing import NDArray

from bil.features.box import Appearance
from bil.models.rapm.multiseason import Rows, build_matrix, fit_context, fit_players
from bil.models.spm import (
    CODES,
    FloatArray,
    LinearPrior,
    dated_histories,
    feature_matrix,
    signed_lineup_sum,
)

IntArray = NDArray[np.int64]
BoolArray = NDArray[np.bool_]
PriorPair = tuple[LinearPrior, LinearPrior]
BOOTSTRAP_RESAMPLES = 1000
BOOTSTRAP_SEED = 30
COURT_NAMES = (
    "league",
    "context",
    "rapm",
    "rapm_context",
    "context_full",
    "context_one_stat",
    "context_full_offense_only",
    "context_full_defense_only",
)
SNAPSHOT_CANDIDATES = ("full", "one_stat")
VOLUME = CODES.index("fga_per_36")


@dataclass(frozen=True)
class CourtBaselines:
    player_ids: IntArray
    intercepts: tuple[float, ...]
    context: FloatArray
    rapm: FloatArray
    rapm_context: FloatArray
    fit_metadata: dict[str, Any]

    def predictions(self, rows: Rows) -> FloatArray:
        values = np.empty((len(rows), 4))
        offset = rows.context @ self.context
        values[:, 0] = self.intercepts[0]
        values[:, 1] = self.intercepts[1] + offset
        offense = lookup(self.player_ids, rows.offense)
        defense = lookup(self.player_ids, rows.defense)
        for col, coefficients in ((2, self.rapm), (3, self.rapm_context)):
            attack, stop = signed_lineup_sum(coefficients, offense, defense)
            values[:, col] = self.intercepts[col] + attack + stop
        values[:, 3] += offset
        return values


def lookup(keys: IntArray, ids: IntArray) -> IntArray:
    """Sorted-key indices; unseen keys go to the appended fallback row."""
    if not keys.size:
        return np.zeros_like(ids)
    indices = np.searchsorted(keys, ids)
    found = (indices < keys.size) & (keys[np.minimum(indices, keys.size - 1)] == ids)
    return np.where(found, indices, keys.size)


def fit_court_baselines(rows: Rows, first_scored_date: date) -> CourtBaselines:
    if np.any(rows.day >= first_scored_date.toordinal()):
        raise ValueError("a comparator row is not strictly earlier than the evaluation season")
    design = build_matrix(rows.offense, rows.defense)
    index = np.arange(len(rows), dtype=np.int64)
    weights = np.ones(len(rows))
    context_mean, gamma = fit_context(rows.context, rows.y, weights)
    plain = fit_players(design, index, rows.y, weights, 4000, 8000)
    adjusted = fit_players(design, index, rows.y - rows.context @ gamma, weights, 4000, 8000)

    def with_fallback(effects: FloatArray) -> FloatArray:
        return np.vstack((effects.reshape(2, -1).T, [0, 0]))

    return CourtBaselines(
        np.asarray(design.player_ids, dtype=np.int64),
        (float(rows.y.mean()), context_mean, plain.intercept, adjusted.intercept),
        gamma,
        with_fallback(plain.effects),
        with_fallback(adjusted.effects),
        {
            "last_date": date.fromordinal(int(np.max(rows.day))).isoformat(),
            "rows": len(rows),
            "context_intercept": context_mean,
            "context_coefficients": gamma.tolist(),
            "offense_ridge": 4000,
            "defense_ridge": 8000,
            "rapm": plain.info,
            "rapm_context": adjusted.info,
        },
    )


@dataclass(frozen=True)
class DatedPriors:
    day: int
    players: IntArray
    minutes: FloatArray
    volume: FloatArray
    priors: FloatArray
    fallback: BoolArray
    has_current_history: BoolArray


@dataclass(frozen=True)
class CourtPredictions:
    values: FloatArray
    minutes: FloatArray
    volume: FloatArray
    missing_history: NDArray[np.int64]
    dated: list[DatedPriors]


def predict_pair(pair: PriorPair, values: FloatArray) -> FloatArray:
    result: FloatArray = np.column_stack([model.predict(values) for model in pair])
    return result


def pair_fallback(pair: PriorPair, values: FloatArray) -> BoolArray:
    fallback: BoolArray = np.column_stack(
        [~np.isfinite(values[:, model.features]).any(axis=1) for model in pair]
    )
    return fallback


def lineup_mean(values: FloatArray) -> FloatArray:
    known = np.isfinite(values)
    count = known.sum(axis=1)
    mean: FloatArray = np.divide(
        np.where(known, values, 0.0).sum(axis=1),
        count,
        out=np.full(len(values), np.nan),
        where=count > 0,
    )
    return mean


def predict_court(
    rows: Rows,
    previous: Sequence[Appearance],
    current: Sequence[Appearance],
    baselines: CourtBaselines,
    models: Mapping[str, PriorPair],
) -> CourtPredictions:
    days = [date.fromordinal(int(day)) for day in np.unique(rows.day)]
    predictions = np.empty((len(rows), len(COURT_NAMES)))
    predictions[:, :4] = baselines.predictions(rows)
    missing_history = np.empty(len(rows), dtype=np.int64)
    minutes_mean = np.empty(len(rows))
    volume_mean = np.empty(len(rows))
    dated = []
    first_current: dict[int, date] = {}
    for row in current:
        if row.minutes_ms > 0:
            player = int(row.player_id)
            first_current[player] = min(first_current.get(player, row.game_date), row.game_date)
    for day, history in dated_histories(previous, current, days):
        ordinal = day.toordinal()
        subset = rows.day == ordinal
        offense, defense = rows.offense[subset], rows.defense[subset]
        ids = np.unique(np.concatenate((offense.ravel(), defense.ravel())))
        offense = np.searchsorted(ids, offense)
        defense = np.searchsorted(ids, defense)
        values, minutes = feature_matrix(history, ids.tolist())
        priors = np.stack(
            [predict_pair(models[name], values) for name in SNAPSHOT_CANDIDATES], axis=1
        )
        full_o, full_d = signed_lineup_sum(priors[:, 0], offense, defense)
        simple_o, simple_d = signed_lineup_sum(priors[:, 1], offense, defense)
        context = predictions[subset, 1]
        predictions[subset, 4:] = np.column_stack(
            (
                context + full_o + full_d,
                context + simple_o + simple_d,
                context + full_o,
                context + full_d,
            )
        )
        minutes_mean[subset] = lineup_mean(minutes[offense])
        volume_mean[subset] = lineup_mean(values[:, VOLUME][offense])
        missing_history[subset] = np.isnan(minutes[offense]).sum(axis=1) + np.isnan(
            minutes[defense]
        ).sum(axis=1)
        fallback = np.stack(
            [pair_fallback(models[name], values) for name in SNAPSHOT_CANDIDATES], axis=1
        )
        has_current_history = np.asarray(
            [first_current.get(int(player), date.max) < day for player in ids], dtype=np.bool_
        )
        dated.append(
            DatedPriors(
                ordinal, ids, minutes, values[:, VOLUME], priors, fallback, has_current_history
            )
        )
    return CourtPredictions(predictions, minutes_mean, volume_mean, missing_history, dated)


def bands(
    values: FloatArray, lower: float, upper: float, names: tuple[str, str, str, str]
) -> dict[str, BoolArray]:
    return dict(
        zip(
            names,
            (
                ~np.isfinite(values),
                np.isfinite(values) & (values < lower),
                (values >= lower) & (values < upper),
                values >= upper,
            ),
            strict=True,
        )
    )


def minutes_bands(values: FloatArray) -> dict[str, BoolArray]:
    return bands(values, 15, 25, ("no_history", "under_15", "15_to_under_25", "25_plus"))


def volume_bands(values: FloatArray) -> dict[str, BoolArray]:
    return bands(values, 9, 15, ("unavailable", "under_9", "9_to_under_15", "15_plus"))


def sum_by(keys: IntArray, values: FloatArray, size: int) -> FloatArray:
    totals = np.zeros((size, values.shape[1]))
    np.add.at(totals, keys, values)
    return totals


def court_scores(
    rows: Rows, predictions: CourtPredictions, births: Mapping[int, date]
) -> tuple[dict[str, Any], FloatArray]:
    """Score only after the caller has frozen the prediction artifact."""
    errors = (predictions.values - rows.y[:, None]) / 100
    squared = errors**2
    score = court_slice(rows, errors, squared, np.ones(len(rows), dtype=bool))
    score["regular"] = court_slice(rows, errors, squared, ~rows.playoff)
    score["playoffs"] = court_slice(rows, errors, squared, rows.playoff)
    score["minutes"] = {
        label: possession_slice(rows, squared, mask)
        for label, mask in minutes_bands(predictions.minutes).items()
    }
    score["shot_volume_role"] = {
        label: possession_slice(rows, squared, mask)
        for label, mask in volume_bands(predictions.volume).items()
    }
    score["history"] = {
        "complete": possession_slice(rows, squared, predictions.missing_history == 0),
        "any_player_missing": possession_slice(rows, squared, predictions.missing_history > 0),
        "missing_lineup_player_slots": int(predictions.missing_history.sum()),
        "dated_players_without_history": sum(
            int(np.isnan(view.minutes).sum()) for view in predictions.dated
        ),
    }
    score["history"]["dated_players_without_current_season_history"] = sum(
        int((~view.has_current_history).sum()) for view in predictions.dated
    )
    score["history"]["intercept_fallback_dated_with_history"] = {
        name: np.stack(
            [
                (view.fallback[:, index] & np.isfinite(view.minutes)[:, None]).sum(axis=0)
                for view in predictions.dated
            ]
        )
        .sum(axis=0)
        .tolist()
        for index, name in enumerate(SNAPSHOT_CANDIDATES)
    }
    age = np.full(len(rows), np.nan)
    for view in predictions.dated:
        day_rows = rows.day == view.day
        offense = np.searchsorted(view.players, rows.offense[day_rows])
        ages = ages_at(view.players, date.fromordinal(view.day), births)
        age[day_rows] = ages[offense].mean(axis=1)
    score["age"] = {
        label: possession_slice(rows, squared, mask) for label, mask in age_bands(age).items()
    }
    score["verification"] = {
        "no_livedata": possession_slice(rows, squared, rows.no_livedata),
        "livedata": possession_slice(rows, squared, ~rows.no_livedata),
    }
    score["roster_position"] = {"status": "unavailable", "possessions": len(rows)}
    _, week = np.unique((rows.day - 1) // 7, return_inverse=True)  # ordinal 1 was Monday
    weekly = sum_by(week, np.column_stack((np.ones(len(rows)), squared)), int(np.max(week)) + 1)
    return score, weekly


def possession_slice(rows: Rows, squared: FloatArray, include: BoolArray) -> dict[str, Any]:
    return {
        "possessions": int(include.sum()),
        "games": int(np.unique(rows.game[include]).size),
        "mse": dict(zip(COURT_NAMES, squared[include].mean(axis=0).tolist(), strict=True))
        if include.any()
        else {},
    }


def court_slice(
    rows: Rows, errors: FloatArray, squared: FloatArray, include: BoolArray
) -> dict[str, Any]:
    score = possession_slice(rows, squared, include)
    if not include.any():
        return score
    _, indices, teams, counts = np.unique(
        rows.team_game[include], return_index=True, return_inverse=True, return_counts=True
    )
    sums = sum_by(teams, errors[include], len(counts))
    team_games = rows.game[include][indices]
    games, inverse, team_counts = np.unique(team_games, return_inverse=True, return_counts=True)
    if np.any(team_counts != 2):
        raise ValueError("every accepted game must have exactly two represented team scores")
    order = np.argsort(inverse, kind="stable")
    margins = sums[order[::2]] - sums[order[1::2]]
    score["team_games"] = int(len(counts))
    score["represented_game_margins"] = int(len(games))
    for name, values in (
        ("team_ppp_rmse", ((sums / counts[:, None]) ** 2).mean(axis=0) ** 0.5),
        ("margin_mae", np.abs(margins).mean(axis=0)),
        ("margin_rmse", (margins**2).mean(axis=0) ** 0.5),
    ):
        score[name] = dict(zip(COURT_NAMES, values.tolist(), strict=True))
    return score


def clustered_interval(
    clusters: Sequence[FloatArray], first: int, second: int, *, rmse: bool
) -> list[float]:
    """Paired cluster bootstrap; each matrix is resampled within its own stratum."""
    if not clusters or any(len(block) == 0 for block in clusters):
        raise ValueError("paired intervals require nonempty clusters")
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    draw = np.zeros((BOOTSTRAP_RESAMPLES, 3))
    for block in clusters:
        numbers = rng.integers(0, len(block), size=(BOOTSTRAP_RESAMPLES, len(block)))
        draw += block[:, [0, first + 1, second + 1]][numbers].sum(axis=1)
    errors = draw[:, 1:] / draw[:, :1]
    if rmse:
        errors = np.sqrt(errors)
    return [float(point) for point in np.quantile(errors[:, 0] - errors[:, 1], [0.025, 0.975])]


def ages_at(players: IntArray, day: date, births: Mapping[int, date]) -> FloatArray:
    ages = np.full(len(players), np.nan)
    for index, player in enumerate(players):
        birth = births.get(int(player))
        if birth is not None:
            years = day.year - birth.year - ((day.month, day.day) < (birth.month, birth.day))
            if 18 <= years <= 50:
                ages[index] = years
    return ages


def age_bands(values: FloatArray) -> dict[str, BoolArray]:
    return bands(values, 24, 30, ("unknown", "under_24", "24_to_under_30", "30_plus"))
