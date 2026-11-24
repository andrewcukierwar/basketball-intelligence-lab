"""Multi-season RAPM: temporal candidates, development selection and frozen outer validation.

Implements ``docs/research/rapm-multiseason-protocol.md`` (issue #26) in two phases.

* ``dev`` reads only the 2018-19 through 2022-23 row sets, selects a temporal candidate and
  separate offense and defense penalties on chronological development folds, and runs the
  stability and sensitivity analyses.
* ``outer`` refuses to start unless it is given the committed, unmodified outer-validation
  addendum with its SHA-256 on a clean working tree. It reads the frozen configuration from
  the addendum and scores it walk-forward on 2023-24 and 2024-25.

No loader accepts a season from 2025-26 on. The pure functions take arrays so that they can be
tested on synthetic data. The solver is the verified reference (``reference._solve_rapm``), reused
by import on row subsets of one sparse design.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import re
import shutil
import subprocess
import time
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from itertools import chain
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.sparse import csr_matrix  # type: ignore[import-untyped]

from bil.models.rapm.baseline import (
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    EVIDENCE_TIER,
    _peak_memory_mib,
    _sha256,
    bootstrap_delta,
    select_penalty,
)
from bil.models.rapm.context import fit_context_only
from bil.models.rapm.context_ablation import (
    CONTEXT_SQL,
    FAMILY_COLUMNS,
    TIMING_SQL,
    ContextRows,
    feature_columns,
    period_start_ms,
    register,
)
from bil.models.rapm.dated import fit_dated_prior_rapm
from bil.models.rapm.reference import Possession, RAPMDesign, RAPMFit, _solve_rapm, fit_prior_rapm

REPO_ROOT = Path(__file__).resolve().parents[4]
HOLDOUT_START_YEAR = 2025  # 2025-26 is the confirmatory holdout; nothing from it on is read
DEV_SEASONS = (2018, 2019, 2020, 2021, 2022)
DEV_SCORED_SEASONS = (2021, 2022)
OUTER_SEASONS = (2023, 2024)
DEV_END = date(2023, 7, 1)
ROW_SET_VERSION = "issue-93-v1"
CONTEXT_FAMILY = "home_score_time"
CONTEXT_COLUMNS = FAMILY_COLUMNS[CONTEXT_FAMILY]
PENALTY_GRID = (1000.0, 2000.0, 4000.0, 8000.0, 16000.0, 32000.0)
SPLIT_FACTORS = (0.25, 0.5, 2.0, 4.0)
SPLIT_EXTENSIONS = 3
EXPOSURE_BANDS = ((0, 2000), (2000, 5000), (5000, 10000), (10000, None))
HALF_MIN_POSSESSIONS = 250
ORACLE_TOLERANCE = 1e-6
CALIBRATION_BINS = 10


@dataclass(frozen=True, slots=True)
class SeasonPin:
    """A season's canonical row set and the pilot build that supplies its context covariates."""

    label: str
    row_manifest_sha256: str
    pilot_build: str
    pilot_manifest_sha256: str


SEASON_PINS: dict[int, SeasonPin] = {
    2018: SeasonPin(
        "2018-19",
        "c0fa49896b96827ec9ff6864bbcf5d3ddb55e8b6079ed693f4a88ebd4b1e1df1",
        "issue-25-v1",
        "a5f52e4880666fb8eb887d82eecedf6cf7ebd1e6c5e5ba42e6fea25fdb43ce35",
    ),
    2019: SeasonPin(
        "2019-20",
        "f17dfd1bd9b39cdd022375656be2681cc119c65b5f66b97466f2992bbd6ed777",
        "issue-25-v1",
        "334daf0237f3f9669d76ca807929802426bf667ad68f0932ffdcdfd0a0a52ac6",
    ),
    2020: SeasonPin(
        "2020-21",
        "231f742dbf7aeeb02e99c5a4b1ff8c2c3eed5e5bfb484390d307ecf0d8c5e756",
        "issue-25-v1",
        "c3c75d43236a93070fd8fb3dd90200f572894af6aa5f5c05b8f38881ede72a11",
    ),
    2021: SeasonPin(
        "2021-22",
        "58fed85cce0822865e7b3bf369e55b5ba5a280f6a1347d19832381df383cc298",
        "issue-25-v1",
        "49bb4a91c71d2f255a17ba1c52a3ae6e5c2737f1a8c6716c0405980949947075",
    ),
    2022: SeasonPin(
        "2022-23",
        "2affb62a8d875963f05e5eb39e2e36d8e8fbab4df43840f1dc0062deb581a1ac",
        "issue-19-v6",
        "89cb2e82af4d0fc4b7a95cf0f94b99b2b088361ffa893ce192de2b519d711570",
    ),
    2023: SeasonPin(
        "2023-24",
        "38bb59c537164df9a2a1cb8042fa51187737deadeadfd216b3edce1e1877bad4",
        "issue-52-v1",
        "1d6ba700ea75ddd984f9b306e018af84c5b90ec8937ad598ec31c20daba3176a",
    ),
    2024: SeasonPin(
        "2024-25",
        "86b0ea747849b70c7321806599f25a8864301f16026b79b4be1daa1f5202972b",
        "issue-52-v1",
        "ad72e1f0b1b97a8ef95f1c040d353254588d9d9ecf40e3064a7b7e131d195978",
    ),
}


def check_season(season: int, allowed: Iterable[int]) -> SeasonPin:
    """Return the pin of an allowed season. Holdout, unpinned and out-of-phase seasons raise."""
    if season >= HOLDOUT_START_YEAR:
        raise ValueError(f"season {season} is the confirmatory holdout or later and is never read")
    if season not in SEASON_PINS:
        raise ValueError(f"season {season} has no pinned row set")
    if season not in set(allowed):
        raise ValueError(f"season {season} is not allowed in this phase")
    return SEASON_PINS[season]


# --- temporal candidates -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Temporal:
    """Rows aged 1 to ``max_age_days`` days before the cutoff, unit or exponentially decayed."""

    name: str
    max_age_days: int
    half_life_days: float | None


TEMPORAL = (
    Temporal("W1", 365, None),
    Temporal("W2", 730, None),
    Temporal("W3", 1095, None),
    Temporal("W5", 1825, None),
    Temporal("H90", 1825, 90.0),
    Temporal("H180", 1825, 180.0),
    Temporal("H365", 1825, 365.0),
    Temporal("H730", 1825, 730.0),
)
TEMPORAL_BY_NAME = {t.name: t for t in TEMPORAL}


def temporal_weights(
    day: NDArray[np.int64], cutoff: date, temporal: Temporal
) -> NDArray[np.float64]:
    """Per-row fit weight at ``cutoff``: zero unless played strictly before it within the window.

    ``day`` holds ``date.toordinal()`` of each Eastern played date. Age is whole days and at
    least 1 for an eligible row (the ``played_before`` rule). Weights are not renormalized.
    """
    age = cutoff.toordinal() - day
    keep = (age >= 1) & (age <= temporal.max_age_days)
    weights = np.zeros(day.shape, dtype=np.float64)
    if temporal.half_life_days is None:
        weights[keep] = 1.0
    else:
        weights[keep] = 0.5 ** (age[keep] / temporal.half_life_days)
    return weights


# --- rows, design and blocks -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Rows:
    """Eligible possessions of several seasons. Rates are points per 100 possessions."""

    season: NDArray[np.int64]
    playoff: NDArray[np.bool_]
    day: NDArray[np.int64]
    game: NDArray[np.int64]
    game_ids: tuple[str, ...]
    team_game: NDArray[np.int64]
    possession_seq: NDArray[np.int64]
    period: NDArray[np.int64]
    y: NDArray[np.float64]
    offense: NDArray[np.int64]
    defense: NDArray[np.int64]
    context: NDArray[np.float64]
    no_livedata: NDArray[np.bool_]

    def __len__(self) -> int:
        return int(self.y.size)


@dataclass(frozen=True, slots=True)
class Design:
    """The reference column layout for every loaded row: intercept, offense IDs, defense IDs."""

    player_ids: tuple[int, ...]
    matrix: csr_matrix
    players: csr_matrix
    on_court: csr_matrix

    @property
    def size(self) -> int:
        return len(self.player_ids)


def build_matrix(offense: NDArray[np.int64], defense: NDArray[np.int64]) -> Design:
    """Vectorized ``reference.build_design`` layout: +1 offense, -1 defense, sorted player IDs."""
    rows = offense.shape[0]
    if offense.shape != (rows, 5) or defense.shape != (rows, 5) or rows == 0:
        raise ValueError("offense and defense must be nonempty (n, 5) arrays")
    both = np.concatenate([offense, defense], axis=1)
    if np.any(both <= 0):
        raise ValueError("player IDs must be positive integers")
    ordered = np.sort(both, axis=1)
    if np.any(ordered[:, 1:] == ordered[:, :-1]):
        raise ValueError("every row requires five distinct players on each side")
    ids = np.unique(both)
    count = int(ids.size)
    columns = np.column_stack(
        (
            np.zeros(rows, dtype=np.int64),
            1 + np.searchsorted(ids, offense),
            1 + count + np.searchsorted(ids, defense),
        )
    )
    signs = np.tile([1.0] * 6 + [-1.0] * 5, rows)
    matrix = csr_matrix(
        (signs, columns.ravel(), np.arange(0, 11 * (rows + 1), 11)), shape=(rows, 1 + 2 * count)
    )
    matrix.sort_indices()
    players = matrix[:, 1:].tocsr()
    return Design(tuple(int(p) for p in ids), matrix, players, abs(players).tocsr())


