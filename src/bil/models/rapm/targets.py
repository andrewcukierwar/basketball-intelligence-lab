"""Provisional long-window RAPM training targets for box-score SPM (issue #28).

Implements ``docs/research/rapm-targets-protocol.md``. Every artifact is a **partial-history
methodology replication**, not a full historical EPM replication (ADR-0026).

A target is a retrospective label, not a forecast. For each reference (``contiguous`` or
``extended``), each rolling origin and each eligible target season, the runner fits a
season-centred, elapsed-time-weighted zero-prior ridge RAPM with unpenalized context columns
(home, score state, game time and season-by-season-type levels) fitted jointly with the players,
and keeps offensive and defensive labels separately. Penalties are chosen at each origin by game-grouped
cross-validation inside the rows eligible at that origin. Origins only ever see rows played
strictly before their cutoff, and every frozen target records the digest of its inputs.

No loader accepts 2017-18, 2023-24, 2024-25 or any season from 2025-26 on. No EPM output is
read. The pure functions take arrays so that they can be tested on synthetic data.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import pickle
import shutil
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from functools import partial
from pathlib import Path
from typing import Any, TypeVar

import numpy as np
from numpy.typing import NDArray
from scipy.sparse.linalg import LinearOperator, lsqr  # type: ignore[import-untyped]

from bil.models.rapm.baseline import EVIDENCE_TIER, _peak_memory_mib, _sha256
from bil.models.rapm.multiseason import (
    EXPOSURE_BANDS,
    HOLDOUT_START_YEAR,
    REPO_ROOT,
    SEASON_PINS,
    AddendumError,
    Design,
    PlayerFit,
    Rows,
    SeasonPin,
    _band_label,
    _solver_summary,
    _versions,
    _write_json,
    assemble,
    build_matrix,
    check_game_dates,
    fit_context,
    fit_players,
    load_season,
    search_penalties,
    split_halves,
    verify_addendum,
)

ISSUE = 28
TARGET_VERSION = "issue-28-v1"
ARTIFACT_LABEL = "partial-history methodology replication"
PROTOCOL_PATH = REPO_ROOT / "docs/research/rapm-targets-protocol.md"
DATA_END = date(2023, 7, 1)  # every target row is played before the outer seasons
AUTHORIZED_SEASONS = (2005, 2006, 2007, 2015, 2016, 2018, 2019, 2020, 2021, 2022)
REFERENCES: dict[str, tuple[int, ...]] = {
    "contiguous": (2018, 2019, 2020, 2021, 2022),
    "extended": AUTHORIZED_SEASONS,
}
REPAIRED_STRATUM = "datanba_event_order"  # ADR-0023 output; not approved for canonical use
CV_FOLDS = 5
FOLD_SALT = TARGET_VERSION
MIN_ROLE_POSSESSIONS = 250
BOOTSTRAP_REPLICATES = 100
BOOTSTRAP_SEED = 28

TARGET_PINS: dict[int, SeasonPin] = {
    2005: SeasonPin(
        "2005-06",
        "0cd0db16dbf6b7819eb5e88449bedccd9577204050b24ce6415429452b06e062",
        "issue-97-v1",
        "66d2904d79e43321b2a57fbef498f294c1ed3e7333dd7dd6c920ac1395cce8c5",
        "issue-97-rows-v1",
    ),
    2006: SeasonPin(
        "2006-07",
        "4dcd6a00be96da4011f9e9aac56152ec043e15f8a16b3e8f18d58106c8686f5c",
        "issue-97-v1",
        "1cb82fe3160d9e722d4e86a8b3362c5a900f1f40da756adfe9ece61d4d67bce9",
        "issue-97-rows-v1",
    ),
    2007: SeasonPin(
        "2007-08",
        "8aa10687f33efb950315eb11c11db2dbb50418882d9a86e5a39e43b727012c57",
        "issue-97-v1",
        "d2e4be9d6bdd53306126252fc527ecb0a88bb77f72175c31aed8a16490809769",
        "issue-97-rows-v1",
    ),
    2015: SeasonPin(
        "2015-16",
        "4214ed84b842a7575848462847d2788867465ff7a09c505479c5cbcc64e29373",
        "issue-98-v1",
        "fa68579155d6689a36ad733c362caf552394e1bc5939e37b1dd2f84c0807fbea",
        "issue-98-rows-v1",
    ),
    2016: SeasonPin(
        "2016-17",
        "eca05cb8515446a6a61f36685d621b3701b502f621f490bc1280614dac8d1bde",
        "issue-96-v1",
        "e96ba9042e6463566cd0666f1c4b88d89b07d2484908a4125b8860218ac2e9b2",
        "issue-96-rows-v1",
    ),
    **{season: SEASON_PINS[season] for season in REFERENCES["contiguous"]},
}

# Season-level verification groups from the ADR-0022 eligibility matrix. The loader checks the
# group against the accepted games' strata and refuses a disagreement.
VERIFICATION_GROUP: dict[int, str] = {
    2005: "no_livedata_no_datanba",
    2006: "no_livedata_no_datanba",
    2007: "no_livedata_no_datanba",
    2015: "no_livedata_no_datanba",
    2016: "no_livedata_datanba_without_ord",
    2018: "no_livedata",
    2019: "no_livedata",
    2020: "livedata",
    2021: "livedata",
    2022: "livedata",
}
ERA: dict[int, str] = {
    **{s: "2005-08" for s in (2005, 2006, 2007)},
    **{s: "2015-17" for s in (2015, 2016)},
    **{s: "2018-23" for s in REFERENCES["contiguous"]},
}


class ProtocolError(RuntimeError):
    """The runner was not given the committed, unmodified protocol on a clean tree."""


class FrozenTargetError(RuntimeError):
    """A frozen target's inputs no longer match the rows it was fitted on."""


def check_target_season(season: int) -> SeasonPin:
    """Return the pin of an authorized target season. Every other season raises."""
    if season >= HOLDOUT_START_YEAR:
        raise ValueError(f"season {season} is the confirmatory holdout or later and is never read")
    if season not in AUTHORIZED_SEASONS:
        raise ValueError(f"season {season} is not an authorized #28 target season")
    return TARGET_PINS[season]


# --- elapsed-time kernel ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Kernel:
    """Weight 1 inside the target season; ``0.5 ** (gap / half_life)`` outside, up to ``cap``.

    ``gap`` is the number of calendar days between a row's played date and the nearest played
    date of the target season, so a missing season counts as the real time that elapsed.
    ``half_life_days=None`` gives unit weight inside the cap.
    """

    name: str
    half_life_days: float | None
    cap_days: float


PRIMARY_KERNEL = Kernel("K365", 365.0, 730.0)
SEASON_ONLY_KERNEL = Kernel("K0", None, 0.0)
WIDE_KERNEL = Kernel("K730", 730.0, 1460.0)
POOLED_KERNEL = Kernel("POOLED", None, float("inf"))


def season_spans(season: NDArray[np.int64], day: NDArray[np.int64]) -> dict[int, tuple[int, int]]:
    """First and last played day (ordinal) of each season present in the rows."""
    spans: dict[int, tuple[int, int]] = {}
    for s in np.unique(season).tolist():
        days = day[season == s]
        spans[int(s)] = (int(days.min()), int(days.max()))
    ordered = sorted(spans.items())
    for (a, (_, last)), (b, (first, _)) in zip(ordered, ordered[1:], strict=False):
        if first <= last:
            raise ValueError(f"seasons {a} and {b} overlap in played dates")
    return spans


def kernel_weights(
    season: NDArray[np.int64],
    day: NDArray[np.int64],
    target: int,
    spans: Mapping[int, tuple[int, int]],
    kernel: Kernel,
) -> NDArray[np.float64]:
    """Per-row weight of a fit centred on ``target`` (zero outside the kernel)."""
    first, last = spans[target]
    gap = np.maximum(0, np.maximum(first - day, day - last))
    same = season == target
    if np.any(~same & (gap == 0)):
        raise ValueError("a row of another season falls inside the target season's dates")
    weights = np.zeros(day.shape, dtype=np.float64)
    weights[same] = 1.0
    other = ~same & (gap <= kernel.cap_days)
    if kernel.half_life_days is None:
        weights[other] = 1.0
    else:
        weights[other] = 0.5 ** (gap[other] / kernel.half_life_days)
    return weights


# --- origins ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Origin:
    """A rolling origin that closes one eligible season: rows played before ``cutoff``."""

    reference: str
    closes_season: int
    cutoff: date

    @property
    def key(self) -> str:
        return f"{self.reference}@{self.cutoff.isoformat()}"


def origin_schedule(reference: str, calendar: Mapping[int, tuple[date, date]]) -> list[Origin]:
    """One origin per eligible season: the day after its last scheduled game.

    ``calendar`` maps each season to the first and last played date of every expected game,
    accepted or quarantined. An origin never falls after the next eligible season's first game.
    """
    seasons = REFERENCES[reference]
    origins = []
    for i, season in enumerate(seasons):
        cutoff = calendar[season][1] + timedelta(days=1)
        if i + 1 < len(seasons) and cutoff > calendar[seasons[i + 1]][0]:
            raise ValueError(f"the origin closing {season} falls inside the next season")
        if cutoff > DATA_END:
            raise ValueError("an origin falls after the development data end")
        origins.append(Origin(reference, season, cutoff))
    return origins


