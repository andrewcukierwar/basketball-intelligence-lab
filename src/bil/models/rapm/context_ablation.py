"""One-at-a-time context ablations of the #23 zero-prior RAPM baseline (issue #24).

Implements the frozen protocol in ``docs/research/rapm-context-protocol.md``. Context covariates
(home court, pre-possession score margin and game time) are derived from the pinned #19 pilot
event ledger using only events sequenced strictly before each possession starts. The pure
functions take in-memory arrays so they can be tested on synthetic data. ``main`` reads the
pinned private inputs and writes aggregate results, private player estimates and a manifest to a
new directory.
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from bil.evaluation.eligibility import played_before
from bil.models.rapm.baseline import (
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    EVIDENCE_TIER,
    PINNED_BUILD_ID,
    PINNED_DIGESTS,
    PLAYOFF_CUTOFF,
    SELECTION_FOLDS,
    Observation,
    _git,
    _peak_memory_mib,
    _sha256,
    bootstrap_delta,
    estimate_shift,
    verify_pins,
)
from bil.models.rapm.context import fit_context_only, fit_context_rapm
from bil.models.rapm.reference import Possession, RAPMFit, fit_rapm_diagnostics

RIDGE = 4000.0  # lambda* from #23, frozen; never re-tuned per variant
PILOT_MANIFEST_SHA256 = "89cb2e82af4d0fc4b7a95cf0f94b99b2b088361ffa893ce192de2b519d711570"
PILOT_DIGESTS = {
    "event.parquet": "6658c1b77f0381f7e2249017bbc7395677612fc3b291c097a073d32dcd00d211",
    "game.parquet": "0f7694ea326ab70f3f761f9e0e0f7aba7b73c57573624a80d046325900cb1a42",
    "score_allocation.parquet": "753968fbf14101723905599d1d78b979519bd46dd17250688cff8c65ab59d4bb",
}
MARGIN_CLIP = 20.0
# Offense-minus-defense margin bins; [-2, 2] is the reference category.
MARGIN_BINS = ((-np.inf, -15), (-14, -8), (-7, -3), (3, 7), (8, 14), (15, np.inf))
LATE_PERIOD = 4
BLOWOUT_MARGIN = 20
BLOWOUT_WEIGHT = 0.5
END_OF_PERIOD_SECONDS = 24
FINAL_MINUTES_SECONDS = 120
REGULATION_PERIOD_MS = 720_000
OVERTIME_PERIOD_MS = 300_000

FAMILY_COLUMNS: dict[str, tuple[str, ...]] = {
    "home": ("offense_home",),
    "score_linear": ("margin_clipped",),
    "score_binned": tuple(f"margin_{lo}_{hi}" for lo, hi in MARGIN_BINS),
    "score_late": ("margin_clipped", "margin_clipped_x_late"),
    "time": ("period_2", "period_3", "period_4", "overtime", "end_of_period", "final_two_minutes"),
    "home_score_time": (
        "offense_home",
        "margin_clipped",
        "period_2",
        "period_3",
        "period_4",
        "overtime",
        "end_of_period",
        "final_two_minutes",
    ),
}
# (name, context family or None, treatment)
VARIANTS: tuple[tuple[str, str | None, str], ...] = (
    ("C0", None, "zero_context"),
    ("H_fit", "home", "fitted"),
    ("H_off", "home", "offset"),
    ("S_fit", "score_linear", "fitted"),
    ("S_off", "score_linear", "offset"),
    ("Sbin_fit", "score_binned", "fitted"),
    ("Slate_fit", "score_late", "fitted"),
    ("T_fit", "time", "fitted"),
    ("T_off", "time", "offset"),
    ("HST_fit", "home_score_time", "fitted"),
    ("HST_off", "home_score_time", "offset"),
    ("W_half", None, "blowout_half_weight"),
    ("W_drop", None, "blowout_excluded"),
)
CONTEXT_ONLY = tuple(f"CTX_{family}" for family in FAMILY_COLUMNS)

# Pre-possession context: the cumulative score and clock at the last event sequenced strictly
# before the possession's first event. Events at or after ``start_seq`` never enter.
CONTEXT_SQL = """
WITH cum AS (
  SELECT game_id, stream_revision, seq, elapsed_ms,
         sum(home_delta) OVER w AS home_points, sum(away_delta) OVER w AS away_points
  FROM event
  WINDOW w AS (PARTITION BY game_id, stream_revision ORDER BY seq
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW))
SELECT m.game_id, m.offense_team_id, m.season_type, m.offense_player_ids, m.defense_player_ids,
       m.model_points, m.game_date, m.season_start_year, m.period, m.start_seq,
       m.offense_team_id = g.home_team_id AS offense_home, g.neutral_site,
       coalesce(c.home_points, 0) AS home_before, coalesce(c.away_points, 0) AS away_before,
       coalesce(c.elapsed_ms, 0) AS elapsed_before_ms, c.seq AS prior_seq,
       m.stream_revision, m.possession_seq