@dataclass(frozen=True, slots=True)
class Block:
    """A scored block: fit on rows before ``cutoff``, score the whole games in ``scored``."""

    label: str
    season: int
    role: str  # "regular" or "playoffs"
    cutoff: date
    scored: NDArray[np.bool_]


def season_blocks(rows: Rows, season: int) -> list[Block]:
    """R1 to R4 (regular season by calendar block) and P (playoffs) for one scored season."""
    in_season = rows.season == season
    regular = in_season & ~rows.playoff
    playoff = in_season & rows.playoff
    if not regular.any():
        return []
    y0 = season
    bounds = (
        ("R1", date(y0, 10, 1), None, date(y0, 12, 1)),
        ("R2", date(y0, 12, 1), date(y0, 12, 1), date(y0 + 1, 2, 1)),
        ("R3", date(y0 + 1, 2, 1), date(y0 + 1, 2, 1), date(y0 + 1, 4, 1)),
        ("R4", date(y0 + 1, 4, 1), date(y0 + 1, 4, 1), None),
    )
    blocks: list[Block] = []
    for name, cutoff, start, end in bounds:
        mask = regular.copy()
        if start is not None:
            mask &= rows.day >= start.toordinal()
        if end is not None:
            mask &= rows.day < end.toordinal()
        blocks.append(Block(f"{season}-{name}", season, "regular", cutoff, mask))
    if playoff.any():
        first = date.fromordinal(int(np.min(rows.day[playoff])))
        blocks.append(Block(f"{season}-P", season, "playoffs", first, playoff))
    for block in blocks:
        if block.scored.any() and int(np.min(rows.day[block.scored])) < block.cutoff.toordinal():
            raise ValueError(f"block {block.label} scores a game played before its cutoff")
    return blocks


def check_game_dates(rows: Rows) -> None:
    """Each game has one played date, so no game can straddle a cutoff."""
    first = np.full(len(rows.game_ids), np.iinfo(np.int64).max)
    last = np.full(len(rows.game_ids), np.iinfo(np.int64).min)
    np.minimum.at(first, rows.game, rows.day)
    np.maximum.at(last, rows.game, rows.day)
    if np.any(first != last):
        raise ValueError("a game has more than one played date")


# --- fits and predictions --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PlayerFit:
    """Intercept and the 2m player effects (offense, then defense); zero for unused players."""

    intercept: float
    effects: NDArray[np.float64]
    used: NDArray[np.bool_]
    exposure: NDArray[np.float64]  # unweighted on-court possessions per player in the fit rows
    info: dict[str, float]

    def totals(self) -> NDArray[np.float64]:
        half = self.effects.size // 2
        total: NDArray[np.float64] = self.effects[:half] + self.effects[half:]
        return total


def fit_players(
    design: Design,
    index: NDArray[np.int64],
    response: NDArray[np.float64],
    weights: NDArray[np.float64],
    offense_ridge: float,
    defense_ridge: float,
) -> PlayerFit:
    """Fit the reference zero-prior two-penalty ridge on the design rows in ``index``."""
    for role, ridge in (("offense", offense_ridge), ("defense", defense_ridge)):
        if not np.isfinite(ridge) or ridge <= 0:
            raise ValueError(f"{role} ridge must be positive and finite")
    if index.size == 0:
        raise ValueError("a fit needs at least one row")
    if response.shape != index.shape or weights.shape != index.shape:
        raise ValueError("response and weights must align with the fit rows")
    if np.any(weights <= 0) or not np.all(np.isfinite(weights)):
        raise ValueError("fit weights must be positive and finite")
    info: dict[str, float] = {}
    started = time.perf_counter()
    subset = RAPMDesign(design.player_ids, design.matrix[index], response, weights)
    fit = _solve_rapm(subset, offense_ridge, defense_ridge, info=info)
    info["fit_seconds"] = time.perf_counter() - started
    info["rows"] = float(index.size)
    ids = design.player_ids
    effects = np.fromiter(
        chain((fit.offense[p] for p in ids), (fit.defense[p] for p in ids)),
        dtype=np.float64,
        count=2 * len(ids),
    )
    counts = np.asarray(design.on_court[index].sum(axis=0), dtype=np.float64).ravel()
    exposure = counts[: len(ids)] + counts[len(ids) :]
    return PlayerFit(fit.intercept, effects, exposure > 0, exposure, info)


def predict(
    fit: PlayerFit, design: Design, index: NDArray[np.int64], part: str = "both"
) -> NDArray[np.float64]:
    """Intercept plus summed offense minus summed defense; ``part`` zeroes one block."""
    effects = fit.effects.copy()
    half = design.size
    if part == "offense":
        effects[half:] = 0.0
    elif part == "defense":
        effects[:half] = 0.0
    elif part != "both":
        raise ValueError(part)
    prediction: NDArray[np.float64] = fit.intercept + design.players[index] @ effects
    return prediction


def fit_context(
    context: NDArray[np.float64], response: NDArray[np.float64], weights: NDArray[np.float64]
) -> tuple[float, NDArray[np.float64]]:
    """Weighted least squares on [1, Z]. Columns that are zero in every fit row get 0."""
    keep = np.any(context != 0, axis=0)
    intercept, gamma = fit_context_only(response, context[:, keep], weights)
    full = np.zeros(context.shape[1], dtype=np.float64)
    full[keep] = gamma
    return intercept, full


def effective_scales(
    design: Design,
    index: NDArray[np.int64],
    weights: NDArray[np.float64],
    offense_ridge: float,
    defense_ridge: float,
) -> dict[str, float]:
    """Total and Kish effective weight, and each penalty over the median weighted exposure."""
    exposure = design.on_court[index].T @ weights
    half = design.size
    offense = exposure[:half][exposure[:half] > 0]
    defense = exposure[half:][exposure[half:] > 0]
    total = float(weights.sum())
    median_offense = float(np.median(offense))
    median_defense = float(np.median(defense))
    return {
        "rows": float(index.size),
        "total_weight": total,
        "kish_effective_rows": total**2 / float((weights**2).sum()),
        "mean_weight": total / index.size,
        "median_weighted_offense_possessions": median_offense,
        "median_weighted_defense_possessions": median_defense,
        "offense_ridge_over_median": offense_ridge / median_offense,
        "defense_ridge_over_median": defense_ridge / median_defense,
    }


# --- scoring ---------------------------------------------------------------------------


def _reindex(values: NDArray[np.int64]) -> NDArray[np.int64]:
    _, inverse = np.unique(values, return_inverse=True)
    return inverse.astype(np.int64)


def week_clusters(day: NDArray[np.int64]) -> NDArray[np.int64]:
    """Calendar (ISO) week of each played date, as a cluster index."""
    keys = np.array(
        [
            (lambda iso: iso[0] * 100 + iso[1])(date.fromordinal(int(d)).isocalendar())
            for d in np.unique(day)
        ]
    )
    lookup = dict(zip(np.unique(day).tolist(), keys.tolist(), strict=True))
    return _reindex(np.array([lookup[int(d)] for d in day], dtype=np.int64))


def paired_delta(
    y: NDArray[np.float64],
    model: NDArray[np.float64],
    reference: NDArray[np.float64],
    clusters: dict[str, NDArray[np.int64]],
    resamples: int = BOOTSTRAP_RESAMPLES,
) -> dict[str, Any]:
    """Mean squared-error delta (model minus reference) with cluster-bootstrap intervals."""
    delta = (model - y) ** 2 - (reference - y) ** 2
    out: dict[str, Any] = {"delta": float(delta.mean())}
    for name, cluster in clusters.items():
        low, high = bootstrap_delta(_reindex(cluster), delta, resamples=resamples)
        out[f"ci95_{name}"] = [low, high]
    return out


def verdict(comparison: dict[str, Any]) -> str:
    """Frozen rule on the game-clustered interval: better, worse or inconclusive."""
    low, high = comparison["ci95_game"]
    if high < 0:
        return "better"
    if low > 0:
        return "worse"
    return "inconclusive"


def team_game_rmse(
    team_game: NDArray[np.int64], y: NDArray[np.float64], prediction: NDArray[np.float64]
) -> float:
    """RMSE in points of summed predicted against modeled points per scored team-game."""
    index = _reindex(team_game)
    size = int(np.max(index)) + 1
    actual = np.bincount(index, weights=y, minlength=size) / 100.0
    predicted = np.bincount(index, weights=prediction, minlength=size) / 100.0
    return float(np.sqrt(np.mean((predicted - actual) ** 2)))


