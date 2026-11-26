"""Separate box-score priors with fit-only preprocessing and dated histories."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np
from numpy.typing import NDArray

from bil.features.box import FEATURES, Accumulator, Appearance

FloatArray = NDArray[np.float64]
OFFENSE = tuple(i for i, feature in enumerate(FEATURES) if feature.group == "offense")
DEFENSE = tuple(i for i, feature in enumerate(FEATURES) if feature.group == "defense")
CODES = tuple(feature.code for feature in FEATURES)
RIDGE = 0.05
MIN_POSSESSIONS = 250


@dataclass(frozen=True)
class Candidate:
    offense: tuple[int, ...]
    defense: tuple[int, ...]
    weighting: str = "exposure"


CANDIDATES = {
    "zero": Candidate((), (), "zero"),
    "mean": Candidate((), ()),
    "one_stat": Candidate((CODES.index("fga_per_36"),), (CODES.index("stl_per_36"),)),
    "full": Candidate(OFFENSE, DEFENSE),
    "full_unweighted": Candidate(OFFENSE, DEFENSE, "unit"),
    "full_one_sided": Candidate(OFFENSE, DEFENSE, "downweight_one_sided"),
    "without_offense_shooting": Candidate(OFFENSE[6:], DEFENSE),
    "without_offense_playmaking_rebounding": Candidate(OFFENSE[:6], DEFENSE),
    "without_defense_events": Candidate(OFFENSE, (DEFENSE[0], DEFENSE[3])),
    "without_defense_rebounds_fouls": Candidate(OFFENSE, DEFENSE[1:3]),
}


@dataclass(frozen=True)
class LinearPrior:
    features: tuple[int, ...]
    mean: FloatArray
    scale: FloatArray
    coefficients: FloatArray
    intercept: float

    def predict(self, values: FloatArray) -> FloatArray:
        selected = values[:, self.features]
        standardized = np.where(np.isfinite(selected), selected, self.mean) - self.mean
        result: FloatArray = self.intercept + standardized / self.scale @ self.coefficients
        return result

    def record(self) -> dict[str, object]:
        return {
            "features": [CODES[i] for i in self.features],
            "mean": self.mean.tolist(),
            "scale": self.scale.tolist(),
            "coefficients": self.coefficients.tolist(),
            "intercept": self.intercept,
        }


def fit_prior(
    values: FloatArray, response: FloatArray, weights: FloatArray, features: tuple[int, ...]
) -> LinearPrior:
    """Solve weighted mean-square loss plus ridge, with an unpenalized intercept."""
    if (
        response.ndim != 1
        or not response.size
        or values.shape != (response.size, len(CODES))
        or weights.shape != response.shape
        or not np.isfinite(response).all()
        or not np.isfinite(weights).all()
        or not (weights > 0).all()
    ):
        raise ValueError("invalid SPM training arrays")
    selected = values[:, features]
    known = np.isfinite(selected)
    safe = np.where(known, selected, 0)
    known_weight = np.sum(known * weights[:, None], axis=0)
    mean = np.divide(
        weights @ safe, known_weight, out=np.zeros(len(features)), where=known_weight > 0
    )
    centered = np.where(known, selected - mean, 0)
    weight_sum = float(weights.sum())
    scale = np.sqrt(weights @ (centered**2) / weight_sum)
    varying = np.any(known & (safe != np.max(np.where(known, safe, -np.inf), axis=0)), axis=0)
    scale[~varying | (scale == 0)] = 1
    centered[:, ~varying] = 0
    standardized = centered / scale
    intercept = float(weights @ response / weight_sum)
    weighted_design = standardized * weights[:, None]
    coefficients = np.linalg.solve(
        standardized.T @ weighted_design / weight_sum + RIDGE * np.eye(len(features)),
        weighted_design.T @ (response - intercept) / weight_sum,
    )
    return LinearPrior(features, mean, scale, coefficients, intercept)


def fit_candidate(
    values: FloatArray,
    labels: FloatArray,
    exposures: FloatArray,
    support: NDArray[np.bool_],
    candidate: Candidate,
) -> tuple[LinearPrior, LinearPrior]:
    if labels.shape != exposures.shape or labels.shape != (len(values), 2):
        raise ValueError("each example needs separate labels and exposure counts")
    if support.shape != (len(values),) or np.any(exposures < MIN_POSSESSIONS):
        raise ValueError("each training example needs the minimum exposure and a support flag")
    weights = exposures / (exposures + 1000)
    if candidate.weighting == "unit":
        weights = np.ones_like(weights)
    if candidate.weighting == "downweight_one_sided":
        weights = weights * np.where(support, 1.0, 0.5)[:, None]
    if candidate.weighting == "zero":
        labels = np.zeros_like(labels)
    return (
        fit_prior(values, labels[:, 0], weights[:, 0], candidate.offense),
        fit_prior(values, labels[:, 1], weights[:, 1], candidate.defense),
    )


History = dict[int, Accumulator]


def update_history(history: History, appearances: Iterable[Appearance]) -> None:
    for row in appearances:
        if row.minutes_ms > 0:
            player = int(row.player_id)
            if player not in history:
                history[player] = Accumulator()
            history[player].add(row)


def completed_history(appearances: Iterable[Appearance], cutoff: date) -> History:
    result: History = {}
    update_history(result, (row for row in appearances if row.game_date < cutoff))
    return result


def dated_histories(
    previous: Iterable[Appearance], current: Iterable[Appearance], days: Sequence[date]
) -> Iterator[tuple[date, Mapping[int, Accumulator]]]:
    """Yield mutable running history views; consume each view before advancing."""
    if list(days) != sorted(set(days)):
        raise ValueError("evaluation dates must be unique and increasing")
    grouped: dict[date, list[Appearance]] = defaultdict(list)
    for row in (*previous, *current):
        grouped[row.game_date].append(row)
    dates = iter(sorted(grouped))
    next_date = next(dates, None)
    history: History = {}
    for day in days:
        while next_date is not None and next_date < day:
            update_history(history, grouped[next_date])
            next_date = next(dates, None)
        yield day, history


def feature_matrix(
    history: Mapping[int, Accumulator], players: Sequence[int]
) -> tuple[FloatArray, FloatArray]:
    values = np.full((len(players), len(CODES)), np.nan)
    minutes = np.full(len(players), np.nan)
    for i, player in enumerate(players):
        stats = history.get(player)
        if stats is None:
            continue
        rates = stats.values()
        values[i] = [rates[name].value for name in CODES]
        minutes[i] = stats.minutes_ms / (60_000 * stats.positive_time_games)
    return values, minutes


def signed_lineup_sum(
    priors: FloatArray, offense: NDArray[np.int64], defense: NDArray[np.int64]
) -> tuple[FloatArray, FloatArray]:
    """The score model adds offense and subtracts positive defense."""
    return priors[offense, 0].sum(axis=1), -priors[defense, 1].sum(axis=1)