FROM model_row m
JOIN game g ON g.game_id = m.game_id AND g.revision = m.game_revision
ASOF LEFT JOIN cum c ON c.game_id = m.game_id AND c.stream_revision = m.stream_revision
  AND m.start_seq > c.seq
ORDER BY m.game_date, m.game_id, m.possession_seq
"""

# Timing audits on the pinned ledgers. Each count is reported; the first must be zero.
TIMING_SQL = {
    # A possession's own control points sequenced before it starts would leak its outcome.
    "own_points_sequenced_before_start": """
        SELECT count(*) FROM score_allocation a JOIN model_row m
          USING (game_id, stream_revision, possession_seq)
        WHERE a.possession_reason = 'control_possession' AND a.seq < m.start_seq""",
    # Own points credited after the possession ends affect only later possessions' state.
    "own_points_sequenced_after_end": """
        SELECT count(*) FROM score_allocation a JOIN model_row m
          USING (game_id, stream_revision, possession_seq)
        WHERE a.possession_reason = 'control_possession' AND a.seq >= m.end_seq""",
    # The clock at the prior event should not be later than the possession's first event.
    "prior_clock_after_first_event": """
        SELECT count(*) FROM context x
        JOIN event b ON b.game_id = x.game_id AND b.stream_revision = x.stream_revision
          AND b.seq = x.prior_seq
        JOIN event f ON f.game_id = x.game_id AND f.stream_revision = x.stream_revision
          AND f.seq = x.start_seq
        WHERE b.elapsed_ms > f.elapsed_ms""",
    # The event ledger and the score-allocation ledger give the same pre-possession score.
    "event_and_allocation_scores_disagree": """
        WITH alloc AS (
          SELECT a.game_id, a.stream_revision, a.seq,
                 sum(a.points_delta) FILTER (a.scoring_team_id = g.home_team_id) AS h,
                 sum(a.points_delta) FILTER (a.scoring_team_id = g.away_team_id) AS v
          FROM score_allocation a JOIN game_latest g USING (game_id) GROUP BY ALL),
        cum AS (
          SELECT game_id, stream_revision, seq,
                 sum(coalesce(h, 0)) OVER w AS home_points,
                 sum(coalesce(v, 0)) OVER w AS away_points
          FROM alloc WINDOW w AS (PARTITION BY game_id, stream_revision ORDER BY seq
                                  ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)),
        by_alloc AS (
          SELECT m.game_id, m.possession_seq, coalesce(c.home_points, 0) AS h,
                 coalesce(c.away_points, 0) AS v
          FROM model_row m ASOF LEFT JOIN cum c ON c.game_id = m.game_id
            AND c.stream_revision = m.stream_revision AND m.start_seq > c.seq)
        SELECT count(*) FROM by_alloc a JOIN context x USING (game_id, possession_seq)
        WHERE a.h <> x.home_before OR a.v <> x.away_before""",
}


@dataclass(frozen=True, slots=True)
class ContextRows:
    """Eligible possessions with their pre-possession covariates, in chronological order."""

    observations: list[Observation]
    dates: list[date]
    offense_home: NDArray[np.bool_]
    neutral: NDArray[np.bool_]
    neutral_unknown: NDArray[np.bool_]
    margin: NDArray[np.float64]  # offense minus defense before the possession
    period: NDArray[np.int64]
    elapsed_ms: NDArray[np.float64]  # game clock elapsed before the possession

    @property
    def playoff(self) -> NDArray[np.bool_]:
        return np.array([o.season_type == "playoffs" for o in self.observations])


def period_start_ms(period: NDArray[np.int64]) -> NDArray[np.float64]:
    regulation = np.minimum(period - 1, 4) * REGULATION_PERIOD_MS
    overtime = np.maximum(period - 5, 0) * OVERTIME_PERIOD_MS
    starts: NDArray[np.float64] = (regulation + overtime).astype(np.float64)
    return starts


def period_end_ms(period: NDArray[np.int64]) -> NDArray[np.float64]:
    length = np.where(period <= 4, REGULATION_PERIOD_MS, OVERTIME_PERIOD_MS)
    return period_start_ms(period) + length


def late_blowout(rows: ContextRows) -> NDArray[np.bool_]:
    """Fourth period or overtime with a pre-possession margin of at least 20 either way."""
    return (rows.period >= LATE_PERIOD) & (np.abs(rows.margin) >= BLOWOUT_MARGIN)


def feature_columns(rows: ContextRows) -> dict[str, NDArray[np.float64]]:
    """Every named context column. Neutral-court possessions code home as zero."""
    home = np.where(rows.neutral, 0.0, np.where(rows.offense_home, 1.0, -1.0))
    clipped = np.clip(rows.margin, -MARGIN_CLIP, MARGIN_CLIP)
    late = (rows.period >= LATE_PERIOD).astype(np.float64)
    remaining_s = (period_end_ms(rows.period) - rows.elapsed_ms) / 1000.0
    columns = {
        "offense_home": home,
        "margin_clipped": clipped,
        "margin_clipped_x_late": clipped * late,
        "period_2": (rows.period == 2).astype(np.float64),
        "period_3": (rows.period == 3).astype(np.float64),
        "period_4": (rows.period == 4).astype(np.float64),
        "overtime": (rows.period >= 5).astype(np.float64),
        "end_of_period": (remaining_s <= END_OF_PERIOD_SECONDS).astype(np.float64),
        "final_two_minutes": (
            (rows.period >= LATE_PERIOD) & (remaining_s <= FINAL_MINUTES_SECONDS)
        ).astype(np.float64),
    }
    for lo, hi in MARGIN_BINS:
        columns[f"margin_{lo}_{hi}"] = ((rows.margin >= lo) & (rows.margin <= hi)).astype(
            np.float64
        )
    return columns


def family_matrix(rows: ContextRows, family: str) -> NDArray[np.float64]:
    columns = feature_columns(rows)
    return np.column_stack([columns[name] for name in FAMILY_COLUMNS[family]])


def fold_masks(
    dates: Sequence[date], cutoff: date, end: date | None
) -> tuple[NDArray[np.bool_], NDArray[np.bool_]]:
    """Fit rows strictly before ``cutoff``; scored rows in ``[cutoff, end)`` (all later if None)."""
    fit = np.array([played_before(d, cutoff) for d in dates])
    scored = np.array([not played_before(d, cutoff) and (end is None or d < end) for d in dates])
    return fit, scored


def player_sums(
    fit: RAPMFit, observations: Sequence[Observation]
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Summed offensive and defensive effects per row. Unseen players take zero."""
    offense = np.array(
        [sum(fit.offense.get(p, 0.0) for p in o.possession.offense) for o in observations]
    )
    defense = np.array(
        [sum(fit.defense.get(p, 0.0) for p in o.possession.defense) for o in observations]
    )
    return offense, defense


