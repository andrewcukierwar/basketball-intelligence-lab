"""Chronological, game-grouped evaluation of the zero-prior RAPM baseline on the #59 rows.

Implements the frozen protocol in ``docs/research/rapm-baseline-protocol.md``. The pure
functions take in-memory observations so they can be tested on synthetic data. ``main``
reads the pinned private row set and writes aggregate results, private player estimates
and a manifest to a new directory.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import resource
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from bil.evaluation.eligibility import played_before
from bil.models.rapm.reference import Possession, RAPMFit, fit_rapm_diagnostics

PINNED_BUILD_ID = "bc7b0174a2277146aba4eedef5bae7dbfd90462e03b6db14f46f63bc3af45b68"
PINNED_DIGESTS = {
    "manifest.json": "0accaa154bc3c85077551a9337c422c56cf8fdfa8dd6a21b00840eca80527a22",
    "model_row.parquet": "ebadd15122df870cdfd40e43b04d381bbb6f7058e014c4c26802d8c93b58ad90",
    "game_reconciliation.parquet": "c0c4fee3398d28691023f2fbc937d424bc7095abda2117f1ec56909ab80eb0e2",
}
EVIDENCE_TIER = "retrospective_capture_bound"


@dataclass(frozen=True)
class RowSetPin:
    """Frozen identity of a row set: manifest build id and the digests that must match."""

    build_id: str
    digests: dict[str, str]


DEFAULT_PIN = RowSetPin(PINNED_BUILD_ID, PINNED_DIGESTS)
PENALTY_GRID = (250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0, 32000.0)
ROUTINE_STRATA = frozenset(
    {"same_clock_free_throw_substitution", "technical_free_throw", "overtime"}
)
# (fit cutoff, exclusive end of the scored block, role)
SELECTION_FOLDS = (
    (date(2022, 12, 15), date(2023, 1, 15)),
    (date(2023, 1, 15), date(2023, 2, 15)),
    (date(2023, 2, 15), date(2023, 3, 15)),
    (date(2023, 3, 15), date(2023, 4, 11)),
)
PLAYOFF_CUTOFF = date(2023, 4, 15)
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 2023
EXPOSURE_THRESHOLDS = (250, 500, 1000)
STABILITY_MIN_POSSESSIONS = 250
MAX_GRID_EXTENSIONS = 5


@dataclass(frozen=True, slots=True)
class Observation:
    """One eligible possession with the game and team keys the protocol groups by."""

    game_id: str
    offense_team: str
    season_type: str
    possession: Possession


@dataclass(frozen=True, slots=True)
class Scored:
    """Held-out arrays for one scored block. Rates are points per 100 possessions."""

    y: NDArray[np.float64]
    model: NDArray[np.float64]
    league: NDArray[np.float64]
    offense_only: NDArray[np.float64]
    defense_only: NDArray[np.float64]
    game: NDArray[np.int64]
    team_game: NDArray[np.int64]
    unseen: NDArray[np.bool_]


def _date(possession: Possession) -> date:
    assert possession.played_date is not None
    return possession.played_date


def split_fold(
    observations: Sequence[Observation], cutoff: date, end: date | None
) -> tuple[list[Observation], list[Observation]]:
    """Fit rows played strictly before ``cutoff``; scored rows in ``[cutoff, end)``.

    ``end=None`` scores every later row. A game is wholly on one side because a game has
    one played date, which is checked.
    """
    fit: list[Observation] = []
    scored: list[Observation] = []
    for row in observations:
        played = _date(row.possession)
        if played_before(played, cutoff):
            fit.append(row)
        elif end is None or played < end:
            scored.append(row)
    if {o.game_id for o in fit} & {o.game_id for o in scored}:
        raise ValueError("a game appears in both the fit and scored partitions")
    return fit, scored


def exclude_games(
    observations: Sequence[Observation], games: frozenset[str] | set[str]
) -> list[Observation]:
    return [row for row in observations if row.game_id not in games]


def fit_observations(
    observations: Sequence[Observation], ridge: float
) -> tuple[RAPMFit, dict[str, float]]:
    """Fit the zero-prior ridge and attach wall time to the LSQR diagnostics."""
    started = time.perf_counter()
    fit, info = fit_rapm_diagnostics([o.possession for o in observations], ridge=ridge)
    info["fit_seconds"] = time.perf_counter() - started
    info["rows"] = float(len(observations))
    return fit, info


def league_mean(observations: Sequence[Observation]) -> float:
    """Mean points per 100 possessions: the intercept of the zero-effects model."""
    return float(np.mean([100.0 * o.possession.points for o in observations]))


def score(fit: RAPMFit, league: float, scored: Sequence[Observation]) -> Scored:
    """Score held-out possessions with frozen effects. Unseen players have zero effect."""
    count = len(scored)
    y = np.empty(count)
    off_sum = np.empty(count)
    def_sum = np.empty(count)
    unseen = np.zeros(count, dtype=bool)
    games: dict[str, int] = {}
    team_games: dict[tuple[str, str], int] = {}
    game_index = np.empty(count, dtype=np.int64)
    team_game_index = np.empty(count, dtype=np.int64)
    for i, row in enumerate(scored):
        possession = row.possession
        y[i] = 100.0 * possession.points
        off_sum[i] = sum(fit.offense.get(p, 0.0) for p in possession.offense)
        def_sum[i] = sum(fit.defense.get(p, 0.0) for p in possession.defense)
        unseen[i] = any(p not in fit.offense for p in possession.offense + possession.defense)
        game_index[i] = games.setdefault(row.game_id, len(games))
        team_game_index[i] = team_games.setdefault((row.game_id, row.offense_team), len(team_games))
    return Scored(
        y=y,
        model=fit.intercept + off_sum - def_sum,
        league=np.full(count, league),
        offense_only=fit.intercept + off_sum,
        defense_only=fit.intercept - def_sum,
        game=game_index,
        team_game=team_game_index,
        unseen=unseen,
    )


def concat(parts: Sequence[Scored]) -> Scored:
    """Pool blocks, keeping game and team-game indices distinct across blocks."""
    game_offset = team_offset = 0
    games: list[NDArray[np.int64]] = []
    team_games: list[NDArray[np.int64]] = []
    for part in parts:
        games.append(part.game + game_offset)
        team_games.append(part.team_game + team_offset)
        game_offset += int(np.max(part.game)) + 1
        team_offset += int(np.max(part.team_game)) + 1
    return Scored(
        y=np.concatenate([p.y for p in parts]),
        model=np.concatenate([p.model for p in parts]),
        league=np.concatenate([p.league for p in parts]),
        offense_only=np.concatenate([p.offense_only for p in parts]),
        defense_only=np.concatenate([p.defense_only for p in parts]),
        game=np.concatenate(games),
        team_game=np.concatenate(team_games),
        unseen=np.concatenate([p.unseen for p in parts]),
    )


def mse(y: NDArray[np.float64], prediction: NDArray[np.float64]) -> float:
    return float(np.mean((prediction - y) ** 2))


def team_game_rmse(scored: Scored, prediction: NDArray[np.float64]) -> float:
    """RMSE in points of summed per-possession predictions against modeled points per team-game."""
    size = int(np.max(scored.team_game)) + 1
    actual = np.bincount(scored.team_game, weights=scored.y, minlength=size) / 100.0
    predicted = np.bincount(scored.team_game, weights=prediction, minlength=size) / 100.0
    return float(np.sqrt(np.mean((predicted - actual) ** 2)))


def bootstrap_delta(
    game: NDArray[np.int64],
    delta: NDArray[np.float64],
    *,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float]:
    """95% percentile interval of the mean per-possession delta, resampling whole games."""
    size = int(np.max(game)) + 1
    sums = np.bincount(game, weights=delta, minlength=size)
    counts = np.bincount(game, minlength=size).astype(np.float64)
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, size, size=(resamples, size))
    means = sums[pick].sum(axis=1) / counts[pick].sum(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return float(low), float(high)


def summarize(scored: Scored, *, resamples: int = BOOTSTRAP_RESAMPLES) -> dict[str, Any]:
    """Held-out metrics for the model, the league baseline and the offense/defense ablations."""
    squared = {
        name: (getattr(scored, name) - scored.y) ** 2
        for name in ("model", "league", "offense_only", "defense_only")
    }
    delta = squared["model"] - squared["league"]
    low, high = bootstrap_delta(scored.game, delta, resamples=resamples)
    return {
        "possessions": int(scored.y.size),
        "games": int(np.max(scored.game)) + 1,
        "possessions_with_unseen_player": int(scored.unseen.sum()),
        "mse": {name: float(values.mean()) for name, values in squared.items()},
        "rmse": {name: float(np.sqrt(values.mean())) for name, values in squared.items()},
        "delta_vs_league": {
            "model": float(delta.mean()),
            "model_ci95": [low, high],
            "offense_only": float((squared["offense_only"] - squared["league"]).mean()),
            "defense_only": float((squared["defense_only"] - squared["league"]).mean()),
        },
        "team_game_rmse_points": {
            name: team_game_rmse(scored, getattr(scored, name))
            for name in ("model", "league", "offense_only", "defense_only")
        },
    }


def select_penalty(
    pooled_mse: Callable[[float], float], grid: Sequence[float] = PENALTY_GRID
) -> tuple[float, dict[float, float]]:
    """Return the lowest-MSE penalty, extending the grid by factors of two off an edge."""
    values = sorted(grid)
    scores = {ridge: pooled_mse(ridge) for ridge in values}
    for _ in range(MAX_GRID_EXTENSIONS):
        best = min(scores, key=lambda ridge: scores[ridge])
        if best == min(scores):
            new = best / 2
        elif best == max(scores):
            new = best * 2
        else:
            return best, scores
        scores[new] = pooled_mse(new)
    return min(scores, key=lambda ridge: scores[ridge]), scores


def exposure(observations: Sequence[Observation]) -> dict[int, tuple[int, int, int]]:
    """Per player: offensive possessions, defensive possessions and distinct games."""
    offense: Counter[int] = Counter()
    defense: Counter[int] = Counter()
    games: dict[int, set[str]] = {}
    for row in observations:
        offense.update(row.possession.offense)
        defense.update(row.possession.defense)
        for player in row.possession.offense + row.possession.defense:
            games.setdefault(player, set()).add(row.game_id)
    return {p: (offense[p], defense[p], len(games[p])) for p in sorted(set(offense) | set(defense))}


def _quantiles(values: Sequence[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    names = ("min", "p05", "p25", "median", "p75", "p95", "max")
    cuts = np.percentile(array, [0, 5, 25, 50, 75, 95, 100])
    return {
        **{name: float(cut) for name, cut in zip(names, cuts, strict=True)},
        "mean": float(array.mean()),
        "sd": float(array.std()),
    }


def exposure_report(observations: Sequence[Observation], fit: RAPMFit) -> dict[str, Any]:
    """Aggregate exposure and estimate distributions. No player identifiers."""
    table = exposure(observations)
    players = sorted(table)
    off = np.array([table[p][0] for p in players], dtype=np.float64)
    dfn = np.array([table[p][1] for p in players], dtype=np.float64)
    total_exposure = off + dfn
    offense = np.array([fit.offense[p] for p in players])
    defense = np.array([fit.defense[p] for p in players])
    total = offense + defense
    rows = len(observations)
    report: dict[str, Any] = {
        "players": len(players),
        "possessions": rows,
        "offensive_possessions": _quantiles(off.tolist()),
        "defensive_possessions": _quantiles(dfn.tolist()),
        "games_per_player": _quantiles([float(table[p][2]) for p in players]),
        "below_threshold": {
            str(t): {
                "players": int(np.sum(off < t)),
                "share_of_players": float(np.mean(off < t)),
                "share_of_player_possessions": float(off[off < t].sum() / off.sum()),
            }
            for t in EXPOSURE_THRESHOLDS
        },
        "estimates_points_per_100": {
            "offense": _quantiles(offense.tolist()),
            "defense": _quantiles(defense.tolist()),
            "total": _quantiles(total.tolist()),
        },
        "offense_defense_correlation": float(np.corrcoef(offense, defense)[0, 1]),
        "intercept": fit.intercept,
    }
    bands = ((0, 500), (500, 1500), (1500, 3000), (3000, float("inf")))
    report["total_estimate_sd_by_on_court_possession_band"] = {
        f"{int(lo)}-{'inf' if hi == float('inf') else int(hi)}": {
            "players": int(mask.sum()),
            "sd": float(total[mask].std()) if mask.sum() > 1 else None,
        }
        for lo, hi in bands
        for mask in [(total_exposure >= lo) & (total_exposure < hi)]
    }
    return report


def split_halves(
    observations: Sequence[Observation],
) -> tuple[list[Observation], list[Observation]]:
    """Alternate games in chronological (date, game id) order into two disjoint halves."""
    order = sorted({(_date(o.possession), o.game_id) for o in observations})
    half = {game: i % 2 for i, (_, game) in enumerate(order)}
    first = [o for o in observations if half[o.game_id] == 0]
    second = [o for o in observations if half[o.game_id] == 1]
    return first, second


def _corr(a: NDArray[np.float64], b: NDArray[np.float64]) -> float:
    return float(np.corrcoef(a, b)[0, 1])


def stability(observations: Sequence[Observation], ridge: float) -> dict[str, Any]:
    """Correlation of estimates from two disjoint game halves, for well-observed players."""
    first, second = split_halves(observations)
    fits = [fit_observations(half, ridge)[0] for half in (first, second)]
    tables = [exposure(half) for half in (first, second)]
    players = [
        p
        for p in sorted(set(tables[0]) & set(tables[1]))
        if all(min(t[p][0], t[p][1]) >= STABILITY_MIN_POSSESSIONS for t in tables)
    ]
    result: dict[str, Any] = {
        "players": len(players),
        "min_possessions_per_role": STABILITY_MIN_POSSESSIONS,
    }
    if len(players) < 3:
        return result
    for name in ("offense", "defense"):
        result[f"{name}_correlation"] = _corr(
            np.array([getattr(fits[0], name)[p] for p in players]),
            np.array([getattr(fits[1], name)[p] for p in players]),
        )
    result["total_correlation"] = _corr(
        np.array([fits[0].offense[p] + fits[0].defense[p] for p in players]),
        np.array([fits[1].offense[p] + fits[1].defense[p] for p in players]),
    )
    return result


def estimate_shift(full: RAPMFit, other: RAPMFit) -> dict[str, Any]:
    """Shift of ``other`` relative to ``full`` for players present in both fits."""
    players = sorted(set(full.offense) & set(other.offense))
    result: dict[str, Any] = {
        "players_in_both": len(players),
        "players_only_in_full": len(full.offense) - len(players),
    }
    pairs = {
        "offense": (full.offense, other.offense),
        "defense": (full.defense, other.defense),
    }
    arrays = {
        name: (
            np.array([a[p] for p in players]),
            np.array([b[p] for p in players]),
        )
        for name, (a, b) in pairs.items()
    }
    arrays["total"] = (
        arrays["offense"][0] + arrays["defense"][0],
        arrays["offense"][1] + arrays["defense"][1],
    )
    for name, (a, b) in arrays.items():
        result[name] = {
            "rms_shift": float(np.sqrt(np.mean((a - b) ** 2))),
            "max_abs_shift": float(np.max(np.abs(a - b))),
            "correlation": _corr(a, b),
        }
    return result


# --- I/O and CLI ---------------------------------------------------------------------


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def pin_from_manifest(row_dir: Path, manifest_sha256: str) -> RowSetPin:
    """Pin a later row set by its manifest digest, which lists the other artifact digests."""
    actual = _sha256(row_dir / "manifest.json")
    if actual != manifest_sha256:
        raise ValueError(
            f"manifest.json SHA-256 {actual} does not match the frozen {manifest_sha256}"
        )
    manifest = json.loads((row_dir / "manifest.json").read_text())
    listed = {a["filename"]: a["sha256"] for a in manifest["output_artifacts"]}
    digests = {"manifest.json": manifest_sha256}
    digests.update({name: listed[name] for name in PINNED_DIGESTS if name != "manifest.json"})
    return RowSetPin(manifest["build_id"], digests)


def verify_pins(row_dir: Path, pin: RowSetPin = DEFAULT_PIN) -> None:
    for name, expected in pin.digests.items():
        actual = _sha256(row_dir / name)
        if actual != expected:
            raise ValueError(f"{name} SHA-256 {actual} does not match the frozen {expected}")
    manifest = json.loads((row_dir / "manifest.json").read_text())
    if manifest["build_id"] != pin.build_id or manifest["evidence_tier"] != EVIDENCE_TIER:
        raise ValueError("row-set manifest build_id or evidence tier differs from the frozen pin")


def load_rows(row_dir: Path) -> tuple[list[Observation], dict[str, frozenset[str]]]:
    """Read pinned model rows and per-stratum game sets. Only season 2022 rows are allowed."""
    import duckdb

    connection = duckdb.connect()
    rows = connection.execute(
        "select game_id, offense_team_id, season_type, offense_player_ids, defense_player_ids,"
        " model_points, game_date, season_start_year from read_parquet(?)"
        " order by game_date, game_id, possession_seq",
        [str(row_dir / "model_row.parquet")],
    ).fetchall()
    if {r[7] for r in rows} != {2022}:
        raise ValueError("only the 2022-23 season is in scope")
    observations = [
        Observation(
            game_id,
            team,
            season_type,
            Possession(tuple(map(int, off)), tuple(map(int, dfn)), points, 1.0, played),
        )
        for game_id, team, season_type, off, dfn, points, played, _ in rows
    ]
    strata: dict[str, set[str]] = {}
    for game_id, names in connection.execute(
        "select game_id, strata from read_parquet(?) where accepted",
        [str(row_dir / "game_reconciliation.parquet")],
    ).fetchall():
        for name in names:
            strata.setdefault(name, set()).add(game_id)
    return observations, {name: frozenset(games) for name, games in strata.items()}


def _peak_memory_mib() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / (1 << 20) if sys.platform == "darwin" else peak / (1 << 10)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=False, cwd=Path(__file__).parent
    ).stdout.strip()


def run(
    row_dir: Path, output_dir: Path, protocol: Path, pin: RowSetPin = DEFAULT_PIN
) -> dict[str, Any]:
    started = time.perf_counter()
    verify_pins(row_dir, pin)
    observations, strata = load_rows(row_dir)
    flagged = frozenset().union(*(g for name, g in strata.items() if name not in ROUTINE_STRATA))
    fit_info: list[dict[str, float]] = []

    def fit_logged(rows: Sequence[Observation], ridge: float) -> RAPMFit:
        fit, info = fit_observations(rows, ridge)
        fit_info.append(info)
        return fit

    fold_rows = [split_fold(observations, cutoff, end) for cutoff, end in SELECTION_FOLDS]
    pooled_by_ridge: dict[float, Scored] = {}

    def selection_mse(ridge: float) -> float:
        parts = [
            score(fit_logged(fit_rows, ridge), league_mean(fit_rows), scored_rows)
            for fit_rows, scored_rows in fold_rows
        ]
        pooled_by_ridge[ridge] = concat(parts)
        return mse(pooled_by_ridge[ridge].y, pooled_by_ridge[ridge].model)

    # Penalty selection on regular-season folds only; the playoff fold never enters.
    chosen, grid_mse = select_penalty(selection_mse)
    sensitivity = {str(r): summarize(pooled_by_ridge[r]) for r in sorted(grid_mse)}

    # With the penalty frozen: per-fold results and the exclusion comparison.
    def exclusion_scores(
        fit_rows: Sequence[Observation], scored_rows: Sequence[Observation]
    ) -> dict[str, Scored]:
        kept = exclude_games(fit_rows, flagged)
        clean = exclude_games(scored_rows, flagged)
        full_fit = fit_logged(fit_rows, chosen)
        excl_fit = fit_logged(kept, chosen)
        full_league, excl_league = league_mean(fit_rows), league_mean(kept)
        return {
            "all_heldout_full_fit": score(full_fit, full_league, scored_rows),
            "all_heldout_exclusion_fit": score(excl_fit, excl_league, scored_rows),
            "nonflagged_heldout_full_fit": score(full_fit, full_league, clean),
            "nonflagged_heldout_exclusion_fit": score(excl_fit, excl_league, clean),
        }

    folds: dict[str, Any] = {}
    pooled: dict[str, list[Scored]] = {}
    for i, ((cutoff, end), (fit_rows, scored_rows)) in enumerate(
        zip(SELECTION_FOLDS, fold_rows, strict=True), start=1
    ):
        parts = exclusion_scores(fit_rows, scored_rows)
        folds[f"R{i}"] = {
            "fit_cutoff": cutoff.isoformat(),
            "scored_block": [cutoff.isoformat(), end.isoformat()],
            "fit_rows": len(fit_rows),
            **summarize(parts["all_heldout_full_fit"]),
        }
        for name, scored in parts.items():
            pooled.setdefault(name, []).append(scored)
    playoff_fit_rows, playoff_scored_rows = split_fold(observations, PLAYOFF_CUTOFF, None)
    playoff = exclusion_scores(playoff_fit_rows, playoff_scored_rows)
    folds["P1"] = {
        "fit_cutoff": PLAYOFF_CUTOFF.isoformat(),
        "scored_block": [PLAYOFF_CUTOFF.isoformat(), None],
        "fit_rows": len(playoff_fit_rows),
        **summarize(playoff["all_heldout_full_fit"]),
    }
    pooled_full = pooled["all_heldout_full_fit"]
    exclusion: dict[str, Any] = {
        "flagged_games": len(flagged),
        "flagged_game_share": len(flagged) / len({o.game_id for o in observations}),
        "regular_season_pooled": {name: summarize(concat(parts)) for name, parts in pooled.items()},
        "playoffs": {name: summarize(scored) for name, scored in playoff.items()},
    }

    # Final in-sample fit on all 2022-23 rows.
    final_fit, final_info = fit_observations(observations, chosen)
    fit_info.append(final_info)
    report = exposure_report(observations, final_fit)
    excluded_fit = fit_logged(exclude_games(observations, flagged), chosen)
    exclusion["final_fit_shift_flagged_games_dropped"] = estimate_shift(final_fit, excluded_fit)
    exclusion["final_fit_shift_by_stratum"] = {}
    for name in sorted(set(strata) - ROUTINE_STRATA):
        reduced = fit_logged(exclude_games(observations, strata[name]), chosen)
        shift = estimate_shift(final_fit, reduced)
        shift["games_dropped"] = len(strata[name])
        shift["possessions_dropped"] = sum(1 for o in observations if o.game_id in strata[name])
        exclusion["final_fit_shift_by_stratum"][name] = shift
    stable = stability(observations, chosen)

    output_dir.mkdir(parents=True, exist_ok=False)
    players = sorted(final_fit.offense)
    table = exposure(observations)
    with (output_dir / "player_estimates.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "player_id",
                "offense",
                "defense",
                "total",
                "off_possessions",
                "def_possessions",
                "games",
            ]
        )
        for p in players:
            off, dfn, games = table[p]
            writer.writerow(
                [
                    p,
                    final_fit.offense[p],
                    final_fit.defense[p],
                    final_fit.offense[p] + final_fit.defense[p],
                    off,
                    dfn,
                    games,
                ]
            )

    iterations = [i["iterations"] for i in fit_info]
    results: dict[str, Any] = {
        "evidence_tier": EVIDENCE_TIER,
        "selected_penalty": chosen,
        "penalty_grid_pooled_regular_season_mse": {str(k): v for k, v in sorted(grid_mse.items())},
        "sensitivity": sensitivity,
        "folds": folds,
        "pooled_regular_season": summarize(concat(pooled_full)),
        "exclusion": exclusion,
        "final_fit": {
            "rows": len(observations),
            "games": len({o.game_id for o in observations}),
            **report,
        },
        "stability_game_halves": stable,
        "optimizer": {
            "fits": len(fit_info),
            "all_converged": all(i["stop"] in {0, 1, 2, 4, 5} for i in fit_info),
            "stop_codes": dict(Counter(int(i["stop"]) for i in fit_info)),
            "iterations": {
                "min": min(iterations),
                "median": float(np.median(iterations)),
                "max": max(iterations),
            },
            "final_fit": final_info,
            "max_condition_estimate": max(i["condition_estimate"] for i in fit_info),
            "total_fit_seconds": sum(i["fit_seconds"] for i in fit_info),
        },
    }
    (output_dir / "results.json").write_text(json.dumps(results, indent=2, sort_keys=True))
    status = _git("status", "--porcelain")
    manifest = {
        "schema_version": 1,
        "issue": 23,
        "evidence_tier": EVIDENCE_TIER,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "row_set_build_id": pin.build_id,
        "row_set_digests": pin.digests,
        "protocol": {"path": str(protocol), "sha256": _sha256(protocol)},
        "code_commit": _git("rev-parse", "HEAD"),
        "working_tree_clean": status == "",
        "selected_penalty": chosen,
        "penalty_grid": sorted(grid_mse),
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
    cli.add_argument("output_dir", type=Path, help="new directory for results")
    cli.add_argument(
        "--protocol",
        type=Path,
        default=Path(__file__).resolve().parents[4] / "docs/research/rapm-baseline-protocol.md",
    )
    cli.add_argument(
        "--pin-manifest-sha256",
        help="pin a later row set by manifest digest instead of the frozen #59 default",
    )
    args = cli.parse_args(argv)
    pin = (
        pin_from_manifest(args.row_dir, args.pin_manifest_sha256)
        if args.pin_manifest_sha256
        else DEFAULT_PIN
    )
    manifest = run(args.row_dir, args.output_dir, args.protocol, pin)
    print(
        json.dumps(
            {
                k: manifest[k]
                for k in ("selected_penalty", "runtime_seconds", "peak_memory_mib", "outputs")
            }
        )
    )


if __name__ == "__main__":
    main()