def calibration(
    y: NDArray[np.float64],
    prediction: NDArray[np.float64],
    game: NDArray[np.int64],
    *,
    bins: int = CALIBRATION_BINS,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Calibration-in-the-large, the OLS slope of outcome on prediction and a quantile table.

    Intervals resample whole games. The slope is reported only when predictions vary.
    """
    cluster = _reindex(game)
    low, high = bootstrap_delta(cluster, y - prediction, resamples=resamples, seed=seed)
    out: dict[str, Any] = {
        "mean_outcome": float(y.mean()),
        "mean_prediction": float(prediction.mean()),
        "outcome_minus_prediction": float((y - prediction).mean()),
        "outcome_minus_prediction_ci95_game": [low, high],
    }
    if float(np.var(prediction)) <= 0:
        return out
    size = int(np.max(cluster)) + 1
    sums = np.stack(
        [
            np.bincount(cluster, weights=values, minlength=size)
            for values in (np.ones_like(y), prediction, y, prediction**2, prediction * y)
        ]
    )

    def slope(totals: NDArray[np.float64]) -> NDArray[np.float64]:
        n, sx, sy, sxx, sxy = totals
        result: NDArray[np.float64] = (sxy - sx * sy / n) / (sxx - sx**2 / n)
        return result

    rng = np.random.default_rng(seed)
    pick = rng.integers(0, size, size=(resamples, size))
    draws = slope(np.stack([sums[k][pick].sum(axis=1) for k in range(5)]))
    slope_low, slope_high = np.percentile(draws, [2.5, 97.5])
    out["slope"] = float(slope(sums.sum(axis=1)))
    out["slope_ci95_game"] = [float(slope_low), float(slope_high)]
    edges = np.quantile(prediction, np.linspace(0, 1, bins + 1))
    which = np.clip(np.searchsorted(edges, prediction, side="right") - 1, 0, bins - 1)
    table = []
    for b in range(bins):
        mask = which == b
        if not mask.any():
            continue
        lo, hi = bootstrap_delta(_reindex(game[mask]), y[mask], resamples=resamples, seed=seed)
        table.append(
            {
                "bin": b,
                "possessions": int(mask.sum()),
                "mean_prediction": float(prediction[mask].mean()),
                "mean_outcome": float(y[mask].mean()),
                "mean_outcome_ci95_game": [lo, hi],
            }
        )
    out["quantile_bins"] = table
    return out


# --- penalty search --------------------------------------------------------------------


def line_search(
    score: Callable[[float], float],
    centre: float,
    factors: Sequence[float] = SPLIT_FACTORS,
    extensions: int = SPLIT_EXTENSIONS,
) -> float:
    """Best of ``centre`` times {1, factors}, extending by twofold steps off an edge optimum."""
    values = sorted({centre, *(centre * f for f in factors)})
    scores = {value: score(value) for value in values}
    for _ in range(extensions):
        best = min(scores, key=lambda v: (scores[v], v))
        if best == min(scores):
            new = best / 2
        elif best == max(scores):
            new = best * 2
        else:
            return best
        scores[new] = score(new)
    return min(scores, key=lambda v: (scores[v], v))


def search_penalties(
    pooled_mse: Callable[[float, float], float],
) -> tuple[tuple[float, float], dict[tuple[float, float], float]]:
    """Protocol search: shared grid, then the defense penalty, then the offense penalty."""
    memo: dict[tuple[float, float], float] = {}

    def cached(offense: float, defense: float) -> float:
        key = (float(offense), float(defense))
        if key not in memo:
            memo[key] = pooled_mse(*key)
        return memo[key]

    shared, _ = select_penalty(lambda ridge: cached(ridge, ridge), PENALTY_GRID)
    defense = line_search(lambda d: cached(shared, d), shared)
    offense = line_search(lambda o: cached(o, defense), shared)
    return (offense, defense), memo


# --- development phase -----------------------------------------------------------------


@dataclass
class Scenario:
    """Rows available to fitting and scoring in one analysis (the primary or a sensitivity)."""

    name: str
    available: NDArray[np.bool_]


def scenario_masks(rows: Rows) -> list[Scenario]:
    everything = np.ones(len(rows), dtype=bool)
    return [
        Scenario("primary", everything),
        Scenario("exclude_2018_19", rows.season != 2018),
        Scenario("exclude_2021_22", rows.season != 2021),
        Scenario("exclude_overtime", rows.period < 5),
        Scenario("exclude_no_livedata", ~rows.no_livedata),
    ]


class Analysis:
    """Fits and scores for one scenario on the development blocks."""

    def __init__(
        self,
        rows: Rows,
        design: Design,
        scenario: Scenario,
        blocks: Sequence[Block],
        log: list[dict[str, Any]],
    ) -> None:
        self.rows = rows
        self.design = design
        self.scenario = scenario
        self.log = log
        self.blocks = [b for b in blocks if (b.scored & scenario.available).any()]
        self.regular = [b for b in self.blocks if b.role == "regular"]
        self.playoffs = [b for b in self.blocks if b.role == "playoffs"]
        self._windows: dict[tuple[date, str], tuple[NDArray[np.int64], NDArray[np.float64]]] = {}

    def window(
        self, cutoff: date, temporal: Temporal
    ) -> tuple[NDArray[np.int64], NDArray[np.float64]]:
        key = (cutoff, temporal.name)
        if key not in self._windows:
            weights = temporal_weights(self.rows.day, cutoff, temporal)
            weights[~self.scenario.available] = 0.0
            index = np.flatnonzero(weights > 0).astype(np.int64)
            if index.size and int(np.max(self.rows.day[index])) >= cutoff.toordinal():
                raise AssertionError("a fit row is not strictly before its cutoff")
            self._windows[key] = (index, weights[index])
        return self._windows[key]

    def scored(self, block: Block) -> NDArray[np.int64]:
        return np.flatnonzero(block.scored & self.scenario.available).astype(np.int64)

    def fit(
        self,
        cutoff: date,
        temporal: Temporal,
        offense_ridge: float,
        defense_ridge: float,
        *,
        offset: NDArray[np.float64] | None = None,
        restrict: NDArray[np.bool_] | None = None,
        label: str = "",
    ) -> PlayerFit:
        index, weights = self.window(cutoff, temporal)
        if restrict is not None:
            keep = restrict[index]
            index, weights = index[keep], weights[keep]
        response = self.rows.y[index] if offset is None else self.rows.y[index] - offset
        fit = fit_players(self.design, index, response, weights, offense_ridge, defense_ridge)
        self.log.append(
            {
                "scenario": self.scenario.name,
                "temporal": temporal.name,
                "cutoff": cutoff.isoformat(),
                "offense_ridge": offense_ridge,
                "defense_ridge": defense_ridge,
                "label": label,
                **fit.info,
            }
        )
        return fit

    def league(self, block: Block, temporal: Temporal) -> NDArray[np.float64]:
        index, weights = self.window(block.cutoff, temporal)
        mean = float(np.average(self.rows.y[index], weights=weights))
        return np.full(self.scored(block).size, mean)

    def context_fit(self, cutoff: date, temporal: Temporal) -> tuple[float, NDArray[np.float64]]:
        index, weights = self.window(cutoff, temporal)
        return fit_context(self.rows.context[index], self.rows.y[index], weights)

    def context(self, block: Block, temporal: Temporal) -> NDArray[np.float64]:
        intercept, gamma = self.context_fit(block.cutoff, temporal)
        prediction: NDArray[np.float64] = intercept + self.rows.context[self.scored(block)] @ gamma
        return prediction

    def rapm(
        self, block: Block, temporal: Temporal, offense_ridge: float, defense_ridge: float
    ) -> tuple[PlayerFit, dict[str, NDArray[np.float64]]]:
        fit = self.fit(block.cutoff, temporal, offense_ridge, defense_ridge, label=block.label)
        scored = self.scored(block)
        return fit, {
            part_name: predict(fit, self.design, scored, part)
            for part_name, part in (
                ("rapm", "both"),
                ("offense_only", "offense"),
                ("defense_only", "defense"),
            )
        }

    def rapm_context(
        self, block: Block, temporal: Temporal, offense_ridge: float, defense_ridge: float
    ) -> NDArray[np.float64]:
        """The #24 eligible-offset construction with the RAPM candidate's rows and weights."""
        _, gamma = self.context_fit(block.cutoff, temporal)
        index, _ = self.window(block.cutoff, temporal)
        offset = self.rows.context[index] @ gamma
        fit = self.fit(
            block.cutoff,
            temporal,
            offense_ridge,
            defense_ridge,
            offset=offset,
            label=f"{block.label}:context_offset",
        )
        scored = self.scored(block)
        prediction: NDArray[np.float64] = predict(fit, self.design, scored) + (
            self.rows.context[scored] @ gamma
        )
        return prediction

    def pooled_mse(self, temporal: Temporal, offense_ridge: float, defense_ridge: float) -> float:
        error = count = 0.0
        for block in self.regular:
            fit = self.fit(
                block.cutoff, temporal, offense_ridge, defense_ridge, label=f"{block.label}:search"
            )
            scored = self.scored(block)
            error += float(((predict(fit, self.design, scored) - self.rows.y[scored]) ** 2).sum())
            count += scored.size
        return error / count

    def baseline_mse(self, kind: str, temporal: Temporal) -> float:
        error = count = 0.0
        for block in self.regular:
            scored = self.scored(block)
            prediction = (
                self.league(block, temporal) if kind == "league" else self.context(block, temporal)
            )
            error += float(((prediction - self.rows.y[scored]) ** 2).sum())
            count += scored.size
        return error / count

    def pooled(
        self, blocks: Sequence[Block]
    ) -> tuple[NDArray[np.int64], dict[str, NDArray[np.int64]]]:
        index = np.concatenate([self.scored(b) for b in blocks])
        clusters = {"game": self.rows.game[index], "week": week_clusters(self.rows.day[index])}
        return index, clusters


def feasible(analysis: Analysis) -> list[Temporal]:
    """Candidates with at least one fit row at every scored block's cutoff in this scenario.

    A candidate whose window is empty at some cutoff (for example one season of history when
    that season is excluded) cannot be fitted there and is not selectable in the scenario.
    """
    return [
        t for t in TEMPORAL if all(analysis.window(b.cutoff, t)[0].size for b in analysis.blocks)
    ]


def _select_baselines(analysis: Analysis) -> dict[str, Any]:
    out: dict[str, Any] = {}
    candidates = feasible(analysis)
    for kind in ("league", "context"):
        scores = {t.name: analysis.baseline_mse(kind, t) for t in candidates}
        best = min(candidates, key=lambda t: scores[t.name]).name
        out[kind] = {"selected_temporal": best, "pooled_regular_mse": scores}
    return out


def _search_all(analysis: Analysis) -> dict[str, Any]:
    per_temporal: dict[str, Any] = {}
    candidates = feasible(analysis)
    for temporal in candidates:

        def pooled(o: float, d: float, t: Temporal = temporal) -> float:
            return analysis.pooled_mse(t, o, d)

        (offense, defense), memo = search_penalties(pooled)
        per_temporal[temporal.name] = {
            "offense_ridge": offense,
            "defense_ridge": defense,
            "pooled_regular_mse": memo[(offense, defense)],
            "evaluated": [
                {"offense_ridge": o, "defense_ridge": d, "pooled_regular_mse": v}
                for (o, d), v in sorted(memo.items())
            ],
        }
    order = {t.name: i for i, t in enumerate(TEMPORAL)}
    best = min(per_temporal, key=lambda n: (per_temporal[n]["pooled_regular_mse"], order[n]))
    return {
        "selected_temporal": best,
        "per_temporal": per_temporal,
        "infeasible": [t.name for t in TEMPORAL if t not in candidates],
    }


@dataclass
class Scored:
    """Held-out predictions of every model over a list of blocks, aligned to ``index``."""

    index: NDArray[np.int64]
    predictions: dict[str, NDArray[np.float64]]
    fits: dict[str, PlayerFit]


def _score_blocks(
    analysis: Analysis,
    blocks: Sequence[Block],
    temporal: Temporal,
    offense_ridge: float,
    defense_ridge: float,
    baselines: dict[str, Temporal],
    *,
    with_context_offset: bool,
) -> Scored:
    parts: dict[str, list[NDArray[np.float64]]] = {}
    fits: dict[str, PlayerFit] = {}
    for block in blocks:
        fit, rapm = analysis.rapm(block, temporal, offense_ridge, defense_ridge)
        fits[block.label] = fit
        rapm["league"] = analysis.league(block, baselines["league"])
        rapm["context"] = analysis.context(block, baselines["context"])
        rapm["league_same_window"] = analysis.league(block, temporal)
        if with_context_offset:
            rapm["rapm_context"] = analysis.rapm_context(
                block, temporal, offense_ridge, defense_ridge
            )
        for name, values in rapm.items():
            parts.setdefault(name, []).append(values)
    index = np.concatenate([analysis.scored(b) for b in blocks])
    return Scored(index, {k: np.concatenate(v) for k, v in parts.items()}, fits)


def summarize(rows: Rows, scored: Scored, comparisons: Sequence[tuple[str, str]]) -> dict[str, Any]:
    """MSE per model, paired deltas with game and week bootstrap intervals, team-game RMSE."""
    index = scored.index
    y = rows.y[index]
    clusters = {"game": rows.game[index], "week": week_clusters(rows.day[index])}
    out: dict[str, Any] = {
        "possessions": int(index.size),
        "games": int(np.unique(rows.game[index]).size),
        "mean_points_per_100": float(y.mean()),
        "mse": {k: float(np.mean((v - y) ** 2)) for k, v in scored.predictions.items()},
        "team_game_rmse_points": {
            k: team_game_rmse(rows.team_game[index], y, v) for k, v in scored.predictions.items()
        },
        "comparisons": {},
    }
    for model, reference in comparisons:
        if model in scored.predictions and reference in scored.predictions:
            entry = paired_delta(
                y, scored.predictions[model], scored.predictions[reference], clusters
            )
            entry["verdict"] = verdict(entry)
            out["comparisons"][f"{model}_minus_{reference}"] = entry
    return out


DEV_COMPARISONS = (
    ("rapm", "league"),
    ("rapm", "context"),
    ("rapm", "league_same_window"),
    ("offense_only", "league"),
    ("defense_only", "league"),
    ("context", "league"),
    ("rapm_context", "context"),
    ("rapm_context", "league"),
)


def compare_fits(
    reference: PlayerFit,
    other: PlayerFit,
    bands_from: NDArray[np.float64],
    players: NDArray[np.bool_] | None = None,
) -> dict[str, Any]:
    """RMS change and correlation of offense, defense and total for players used in both."""
    common = reference.used & other.used if players is None else players
    half = reference.effects.size // 2
    arrays = {
        "offense": (reference.effects[:half], other.effects[:half]),
        "defense": (reference.effects[half:], other.effects[half:]),
        "total": (reference.totals(), other.totals()),
    }

    def stats(mask: NDArray[np.bool_]) -> dict[str, Any]:
        entry: dict[str, Any] = {"players": int(mask.sum())}
        if mask.sum() < 3:
            return entry
        for name, (a, b) in arrays.items():
            entry[name] = {
                "rms_change": float(np.sqrt(np.mean((a[mask] - b[mask]) ** 2))),
                "correlation": float(np.corrcoef(a[mask], b[mask])[0, 1]),
            }
        return entry

    result = stats(common)
    result["by_exposure_band"] = {
        _band_label(lo, hi): stats(
            common & (bands_from >= lo) & (bands_from < (np.inf if hi is None else hi))
        )
        for lo, hi in EXPOSURE_BANDS
    }
    return result


def _band_label(lo: int, hi: int | None) -> str:
    return f"{lo}-{'inf' if hi is None else hi}"


def split_halves(
    rows: Rows, index: NDArray[np.int64]
) -> tuple[NDArray[np.bool_], NDArray[np.bool_]]:
    """Alternate the window's games in (date, game id) order into two disjoint halves."""
    games = np.unique(rows.game[index])
    order = sorted(
        games.tolist(), key=lambda g: (int(rows.day[rows.game == g][0]), rows.game_ids[g])
    )
    half = np.full(len(rows.game_ids), -1)
    for i, g in enumerate(order):
        half[g] = i % 2
    first = half[rows.game] == 0
    second = half[rows.game] == 1
    return first, second


def _stability(
    analysis: Analysis,
    temporal: Temporal,
    offense_ridge: float,
    defense_ridge: float,
    refits: dict[str, PlayerFit],
) -> tuple[dict[str, Any], PlayerFit]:
    rows, design = analysis.rows, analysis.design
    final = analysis.fit(DEV_END, temporal, offense_ridge, defense_ridge, label="final")
    previous = analysis.fit(
        date(2022, 7, 1), temporal, offense_ridge, defense_ridge, label="year_end_2022"
    )
    index, _ = analysis.window(DEV_END, temporal)
    first, second = split_halves(rows, index)
    halves = [
        analysis.fit(DEV_END, temporal, offense_ridge, defense_ridge, restrict=m, label=f"half{i}")
        for i, m in enumerate((first, second), start=1)
    ]
    roles = []
    for m in (first, second):
        sub = index[m[index]]
        counts = np.asarray(design.on_court[sub].sum(axis=0)).ravel()
        roles.append(np.minimum(counts[: design.size], counts[design.size :]))
    eligible = (roles[0] >= HALF_MIN_POSSESSIONS) & (roles[1] >= HALF_MIN_POSSESSIONS)
    out: dict[str, Any] = {
        "split_halves": compare_fits(halves[0], halves[1], final.exposure, eligible),
        "year_over_year": compare_fits(previous, final, final.exposure),
    }
    volatility: dict[str, Any] = {}
    season_type: dict[str, Any] = {}
    for season, year_end in ((2021, previous), (2022, final)):
        labels = [f"{season}-R{i}" for i in range(1, 5)] + [f"{season}-P"]
        present = [label for label in labels if label in refits]
        for a, b in zip(present, present[1:], strict=False):
            volatility[f"{a}_to_{b}"] = compare_fits(refits[a], refits[b], refits[b].exposure)
        if f"{season}-P" in refits:
            season_type[f"{season}_playoff_cutoff_to_year_end"] = compare_fits(
                refits[f"{season}-P"], year_end, year_end.exposure
            )
    out["refit_volatility"] = volatility
    out["season_type"] = season_type
    return out, final


def _oracle(analysis: Analysis, block: Block) -> dict[str, float]:
    """Independent check of the design reuse and weights against the dated reference path."""
    rows = analysis.rows
    out: dict[str, float] = {}
    for name in ("W2", "H365"):
        temporal = TEMPORAL_BY_NAME[name]
        index, _ = analysis.window(block.cutoff, temporal)
        ours = analysis.fit(block.cutoff, temporal, 4000.0, 8000.0, label="oracle")
        possessions = [
            Possession(
                tuple(int(p) for p in rows.offense[i]),
                tuple(int(p) for p in rows.defense[i]),
                float(rows.y[i]) / 100.0,
                1.0,
                date.fromordinal(int(rows.day[i])),
            )
            for i in index
        ]
        reference: RAPMFit
        if temporal.half_life_days is None:
            reference = fit_prior_rapm(possessions, offense_ridge=4000.0, defense_ridge=8000.0)
        else:
            reference = fit_dated_prior_rapm(
                possessions,
                as_of=block.cutoff,
                half_life_days=temporal.half_life_days,
                offense_ridge=4000.0,
                defense_ridge=8000.0,
            ).fit
        ids = analysis.design.player_ids
        diffs = [abs(reference.intercept - ours.intercept)]
        for j, p in enumerate(ids):
            if p in reference.offense:
                diffs.append(abs(reference.offense[p] - ours.effects[j]))
                diffs.append(abs(reference.defense[p] - ours.effects[len(ids) + j]))
            elif ours.used[j]:
                raise AssertionError("a used player is missing from the reference fit")
        out[name] = max(diffs)
        if out[name] > ORACLE_TOLERANCE:
            raise AssertionError(f"design reuse differs from the reference solver by {out[name]}")
    return out


def run_development(rows: Rows, design: Design, log: list[dict[str, Any]]) -> dict[str, Any]:
    """Phase 1 on development rows only. Returns the aggregate results."""
    if set(np.unique(rows.season).tolist()) - set(DEV_SEASONS):
        raise ValueError("development rows must come from 2018-19 through 2022-23 only")
    if int(np.max(rows.day)) >= DEV_END.toordinal():
        raise ValueError("a development row is dated on or after 2023-07-01")
    check_game_dates(rows)
    blocks = [b for s in DEV_SCORED_SEASONS for b in season_blocks(rows, s)]
    results: dict[str, Any] = {
        "blocks": {
            b.label: {
                "cutoff": b.cutoff.isoformat(),
                "role": b.role,
                "possessions": int(b.scored.sum()),
                "games": int(np.unique(rows.game[b.scored]).size),
            }
            for b in blocks
        },
        "scenarios": {},
    }
    primary_predictions: NDArray[np.float64] | None = None
    primary_final: PlayerFit | None = None
    primary_config: tuple[Temporal, float, float] | None = None
    comparisons = DEV_COMPARISONS
    for scenario in scenario_masks(rows):
        started = time.perf_counter()
        analysis = Analysis(rows, design, scenario, blocks, log)
        baselines_report = _select_baselines(analysis)
        baselines = {
            kind: TEMPORAL_BY_NAME[baselines_report[kind]["selected_temporal"]]
            for kind in ("league", "context")
        }
        search = _search_all(analysis)
        report: dict[str, Any] = {
            "blocks_scored": [b.label for b in analysis.blocks],
            "baselines": baselines_report,
            "search": search,
            "per_temporal": {},
        }
        if scenario.name == "primary":
            report["oracle_max_abs_diff"] = _oracle(analysis, analysis.regular[0])
        selected = TEMPORAL_BY_NAME[search["selected_temporal"]]
        for temporal in TEMPORAL:
            if temporal.name not in search["per_temporal"]:
                continue
            chosen = search["per_temporal"][temporal.name]
            o, d = chosen["offense_ridge"], chosen["defense_ridge"]
            is_selected = temporal == selected
            if scenario.name != "primary" and not is_selected:
                continue
            regular = _score_blocks(
                analysis,
                analysis.regular,
                temporal,
                o,
                d,
                baselines,
                with_context_offset=is_selected,
            )
            playoffs = _score_blocks(
                analysis,
                analysis.playoffs,
                temporal,
                o,
                d,
                baselines,
                with_context_offset=is_selected,
            )
            entry: dict[str, Any] = {
                "offense_ridge": o,
                "defense_ridge": d,
                "regular_pooled": summarize(rows, regular, comparisons),
                "playoffs_pooled": summarize(rows, playoffs, comparisons),
                "per_block": {
                    b.label: summarize(
                        rows,
                        _restrict(regular if b.role == "regular" else playoffs, analysis.scored(b)),
                        (("rapm", "league"), ("rapm", "context")),
                    )
                    for b in analysis.blocks
                },
                "effective_scales": {
                    b.label: effective_scales(design, *analysis.window(b.cutoff, temporal), o, d)
                    for b in analysis.blocks
                },
            }
            if scenario.name == "primary":
                refits = {**regular.fits, **playoffs.fits}
                stability, final = _stability(analysis, temporal, o, d, refits)
                entry["stability"] = stability
                entry["final_fit"] = {
                    "players": int(final.used.sum()),
                    "intercept": final.intercept,
                    "effective_scales": effective_scales(
                        design, *analysis.window(DEV_END, temporal), o, d
                    ),
                    "total_sd": float(final.totals()[final.used].std()),
                    "offense_sd": float(final.effects[: design.size][final.used].std()),
                    "defense_sd": float(final.effects[design.size :][final.used].std()),
                }
                if is_selected:
                    primary_final = final
                    primary_config = (temporal, o, d)
                    primary_predictions = np.full(len(rows), np.nan)
                    primary_predictions[regular.index] = regular.predictions["rapm"]
                    primary_predictions[playoffs.index] = playoffs.predictions["rapm"]
            report["per_temporal"][temporal.name] = entry
        if scenario.name != "primary":
            assert primary_config is not None and primary_final is not None
            assert primary_predictions is not None
            if primary_config[0].name in search["per_temporal"]:
                report["primary_config_under_scenario"] = _sensitivity_extras(
                    analysis, primary_config, primary_final, primary_predictions, results
                )
            else:
                report["primary_config_under_scenario"] = {"infeasible": True}
        report["seconds"] = time.perf_counter() - started
        results["scenarios"][scenario.name] = report
    assert primary_config is not None and primary_final is not None
    temporal, o, d = primary_config
    results["selected"] = {
        "temporal": temporal.name,
        "max_age_days": temporal.max_age_days,
        "half_life_days": temporal.half_life_days,
        "offense_ridge": o,
        "defense_ridge": d,
        "league_temporal": results["scenarios"]["primary"]["baselines"]["league"][
            "selected_temporal"
        ],
        "context_temporal": results["scenarios"]["primary"]["baselines"]["context"][
            "selected_temporal"
        ],
    }
    results["_final_fit"] = primary_final
    return results


def _restrict(scored: Scored, index: NDArray[np.int64]) -> Scored:
    keep = np.isin(scored.index, index)
    return Scored(scored.index[keep], {k: v[keep] for k, v in scored.predictions.items()}, {})


def _sensitivity_extras(
    analysis: Analysis,
    config: tuple[Temporal, float, float],
    primary_final: PlayerFit,
    primary_predictions: NDArray[np.float64],
    results: dict[str, Any],
) -> dict[str, Any]:
    temporal, o, d = config
    rows = analysis.rows
    primary = results["scenarios"]["primary"]["search"]["per_temporal"]
    here = analysis.pooled_mse(temporal, o, d)
    reduced: list[NDArray[np.float64]] = []
    full: list[NDArray[np.float64]] = []
    index_parts: list[NDArray[np.int64]] = []
    for block in analysis.regular:
        fit = analysis.fit(block.cutoff, temporal, o, d, label=f"{block.label}:primary_config")
        scored = analysis.scored(block)
        reduced.append(predict(fit, analysis.design, scored))
        full.append(primary_predictions[scored])
        index_parts.append(scored)
    index = np.concatenate(index_parts)
    y = rows.y[index]
    full_prediction = np.concatenate(full)
    if np.any(np.isnan(full_prediction)):
        raise AssertionError("a sensitivity row was not scored in the primary analysis")
    paired = paired_delta(
        y,
        np.concatenate(reduced),
        full_prediction,
        {"game": rows.game[index], "week": week_clusters(rows.day[index])},
    )
    final = analysis.fit(DEV_END, temporal, o, d, label="final_primary_config")
    return {
        "pooled_regular_mse": here,
        "primary_analysis_pooled_regular_mse": primary[temporal.name]["pooled_regular_mse"],
        "reduced_fit_minus_full_fit_on_scenario_rows": paired,
        "final_fit_shift": compare_fits(primary_final, final, primary_final.exposure),
    }


def sensitivity_summary(results: dict[str, Any]) -> dict[str, Any]:
    """Selection changes: chosen configuration, rank of the primary one, rank correlation."""
    from scipy.stats import spearmanr  # type: ignore[import-untyped]

    primary = results["scenarios"]["primary"]["search"]
    selected = results["selected"]["temporal"]
    out: dict[str, Any] = {}
    for name, report in results["scenarios"].items():
        if name == "primary":
            continue
        search = report["search"]
        common = [t for t in TEMPORAL if t.name in search["per_temporal"]]
        scores = [search["per_temporal"][t.name]["pooled_regular_mse"] for t in common]
        reference = [primary["per_temporal"][t.name]["pooled_regular_mse"] for t in common]
        ranking = [
            t.name
            for t in sorted(
                common, key=lambda t: search["per_temporal"][t.name]["pooled_regular_mse"]
            )
        ]
        chosen = search["selected_temporal"]
        entry = report["per_temporal"][chosen]
        out[name] = {
            "selected_temporal": chosen,
            "offense_ridge": entry["offense_ridge"],
            "defense_ridge": entry["defense_ridge"],
            "selected_minus_league": entry["regular_pooled"]["comparisons"]["rapm_minus_league"],
            "baselines": {
                k: report["baselines"][k]["selected_temporal"] for k in ("league", "context")
            },
            "infeasible_candidates": search["infeasible"],
            "primary_temporal_rank": 1 + ranking.index(selected) if selected in ranking else None,
            "candidate_rank_correlation_over_feasible": float(spearmanr(reference, scores)[0]),
            **report["primary_config_under_scenario"],
        }
    return out


# --- outer phase -----------------------------------------------------------------------


class AddendumError(RuntimeError):
    """The outer runner was not given a valid, committed, frozen addendum."""


FROZEN_BLOCK = re.compile(r"<!-- frozen-config -->\s*```json\n(.*?)\n```", re.DOTALL)


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False, cwd=repo)