@dataclass(frozen=True, slots=True)
class VariantFit:
    """A fitted variant: player fit, the context columns it uses and their fixed or fitted values."""

    players: RAPMFit
    family: str | None
    context: NDArray[np.float64]  # coefficients applied to the family's columns at prediction
    info: dict[str, float]


def _subset(rows: Sequence[Observation], mask: NDArray[np.bool_]) -> list[Observation]:
    return [row for row, keep in zip(rows, mask, strict=True) if keep]


def fit_variant(
    name: str,
    rows: ContextRows,
    mask: NDArray[np.bool_],
    *,
    ridge: float = RIDGE,
) -> VariantFit:
    """Fit one registered variant on the rows selected by ``mask`` (the fit window)."""
    family, treatment = next((f, t) for n, f, t in VARIANTS if n == name)
    fit_rows = _subset(rows.observations, mask)
    possessions = [o.possession for o in fit_rows]
    info: dict[str, float] = {}
    started = time.perf_counter()
    empty = np.zeros(0)
    if treatment == "zero_context":
        fit = fit_context_rapm(possessions, ridge=ridge, info=info)
        result = VariantFit(fit.players(), None, empty, info)
    elif treatment == "fitted":
        assert family is not None
        z = family_matrix(rows, family)[mask]
        fit = fit_context_rapm(possessions, z, ridge=ridge, info=info)
        result = VariantFit(fit.players(), family, np.array(fit.context), info)
    elif treatment == "offset":
        assert family is not None
        z = family_matrix(rows, family)[mask]
        y = np.array([100.0 * p.points for p in possessions])
        _, gamma = fit_context_only(y, z)
        fit = fit_context_rapm(possessions, ridge=ridge, offset=z @ gamma, info=info)
        result = VariantFit(fit.players(), family, gamma, info)
    elif treatment == "blowout_half_weight":
        weights = np.where(late_blowout(rows)[mask], BLOWOUT_WEIGHT, 1.0)
        weights = weights / weights.mean()  # mean weight 1 keeps lambda per unit possession
        weighted = [replace(p, weight=float(w)) for p, w in zip(possessions, weights, strict=True)]
        fit = fit_context_rapm(weighted, ridge=ridge, info=info)
        result = VariantFit(fit.players(), None, empty, info)
    elif treatment == "blowout_excluded":
        keep = mask & ~late_blowout(rows)
        fit = fit_context_rapm(
            [o.possession for o in _subset(rows.observations, keep)], ridge=ridge, info=info
        )
        result = VariantFit(fit.players(), None, empty, info)
    else:  # pragma: no cover - VARIANTS is closed
        raise ValueError(treatment)
    info["fit_seconds"] = time.perf_counter() - started
    info["rows"] = float(mask.sum())
    return result