def unavailable_origins(reference: str) -> list[dict[str, Any]]:
    """Seasons with no eligible rows between a reference's first and last season."""
    seasons = REFERENCES[reference]
    out = []
    for season in range(seasons[0], seasons[-1] + 1):
        if season in seasons:
            continue
        earlier = max(s for s in seasons if s < season)
        out.append(
            {
                "season": season,
                "status": "unavailable",
                "reason": "season not eligible (ADR-0022, ADR-0026); no target closes it",
                "latest_available_origin_closes": earlier,
            }
        )
    return out


# --- rows at one origin ----------------------------------------------------------------------


def subset_rows(rows: Rows, mask: NDArray[np.bool_]) -> Rows:
    """The rows in ``mask``, with game and team-game codes renumbered from zero."""
    games, game = np.unique(rows.game[mask], return_inverse=True)
    _, team_game = np.unique(rows.team_game[mask], return_inverse=True)
    return Rows(
        season=rows.season[mask],
        playoff=rows.playoff[mask],
        day=rows.day[mask],
        game=game.astype(np.int64),
        game_ids=tuple(rows.game_ids[g] for g in games.tolist()),
        team_game=team_game.astype(np.int64),
        possession_seq=rows.possession_seq[mask],
        period=rows.period[mask],
        y=rows.y[mask],
        offense=rows.offense[mask],
        defense=rows.defense[mask],
        context=rows.context[mask],
        no_livedata=rows.no_livedata[mask],
    )


def eligible_mask(
    rows: Rows, seasons: Iterable[int], cutoff: date, available: NDArray[np.bool_] | None = None
) -> NDArray[np.bool_]:
    """Rows of the reference seasons played strictly before ``cutoff``."""
    mask = (rows.day < cutoff.toordinal()) & np.isin(rows.season, list(seasons))
    if available is not None:
        mask &= available
    return mask


def input_digest(rows: Rows, teams: NDArray[np.int64] | None = None) -> str:
    """SHA-256 of every input a target fit reads, independent of row order.

    Covers game identity, possession sequence, season, season type, played date, period,
    outcome, both lineups, the context covariates, the verification flag and the teams.
    """
    rank = np.argsort(np.argsort(np.array(rows.game_ids, dtype=object)))
    order = np.lexsort((rows.possession_seq, rank[rows.game]))
    digest = hashlib.sha256()
    digest.update("\n".join(sorted(rows.game_ids)).encode())
    arrays: list[NDArray[Any]] = [
        rank[rows.game],
        rows.possession_seq,
        rows.season,
        rows.playoff.astype(np.uint8),
        rows.day,
        rows.period,
        rows.y,
        rows.offense,
        rows.defense,
        rows.context,
        rows.no_livedata.astype(np.uint8),
    ]
    if teams is not None:
        arrays.append(teams)
    for array in arrays:
        values = np.ascontiguousarray(array[order])
        digest.update(str(values.dtype).encode() + str(values.shape).encode())
        digest.update(values.astype(values.dtype.newbyteorder("<")).tobytes())
    return digest.hexdigest()


def game_folds(
    game_ids: Sequence[str], folds: int = CV_FOLDS, salt: str = FOLD_SALT
) -> NDArray[np.int64]:
    """Deterministic fold of each game from a salted SHA-256 of its game ID."""
    return np.array(
        [int(hashlib.sha256(f"{salt}:{g}".encode()).hexdigest(), 16) % folds for g in game_ids],
        dtype=np.int64,
    )


def team_change_counts(
    design: Design,
    offense: NDArray[np.int64],
    defense: NDArray[np.int64],
    teams: NDArray[np.int64],
    mask: NDArray[np.bool_],
) -> NDArray[np.int64]:
    """Distinct teams each design player appeared for in the masked rows."""
    ids = np.asarray(design.player_ids, dtype=np.int64)
    players = np.concatenate([offense[mask].ravel(), defense[mask].ravel()])
    clubs = np.concatenate([np.repeat(teams[mask, 0], 5), np.repeat(teams[mask, 1], 5)])
    pairs = np.unique(np.column_stack([np.searchsorted(ids, players), clubs]), axis=0)
    return np.bincount(pairs[:, 0], minlength=ids.size).astype(np.int64)


@dataclass
class OffsetModel:
    """Weighted least squares of the response on context columns and season-type levels."""

    intercept: float
    context: NDArray[np.float64]
    levels: tuple[int, ...]  # level codes; the first is the baseline
    level_effects: NDArray[np.float64]

    def offset(self, context: NDArray[np.float64], level: NDArray[np.int64]) -> NDArray[np.float64]:
        """Context and level contribution, without the intercept (the player fit keeps one)."""
        out: NDArray[np.float64] = context @ self.context
        for code, effect in zip(self.levels[1:], self.level_effects, strict=True):
            out = out + effect * (level == code)
        return out


def level_columns(level: NDArray[np.int64]) -> tuple[tuple[int, ...], NDArray[np.float64]]:
    """Indicator columns of every season-type level in the rows except the first (baseline)."""
    levels = tuple(int(v) for v in np.unique(level).tolist())
    if len(levels) == 1:
        return levels, np.zeros((level.size, 0))
    return levels, np.column_stack([(level == code).astype(np.float64) for code in levels[1:]])


def fit_offset(
    context: NDArray[np.float64],
    level: NDArray[np.int64],
    response: NDArray[np.float64],
    weights: NDArray[np.float64],
) -> OffsetModel:
    """Two-stage sensitivity only: the context and levels fitted without players."""
    levels, dummies = level_columns(level)
    intercept, gamma = fit_context(np.column_stack([context, dummies]), response, weights)
    k = context.shape[1]
    return OffsetModel(intercept, gamma[:k], levels, gamma[k:])


_CONVERGED = {0, 1, 2, 4, 5}
_RANK_TOLERANCE = 1e-10