def verify_addendum(path: Path | None, expected_sha256: str | None, repo: Path) -> dict[str, Any]:
    """Refuse unless the addendum exists, matches its digest, is committed and the tree is clean."""
    if path is None or expected_sha256 is None:
        raise AddendumError("the outer runner requires the frozen addendum and its SHA-256")
    if not path.is_file():
        raise AddendumError(f"addendum {path} does not exist")
    actual = _sha256(path)
    if actual != expected_sha256:
        raise AddendumError(f"addendum SHA-256 {actual} does not match {expected_sha256}")
    try:
        relative = path.resolve().relative_to(repo.resolve())
    except ValueError as exc:
        raise AddendumError("the addendum must be inside the repository") from exc
    if _run_git(repo, "ls-files", "--error-unmatch", str(relative)).returncode != 0:
        raise AddendumError("the addendum is not committed")
    if _run_git(repo, "diff", "--quiet", "HEAD", "--", str(relative)).returncode != 0:
        raise AddendumError("the addendum differs from the committed version")
    status = _run_git(repo, "status", "--porcelain")
    if status.returncode != 0 or status.stdout.strip():
        raise AddendumError("the working tree is not clean")
    return {
        "path": str(relative),
        "sha256": actual,
        "addendum_commit": _run_git(
            repo, "log", "-1", "--format=%H", "--", str(relative)
        ).stdout.strip(),
        "head_commit": _run_git(repo, "rev-parse", "HEAD").stdout.strip(),
        "committed": True,
        "working_tree_clean": True,
    }