def predict_variant(
    variant: VariantFit, rows: ContextRows, mask: NDArray[np.bool_]
) -> NDArray[np.float64]:
    offense, defense = player_sums(variant.players, _subset(rows.observations, mask))
    prediction = variant.players.intercept + offense - defense
    if variant.family is not None:
        prediction = prediction + family_matrix(rows, variant.family)[mask] @ variant.context
    return prediction


def context_only(
    rows: ContextRows, family: str, fit_mask: NDArray[np.bool_], scored_mask: NDArray[np.bool_]
) -> tuple[NDArray[np.float64], float, NDArray[np.float64]]:
    """Context-only comparator: no players. Returns predictions, intercept and coefficients."""
    z = family_matrix(rows, family)
    y = np.array([100.0 * o.possession.points for o in rows.observations])
    intercept, gamma = fit_context_only(y[fit_mask], z[fit_mask])
    return intercept + z[scored_mask] @ gamma, intercept, gamma


# --- scoring ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Block:
    """Held-out predictions for one scored set, keyed by model name."""

    y: NDArray[np.float64]
    predictions: dict[str, NDArray[np.float64]]
    game: NDArray[np.int64]
    team_game: NDArray[np.int64]
    blowout: NDArray[np.bool_]

    def subset(self, keep: NDArray[np.bool_]) -> Block:
        _, game = np.unique(self.game[keep], return_inverse=True)
        _, team_game = np.unique(self.team_game[keep], return_inverse=True)
        return Block(
            self.y[keep],
            {k: v[keep] for k, v in self.predictions.items()},
            game.astype(np.int64),
            team_game.astype(np.int64),
            self.blowout[keep],
        )


def block_indices(
    observations: Sequence[Observation],
) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    games: dict[str, int] = {}
    team_games: dict[tuple[str, str], int] = {}
    game = np.array([games.setdefault(o.game_id, len(games)) for o in observations])
    team_game = np.array(
        [team_games.setdefault((o.game_id, o.offense_team), len(team_games)) for o in observations]
    )
    return game.astype(np.int64), team_game.astype(np.int64)


def pool(blocks: Sequence[Block]) -> Block:
    game_offset = team_offset = 0
    games, team_games = [], []
    for block in blocks:
        games.append(block.game + game_offset)
        team_games.append(block.team_game + team_offset)
        game_offset += int(np.max(block.game)) + 1
        team_offset += int(np.max(block.team_game)) + 1
    return Block(
        np.concatenate([b.y for b in blocks]),
        {k: np.concatenate([b.predictions[k] for b in blocks]) for k in blocks[0].predictions},
        np.concatenate(games),
        np.concatenate(team_games),
        np.concatenate([b.blowout for b in blocks]),
    )


def team_game_rmse(block: Block, prediction: NDArray[np.float64]) -> float:
    size = int(np.max(block.team_game)) + 1
    actual = np.bincount(block.team_game, weights=block.y, minlength=size) / 100.0
    predicted = np.bincount(block.team_game, weights=prediction, minlength=size) / 100.0
    return float(np.sqrt(np.mean((predicted - actual) ** 2)))


def paired(
    block: Block, model: str, reference: str, *, resamples: int = BOOTSTRAP_RESAMPLES
) -> dict[str, Any]:
    """Mean per-possession squared-error delta (model minus reference) with a game bootstrap."""
    delta = (block.predictions[model] - block.y) ** 2 - (
        block.predictions[reference] - block.y
    ) ** 2
    low, high = bootstrap_delta(block.game, delta, resamples=resamples, seed=BOOTSTRAP_SEED)
    return {"delta": float(delta.mean()), "ci95": [low, high]}