def fit_joint(
    design: Design,
    index: NDArray[np.int64],
    response: NDArray[np.float64],
    weights: NDArray[np.float64],
    unpenalized: NDArray[np.float64],
    offense_ridge: float,
    defense_ridge: float,
) -> tuple[PlayerFit, NDArray[np.float64]]:
    """Two-penalty player ridge with an unpenalized intercept and columns ``C``, fitted jointly.

    Minimizes ``sum w (y - a - C g - X b)^2 + l_o |b_o|^2 + l_d |b_d|^2`` over ``a``, ``g`` and
    ``b``. The weighted span of ``[1, C]`` is projected out of the player design and response
    (Frisch-Waugh-Lovell), the penalized player problem is solved by sparse LSQR with each role
    rescaled to a unit penalty, and ``a`` and ``g`` follow by weighted least squares on the
    player residual. Columns of ``C`` that are zero in every fit row get coefficient 0. Each
    player block has zero mean over its observed players, as the free intercept implies.
    """
    for role, ridge in (("offense", offense_ridge), ("defense", defense_ridge)):
        if not np.isfinite(ridge) or ridge <= 0:
            raise ValueError(f"{role} ridge must be positive and finite")
    n = index.size
    if n == 0 or response.shape != (n,) or weights.shape != (n,) or unpenalized.shape[0] != n:
        raise ValueError("response, weights and unpenalized columns must align with the rows")
    if np.any(weights <= 0) or not np.all(np.isfinite(weights)):
        raise ValueError("fit weights must be positive and finite")
    started = time.perf_counter()
    keep = np.any(unpenalized != 0, axis=0)
    root = np.sqrt(weights)
    columns = np.column_stack((np.ones(n), unpenalized[:, keep])) * root[:, None]
    q, r = np.linalg.qr(columns)
    diagonal = np.abs(np.diag(r))
    if diagonal.min() <= _RANK_TOLERANCE * diagonal.max():
        raise ValueError("unpenalized columns are collinear with each other or the intercept")
    m = design.size
    players = design.players[index]
    scales = np.concatenate(
        (np.full(m, 1.0 / np.sqrt(offense_ridge)), np.full(m, 1.0 / np.sqrt(defense_ridge)))
    )
    scaled = players.multiply(root[:, None]).tocsr().multiply(scales).tocsr()
    used = np.bincount(players.indices, minlength=2 * m) > 0

    def project(values: NDArray[np.float64]) -> NDArray[np.float64]:
        projected: NDArray[np.float64] = values - q @ (q.T @ values)
        return projected

    def matvec(coefficients: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.concatenate((project(scaled @ coefficients), coefficients))

    def rmatvec(values: NDArray[np.float64]) -> NDArray[np.float64]:
        back: NDArray[np.float64] = scaled.T @ project(values[:n])
        return back + values[n:]

    system = LinearOperator((n + 2 * m, 2 * m), matvec=matvec, rmatvec=rmatvec, dtype=np.float64)
    response_scale = float(np.max(np.abs(response))) or 1.0
    target = np.concatenate((project(root * (response / response_scale)), np.zeros(2 * m)))
    result = lsqr(system, target, atol=1e-12, btol=1e-12)
    solution, stop = result[0], result[1]
    if not np.all(np.isfinite(solution)):
        raise RuntimeError(f"joint RAPM solve is not finite (LSQR stop {stop})")
    # A finite solve that stopped without converging is kept and recorded (protocol §10).
    effects = solution * scales * response_scale
    for block in (slice(0, m), slice(m, 2 * m)):
        active = used[block]
        values = effects[block]
        values[active] -= np.mean(values[active])
        values[~active] = 0.0
    residual = response - players @ effects
    coefficients = np.linalg.solve(r, q.T @ (root * residual))
    gamma = np.zeros(unpenalized.shape[1], dtype=np.float64)
    gamma[keep] = coefficients[1:]
    counts = np.asarray(design.on_court[index].sum(axis=0), dtype=np.float64).ravel()
    exposure = counts[:m] + counts[m:]
    info = {
        "stop": float(stop),
        "iterations": float(result[2]),
        "scaled_residual_norm": float(result[3]),
        "condition_estimate": float(result[6]),
        "converged": float(stop in _CONVERGED),
        "fit_seconds": time.perf_counter() - started,
        "rows": float(n),
    }
    fit = PlayerFit(float(coefficients[0]), effects, exposure > 0, exposure, info)
    return fit, gamma


@dataclass
class SeasonFit:
    """One season-centred target fit."""

    target: int
    index: NDArray[np.int64]
    weights: NDArray[np.float64]
    offset: OffsetModel
    players: PlayerFit


@dataclass
class OriginData:
    """The rows eligible at one origin, with a design built from those rows alone."""

    rows: Rows
    teams: NDArray[np.int64]  # (n, 2): offense and defense team codes
    design: Design
    spans: dict[int, tuple[int, int]]
    level: NDArray[np.int64]
    folds: NDArray[np.int64]  # per row
    digest: str
    log: list[dict[str, Any]]
    label: str = ""
    offset_mode: str = "joint"  # "joint" (primary) or "two_stage" (sensitivity)
    _kernels: dict[tuple[int, str], NDArray[np.float64]] = field(default_factory=dict)
    _offsets: dict[tuple[Any, ...], OffsetModel] = field(default_factory=dict)

    @property
    def seasons(self) -> list[int]:
        return sorted(self.spans)

    def kernel(self, target: int, kernel: Kernel) -> NDArray[np.float64]:
        key = (target, kernel.name)
        if key not in self._kernels:
            self._kernels[key] = kernel_weights(
                self.rows.season, self.rows.day, target, self.spans, kernel
            )
        return self._kernels[key]


def origin_data(
    rows: Rows,
    teams: NDArray[np.int64],
    mask: NDArray[np.bool_],
    log: list[dict[str, Any]],
    label: str = "",
    offset_mode: str = "joint",
) -> OriginData:
    """Restrict to ``mask`` and build everything a set of target fits reads."""
    if not mask.any():
        raise ValueError("an origin needs at least one eligible row")
    sub = subset_rows(rows, mask)
    check_game_dates(sub)
    level = (sub.season * 2 + sub.playoff.astype(np.int64)).astype(np.int64)
    return OriginData(
        rows=sub,
        teams=teams[mask],
        design=build_matrix(sub.offense, sub.defense),
        spans=season_spans(sub.season, sub.day),
        level=level,
        folds=game_folds(sub.game_ids)[sub.game],
        digest=input_digest(sub, teams[mask]),
        log=log,
        label=label,
        offset_mode=offset_mode,
    )


def fit_season(
    od: OriginData,
    target: int,
    kernel: Kernel,
    offense_ridge: float,
    defense_ridge: float,
    *,
    keep: NDArray[np.bool_] | None = None,
    multiplicity: NDArray[np.float64] | None = None,
    cache_key: tuple[Any, ...] | None = None,
    note: str = "",
) -> SeasonFit:
    """Fit the players, context and season-type levels on the kernel rows.

    The primary ``joint`` mode estimates the unpenalized context and level columns together
    with the penalized players. ``two_stage`` (sensitivity only) fits them first, without
    players, and the players on the residual.
    """
    weights = od.kernel(target, kernel).copy()
    if keep is not None:
        weights[~keep] = 0.0
    if multiplicity is not None:
        weights *= multiplicity
    index = np.flatnonzero(weights > 0).astype(np.int64)
    if not np.any(od.rows.season[index] == target):
        raise ValueError(f"no rows of target season {target} in the fit")
    w = weights[index]
    rows = od.rows
    if od.offset_mode == "joint":
        levels, dummies = level_columns(od.level[index])
        players, gamma = fit_joint(
            od.design,
            index,
            rows.y[index],
            w,
            np.column_stack([rows.context[index], dummies]),
            offense_ridge,
            defense_ridge,
        )
        k = rows.context.shape[1]
        offset = OffsetModel(players.intercept, gamma[:k], levels, gamma[k:])
    elif od.offset_mode == "two_stage":
        key = None if cache_key is None else (target, kernel.name, *cache_key)
        if key is not None and key in od._offsets:
            offset = od._offsets[key]
        else:
            offset = fit_offset(rows.context[index], od.level[index], rows.y[index], w)
            if key is not None:
                od._offsets[key] = offset
        response = rows.y[index] - offset.offset(rows.context[index], od.level[index])
        players = fit_players(od.design, index, response, w, offense_ridge, defense_ridge)
    else:
        raise ValueError(f"unknown offset mode {od.offset_mode}")
    od.log.append(
        {
            "origin": od.label,
            "target": target,
            "kernel": kernel.name,
            "offset_mode": od.offset_mode,
            "offense_ridge": offense_ridge,
            "defense_ridge": defense_ridge,
            "note": note,
            "total_weight": float(w.sum()),
            **players.info,
        }
    )
    return SeasonFit(target, index, w, offset, players)


def predict_rows(od: OriginData, fit: SeasonFit, index: NDArray[np.int64]) -> NDArray[np.float64]:
    """Intercept, offset and player effects; unseen players contribute zero."""
    rows = od.rows
    prediction: NDArray[np.float64] = (
        fit.players.intercept
        + fit.offset.offset(rows.context[index], od.level[index])
        + od.design.players[index] @ fit.players.effects
    )
    return prediction


# --- penalty selection -----------------------------------------------------------------------


def cv_mse(
    od: OriginData,
    kernel: Kernel,
    offense_ridge: float,
    defense_ridge: float,
    *,
    targets: Sequence[int] | None = None,
) -> float:
    """Pooled held-out squared error of target-season rows over game-grouped folds.

    Fold ``k`` fits every target season's kernel on games outside fold ``k`` and scores the
    target season's own rows in fold ``k``. No held-out game reaches its fit.
    """
    error = 0.0
    count = 0
    for target in targets if targets is not None else od.seasons:
        for k in range(CV_FOLDS):
            train = od.folds != k
            held = (od.folds == k) & (od.rows.season == target)
            scored = np.flatnonzero(held).astype(np.int64)
            if scored.size == 0:
                continue
            fit = fit_season(
                od,
                target,
                kernel,
                offense_ridge,
                defense_ridge,
                keep=train,
                cache_key=("cv", k),
                note=f"cv{k}",
            )
            if np.intersect1d(fit.index, scored).size:
                raise AssertionError("a held-out row reached its fit")
            error += float(((predict_rows(od, fit, scored) - od.rows.y[scored]) ** 2).sum())
            count += int(scored.size)
    if count == 0:
        raise ValueError("cross-validation scored no rows")
    return error / count


def select_penalties(
    od: OriginData, kernel: Kernel
) -> tuple[tuple[float, float], dict[str, float]]:
    """The #26 search (shared grid, then defense, then offense) on the in-window CV error."""
    (offense, defense), memo = search_penalties(lambda o, d: cv_mse(od, kernel, o, d))
    return (offense, defense), {f"{o:g}/{d:g}": v for (o, d), v in sorted(memo.items())}


# --- labels ----------------------------------------------------------------------------------

LABEL_FIELDS = (
    "player_id",
    "offense",
    "defense",
    "total",
    "offense_raw",
    "defense_raw",
    "offense_possessions",
    "defense_possessions",
    "kernel_offense_weight",
    "kernel_defense_weight",
    "teams",
)


def season_exposure(
    od: OriginData, target: int, keep: NDArray[np.bool_] | None = None
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Offensive and defensive possessions of each design player in the target season."""
    mask = od.rows.season == target
    if keep is not None:
        mask = mask & keep
    counts = np.asarray(od.design.on_court[np.flatnonzero(mask)].sum(axis=0)).ravel()
    m = od.design.size
    return counts[:m].astype(np.float64), counts[m:].astype(np.float64)


def labels(
    od: OriginData,
    fit: SeasonFit,
    keep: NDArray[np.bool_] | None = None,
    centre: tuple[NDArray[np.float64], NDArray[np.float64]] | None = None,
) -> dict[str, NDArray[Any]]:
    """Labels of players with possessions in both roles in the target season.

    ``offense`` and ``defense`` are centred so that their target-season possession-weighted
    means are zero over the labelled players (``centre`` overrides the centring weights).
    The ``*_raw`` columns keep the ADR-0012 centring of the fit universe.
    """
    off_pos, def_pos = season_exposure(od, fit.target, keep)
    m = od.design.size
    selected = np.flatnonzero((off_pos > 0) & (def_pos > 0))
    off_raw = fit.players.effects[:m][selected]
    def_raw = fit.players.effects[m:][selected]
    w_off, w_def = (off_pos, def_pos) if centre is None else centre
    off = off_raw - float(np.average(off_raw, weights=w_off[selected]))
    dfn = def_raw - float(np.average(def_raw, weights=w_def[selected]))
    weighted = od.design.on_court[fit.index].T @ fit.weights
    mask = od.rows.season == fit.target
    if keep is not None:
        mask = mask & keep
    teams = team_change_counts(od.design, od.rows.offense, od.rows.defense, od.teams, mask)
    return {
        "player_id": np.asarray(od.design.player_ids, dtype=np.int64)[selected],
        "offense": off,
        "defense": dfn,
        "total": off + dfn,
        "offense_raw": off_raw,
        "defense_raw": def_raw,
        "offense_possessions": off_pos[selected],
        "defense_possessions": def_pos[selected],
        "kernel_offense_weight": np.asarray(weighted[:m])[selected],
        "kernel_defense_weight": np.asarray(weighted[m:])[selected],
        "teams": teams[selected],
    }


def label_digest(table: Mapping[str, NDArray[Any]]) -> str:
    """SHA-256 of a label table, independent of row order."""
    lines = sorted(
        "|".join(repr(table[name][i].item()) for name in LABEL_FIELDS)
        for i in range(table["player_id"].size)
    )
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


# --- frozen targets --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FrozenTarget:
    """The record that pins a target set to the exact rows and rules it was fitted with."""

    version: str
    reference: str
    kernel: str
    kernel_half_life_days: float | None
    kernel_cap_days: float
    offset_mode: str
    cv_folds: int
    fold_salt: str
    cutoff: str
    closes_season: int
    seasons: tuple[int, ...]
    offense_ridge: float
    defense_ridge: float
    input_digest: str
    label_digests: dict[int, str]
    rows: int
    scenario: str = "primary"
    code_commit: str = ""
    protocol_sha256: str = ""
    artifact_label: str = ARTIFACT_LABEL


def build_target_set(
    rows: Rows,
    teams: NDArray[np.int64],
    origin: Origin,
    kernel: Kernel,
    log: list[dict[str, Any]],
    *,
    penalties: tuple[float, float] | None = None,
    available: NDArray[np.bool_] | None = None,
    scenario: str = "primary",
    offset_mode: str = "joint",
    provenance: Mapping[str, str] | None = None,
) -> tuple[FrozenTarget, dict[int, dict[str, NDArray[Any]]], OriginData, dict[str, Any]]:
    """Fit every eligible target season at one origin and freeze the result.

    Only rows of the reference seasons played strictly before the origin's cutoff are read,
    so rows played later, or any change to them, cannot change the result. Any other fit
    (a restricted row set, a non-primary kernel, the two-stage offset or fixed penalties)
    must name its scenario and is never a frozen target.
    """
    primary_rules = (
        available is None
        and kernel == PRIMARY_KERNEL
        and offset_mode == "joint"
        and penalties is None
    )
    if not primary_rules and scenario == "primary":
        raise ValueError("a non-primary fit must name its scenario")
    seasons = REFERENCES[origin.reference]
    mask = eligible_mask(rows, seasons, origin.cutoff, available)
    od = origin_data(rows, teams, mask, log, label=origin.key, offset_mode=offset_mode)
    if int(np.max(od.rows.day)) >= origin.cutoff.toordinal():
        raise AssertionError("a target row is not strictly before its origin")
    search: dict[str, Any] = {}
    if penalties is None:
        penalties, memo = select_penalties(od, kernel)
        search = {"cv_mse": memo}
    offense_ridge, defense_ridge = penalties
    tables: dict[int, dict[str, NDArray[Any]]] = {}
    fits: dict[int, SeasonFit] = {}
    for target in od.seasons:
        fits[target] = fit_season(od, target, kernel, offense_ridge, defense_ridge, note="label")
        tables[target] = labels(od, fits[target])
    frozen = FrozenTarget(
        version=TARGET_VERSION,
        reference=origin.reference,
        kernel=kernel.name,
        kernel_half_life_days=kernel.half_life_days,
        kernel_cap_days=kernel.cap_days,
        offset_mode=offset_mode,
        cv_folds=CV_FOLDS,
        fold_salt=FOLD_SALT,
        cutoff=origin.cutoff.isoformat(),
        closes_season=origin.closes_season,
        seasons=tuple(od.seasons),
        offense_ridge=offense_ridge,
        defense_ridge=defense_ridge,
        input_digest=od.digest,
        label_digests={s: label_digest(t) for s, t in tables.items()},
        rows=len(od.rows),
        scenario=scenario,
        code_commit=(provenance or {}).get("code_commit", ""),
        protocol_sha256=(provenance or {}).get("protocol_sha256", ""),
    )
    search["fits"] = {}
    for s, f in fits.items():
        kernel_seasons = sorted(np.unique(od.rows.season[f.index]).tolist())
        forward = bool(np.any(od.rows.season[f.index] > s))
        size = tables[s]["player_id"].size
        tables[s]["forward_support"] = np.full(size, forward)
        tables[s]["kernel_seasons"] = np.full(
            size, ";".join(map(str, kernel_seasons)), dtype=object
        )
        search["fits"][str(s)] = {
            "intercept": f.players.intercept,
            "context": f.offset.context.tolist(),
            "level_effects": dict(
                zip(map(str, f.offset.levels[1:]), f.offset.level_effects.tolist(), strict=True)
            ),
            "rows": int(f.index.size),
            "total_weight": float(f.weights.sum()),
            "kernel_seasons": kernel_seasons,
            "forward_support": forward,
        }
    return frozen, tables, od, search


def verify_frozen(frozen: FrozenTarget, rows: Rows, teams: NDArray[np.int64]) -> None:
    """Raise unless the rows a frozen target reads are byte-for-byte those it was fitted on."""
    if (
        frozen.scenario != "primary"
        or frozen.kernel != PRIMARY_KERNEL.name
        or frozen.offset_mode != "joint"
    ):
        raise FrozenTargetError("only primary target sets are frozen targets")
    cutoff = date.fromisoformat(frozen.cutoff)
    mask = eligible_mask(rows, REFERENCES[frozen.reference], cutoff)
    if not mask.any():
        raise FrozenTargetError(f"{frozen.reference} at {frozen.cutoff} has no eligible rows")
    actual = input_digest(subset_rows(rows, mask), teams[mask])
    if actual != frozen.input_digest:
        raise FrozenTargetError(
            f"{frozen.reference} target at {frozen.cutoff} was fitted on different rows; "
            "a revised input needs a new target version"
        )


# --- reliability, stability and exposure -----------------------------------------------------


def _corr(a: NDArray[np.float64], b: NDArray[np.float64]) -> float | None:
    if a.size < 3 or np.std(a) == 0 or np.std(b) == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def spearman_brown(r: float | None) -> float | None:
    """Full-sample reliability from a split-half correlation."""
    if r is None or r <= -1:
        return None
    return 2 * r / (1 + r)


def band_of(exposure: NDArray[np.float64]) -> NDArray[Any]:
    out = np.empty(exposure.size, dtype=object)
    for lo, hi in EXPOSURE_BANDS:
        inside = (exposure >= lo) & (exposure < (np.inf if hi is None else hi))
        out[inside] = _band_label(lo, hi)
    return out


def _join(
    a: Mapping[str, NDArray[Any]], b: Mapping[str, NDArray[Any]]
) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    _, ia, ib = np.intersect1d(a["player_id"], b["player_id"], return_indices=True)
    return ia.astype(np.int64), ib.astype(np.int64)


def compare_labels(a: Mapping[str, NDArray[Any]], b: Mapping[str, NDArray[Any]]) -> dict[str, Any]:
    """Correlation and RMS difference of offense, defense and total for players in both."""
    ia, ib = _join(a, b)
    exposure = a["offense_possessions"][ia] + a["defense_possessions"][ia]
    groups: dict[str, NDArray[np.bool_]] = {"all": np.ones(ia.size, dtype=bool)}
    bands = band_of(exposure)
    for lo, hi in EXPOSURE_BANDS:
        groups[f"band_{_band_label(lo, hi)}"] = bands == _band_label(lo, hi)
    out: dict[str, Any] = {}
    for name, keep in groups.items():
        result: dict[str, Any] = {"players": int(keep.sum())}
        for role in ("offense", "defense", "total"):
            x, y = a[role][ia][keep], b[role][ib][keep]
            result[role] = {
                "r": _corr(x, y),
                "rms_difference": float(np.sqrt(np.mean((x - y) ** 2))) if x.size else None,
            }
        out[name] = result
    return out


@dataclass
class HalfPairs:
    """Split-half label pairs of one role in one target season."""

    player_id: NDArray[np.int64]
    first: NDArray[np.float64]
    second: NDArray[np.float64]
    exposure: NDArray[np.float64]  # full target-season possessions, both roles


def split_half_target(
    od: OriginData,
    target: int,
    kernel: Kernel,
    penalties: tuple[float, float],
    halves: tuple[NDArray[np.bool_], NDArray[np.bool_]],
) -> dict[str, HalfPairs]:
    """Fit one target on two alternating-game halves and pair the labels by role.

    A role's label is paired for players with at least ``MIN_ROLE_POSSESSIONS`` possessions in
    that role in the target season in both halves. Both halves use the frozen penalties, and
    the games of every season in the kernel alternate, so the halves share no possession.
    """
    tables = []
    for i, keep in enumerate(halves, start=1):
        fit = fit_season(od, target, kernel, *penalties, keep=keep, note=f"half{i}")
        tables.append(labels(od, fit, keep))
    a, b = tables
    ia, ib = _join(a, b)
    off_pos, def_pos = season_exposure(od, target)
    ids = np.asarray(od.design.player_ids, dtype=np.int64)
    full = (off_pos + def_pos)[np.searchsorted(ids, a["player_id"][ia])]
    out: dict[str, HalfPairs] = {}
    for role in ("offense", "defense"):
        enough = (a[f"{role}_possessions"][ia] >= MIN_ROLE_POSSESSIONS) & (
            b[f"{role}_possessions"][ib] >= MIN_ROLE_POSSESSIONS
        )
        out[role] = HalfPairs(
            a["player_id"][ia][enough], a[role][ia][enough], b[role][ib][enough], full[enough]
        )
    return out


def split_half_reliability(
    od: OriginData, kernel: Kernel, penalties: tuple[float, float]
) -> dict[int, dict[str, HalfPairs]]:
    """``split_half_target`` for every target season of the origin."""
    halves = split_halves(od.rows, np.arange(len(od.rows), dtype=np.int64))
    return {t: split_half_target(od, t, kernel, penalties, halves) for t in od.seasons}


def reliability_summary(
    pairs: Mapping[int, Mapping[str, HalfPairs]],
    team_counts: Mapping[int, Mapping[str, NDArray[Any]]],
) -> dict[str, Any]:
    """Split-half r and Spearman-Brown reliability by season, era, stratum, band and roster."""
    groups: dict[str, list[tuple[NDArray[np.float64], NDArray[np.float64]]]] = {}
    for season, roles in pairs.items():
        table = team_counts[season]
        for role, p in roles.items():
            changed = table["teams"][np.searchsorted(table["player_id"], p.player_id)] > 1
            bands = band_of(p.exposure)
            keys: list[tuple[str, NDArray[np.bool_]]] = [
                ("all", np.ones(p.first.size, dtype=bool)),
                (f"season:{season}", np.ones(p.first.size, dtype=bool)),
                (f"era:{ERA[season]}", np.ones(p.first.size, dtype=bool)),
                (f"verification:{VERIFICATION_GROUP[season]}", np.ones(p.first.size, dtype=bool)),
                ("roster:team_change", changed),
                ("roster:single_team", ~changed),
            ]
            keys += [
                (f"band:{_band_label(lo, hi)}", bands == _band_label(lo, hi))
                for lo, hi in EXPOSURE_BANDS
            ]
            for name, keep in keys:
                groups.setdefault(f"{role}|{name}", []).append((p.first[keep], p.second[keep]))
    out: dict[str, Any] = {}
    for name, parts in sorted(groups.items()):
        x = np.concatenate([a for a, _ in parts])
        y = np.concatenate([b for _, b in parts])
        r = _corr(x, y)
        out[name] = {"pairs": int(x.size), "split_half_r": r, "spearman_brown": spearman_brown(r)}
    return out


def bootstrap_target(
    od: OriginData,
    target: int,
    kernel: Kernel,
    penalties: tuple[float, float],
    table: Mapping[str, NDArray[Any]],
    *,
    replicates: int = BOOTSTRAP_REPLICATES,
    seed: int = BOOTSTRAP_SEED,
    reference: str = "",
) -> dict[str, Any]:
    """Game-clustered bootstrap standard errors of one season's labels.

    Each replicate redraws the games of the origin's rows with replacement (multinomial game
    counts), multiplies the kernel weights by the counts and refits the joint model with the
    frozen penalties. Labels are centred with the full-sample target-season exposures. A
    replicate whose fit fails is recorded and left out; it never stops the others.
    """
    games = len(od.rows.game_ids)
    rng = np.random.default_rng([seed, target, sum(map(ord, reference))])
    draws = {
        role: np.full((replicates, table["player_id"].size), np.nan)
        for role in ("offense", "defense")
    }
    centre = season_exposure(od, target)
    failures: list[str] = []
    for b in range(replicates):
        counts = rng.multinomial(games, np.full(games, 1.0 / games)).astype(np.float64)
        try:
            fit = fit_season(
                od, target, kernel, *penalties, multiplicity=counts[od.rows.game], note=f"boot{b}"
            )
        except FIT_FAILURES as exc:
            failures.append(f"replicate {b}: {type(exc).__name__}: {exc}")
            continue
        replicate = labels(od, fit, centre=centre)
        ia, ib = _join(table, replicate)
        for role in ("offense", "defense"):
            draws[role][b, ia] = replicate[role][ib]
    with np.errstate(invalid="ignore"):
        out: dict[str, Any] = {
            f"{role}_se": np.nanstd(values, axis=0, ddof=1) for role, values in draws.items()
        }
    out["replicates_with_label"] = np.sum(~np.isnan(draws["offense"]), axis=0).astype(np.float64)
    out["failed_replicates"] = failures
    return out


def bootstrap_labels(
    od: OriginData,
    kernel: Kernel,
    penalties: tuple[float, float],
    tables: Mapping[int, Mapping[str, NDArray[Any]]],
    *,
    replicates: int = BOOTSTRAP_REPLICATES,
    seed: int = BOOTSTRAP_SEED,
    reference: str = "",
) -> dict[int, dict[str, Any]]:
    """``bootstrap_target`` for every target season of the origin."""
    return {
        t: bootstrap_target(
            od,
            t,
            kernel,
            penalties,
            tables[t],
            replicates=replicates,
            seed=seed,
            reference=reference,
        )
        for t in od.seasons
    }


def exposure_summary(
    tables: Mapping[int, Mapping[str, NDArray[Any]]],
    errors: Mapping[int, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Label spread, shrinkage and bootstrap reliability by target-season exposure band."""
    pooled = {k: np.concatenate([t[k] for t in tables.values()]) for k in LABEL_FIELDS}
    se = (
        {
            role: np.concatenate([errors[s][f"{role}_se"] for s in tables])
            for role in ("offense", "defense")
        }
        if errors
        else None
    )
    exposure = pooled["offense_possessions"] + pooled["defense_possessions"]
    bands = band_of(exposure)
    out: dict[str, Any] = {}
    for lo, hi in EXPOSURE_BANDS:
        keep = bands == _band_label(lo, hi)
        result: dict[str, Any] = {"labels": int(keep.sum())}
        for role in ("offense", "defense"):
            values = pooled[role][keep]
            entry: dict[str, Any] = {
                "sd": float(np.std(values)) if values.size else None,
                "mean_abs": float(np.mean(np.abs(values))) if values.size else None,
            }
            if se is not None and values.size > 1:
                mean_var = float(np.nanmean(se[role][keep] ** 2))
                entry["mean_bootstrap_se"] = float(np.sqrt(mean_var))
                variance = float(np.var(values))
                entry["bootstrap_reliability"] = 1 - mean_var / variance if variance > 0 else None
            result[role] = entry
        out[_band_label(lo, hi)] = result
    return out


def season_summary(tables: Mapping[int, Mapping[str, NDArray[Any]]]) -> dict[str, Any]:
    """Per-season label counts, spread, cohort sizes and raw-centring shift."""
    out: dict[str, Any] = {}
    for season, t in sorted(tables.items()):
        common = (t["offense_possessions"] >= MIN_ROLE_POSSESSIONS) & (
            t["defense_possessions"] >= MIN_ROLE_POSSESSIONS
        )
        out[str(season)] = {
            "era": ERA[season],
            "verification_group": VERIFICATION_GROUP[season],
            "labels": int(t["player_id"].size),
            "labels_min_role_possessions": int(common.sum()),
            "players_with_team_change": int(np.sum(t["teams"] > 1)),
            **{f"{role}_sd": float(np.std(t[role])) for role in ("offense", "defense", "total")},
            **{
                f"{role}_sd_min_role_possessions": float(np.std(t[role][common]))
                if common.any()
                else None
                for role in ("offense", "defense")
            },
            "offense_raw_weighted_mean": float(
                np.average(t["offense_raw"], weights=t["offense_possessions"])
            ),
            "defense_raw_weighted_mean": float(
                np.average(t["defense_raw"], weights=t["defense_possessions"])
            ),
        }
    return out


# --- the reference run -----------------------------------------------------------------------


# Fit failures that protocol §10 records instead of stopping the run. Leakage and identity
# guards raise AssertionError, which is never caught.
FIT_FAILURES: tuple[type[Exception], ...] = (ValueError, RuntimeError, np.linalg.LinAlgError)
T = TypeVar("T")


class Checkpoints:
    """Run each stage once, record a failure instead of raising, and persist the outcome.

    With a directory, every stage's outcome and its fit-log entries are pickled atomically under
    a key, and a resumed run reloads them instead of recomputing. Every stage is deterministic,
    so resuming does not change any result. ``progress.jsonl`` records each stage.
    """

    def __init__(self, directory: Path | None, log: list[dict[str, Any]]) -> None:
        self.directory = directory
        self.log = log
        self.failures: list[dict[str, str]] = []
        if directory is not None:
            directory.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        assert self.directory is not None
        return self.directory / f"{hashlib.sha256(key.encode()).hexdigest()[:40]}.pkl"

    def attempt(self, key: str, compute: Callable[[], T]) -> tuple[bool, T | str]:
        started = time.perf_counter()
        if self.directory is not None and self._path(key).is_file():
            with self._path(key).open("rb") as handle:
                payload = pickle.load(handle)
            if payload["key"] != key:
                raise AssertionError(f"checkpoint {key} holds another stage")
            self.log.extend(payload["log"])
            ok, value, status = payload["ok"], payload["value"], "resumed"
        else:
            first = len(self.log)
            try:
                value = compute()
                ok = True
            except FIT_FAILURES as exc:
                value = f"{type(exc).__name__}: {exc}"
                ok = False
            status = "computed"
            if self.directory is not None:
                temporary = self._path(key).with_suffix(".tmp")
                with temporary.open("wb") as handle:
                    pickle.dump(
                        {"key": key, "ok": ok, "value": value, "log": self.log[first:]}, handle
                    )
                os.replace(temporary, self._path(key))
        if not ok:
            self.failures.append({"stage": key, "reason": str(value)})
        if self.directory is not None:
            with (self.directory.parent / "progress.jsonl").open("a") as handle:
                handle.write(
                    json.dumps(
                        {
                            "at": datetime.now(timezone.utc).isoformat(),
                            "stage": key,
                            "status": status,
                            "ok": ok,
                            "seconds": round(time.perf_counter() - started, 3),
                        }
                    )
                    + "\n"
                )
        return ok, value


@dataclass
class ReferenceResult:
    frozen: list[FrozenTarget]
    tables: dict[str, dict[int, dict[str, NDArray[Any]]]]  # origin key -> season -> table
    eval_tables: dict[int, dict[str, NDArray[Any]]]
    sensitivity_tables: dict[str, dict[int, dict[str, NDArray[Any]]]]
    errors: dict[int, dict[str, Any]]
    summary: dict[str, Any]


EVALUATION_SCENARIO = "evaluation_K0"


def sensitivity_scenarios(
    reference: str, rows: Rows
) -> list[tuple[str, Kernel, NDArray[np.bool_] | None, str]]:
    """Final-origin sensitivities: (name, kernel, available rows, offset mode)."""
    if reference != "contiguous":
        return []
    return [
        ("K730", WIDE_KERNEL, None, "joint"),
        ("regular_only", PRIMARY_KERNEL, ~rows.playoff, "joint"),
        ("pooled_window", POOLED_KERNEL, None, "joint"),
        ("exclude_no_livedata", PRIMARY_KERNEL, ~rows.no_livedata, "joint"),
        ("two_stage_offset", PRIMARY_KERNEL, None, "two_stage"),
    ]


def year_to_year(
    tables: Mapping[int, Mapping[str, NDArray[Any]]], calendar: Mapping[int, tuple[date, date]]
) -> dict[str, Any]:
    """Consecutive eligible seasons' season-only labels: disjoint data, real elapsed years."""
    seasons = sorted(tables)
    out: dict[str, Any] = {}
    for a, b in zip(seasons, seasons[1:], strict=False):
        out[f"{a}->{b}"] = {
            "elapsed_days_between_season_midpoints": (
                calendar[b][0]
                + (calendar[b][1] - calendar[b][0]) / 2
                - (calendar[a][0] + (calendar[a][1] - calendar[a][0]) / 2)
            ).days,
            **compare_labels(tables[a], tables[b]),
        }
    return out


def _target_set(
    rows: Rows,
    teams: NDArray[np.int64],
    origin: Origin,
    kernel: Kernel,
    log: list[dict[str, Any]],
    **kwargs: Any,
) -> tuple[FrozenTarget, dict[int, dict[str, NDArray[Any]]], dict[str, Any]]:
    """``build_target_set`` without the origin data, which is rebuilt when needed."""
    record, tables, od, search = build_target_set(rows, teams, origin, kernel, log, **kwargs)
    search["players"] = od.design.size
    return record, tables, search


def run_reference(
    rows: Rows,
    teams: NDArray[np.int64],
    reference: str,
    calendar: Mapping[int, tuple[date, date]],
    log: list[dict[str, Any]],
    *,
    bootstrap_replicates: int = BOOTSTRAP_REPLICATES,
    provenance: Mapping[str, str] | None = None,
    checkpoints: Checkpoints | None = None,
) -> ReferenceResult:
    """Every rolling origin, then reliability, evaluation labels and sensitivities at the last.

    Protocol §10: a stage whose fit fails is recorded with its reason and nothing is
    substituted. A failed origin is unavailable. If the final origin fails, the final-origin
    analyses are unavailable too.
    """
    ck = checkpoints if checkpoints is not None else Checkpoints(None, log)
    first_failure = len(ck.failures)
    origins = origin_schedule(reference, calendar)
    frozen: list[FrozenTarget] = []
    tables: dict[str, dict[int, dict[str, NDArray[Any]]]] = {}
    per_origin: dict[str, Any] = {}
    failed_origins: list[dict[str, Any]] = []
    for origin in origins:
        ok, value = ck.attempt(
            f"{reference}/origin/{origin.key}",
            partial(_target_set, rows, teams, origin, PRIMARY_KERNEL, log, provenance=provenance),
        )
        if not ok:
            failed_origins.append(
                {
                    "origin": origin.key,
                    "closes_season": origin.closes_season,
                    "status": "unavailable",
                    "reason": value,
                }
            )
            continue
        assert not isinstance(value, str)
        record, origin_tables, search = value
        frozen.append(record)
        tables[origin.key] = origin_tables
        per_origin[origin.key] = {
            "closes_season": origin.closes_season,
            "cutoff": origin.cutoff.isoformat(),
            "seasons": list(record.seasons),
            "rows": record.rows,
            "offense_ridge": record.offense_ridge,
            "defense_ridge": record.defense_ridge,
            "input_digest": record.input_digest,
            "label_counts": {str(s): int(t["player_id"].size) for s, t in origin_tables.items()},
            **search,
        }
    final = origins[-1]
    summary: dict[str, Any] = {
        "reference": reference,
        "seasons": list(REFERENCES[reference]),
        "artifact_label": ARTIFACT_LABEL,
        "origins": per_origin,
        "unavailable_origins": unavailable_origins(reference),
        "failed_origins": failed_origins,
        "final_origin": final.key,
    }
    if final.key not in tables:
        summary["final_analyses"] = "unavailable: the final origin could not be fitted"
        summary["failures"] = ck.failures[first_failure:]
        return ReferenceResult(frozen, tables, {}, {}, {}, summary)
    last = frozen[-1]
    penalties = (last.offense_ridge, last.defense_ridge)
    final_tables = tables[final.key]
    final_od = origin_data(
        rows, teams, eligible_mask(rows, REFERENCES[reference], final.cutoff), log, label=final.key
    )
    if final_od.digest != last.input_digest:
        raise AssertionError("the rebuilt final origin differs from its frozen inputs")

    # Reliability at the final origin, one stage per target season.
    halves = split_halves(final_od.rows, np.arange(len(final_od.rows), dtype=np.int64))
    pairs: dict[int, dict[str, HalfPairs]] = {}
    errors: dict[int, dict[str, Any]] = {}
    for target in final_od.seasons:
        half_ok, half_value = ck.attempt(
            f"{reference}/split_half/{target}",
            partial(split_half_target, final_od, target, PRIMARY_KERNEL, penalties, halves),
        )
        if half_ok:
            assert not isinstance(half_value, str)
            pairs[target] = half_value
        boot_ok, boot_value = ck.attempt(
            f"{reference}/bootstrap/{target}",
            partial(
                bootstrap_target,
                final_od,
                target,
                PRIMARY_KERNEL,
                penalties,
                final_tables[target],
                replicates=bootstrap_replicates,
                reference=reference,
            ),
        )
        if boot_ok:
            assert not isinstance(boot_value, str)
            errors[target] = boot_value
    split = reliability_summary(pairs, final_tables)

    # Label revision as later seasons arrive: as frozen (each origin's own penalties), and
    # refitted with the final penalties so that data change is separated from penalty change.
    revision: dict[str, Any] = {}
    revision_fixed: dict[str, Any] = {}
    for origin in origins[:-1]:
        if origin.key not in tables:
            continue
        ok, value = ck.attempt(
            f"{reference}/revision_final_penalties/{origin.key}",
            partial(
                _target_set,
                rows,
                teams,
                origin,
                PRIMARY_KERNEL,
                log,
                penalties=penalties,
                scenario="revision_final_penalties",
            ),
        )
        for season, table in tables[origin.key].items():
            key = f"{season}@{origin.cutoff.isoformat()}"
            revision[key] = compare_labels(table, final_tables[season])
            if ok:
                assert not isinstance(value, str)
                revision_fixed[key] = compare_labels(value[1][season], final_tables[season])

    # Evaluation labels for #30: season-only (K0) labels at the final origin with their own
    # cross-validated penalties. Each uses only its own season's rows.
    eval_tables: dict[int, dict[str, NDArray[Any]]] = {}
    eval_meta: dict[str, Any] = {"scenario": EVALUATION_SCENARIO}
    ok, value = ck.attempt(
        f"{reference}/{EVALUATION_SCENARIO}",
        partial(
            _target_set, rows, teams, final, SEASON_ONLY_KERNEL, log, scenario=EVALUATION_SCENARIO
        ),
    )
    if ok:
        assert not isinstance(value, str)
        eval_record, eval_tables, eval_search = value
        for season, table in eval_tables.items():
            if set(table["kernel_seasons"].tolist()) != {str(season)}:
                raise AssertionError("an evaluation label read a row of another season")
        eval_meta.update(
            {
                "kernel": eval_record.kernel,
                "offense_ridge": eval_record.offense_ridge,
                "defense_ridge": eval_record.defense_ridge,
                "cv_mse": eval_search.get("cv_mse"),
                "label_counts": {str(s): int(t["player_id"].size) for s, t in eval_tables.items()},
                "year_to_year": year_to_year(eval_tables, calendar),
                "primary_vs_season_only": {
                    str(s): compare_labels(final_tables[s], t) for s, t in eval_tables.items()
                },
            }
        )
    else:
        eval_meta["status"] = f"unavailable: {value}"

    # Sensitivities at the final origin; each reselects its penalties by the same CV.
    sensitivity_tables: dict[str, dict[int, dict[str, NDArray[Any]]]] = {}
    sensitivity: dict[str, Any] = {}
    for name, kernel, available, mode in sensitivity_scenarios(reference, rows):
        ok, value = ck.attempt(
            f"{reference}/sensitivity/{name}",
            partial(
                _target_set,
                rows,
                teams,
                final,
                kernel,
                log,
                available=available,
                scenario=name,
                offset_mode=mode,
            ),
        )
        if not ok:
            sensitivity[name] = {"status": f"unavailable: {value}"}
            continue
        assert not isinstance(value, str)
        record, scenario_tables, search = value
        sensitivity_tables[name] = scenario_tables
        sensitivity[name] = {
            "kernel": kernel.name,
            "offset_mode": mode,
            "offense_ridge": record.offense_ridge,
            "defense_ridge": record.defense_ridge,
            "rows": record.rows,
            "seasons": list(record.seasons),
            "label_shift_vs_primary": {
                str(s): compare_labels(final_tables[s], t)
                for s, t in scenario_tables.items()
                if s in final_tables
            },
            "cv_mse": search.get("cv_mse"),
        }

    summary.update(
        {
            "split_half": split,
            "split_half_seasons": sorted(pairs),
            "bootstrap": {
                str(t): {
                    "failed_replicates": e["failed_replicates"],
                    "min_replicates_with_label": float(np.min(e["replicates_with_label"]))
                    if e["replicates_with_label"].size
                    else None,
                }
                for t, e in errors.items()
            },
            "exposure": exposure_summary({t: final_tables[t] for t in errors}, errors),
            "seasons_final": season_summary(final_tables),
            "label_revision_vs_final": revision,
            "label_revision_vs_final_fixed_penalties": revision_fixed,
            "evaluation_labels": eval_meta,
            "sensitivity": sensitivity,
            "failures": ck.failures[first_failure:],
        }
    )
    return ReferenceResult(frozen, tables, eval_tables, sensitivity_tables, errors, summary)


def chronological_registration(
    calendar: Mapping[int, tuple[date, date]],
) -> dict[str, Any]:
    """The #30 evaluation folds: train on targets frozen before season e, score season e."""
    out: dict[str, Any] = {}
    for reference in REFERENCES:
        origins = origin_schedule(reference, calendar)
        folds = []
        for previous, origin in zip(origins, origins[1:], strict=False):
            folds.append(
                {
                    "evaluation_season": origin.closes_season,
                    "training_target_set": previous.key,
                    "training_seasons": [
                        s for s in REFERENCES[reference] if s <= previous.closes_season
                    ],
                    "evaluation_label": (
                        f"{reference}:{EVALUATION_SCENARIO}@{origins[-1].key}:"
                        f"{origin.closes_season}"
                    ),
                    "evaluation_label_rows": f"season {origin.closes_season} only",
                }
            )
        out[reference] = {
            "folds": folds,
            "first_season_unavailable": {
                "season": origins[0].closes_season,
                "reason": "no eligible earlier target in this reference",
            },
            "outer_seasons_use": origins[-1].key,
        }
    return out


# --- I/O and runner --------------------------------------------------------------------------


def season_calendar_and_strata(
    processed: Path, season: int
) -> tuple[tuple[date, date], dict[str, int]]:
    """First and last date of every expected game, and accepted-game strata counts."""
    import duckdb

    pin = check_target_season(season)
    path = str(processed / pin.label / pin.row_set / "game_reconciliation.parquet")
    source = f"read_parquet('{path.replace(chr(39), chr(39) * 2)}')"
    connection = duckdb.connect()
    span = connection.execute(f"SELECT min(game_date), max(game_date) FROM {source}").fetchone()
    strata = dict(
        connection.execute(
            f"SELECT s, count(*) FROM (SELECT unnest(strata) s FROM {source} WHERE accepted) "
            "GROUP BY 1"
        ).fetchall()
    )
    accepted = connection.execute(f"SELECT count(*) FROM {source} WHERE accepted").fetchone()
    connection.close()
    if span is None or accepted is None:
        raise ValueError(f"{pin.label} reconciliation is empty")
    strata = {str(k): int(v) for k, v in strata.items()}
    strata["_accepted_games"] = int(accepted[0])
    return (span[0], span[1]), strata


def check_strata(season: int, strata: Mapping[str, int]) -> None:
    """Refuse repaired games and a verification group that disagrees with the strata."""
    if strata.get(REPAIRED_STRATUM, 0):
        raise ValueError(f"{season} contains ADR-0023 repaired games, which are not canonical")
    accepted = strata["_accepted_games"]
    group = VERIFICATION_GROUP[season]
    no_livedata = strata.get("no_livedata", 0)
    no_datanba = strata.get("no_datanba", 0)
    expected_livedata = 0 if group == "livedata" else accepted
    expected_datanba = accepted if group.endswith("no_datanba") else 0
    if no_livedata != expected_livedata or no_datanba != expected_datanba:
        raise ValueError(f"{season} strata disagree with verification group {group}")


def team_codes(offense_team: NDArray[Any], game: NDArray[np.int64]) -> NDArray[np.int64]:
    """Raw numeric offense and defense team IDs per row; the defense is the game's other team.

    Raw IDs, not codes built from every loaded season, so a later season cannot change them.
    """
    offense = np.array([int(str(t)) for t in np.asarray(offense_team).tolist()], dtype=np.int64)
    if offense.size and int(np.min(offense)) <= 0:
        raise ValueError("team IDs must be positive integers")
    games = int(np.max(game)) + 1
    low = np.full(games, np.iinfo(np.int64).max)
    high = np.full(games, np.iinfo(np.int64).min)
    np.minimum.at(low, game, offense)
    np.maximum.at(high, game, offense)
    present = np.unique(game)
    if np.any(low[present] == high[present]):
        raise ValueError("a game has rows for only one offense")
    if np.any((offense != low[game]) & (offense != high[game])):
        raise ValueError("a game has more than two offenses")
    return np.column_stack([offense, low[game] + high[game] - offense])


def verify_protocol(
    path: Path, expected_sha256: str | None, repo: Path = REPO_ROOT
) -> dict[str, Any]:
    """Refuse unless the protocol is committed, unmodified, matches its digest, on a clean tree."""
    try:
        return verify_addendum(path, expected_sha256, repo)
    except AddendumError as exc:
        raise ProtocolError(str(exc).replace("addendum", "protocol")) from exc


def _cell(value: Any) -> Any:
    return value.item() if isinstance(value, np.generic) else value


def _write_tables(
    path: Path, tables: Iterable[tuple[Mapping[str, Any], Mapping[str, NDArray[Any]]]]
) -> None:
    keys = None
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        for meta, table in tables:
            columns = [name for name in table]
            if keys is None:
                keys = list(meta) + columns
                writer.writerow(keys)
            for i in range(table["player_id"].size):
                writer.writerow([*meta.values(), *(_cell(table[c][i]) for c in columns)])


def main_run(
    processed: Path,
    output_dir: Path,
    protocol: Path,
    protocol_sha256: str | None,
    repo: Path = REPO_ROOT,
    *,
    resume: bool = False,
) -> dict[str, Any]:
    """The single phase-2 run: refuses without the committed protocol on a clean tree.

    ``resume`` continues an interrupted run in its own directory. It refuses unless the
    directory's ``run_state.json`` names the same code commit, protocol digest and input rows,
    then reloads the completed stages from their checkpoints. Every stage is deterministic, so
    a resumed run writes the same results as an uninterrupted one.
    """
    freeze = verify_protocol(protocol, protocol_sha256, repo)
    provenance = {"code_commit": freeze["head_commit"], "protocol_sha256": freeze["sha256"]}
    started = time.perf_counter()
    state_path = output_dir / "run_state.json"
    if resume:
        if not state_path.is_file():
            raise ProtocolError(f"{output_dir} has no run state to resume")
        state = json.loads(state_path.read_text())
        if state["provenance"] != provenance or state["version"] != TARGET_VERSION:
            raise ProtocolError("the run to resume used another commit, protocol or version")
        if (output_dir / "manifest.json").exists():
            raise ProtocolError("the run already finished")
    else:
        output_dir.mkdir(parents=True, exist_ok=False)
    temp = output_dir / "duckdb_tmp"
    if temp.exists():
        shutil.rmtree(temp)
    temp.mkdir()
    calendar: dict[int, tuple[date, date]] = {}
    strata: dict[int, dict[str, int]] = {}
    for season in AUTHORIZED_SEASONS:
        calendar[season], strata[season] = season_calendar_and_strata(processed, season)
        check_strata(season, strata[season])
    loads = [
        load_season(processed, s, AUTHORIZED_SEASONS, temp, TARGET_PINS) for s in AUTHORIZED_SEASONS
    ]
    shutil.rmtree(temp)
    rows = assemble(loads)
    if int(np.max(rows.day)) >= DATA_END.toordinal() or not set(
        np.unique(rows.season).tolist()
    ) <= set(AUTHORIZED_SEASONS):
        raise AssertionError("a loaded row is outside the authorized seasons or dates")
    teams = team_codes(
        np.concatenate([np.asarray(s.data["offense_team_id"]) for s in loads]), rows.game
    )
    rows_digest = input_digest(rows, teams)
    if resume:
        if state["rows_digest"] != rows_digest:
            raise ProtocolError("the input rows differ from the run being resumed")
    else:
        _write_json(
            state_path,
            {
                "version": TARGET_VERSION,
                "provenance": provenance,
                "rows_digest": rows_digest,
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    with (output_dir / "progress.jsonl").open("a") as handle:
        handle.write(
            json.dumps(
                {
                    "at": datetime.now(timezone.utc).isoformat(),
                    "stage": "loaded",
                    "status": "resumed" if resume else "started",
                    "rows": len(rows),
                }
            )
            + "\n"
        )
    log: list[dict[str, Any]] = []
    checkpoints = Checkpoints(output_dir / "checkpoints", log)
    results: dict[str, Any] = {
        "issue": ISSUE,
        "version": TARGET_VERSION,
        "artifact_label": ARTIFACT_LABEL,
        "evidence_tier": EVIDENCE_TIER,
        "chronological_registration": chronological_registration(calendar),
        "references": {},
    }
    frozen: list[FrozenTarget] = []
    outputs: list[tuple[Mapping[str, Any], Mapping[str, NDArray[Any]]]] = []
    eval_out: list[tuple[Mapping[str, Any], Mapping[str, NDArray[Any]]]] = []
    sens_out: list[tuple[Mapping[str, Any], Mapping[str, NDArray[Any]]]] = []
    finals: dict[str, dict[int, dict[str, NDArray[Any]]]] = {}
    for reference in REFERENCES:
        result = run_reference(
            rows, teams, reference, calendar, log, provenance=provenance, checkpoints=checkpoints
        )
        results["references"][reference] = result.summary
        frozen.extend(result.frozen)
        final_key = result.summary["final_origin"]
        finals[reference] = result.tables.get(final_key, {})
        for key, by_season in result.tables.items():
            for season, table in sorted(by_season.items()):
                extra: dict[str, NDArray[Any]] = {}
                if key == final_key and season in result.errors:
                    extra = {
                        "offense_se": result.errors[season]["offense_se"],
                        "defense_se": result.errors[season]["defense_se"],
                    }
                else:
                    n = table["player_id"].size
                    extra = {"offense_se": np.full(n, np.nan), "defense_se": np.full(n, np.nan)}
                meta = {
                    "version": TARGET_VERSION,
                    "artifact_label": ARTIFACT_LABEL,
                    "reference": reference,
                    "origin": key,
                    "final_origin": key == final_key,
                    "target_season": season,
                    "verification_group": VERIFICATION_GROUP[season],
                }
                outputs.append((meta, {**table, **extra}))
        for season, table in sorted(result.eval_tables.items()):
            eval_out.append(
                (
                    {
                        "version": TARGET_VERSION,
                        "artifact_label": ARTIFACT_LABEL,
                        "reference": reference,
                        "scenario": EVALUATION_SCENARIO,
                        "origin": final_key,
                        "evaluation_season": season,
                    },
                    table,
                )
            )
        for name, by_season in result.sensitivity_tables.items():
            for season, table in sorted(by_season.items()):
                sens_out.append(
                    (
                        {
                            "artifact_label": ARTIFACT_LABEL,
                            "reference": reference,
                            "scenario": name,
                            "target_season": season,
                        },
                        table,
                    )
                )
    common = {
        str(s): compare_labels(finals["contiguous"][s], finals["extended"][s])
        for s in REFERENCES["contiguous"]
        if s in finals["contiguous"] and s in finals["extended"]
    }
    results["reference_agreement_final"] = common
    results["solver"] = _solver_summary([{**e, "temporal": e.get("kernel", "")} for e in log])
    results["solver"]["unconverged_kept"] = sum(1 for e in log if e.get("converged") == 0.0)
    results["failures"] = checkpoints.failures
    results["rows"] = {
        "possessions": len(rows),
        "games": len(rows.game_ids),
        "by_season": {str(s): int((rows.season == s).sum()) for s in AUTHORIZED_SEASONS},
    }
    results["calendar"] = {str(s): [a.isoformat(), b.isoformat()] for s, (a, b) in calendar.items()}
    results["strata"] = {str(s): v for s, v in strata.items()}
    _write_json(output_dir / "results.json", results)
    _write_json(output_dir / "frozen_targets.json", [_frozen_dict(f) for f in frozen])
    _write_json(output_dir / "fit_log.json", log)
    _write_tables(output_dir / "targets.csv", outputs)
    _write_tables(output_dir / "evaluation_labels.csv", eval_out)
    _write_tables(output_dir / "sensitivity_labels.csv", sens_out)
    names = (
        "results.json",
        "frozen_targets.json",
        "fit_log.json",
        "targets.csv",
        "evaluation_labels.csv",
        "sensitivity_labels.csv",
    )
    manifest = {
        "schema_version": 1,
        "issue": ISSUE,
        "version": TARGET_VERSION,
        "artifact_label": ARTIFACT_LABEL,
        "evidence_tier": EVIDENCE_TIER,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol": freeze,
        "inputs": {
            TARGET_PINS[s.season].label: {
                "row_set": s.pin.row_set,
                "row_manifest_sha256": s.pin.row_manifest_sha256,
                "row_set_build_id": s.row_manifest["build_id"],
                "pilot_build": s.pin.pilot_build,
                "pilot_manifest_sha256": s.pin.pilot_manifest_sha256,
                "pilot_digests": s.pilot_digests,
                "timing_audit": s.audit,
                "coverage": s.coverage,
            }
            for s in loads
        },
        "versions": _versions(),
        "runtime_seconds": time.perf_counter() - started,
        "peak_memory_mib": _peak_memory_mib(),
        "outputs": {name: _sha256(output_dir / name) for name in names},
        "private_outputs": [
            "targets.csv",
            "evaluation_labels.csv",
            "sensitivity_labels.csv",
            "frozen_targets.json",
        ],
    }
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def _frozen_dict(frozen: FrozenTarget) -> dict[str, Any]:
    return {name: getattr(frozen, name) for name in FrozenTarget.__slots__}


def main(argv: Sequence[str] | None = None) -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("processed", type=Path, help="the data/processed directory")
    cli.add_argument("output_dir", type=Path, help="new directory for the target run")
    cli.add_argument("--protocol", type=Path, default=PROTOCOL_PATH)
    cli.add_argument("--protocol-sha256", required=True)
    cli.add_argument(
        "--resume", action="store_true", help="continue an interrupted run in its own directory"
    )
    args = cli.parse_args(argv)
    manifest = main_run(
        args.processed, args.output_dir, args.protocol, args.protocol_sha256, resume=args.resume
    )
    print(json.dumps({k: manifest[k] for k in ("runtime_seconds", "peak_memory_mib", "outputs")}))


if __name__ == "__main__":
    main()