def parse_frozen(text: str) -> dict[str, Any]:
    """Read and validate the machine-readable frozen configuration of the addendum."""
    match = FROZEN_BLOCK.search(text)
    if match is None:
        raise AddendumError("the addendum has no frozen-config block")
    config: dict[str, Any] = json.loads(match.group(1))
    if config.get("issue") != 26 or config.get("outer_seasons") != list(OUTER_SEASONS):
        raise AddendumError("the frozen block must be for #26 and seasons 2023 and 2024 only")
    primary = config["primary"]
    for name in (primary["temporal"], config["league_temporal"], config["context_temporal"]):
        if name not in TEMPORAL_BY_NAME:
            raise AddendumError(f"unknown temporal candidate {name}")
    for key in ("offense_ridge", "defense_ridge"):
        value = float(primary[key])
        if not np.isfinite(value) or value <= 0:
            raise AddendumError(f"{key} must be positive and finite")
    for key in ("dev_manifest_sha256", "protocol_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(config.get(key, ""))):
            raise AddendumError(f"{key} must be a SHA-256")
    return config


OUTER_COMPARISONS = (
    ("rapm", "league"),
    ("rapm", "context"),
    ("rapm_context", "context"),
    ("rapm_context", "league"),
    ("context", "league"),
    ("offense_only", "league"),
    ("defense_only", "league"),
)


def run_outer(
    rows: Rows, design: Design, config: dict[str, Any], log: list[dict[str, Any]]
) -> dict[str, Any]:
    """Phase 2: walk-forward scoring of the frozen configuration on 2023-24 and 2024-25."""
    seasons = set(np.unique(rows.season).tolist())
    if seasons - set(DEV_SEASONS) - set(OUTER_SEASONS):
        raise ValueError("outer rows must come from 2018-19 through 2024-25 only")
    check_game_dates(rows)
    temporal = TEMPORAL_BY_NAME[config["primary"]["temporal"]]
    o = float(config["primary"]["offense_ridge"])
    d = float(config["primary"]["defense_ridge"])
    baselines = {
        "league": TEMPORAL_BY_NAME[config["league_temporal"]],
        "context": TEMPORAL_BY_NAME[config["context_temporal"]],
    }
    everything = Scenario("outer", np.ones(len(rows), dtype=bool))
    blocks = [b for s in OUTER_SEASONS for b in season_blocks(rows, s)]
    analysis = Analysis(rows, design, everything, blocks, log)
    scored = _score_blocks(analysis, blocks, temporal, o, d, baselines, with_context_offset=True)
    for block in blocks:
        index, _ = analysis.window(block.cutoff, temporal)
        if int(np.max(rows.day[index])) >= block.cutoff.toordinal():
            raise AssertionError("an outer fit used a row on or after its cutoff")
    unseen = np.zeros(len(rows), dtype=bool)
    for block in blocks:
        fit = scored.fits[block.label]
        idx = analysis.scored(block)
        sub = design.on_court[idx]
        unseen[idx] = (
            np.asarray(sub @ (~np.concatenate([fit.used, fit.used])).astype(np.float64)).ravel() > 0
        )

    def subset(mask: NDArray[np.bool_]) -> Scored:
        keep = mask[scored.index]
        return Scored(scored.index[keep], {k: v[keep] for k, v in scored.predictions.items()}, {})

    sets: dict[str, NDArray[np.bool_]] = {}
    for season in OUTER_SEASONS:
        for role in ("regular", "playoffs"):
            sets[f"{season}_{role}"] = (rows.season == season) & (
                rows.playoff == (role == "playoffs")
            )
    for role in ("regular", "playoffs"):
        sets[f"pooled_{role}"] = np.isin(rows.season, OUTER_SEASONS) & (
            rows.playoff == (role == "playoffs")
        )
    summaries: dict[str, Any] = {}
    for name, mask in sets.items():
        part = subset(mask)
        entry = summarize(rows, part, OUTER_COMPARISONS)
        y = rows.y[part.index]
        game = rows.game[part.index]
        entry["calibration"] = {
            model: calibration(y, part.predictions[model], game)
            for model in ("rapm", "rapm_context", "context", "league")
        }
        entry["possessions_with_unseen_player"] = int(unseen[part.index].sum())
        summaries[name] = entry
    per_block = {
        b.label: {
            "cutoff": b.cutoff.isoformat(),
            **summarize(rows, subset(b.scored), (("rapm", "league"), ("rapm", "context"))),
            "effective_scales": effective_scales(
                design, *analysis.window(b.cutoff, temporal), o, d
            ),
        }
        for b in blocks
    }
    refits = scored.fits
    labels = [b.label for b in blocks]
    volatility = {
        f"{a}_to_{b}": compare_fits(refits[a], refits[b], refits[b].exposure)
        for a, b in zip(labels, labels[1:], strict=False)
    }
    return {
        "configuration": {
            "temporal": temporal.name,
            "offense_ridge": o,
            "defense_ridge": d,
            **{f"{k}_temporal": v.name for k, v in baselines.items()},
        },
        "sets": summaries,
        "per_block": per_block,
        "refit_volatility": volatility,
        "_scored": scored,
        "_unseen": unseen,
    }


# --- I/O -------------------------------------------------------------------------------

ROW_SQL = """
SELECT c.game_id, c.season_type, c.game_date, c.season_start_year, c.period,
       c.possession_seq, c.model_points, c.offense_team_id,
       c.offense_home, coalesce(c.neutral_site, false) AS neutral,
       c.neutral_site IS NULL AS neutral_unknown, c.home_before, c.away_before,
       c.elapsed_before_ms, c.prior_seq IS NULL AS no_prior,
       len(c.offense_player_ids) AS off_n, len(c.defense_player_ids) AS def_n,
       {players}
FROM context c
ORDER BY c.game_date, c.game_id, c.possession_seq
"""


def verify_row_set(row_dir: Path, season: int, pin: SeasonPin) -> dict[str, Any]:
    actual = _sha256(row_dir / "manifest.json")
    if actual != pin.row_manifest_sha256:
        raise ValueError(f"{pin.label} row-set manifest SHA-256 {actual} differs from the pin")
    manifest: dict[str, Any] = json.loads((row_dir / "manifest.json").read_text())
    if (
        manifest["season_start_year"] != season
        or manifest["evidence_tier"] != EVIDENCE_TIER
        or manifest["variant"] != "canonical"
        or manifest["pilot_manifest_sha256"] != pin.pilot_manifest_sha256
    ):
        raise ValueError(f"{pin.label} row-set manifest differs from the pinned identity")
    listed = {a["filename"]: a["sha256"] for a in manifest["output_artifacts"]}
    for name in ("model_row.parquet", "game_reconciliation.parquet"):
        if _sha256(row_dir / name) != listed[name]:
            raise ValueError(f"{pin.label} {name} differs from its manifest digest")
    return manifest


def verify_pilot(pilot_dir: Path, pin: SeasonPin, row_manifest: dict[str, Any]) -> dict[str, str]:
    if _sha256(pilot_dir / "manifest.json") != pin.pilot_manifest_sha256:
        raise ValueError(f"{pin.label} pilot manifest differs from the pin")
    listed = {
        a["filename"]: a["sha256"]
        for a in json.loads((pilot_dir / "manifest.json").read_text())["output_artifacts"]
    }
    digests: dict[str, str] = {}
    for name in ("event.parquet", "game.parquet", "score_allocation.parquet"):
        expected = row_manifest["pilot_input_tables"][name]
        if listed.get(name) != expected or _sha256(pilot_dir / name) != expected:
            raise ValueError(f"{pin.label} pilot {name} differs from the pinned digest")
        digests[name] = expected
    return digests


@dataclass
class SeasonLoad:
    season: int
    pin: SeasonPin
    row_manifest: dict[str, Any]
    pilot_digests: dict[str, str]
    audit: dict[str, int]
    coverage: dict[str, Any]
    data: dict[str, NDArray[Any]]
    no_livedata_games: set[str]


def _count(connection: Any, sql: str) -> int:
    row = connection.execute(sql).fetchone()
    if row is None:
        raise ValueError("a count query returned no row")
    return int(row[0])


def load_season(processed: Path, season: int, allowed: Iterable[int], temp: Path) -> SeasonLoad:
    """Verify and read one season's rows and pre-possession context. Holdout seasons refuse."""
    import duckdb

    pin = check_season(season, allowed)
    row_dir = processed / pin.label / ROW_SET_VERSION
    pilot_dir = processed / pin.label / pin.pilot_build
    manifest = verify_row_set(row_dir, season, pin)
    digests = verify_pilot(pilot_dir, pin, manifest)
    connection = duckdb.connect()
    connection.execute(f"SET temp_directory = '{str(temp).replace(chr(39), chr(39) * 2)}'")
    register(connection, row_dir, pilot_dir)
    for table in ("game", "model_row"):
        years = {
            r[0]
            for r in connection.execute(
                f"SELECT DISTINCT season_start_year FROM {table}"
            ).fetchall()
        }
        if years != {season}:
            raise ValueError(f"{pin.label} {table} has seasons {years}")
    if connection.execute("SELECT count(*) FROM model_row WHERE weight <> 1.0").fetchone() != (0,):
        raise ValueError("model rows must have unit weight (ADR-0013)")
    connection.execute(f"CREATE OR REPLACE TEMP TABLE context AS {CONTEXT_SQL}")
    connection.execute(
        "CREATE OR REPLACE TEMP VIEW game_latest AS SELECT game_id, home_team_id, away_team_id "
        "FROM game QUALIFY row_number() OVER (PARTITION BY game_id ORDER BY revision DESC) = 1"
    )
    audit = {name: _count(connection, sql) for name, sql in TIMING_SQL.items()}
    if audit["own_points_sequenced_before_start"] or audit["event_and_allocation_scores_disagree"]:
        raise ValueError(f"{pin.label} pre-possession covariates fail the timing audit: {audit}")
    players = ", ".join(
        f"CAST(c.{side}_player_ids[{i}] AS BIGINT) AS {side[0]}{i}"
        for side in ("offense", "defense")
        for i in range(1, 6)
    )
    data = connection.execute(ROW_SQL.format(players=players)).fetchnumpy()
    if np.any(data["off_n"] != 5) or np.any(data["def_n"] != 5):
        raise ValueError("every model row needs five players on each side")
    period = np.asarray(data["period"], dtype=np.int64)
    elapsed = np.asarray(data["elapsed_before_ms"], dtype=np.float64)
    audit["prior_clock_before_period_start_clamped"] = int(
        np.sum(elapsed < period_start_ms(period))
    )
    audit["possessions_without_prior_event"] = int(np.sum(data["no_prior"]))
    reconciliation = str(row_dir / "game_reconciliation.parquet").replace("'", "''")
    coverage_rows = connection.execute(
        f"SELECT season_type, count(*), count(*) FILTER (accepted), "
        f"count(*) FILTER (NOT accepted), sum(eligible) FILTER (accepted) "
        f"FROM read_parquet('{reconciliation}') GROUP BY 1 ORDER BY 1"
    ).fetchall()
    coverage = {
        r[0]: {
            "games_in_reconciliation": int(r[1]),
            "games_accepted": int(r[2]),
            "games_quarantined_not_scored": int(r[3]),
            "eligible_possessions": int(r[4] or 0),
        }
        for r in coverage_rows
    }
    no_livedata = {
        r[0]
        for r in connection.execute(
            f"SELECT game_id FROM read_parquet('{reconciliation}') "
            "WHERE accepted AND list_contains(strata, 'no_livedata')"
        ).fetchall()
    }
    connection.close()
    return SeasonLoad(season, pin, manifest, digests, audit, coverage, data, no_livedata)


def assemble(loads: Sequence[SeasonLoad]) -> Rows:
    """Concatenate seasons in chronological order and derive the context columns."""
    data = {k: np.concatenate([np.asarray(s.data[k]) for s in loads]) for k in loads[0].data}
    game_text = data["game_id"].astype(str)
    game_ids, game = np.unique(game_text, return_inverse=True)
    team_text = np.char.add(np.char.add(game_text, ":"), data["offense_team_id"].astype(str))
    _, team_game = np.unique(team_text, return_inverse=True)
    day = np.array(
        [d.toordinal() for d in data["game_date"].astype("datetime64[D]").astype(object)]
    )
    period = data["period"].astype(np.int64)
    offense_home = data["offense_home"].astype(bool)
    home_before = data["home_before"].astype(np.float64)
    away_before = data["away_before"].astype(np.float64)
    margin = np.where(offense_home, home_before - away_before, away_before - home_before)
    elapsed = np.maximum(data["elapsed_before_ms"].astype(np.float64), period_start_ms(period))
    covariates = ContextRows(
        observations=[],  # only the covariate arrays below are read by feature_columns
        dates=[],
        offense_home=offense_home,
        neutral=data["neutral"].astype(bool),
        neutral_unknown=data["neutral_unknown"].astype(bool),
        margin=margin,
        period=period,
        elapsed_ms=elapsed,
    )
    columns = feature_columns(covariates)
    no_livedata_games = set().union(*(s.no_livedata_games for s in loads))
    return Rows(
        season=data["season_start_year"].astype(np.int64),
        playoff=data["season_type"].astype(str) == "playoffs",
        day=day.astype(np.int64),
        game=game.astype(np.int64),
        game_ids=tuple(str(g) for g in game_ids),
        team_game=team_game.astype(np.int64),
        possession_seq=data["possession_seq"].astype(np.int64),
        period=period,
        y=100.0 * data["model_points"].astype(np.float64),
        offense=np.column_stack([data[f"o{i}"] for i in range(1, 6)]).astype(np.int64),
        defense=np.column_stack([data[f"d{i}"] for i in range(1, 6)]).astype(np.int64),
        context=np.column_stack([columns[name] for name in CONTEXT_COLUMNS]),
        no_livedata=np.isin(game_text, sorted(no_livedata_games)),
    )


def outcome_digest(rows: Rows, mask: NDArray[np.bool_]) -> str:
    """SHA-256 of the scored outcomes: sorted ``game_id,possession_seq,points_per_100`` lines."""
    lines = sorted(
        f"{rows.game_ids[g]},{s},{v!r}"
        for g, s, v in zip(
            rows.game[mask].tolist(),
            rows.possession_seq[mask].tolist(),
            rows.y[mask].tolist(),
            strict=True,
        )
    )
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def _versions() -> dict[str, str]:
    import duckdb
    import scipy  # type: ignore[import-untyped]

    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "duckdb": duckdb.__version__,
    }