def summarize_block(
    block: Block, *, team_games: bool = True, resamples: int = BOOTSTRAP_RESAMPLES
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "possessions": int(block.y.size),
        "games": int(np.max(block.game)) + 1,
        "mean_points_per_100": float(block.y.mean()),
        "models": {},
    }
    for name, prediction in block.predictions.items():
        entry: dict[str, Any] = {"mse": float(np.mean((prediction - block.y) ** 2))}
        if name != "league":
            entry["vs_league"] = paired(block, name, "league", resamples=resamples)
        if name not in {"league", "C0"}:
            entry["vs_C0"] = paired(block, name, "C0", resamples=resamples)
        if team_games:
            entry["team_game_rmse_points"] = team_game_rmse(block, prediction)
        out["models"][name] = entry
    return out


def verdict(comparison: dict[str, Any]) -> str:
    """Frozen rule: supported if the interval is wholly below zero, rejected if the point delta
    is at least zero, otherwise inconclusive."""
    low, high = comparison["ci95"]
    if high < 0:
        return "supported"
    if comparison["delta"] >= 0:
        return "rejected"
    return "inconclusive"


def context_bootstrap(
    rows: ContextRows, family: str, *, resamples: int = BOOTSTRAP_RESAMPLES
) -> dict[str, Any]:
    """Context-only coefficients on all rows with a game-clustered 95% percentile interval."""
    z = np.column_stack((np.ones(len(rows.observations)), family_matrix(rows, family)))
    y = np.array([100.0 * o.possession.points for o in rows.observations])
    game, _ = block_indices(rows.observations)
    size = int(np.max(game)) + 1
    k = z.shape[1]
    gram = np.zeros((size, k, k))
    moment = np.zeros((size, k))
    np.add.at(gram, game, z[:, :, None] * z[:, None, :])
    np.add.at(moment, game, z * y[:, None])
    point = np.linalg.solve(gram.sum(0), moment.sum(0))
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    draws = []
    for _ in range(resamples):
        pick = rng.integers(0, size, size=size)
        try:
            draws.append(np.linalg.solve(gram[pick].sum(0), moment[pick].sum(0)))
        except np.linalg.LinAlgError:  # a resample can miss a sparse indicator entirely
            continue
    low, high = np.percentile(np.array(draws), [2.5, 97.5], axis=0)
    names = ("intercept", *FAMILY_COLUMNS[family])
    return {
        name: {"estimate": float(point[i]), "ci95": [float(low[i]), float(high[i])]}
        for i, name in enumerate(names)
    } | {"usable_resamples": len(draws)}


# --- I/O --------------------------------------------------------------------------------


def verify_pilot(pilot_dir: Path, row_dir: Path) -> None:
    actual = _sha256(pilot_dir / "manifest.json")
    if actual != PILOT_MANIFEST_SHA256:
        raise ValueError(f"pilot manifest SHA-256 {actual} does not match the frozen pin")
    if json.loads((row_dir / "manifest.json").read_text())["pilot_manifest_sha256"] != actual:
        raise ValueError("row set was not built from the pinned pilot")
    listed = {
        a["filename"]: a["sha256"]
        for a in json.loads((pilot_dir / "manifest.json").read_text())["output_artifacts"]
    }
    for name, expected in PILOT_DIGESTS.items():
        if listed.get(name) != expected or _sha256(pilot_dir / name) != expected:
            raise ValueError(f"pilot {name} digest differs from the frozen pin")


def register(connection: Any, row_dir: Path, pilot_dir: Path) -> None:
    """Register the pinned tables under the names the SQL above uses."""
    for name, path in (
        ("model_row", row_dir / "model_row.parquet"),
        ("event", pilot_dir / "event.parquet"),
        ("game", pilot_dir / "game.parquet"),
        ("score_allocation", pilot_dir / "score_allocation.parquet"),
    ):
        literal = str(path).replace("'", "''")
        connection.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{literal}')")


def read_context(connection: Any) -> tuple[ContextRows, list[tuple[Any, ...]]]:
    """Run ``CONTEXT_SQL`` on registered ``model_row``, ``event`` and ``game`` tables."""
    connection.execute(f"CREATE OR REPLACE TEMP TABLE context AS {CONTEXT_SQL}")
    raw = connection.execute("SELECT * FROM context").fetchall()
    observations = [
        Observation(
            game_id,
            team,
            season_type,
            Possession(tuple(map(int, off)), tuple(map(int, dfn)), points, 1.0, played),
        )
        for game_id, team, season_type, off, dfn, points, played, *_ in raw
    ]
    period = np.array([r[8] for r in raw], dtype=np.int64)
    home_before = np.array([r[12] for r in raw], dtype=np.float64)
    away_before = np.array([r[13] for r in raw], dtype=np.float64)
    offense_home = np.array([bool(r[10]) for r in raw])
    margin = np.where(offense_home, home_before - away_before, away_before - home_before)
    elapsed = np.maximum(np.array([r[14] for r in raw], dtype=np.float64), period_start_ms(period))
    rows = ContextRows(
        observations=observations,
        dates=[r[6] for r in raw],
        offense_home=offense_home,
        neutral=np.array([r[11] is True for r in raw]),
        neutral_unknown=np.array([r[11] is None for r in raw]),
        margin=margin,
        period=period,
        elapsed_ms=elapsed,
    )
    return rows, raw