def _solver_summary(log: Sequence[dict[str, Any]]) -> dict[str, Any]:
    iterations = [e["iterations"] for e in log]
    largest = max(log, key=lambda e: e["rows"])
    return {
        "fits": len(log),
        "all_converged": all(e["stop"] in {0, 1, 2, 4, 5} for e in log),
        "stop_codes": dict(Counter(int(e["stop"]) for e in log)),
        "iterations": {
            "min": min(iterations),
            "median": float(np.median(iterations)),
            "max": max(iterations),
        },
        "max_condition_estimate": max(e["condition_estimate"] for e in log),
        "total_fit_seconds": sum(e["fit_seconds"] for e in log),
        "median_fit_seconds": float(np.median([e["fit_seconds"] for e in log])),
        "largest_fit": {k: largest[k] for k in ("rows", "fit_seconds", "iterations", "temporal")},
    }


def _prepare(
    processed: Path, seasons: Sequence[int], allowed: Iterable[int], output_dir: Path
) -> tuple[list[SeasonLoad], Rows, Design, dict[str, Any]]:
    temp = output_dir / "duckdb_tmp"
    temp.mkdir()
    loads = [load_season(processed, s, allowed, temp) for s in seasons]
    shutil.rmtree(temp)
    started = time.perf_counter()
    rows = assemble(loads)
    design = build_matrix(rows.offense, rows.defense)
    inputs: dict[str, Any] = {
        SEASON_PINS[s.season].label: {
            "row_set": ROW_SET_VERSION,
            "row_manifest_sha256": s.pin.row_manifest_sha256,
            "row_set_build_id": s.row_manifest["build_id"],
            "row_set_digests": {
                a["filename"]: a["sha256"]
                for a in s.row_manifest["output_artifacts"]
                if a["filename"] in ("model_row.parquet", "game_reconciliation.parquet")
            },
            "pilot_build": s.pin.pilot_build,
            "pilot_manifest_sha256": s.pin.pilot_manifest_sha256,
            "pilot_digests": s.pilot_digests,
            "timing_audit": s.audit,
            "coverage": s.coverage,
        }
        for s in loads
    }
    inputs["_assemble_seconds"] = time.perf_counter() - started
    return loads, rows, design, inputs