def timing_audit(connection: Any, raw: Sequence[tuple[Any, ...]]) -> dict[str, int]:
    """Count timing violations; requires ``context`` from ``read_context``."""
    connection.execute(
        "CREATE OR REPLACE TEMP VIEW game_latest AS SELECT game_id, home_team_id, away_team_id "
        "FROM game QUALIFY row_number() OVER (PARTITION BY game_id ORDER BY revision DESC) = 1"
    )
    audit = {name: int(connection.execute(sql).fetchone()[0]) for name, sql in TIMING_SQL.items()}
    period = np.array([r[8] for r in raw], dtype=np.int64)
    elapsed = np.array([r[14] for r in raw], dtype=np.float64)
    audit["prior_clock_before_period_start_clamped"] = int(
        np.sum(elapsed < period_start_ms(period))
    )
    audit["possessions_without_prior_event"] = sum(1 for r in raw if r[15] is None)
    return audit


def load(row_dir: Path, pilot_dir: Path) -> tuple[ContextRows, dict[str, int]]:
    import duckdb

    verify_pins(row_dir)
    verify_pilot(pilot_dir, row_dir)
    connection = duckdb.connect()
    register(connection, row_dir, pilot_dir)
    seasons = {
        r[0] for r in connection.execute("SELECT DISTINCT season_start_year FROM game").fetchall()
    }
    if seasons != {2022}:
        raise ValueError("only the 2022-23 season is in scope")
    rows, raw = read_context(connection)
    if {r[7] for r in raw} != {2022}:
        raise ValueError("only the 2022-23 season is in scope")
    audit = timing_audit(connection, raw)
    if audit["own_points_sequenced_before_start"] or audit["event_and_allocation_scores_disagree"]:
        raise ValueError(f"pre-possession covariates fail the timing audit: {audit}")
    return rows, audit


def _strata_counts(rows: ContextRows) -> dict[str, Any]:
    blow = late_blowout(rows)
    playoff = rows.playoff
    out: dict[str, Any] = {}
    for label, season in (("regular", ~playoff), ("playoffs", playoff)):
        games = {o.game_id for o, keep in zip(rows.observations, season, strict=True) if keep}
        out[label] = {
            "possessions": int(season.sum()),
            "games": len(games),
            "late_blowout_possessions": int((season & blow).sum()),
            "offense_home_possessions": int((season & rows.offense_home).sum()),
            "neutral_flagged_possessions": int((season & rows.neutral).sum()),
            "neutral_unknown_possessions": int((season & rows.neutral_unknown).sum()),
            "overtime_possessions": int((season & (rows.period >= 5)).sum()),
        }
    out["margin_distribution"] = {
        "p01": float(np.percentile(rows.margin, 1)),
        "p50": float(np.percentile(rows.margin, 50)),
        "p99": float(np.percentile(rows.margin, 99)),
        "share_clipped": float(np.mean(np.abs(rows.margin) > MARGIN_CLIP)),
    }
    columns = feature_columns(rows)
    out["column_means"] = {name: float(values.mean()) for name, values in columns.items()}
    return out


def run(row_dir: Path, pilot_dir: Path, output_dir: Path, protocol: Path) -> dict[str, Any]:
    started = time.perf_counter()
    rows, audit = load(row_dir, pilot_dir)
    y_all = np.array([100.0 * o.possession.points for o in rows.observations])
    blowout = late_blowout(rows)
    fit_log: list[dict[str, Any]] = []
    coefficients: dict[str, dict[str, Any]] = {}
    reference_check: dict[str, float] = {}

    def run_fold(label: str, fit_mask: NDArray[np.bool_], scored_mask: NDArray[np.bool_]) -> Block:
        scored_obs = _subset(rows.observations, scored_mask)
        predictions: dict[str, NDArray[np.float64]] = {
            "league": np.full(int(scored_mask.sum()), y_all[fit_mask].mean())
        }
        fold_coefficients: dict[str, Any] = {}
        for name, family, _ in VARIANTS:
            variant = fit_variant(name, rows, fit_mask)
            fit_log.append({"fold": label, "variant": name, **variant.info})
            predictions[name] = predict_variant(variant, rows, scored_mask)
            if family is not None:
                fold_coefficients[name] = dict(
                    zip(FAMILY_COLUMNS[family], map(float, variant.context), strict=True)
                )
            if name == "C0":
                # Oracle check: the zero-context solver equals the verified #23 solver.
                reference, info = fit_rapm_diagnostics(
                    [o.possession for o in _subset(rows.observations, fit_mask)], ridge=RIDGE
                )
                fit_log.append({"fold": label, "variant": "C0_reference_solver", **info})
                c0 = variant.players
                reference_check[label] = max(
                    abs(reference.intercept - c0.intercept),
                    max(abs(reference.offense[p] - c0.offense[p]) for p in c0.offense),
                    max(abs(reference.defense[p] - c0.defense[p]) for p in c0.defense),
                )
        for family in FAMILY_COLUMNS:
            prediction, intercept, gamma = context_only(rows, family, fit_mask, scored_mask)
            predictions[f"CTX_{family}"] = prediction
            fold_coefficients[f"CTX_{family}"] = {
                "intercept": intercept,
                **dict(zip(FAMILY_COLUMNS[family], map(float, gamma), strict=True)),
            }
        coefficients[label] = fold_coefficients
        game, team_game = block_indices(scored_obs)
        return Block(y_all[scored_mask], predictions, game, team_game, blowout[scored_mask])

    blocks: dict[str, Block] = {}
    fold_meta: dict[str, Any] = {}
    for i, (cutoff, end) in enumerate(SELECTION_FOLDS, start=1):
        fit_mask, scored_mask = fold_masks(rows.dates, cutoff, end)
        label = f"R{i}"
        blocks[label] = run_fold(label, fit_mask, scored_mask)
        fold_meta[label] = {
            "fit_cutoff": cutoff.isoformat(),
            "scored_block": [cutoff.isoformat(), end.isoformat()],
            "fit_rows": int(fit_mask.sum()),
            "fit_late_blowout_rows": int((fit_mask & blowout).sum()),
        }
    fit_mask, scored_mask = fold_masks(rows.dates, PLAYOFF_CUTOFF, None)
    blocks["P1"] = run_fold("P1", fit_mask, scored_mask)
    fold_meta["P1"] = {
        "fit_cutoff": PLAYOFF_CUTOFF.isoformat(),
        "scored_block": [PLAYOFF_CUTOFF.isoformat(), None],
        "fit_rows": int(fit_mask.sum()),
        "fit_late_blowout_rows": int((fit_mask & blowout).sum()),
    }

    pooled = pool([blocks[f"R{i}"] for i in range(1, 5)])
    sets = {
        "regular_season_pooled": pooled,
        "regular_season_late_blowout": pooled.subset(pooled.blowout),
        "regular_season_not_blowout": pooled.subset(~pooled.blowout),
        "playoffs": blocks["P1"],
        "playoffs_late_blowout": blocks["P1"].subset(blocks["P1"].blowout),
        "playoffs_not_blowout": blocks["P1"].subset(~blocks["P1"].blowout),
    }
    # Team-game totals are only meaningful when every possession of a team-game is scored.
    scored_sets = {
        name: summarize_block(block, team_games="blowout" not in name)
        for name, block in sets.items()
    }
    per_fold = {
        label: {**fold_meta[label], **summarize_block(block, team_games=False)}
        for label, block in blocks.items()
    }
    verdicts = {
        name: verdict(scored_sets["regular_season_pooled"]["models"][name]["vs_C0"])
        for name, _, _ in VARIANTS[1:]
    }
    offset_vs_fitted = {
        family_name: {
            "regular_season_pooled": paired(pooled, f"{family_name}_fit", f"{family_name}_off"),
            "playoffs": paired(blocks["P1"], f"{family_name}_fit", f"{family_name}_off"),
        }
        for family_name in ("H", "S", "T", "HST")
    }

    # Final in-sample fits on all 2022-23 rows (descriptive coefficient sensitivity).
    everything = np.ones(len(rows.observations), dtype=bool)
    finals: dict[str, VariantFit] = {}
    final_report: dict[str, Any] = {}
    for name, family, _ in VARIANTS:
        variant = fit_variant(name, rows, everything)
        fit_log.append({"fold": "final", "variant": name, **variant.info})
        finals[name] = variant
        prediction = predict_variant(variant, rows, everything)
        entry: dict[str, Any] = {
            "in_sample_mse": float(np.mean((prediction - y_all) ** 2)),
            "intercept": variant.players.intercept,
        }
        if family is not None:
            entry["context"] = dict(
                zip(FAMILY_COLUMNS[family], map(float, variant.context), strict=True)
            )
        if name != "C0":
            entry["shift_vs_C0"] = estimate_shift(finals["C0"].players, variant.players)
            entry["in_sample_mse_delta_vs_C0"] = (
                entry["in_sample_mse"] - final_report["C0"]["in_sample_mse"]
            )
        final_report[name] = entry
    final_context_only = {family: context_bootstrap(rows, family) for family in FAMILY_COLUMNS}

    output_dir.mkdir(parents=True, exist_ok=False)
    players = sorted(finals["C0"].players.offense)
    with (output_dir / "player_estimates.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "player_id",
                *(f"{n}_{part}" for n, _, _ in VARIANTS for part in ("offense", "defense")),
            ]
        )
        for p in players:
            writer.writerow(
                [
                    p,
                    *(
                        value
                        for n, _, _ in VARIANTS
                        for value in (
                            finals[n].players.offense.get(p, ""),
                            finals[n].players.defense.get(p, ""),
                        )
                    ),
                ]
            )

    iterations = [entry["iterations"] for entry in fit_log]
    results: dict[str, Any] = {
        "evidence_tier": EVIDENCE_TIER,
        "ridge": RIDGE,
        "variants": [{"name": n, "family": f, "treatment": t} for n, f, t in VARIANTS],
        "family_columns": FAMILY_COLUMNS,
        "timing_audit": audit,
        "strata_counts": _strata_counts(rows),
        "neutral_court": {
            "flagged_possessions": int(rows.neutral.sum()),
            "unknown_possessions": int(rows.neutral_unknown.sum()),
        },
        "scored_sets": scored_sets,
        "folds": per_fold,
        "verdicts_regular_season_pooled_vs_C0": verdicts,
        "fitted_minus_offset": offset_vs_fitted,
        "fold_coefficients": coefficients,
        "final_fits": final_report,
        "final_context_only_coefficients": final_context_only,
        "zero_context_vs_reference_solver_max_abs_diff": reference_check,
        "optimizer": {
            "fits": len(fit_log),
            "all_converged": all(e["stop"] in {0, 1, 2, 4, 5} for e in fit_log),
            "stop_codes": dict(Counter(int(e["stop"]) for e in fit_log)),
            "iterations": {
                "min": min(iterations),
                "median": float(np.median(iterations)),
                "max": max(iterations),
            },
            "max_condition_estimate": max(e["condition_estimate"] for e in fit_log),
            "total_fit_seconds": sum(e.get("fit_seconds", 0.0) for e in fit_log),
            "per_fit": fit_log,
        },
    }
    (output_dir / "results.json").write_text(json.dumps(results, indent=2, sort_keys=True))
    status = _git("status", "--porcelain")
    manifest = {
        "schema_version": 1,
        "issue": 24,
        "evidence_tier": EVIDENCE_TIER,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "row_set_build_id": PINNED_BUILD_ID,
        "row_set_digests": PINNED_DIGESTS,
        "pilot_manifest_sha256": PILOT_MANIFEST_SHA256,
        "pilot_digests": PILOT_DIGESTS,
        "protocol": {"path": str(protocol), "sha256": _sha256(protocol)},
        "code_commit": _git("rev-parse", "HEAD"),
        "working_tree_clean": status == "",
        "ridge": RIDGE,
        "versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": __import__("scipy").__version__,
            "duckdb": __import__("duckdb").__version__,
        },
        "runtime_seconds": time.perf_counter() - started,
        "peak_memory_mib": _peak_memory_mib(),
        "outputs": {
            name: _sha256(output_dir / name) for name in ("player_estimates.csv", "results.json")
        },
        "private_outputs": ["player_estimates.csv"],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def main(argv: Sequence[str] | None = None) -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("row_dir", type=Path, help="pinned #59 row-set directory")
    cli.add_argument("pilot_dir", type=Path, help="pinned #19 pilot build directory")
    cli.add_argument("output_dir", type=Path, help="new directory for results")
    cli.add_argument(
        "--protocol",
        type=Path,
        default=Path(__file__).resolve().parents[4] / "docs/research/rapm-context-protocol.md",
    )
    args = cli.parse_args(argv)
    manifest = run(args.row_dir, args.pilot_dir, args.output_dir, args.protocol)
    print(json.dumps({k: manifest[k] for k in ("runtime_seconds", "peak_memory_mib", "outputs")}))


if __name__ == "__main__":
    main()