def _git_head() -> tuple[str, bool]:
    head = _run_git(REPO_ROOT, "rev-parse", "HEAD").stdout.strip()
    clean = _run_git(REPO_ROOT, "status", "--porcelain").stdout.strip() == ""
    return head, clean


def _default(value: Any) -> Any:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    raise TypeError(type(value))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=_default))


def dev_main(processed: Path, output_dir: Path, protocol: Path) -> dict[str, Any]:
    head, clean = _git_head()
    if not clean:
        raise RuntimeError("the development run must start from a clean working tree")
    started = time.perf_counter()
    output_dir.mkdir(parents=True, exist_ok=False)
    _, rows, design, inputs = _prepare(processed, DEV_SEASONS, DEV_SEASONS, output_dir)
    log: list[dict[str, Any]] = []
    results = run_development(rows, design, log)
    final: PlayerFit = results.pop("_final_fit")
    results["sensitivity_summary"] = sensitivity_summary(results)
    results["solver"] = _solver_summary(log)
    results["evidence_tier"] = EVIDENCE_TIER
    results["temporal_candidates"] = [
        {"name": t.name, "max_age_days": t.max_age_days, "half_life_days": t.half_life_days}
        for t in TEMPORAL
    ]
    results["rows"] = {
        "possessions": len(rows),
        "games": len(rows.game_ids),
        "players": design.size,
        "by_season": {SEASON_PINS[s].label: int((rows.season == s).sum()) for s in DEV_SEASONS},
    }
    _write_json(output_dir / "results.json", results)
    _write_json(output_dir / "fit_log.json", log)
    with (output_dir / "player_estimates.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["player_id", "offense", "defense", "total", "on_court_possessions"])
        half = design.size
        for j, p in enumerate(design.player_ids):
            if final.used[j]:
                writer.writerow(
                    [
                        p,
                        final.effects[j],
                        final.effects[half + j],
                        final.totals()[j],
                        final.exposure[j],
                    ]
                )
    manifest = {
        "schema_version": 1,
        "issue": 26,
        "phase": "development",
        "evidence_tier": EVIDENCE_TIER,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": inputs,
        "protocol": {
            "path": str(protocol.resolve().relative_to(REPO_ROOT)),
            "sha256": _sha256(protocol),
        },
        "code_commit": head,
        "working_tree_clean": clean,
        "selected": results["selected"],
        "versions": _versions(),
        "runtime_seconds": time.perf_counter() - started,
        "peak_memory_mib": _peak_memory_mib(),
        "outputs": {
            name: _sha256(output_dir / name)
            for name in ("results.json", "fit_log.json", "player_estimates.csv")
        },
        "private_outputs": ["player_estimates.csv"],
    }
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def outer_main(
    processed: Path,
    output_dir: Path,
    addendum: Path | None,
    addendum_sha256: str | None,
    dev_manifest: Path | None,
    repo: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Refuse without the frozen addendum; otherwise score the frozen configuration once."""
    freeze = verify_addendum(addendum, addendum_sha256, repo)
    assert addendum is not None
    config = parse_frozen(addendum.read_text())
    if dev_manifest is None or _sha256(dev_manifest) != config["dev_manifest_sha256"]:
        raise AddendumError("the development manifest does not match the addendum")
    protocol = repo / "docs/research/rapm-multiseason-protocol.md"
    if _sha256(protocol) != config["protocol_sha256"]:
        raise AddendumError("the development protocol differs from the one the addendum names")
    started = time.perf_counter()
    output_dir.mkdir(parents=True, exist_ok=False)
    seasons = DEV_SEASONS + OUTER_SEASONS
    _, rows, design, inputs = _prepare(processed, seasons, seasons, output_dir)
    log: list[dict[str, Any]] = []
    results = run_outer(rows, design, config, log)
    scored: Scored = results.pop("_scored")
    unseen: NDArray[np.bool_] = results.pop("_unseen")
    results["solver"] = _solver_summary(log)
    results["evidence_tier"] = EVIDENCE_TIER
    outcomes = {
        f"{SEASON_PINS[s].label}_{role}": {
            "scored_possessions": int(
                ((rows.season == s) & (rows.playoff == (role == "playoffs"))).sum()
            ),
            "outcome_sha256": outcome_digest(
                rows, (rows.season == s) & (rows.playoff == (role == "playoffs"))
            ),
        }
        for s in OUTER_SEASONS
        for role in ("regular", "playoffs")
    }
    results["outcomes"] = outcomes
    _write_json(output_dir / "results.json", results)
    _write_json(output_dir / "fit_log.json", log)
    arrays: dict[str, Any] = {
        "game_id": np.array([rows.game_ids[g] for g in rows.game[scored.index]]),
        "possession_seq": rows.possession_seq[scored.index],
        "y": rows.y[scored.index],
        "unseen": unseen[scored.index],
        **scored.predictions,
    }
    np.savez_compressed(output_dir / "predictions.npz", **arrays)
    head, clean = _git_head()
    manifest = {
        "schema_version": 1,
        "issue": 26,
        "phase": "outer_validation",
        "evidence_tier": EVIDENCE_TIER,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "addendum": freeze,
        "frozen_configuration": config,
        "dev_manifest_sha256": config["dev_manifest_sha256"],
        "inputs": inputs,
        "outcomes": outcomes,
        "code_commit": head,
        "working_tree_clean_at_end": clean,
        "versions": _versions(),
        "runtime_seconds": time.perf_counter() - started,
        "peak_memory_mib": _peak_memory_mib(),
        "outputs": {
            name: _sha256(output_dir / name)
            for name in ("results.json", "fit_log.json", "predictions.npz")
        },
        "private_outputs": ["predictions.npz"],
    }
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def main(argv: Sequence[str] | None = None) -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest="phase", required=True)
    dev = sub.add_parser("dev", help="Phase 1: development selection, stability and sensitivity")
    dev.add_argument("processed", type=Path, help="the data/processed directory")
    dev.add_argument("output_dir", type=Path, help="new directory for results")
    dev.add_argument(
        "--protocol", type=Path, default=REPO_ROOT / "docs/research/rapm-multiseason-protocol.md"
    )
    outer = sub.add_parser("outer", help="Phase 2: frozen outer validation (needs the addendum)")
    outer.add_argument("processed", type=Path)
    outer.add_argument("output_dir", type=Path)
    outer.add_argument("--addendum", type=Path)
    outer.add_argument("--addendum-sha256")
    outer.add_argument("--dev-manifest", type=Path)
    args = cli.parse_args(argv)
    if args.phase == "dev":
        manifest = dev_main(args.processed, args.output_dir, args.protocol)
    else:
        manifest = outer_main(
            args.processed, args.output_dir, args.addendum, args.addendum_sha256, args.dev_manifest
        )
    print(json.dumps({k: manifest[k] for k in ("runtime_seconds", "peak_memory_mib", "outputs")}))


if __name__ == "__main__":
    main()
