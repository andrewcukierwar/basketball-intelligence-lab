"""Split-penalty selection, random-game exclusion control and per-fit diagnostics for #77.

Implements the frozen addendum ``docs/research/rapm-baseline-controls-protocol.md`` on top of
the #23 baseline (``bil.models.rapm.baseline``). The pure functions take in-memory
observations so they can be tested on synthetic data. ``main`` reads the pinned private row
set and writes aggregate results and a manifest to a new directory.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from bisect import bisect_right
from collections import Counter
from collections.abc import Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from bil.models.rapm.baseline import (
    PLAYOFF_CUTOFF,
    ROUTINE_STRATA,
    SELECTION_FOLDS,
    Observation,
    RowSetPin,
    Scored,
    _date,
    _git,
    _peak_memory_mib,
    _sha256,
    bootstrap_delta,
    concat,
    estimate_shift,
    exclude_games,
    exposure_report,
    league_mean,
    load_rows,
    pin_from_manifest,
    split_fold,
    summarize,
    verify_pins,
)
from bil.models.rapm.reference import RAPMFit, fit_split_rapm_diagnostics

PENALTY_GRID = (500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0, 32000.0)
SINGLE_PENALTY = 4000.0
MAX_GRID_EXTENSIONS = 4
CONTROL_DRAWS = 300
CONTROL_SEED = 77
BLOCK_BOUNDARIES = (
    date(2022, 12, 15),
    date(2023, 1, 15),
    date(2023, 2, 15),
    date(2023, 3, 15),
    date(2023, 4, 15),
)
TWO_SIDED = frozenset({"mse_delta_regular", "mse_delta_playoff"})
CONDITIONAL_TOLERANCE = 0.10
_CONVERGED = {0, 1, 2, 4, 5}

Cell = tuple[float, float]


# --- Held-out scoring, vectorized ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class HeldOut:
    """Precomputed arrays of one scored block, so many fits can be scored quickly."""

    y: NDArray[np.float64]
    offense: NDArray[np.int64]
    defense: NDArray[np.int64]
    game: NDArray[np.int64]
    team_game: NDArray[np.int64]


def prepare_held_out(scored: Sequence[Observation]) -> HeldOut:
    games: dict[str, int] = {}
    team_games: dict[tuple[str, str], int] = {}
    game = np.empty(len(scored), dtype=np.int64)
    team_game = np.empty(len(scored), dtype=np.int64)
    for i, row in enumerate(scored):
        game[i] = games.setdefault(row.game_id, len(games))
        team_game[i] = team_games.setdefault((row.game_id, row.offense_team), len(team_games))
    return HeldOut(
        y=np.array([100.0 * o.possession.points for o in scored]),
        offense=np.array([o.possession.offense for o in scored], dtype=np.int64),
        defense=np.array([o.possession.defense for o in scored], dtype=np.int64),
        game=game,
        team_game=team_game,
    )


def _effects(
    table: Mapping[int, float], players: NDArray[np.int64]
) -> tuple[NDArray[np.float64], NDArray[np.bool_]]:
    ids = np.array(sorted(table), dtype=np.int64)
    values = np.array([table[p] for p in ids.tolist()], dtype=np.float64)
    position = np.minimum(np.searchsorted(ids, players), len(ids) - 1)
    hit = ids[position] == players
    return np.where(hit, values[position], 0.0), hit


def score_held_out(fit: RAPMFit, league: float, held: HeldOut) -> Scored:
    """Same predictions as ``baseline.score``: unseen players have zero effect."""
    off, off_hit = _effects(fit.offense, held.offense)
    dfn, def_hit = _effects(fit.defense, held.defense)
    off_sum, def_sum = off.sum(axis=1), dfn.sum(axis=1)
    return Scored(
        y=held.y,
        model=fit.intercept + off_sum - def_sum,
        league=np.full(held.y.size, league),
        offense_only=fit.intercept + off_sum,
        defense_only=fit.intercept - def_sum,
        game=held.game,
        team_game=held.team_game,
        unseen=~(off_hit.all(axis=1) & def_hit.all(axis=1)),
    )


def squared_error_sum(scored: Scored) -> float:
    return float(np.sum((scored.model - scored.y) ** 2))


# --- Fits with a diagnostics log -----------------------------------------------------


class FitLog:
    """Run split-penalty fits and keep one diagnostics record per fit."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def fit(
        self, observations: Sequence[Observation], cell: Cell, *, stage: str, fold: str = ""
    ) -> RAPMFit:
        started = time.perf_counter()
        fit, info = fit_split_rapm_diagnostics(
            [o.possession for o in observations], offense_ridge=cell[0], defense_ridge=cell[1]
        )
        self.records.append(
            {
                "stage": stage,
                "fold": fold,
                "offense_ridge": cell[0],
                "defense_ridge": cell[1],
                "rows": len(observations),
                "stop": int(info["stop"]),
                "iterations": int(info["iterations"]),
                "scaled_residual_norm": info["scaled_residual_norm"],
                "condition_estimate": info["condition_estimate"],
                "fit_seconds": time.perf_counter() - started,
            }
        )
        return fit

    def summary(self) -> dict[str, Any]:
        iterations = [r["iterations"] for r in self.records]
        return {
            "fits": len(self.records),
            "all_converged": all(r["stop"] in _CONVERGED for r in self.records),
            "stop_codes": {
                str(code): count
                for code, count in sorted(Counter(r["stop"] for r in self.records).items())
            },
            "iterations": {
                "min": min(iterations),
                "median": float(np.median(iterations)),
                "max": max(iterations),
            },
            "max_condition_estimate": max(r["condition_estimate"] for r in self.records),
            "total_fit_seconds": sum(r["fit_seconds"] for r in self.records),
        }


# --- Item 1: two-dimensional penalty selection ---------------------------------------


def select_grid(
    evaluate: Callable[[Cell], float],
    offense_grid: Sequence[float] = PENALTY_GRID,
    defense_grid: Sequence[float] = PENALTY_GRID,
    max_extensions: int = MAX_GRID_EXTENSIONS,
) -> tuple[Cell, dict[Cell, float], list[str]]:
    """Lowest-MSE cell, extending an axis by a factor of two off an edge (new cells only).

    Ties go to the first cell in (offense, defense) order. Returns the extensions made.
    """
    offense, defense = sorted(offense_grid), sorted(defense_grid)
    scores: dict[Cell, float] = {}
    extensions: list[str] = []
    while True:
        for o in offense:
            for d in defense:
                if (o, d) not in scores:
                    scores[(o, d)] = evaluate((o, d))
        best = min(scores, key=lambda cell: (scores[cell], cell))
        if len(extensions) >= max_extensions:
            break
        grew = False
        for axis, values, value in (("offense", offense, best[0]), ("defense", defense, best[1])):
            if value == values[0]:
                values.insert(0, value / 2)
                extensions.append(f"{axis}:low")
                grew = True
            elif value == values[-1]:
                values.append(value * 2)
                extensions.append(f"{axis}:high")
                grew = True
        if not grew:
            break
    return best, scores, extensions


def compare_scored(candidate: Scored, comparator: Scored) -> dict[str, Any]:
    """MSE(candidate) − MSE(comparator) on identical possessions, with a clustered interval."""
    delta = (candidate.model - candidate.y) ** 2 - (comparator.model - comparator.y) ** 2
    low, high = bootstrap_delta(candidate.game, delta)
    return {
        "candidate_mse": float(np.mean((candidate.model - candidate.y) ** 2)),
        "comparator_mse": float(np.mean((comparator.model - comparator.y) ** 2)),
        "delta": float(delta.mean()),
        "ci95": [low, high],
    }


# --- Item 2: random-game exclusion control -------------------------------------------


def block_of(played: date) -> int:
    return bisect_right(BLOCK_BOUNDARIES, played)


def random_game_set(
    keys: Mapping[str, Hashable],
    observed: frozenset[str],
    ordinary: frozenset[str],
    rng: np.random.Generator,
) -> frozenset[str]:
    """Random games from ``ordinary`` with the observed count in every matching cell."""
    wanted = Counter(keys[game] for game in observed)
    chosen: set[str] = set()
    for key in sorted(wanted, key=repr):
        pool = sorted(game for game in ordinary if keys[game] == key)
        if len(pool) < wanted[key]:
            raise ValueError(
                f"matching cell {key!r} has {len(pool)} ordinary games, {wanted[key]} needed"
            )
        picks = rng.choice(len(pool), size=wanted[key], replace=False)
        chosen.update(pool[i] for i in picks.tolist())
    return frozenset(chosen)


def draw_rng(variant: int, draw: int) -> np.random.Generator:
    return np.random.default_rng([CONTROL_SEED, variant, draw])


def empirical_tail(
    observed: float, draws: Sequence[float] | NDArray[np.float64], *, two_sided: bool
) -> float:
    """(1 + number of draws at least as extreme) / (draws + 1)."""
    values = np.asarray(draws, dtype=np.float64)
    if two_sided:
        extreme = int(np.sum(np.abs(values) >= abs(observed)))
    else:
        extreme = int(np.sum(values >= observed))
    return (1 + extreme) / (values.size + 1)


def compare_to_draws(
    observed: Mapping[str, float], draws: Sequence[Mapping[str, float]]
) -> dict[str, Any]:
    """Place each observed statistic in the draws' distribution, overall and conditional."""
    target = observed["possessions_removed"]
    near = [
        d for d in draws if abs(d["possessions_removed"] - target) <= CONDITIONAL_TOLERANCE * target
    ]

    def block(subset: Sequence[Mapping[str, float]]) -> dict[str, Any]:
        out: dict[str, Any] = {"draws": len(subset)}
        if not subset:
            return out
        for name, value in observed.items():
            values = np.array([d[name] for d in subset])
            low, high = np.percentile(values, [2.5, 97.5])
            out[name] = {
                "observed": value,
                "draw_mean": float(values.mean()),
                "draw_sd": float(values.std()),
                "draw_p2_5": float(low),
                "draw_p97_5": float(high),
                "empirical_p": empirical_tail(value, values, two_sided=name in TWO_SIDED),
            }
        return out

    return {"all_draws": block(draws), "draws_within_10pct_of_observed_possessions": block(near)}


def exclusion_statistics(
    excluded: frozenset[str],
    *,
    log: FitLog,
    stage: str,
    folds: Sequence[tuple[Sequence[Observation], HeldOut]],
    playoff: tuple[Sequence[Observation], HeldOut],
    observations: Sequence[Observation],
    full_regular_squared_error: float,
    full_regular_count: int,
    full_playoff_mse: float,
    full_final: RAPMFit,
    cell: Cell = (SINGLE_PENALTY, SINGLE_PENALTY),
) -> dict[str, float]:
    """Effect of dropping ``excluded`` games from every fit, at a fixed penalty cell."""
    squared = 0.0
    for i, (fit_rows, held) in enumerate(folds, start=1):
        kept = exclude_games(fit_rows, excluded)
        fit = log.fit(kept, cell, stage=stage, fold=f"R{i}")
        squared += squared_error_sum(score_held_out(fit, league_mean(kept), held))
    p_rows, p_held = playoff
    p_kept = exclude_games(p_rows, excluded)
    p_fit = log.fit(p_kept, cell, stage=stage, fold="P1")
    playoff_mse = float(
        np.mean((score_held_out(p_fit, league_mean(p_kept), p_held).model - p_held.y) ** 2)
    )
    remaining = exclude_games(observations, excluded)
    final = log.fit(remaining, cell, stage=stage, fold="final")
    shift = estimate_shift(full_final, final)
    return {
        "mse_delta_regular": squared / full_regular_count
        - full_regular_squared_error / full_regular_count,
        "mse_delta_playoff": playoff_mse - full_playoff_mse,
        "total_rms_shift": shift["total"]["rms_shift"],
        "offense_rms_shift": shift["offense"]["rms_shift"],
        "defense_rms_shift": shift["defense"]["rms_shift"],
        "one_minus_total_correlation": 1.0 - shift["total"]["correlation"],
        "players_dropped": float(shift["players_only_in_full"]),
        "possessions_removed": float(len(observations) - len(remaining)),
    }


# --- Run -----------------------------------------------------------------------------


def _progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def run(
    row_dir: Path,
    output_dir: Path,
    protocol: Path,
    pin: RowSetPin,
    *,
    draws: int = CONTROL_DRAWS,
) -> dict[str, Any]:
    started = time.perf_counter()
    verify_pins(row_dir, pin)
    observations, strata = load_rows(row_dir)
    games = {o.game_id for o in observations}
    flagged = frozenset().union(*(g for name, g in strata.items() if name not in ROUTINE_STRATA))
    if not flagged <= games:
        raise ValueError("flagged games without model rows")
    ordinary = frozenset(games) - flagged
    log = FitLog()
    single: Cell = (SINGLE_PENALTY, SINGLE_PENALTY)

    fold_rows = [split_fold(observations, cutoff, end) for cutoff, end in SELECTION_FOLDS]
    helds = [prepare_held_out(scored) for _, scored in fold_rows]
    leagues = [league_mean(fit_rows) for fit_rows, _ in fold_rows]
    pooled_mse: dict[Cell, float] = {}
    kept_parts: dict[Cell, list[Scored]] = {}

    def evaluate(cell: Cell) -> float:
        parts = [
            score_held_out(log.fit(fit_rows, cell, stage="selection", fold=f"R{i}"), league, held)
            for i, ((fit_rows, _), league, held) in enumerate(
                zip(fold_rows, leagues, helds, strict=True), start=1
            )
        ]
        pooled = concat(parts)
        pooled_mse[cell] = float(np.mean((pooled.model - pooled.y) ** 2))
        kept_parts[cell] = parts
        diagonal = [c for c in pooled_mse if c[0] == c[1]]
        keep = {
            single,
            min(pooled_mse, key=lambda c: (pooled_mse[c], c)),
            min(diagonal, key=lambda c: (pooled_mse[c], c)),
        }
        for other in list(kept_parts):
            if other not in keep:
                del kept_parts[other]
        return pooled_mse[cell]

    chosen, grid_mse, extensions = select_grid(evaluate)
    diagonal_best = min((c for c in grid_mse if c[0] == c[1]), key=lambda c: (grid_mse[c], c))
    _progress(f"selected {chosen}, diagonal best {diagonal_best}, extensions {extensions}")

    # With the cell frozen: fold and pooled comparisons, then the playoff fold.
    split_parts, single_parts = kept_parts[chosen], kept_parts[single]
    fold_results: dict[str, Any] = {}
    for i, (cutoff_end, a, b) in enumerate(
        zip(SELECTION_FOLDS, split_parts, single_parts, strict=True), start=1
    ):
        fold_results[f"R{i}"] = {
            "scored_block": [cutoff_end[0].isoformat(), cutoff_end[1].isoformat()],
            **summarize(a),
            "vs_single_penalty": compare_scored(a, b),
        }
    pooled_split, pooled_single = concat(split_parts), concat(single_parts)
    pooled_result: dict[str, Any] = {
        **summarize(pooled_split),
        "vs_single_penalty": compare_scored(pooled_split, pooled_single),
        "vs_diagonal_best": compare_scored(pooled_split, concat(kept_parts[diagonal_best])),
        "diagonal_best_vs_single_penalty": compare_scored(
            concat(kept_parts[diagonal_best]), pooled_single
        ),
    }

    p_fit_rows, p_scored_rows = split_fold(observations, PLAYOFF_CUTOFF, None)
    p_held = prepare_held_out(p_scored_rows)
    p_league = league_mean(p_fit_rows)
    p_split = score_held_out(
        log.fit(p_fit_rows, chosen, stage="playoff", fold="P1"), p_league, p_held
    )
    p_single = score_held_out(
        log.fit(p_fit_rows, single, stage="playoff", fold="P1"), p_league, p_held
    )
    playoff_result = {
        "fit_cutoff": PLAYOFF_CUTOFF.isoformat(),
        "fit_rows": len(p_fit_rows),
        **summarize(p_split),
        "vs_single_penalty": compare_scored(p_split, p_single),
    }

    # Final fits on all rows (descriptive, in-sample).
    final_split = log.fit(observations, chosen, stage="final", fold="split")
    final_single = log.fit(observations, single, stage="final", fold="single")
    final_result = {
        "rows": len(observations),
        "games": len(games),
        **exposure_report(observations, final_split),
        "shift_versus_single_penalty": estimate_shift(final_single, final_split),
    }

    # Item 2: observed stratum exclusion against random game sets.
    full_squared = squared_error_sum(pooled_single)
    context: dict[str, Any] = {
        "log": log,
        "folds": [(fit_rows, held) for (fit_rows, _), held in zip(fold_rows, helds, strict=True)],
        "playoff": (p_fit_rows, p_held),
        "observations": observations,
        "full_regular_squared_error": full_squared,
        "full_regular_count": int(pooled_single.y.size),
        "full_playoff_mse": float(np.mean((p_single.model - p_single.y) ** 2)),
        "full_final": final_single,
    }
    observed = exclusion_statistics(flagged, stage="control:observed", **context)
    _progress(f"observed stratum effect {observed}")
    game_date = {o.game_id: _date(o.possession) for o in observations}
    season_type = {o.game_id: o.season_type for o in observations}
    variants: dict[str, Mapping[str, Hashable]] = {
        "A_size_and_season_type": season_type,
        "B_size_season_type_and_date_block": {
            g: (season_type[g], block_of(game_date[g])) for g in games
        },
    }
    control: dict[str, Any] = {
        "observed_games": len(flagged),
        "observed_by_season_type": dict(Counter(season_type[g] for g in flagged)),
        "observed_by_date_block": dict(
            sorted(Counter(block_of(game_date[g]) for g in flagged).items())
        ),
        "ordinary_games": len(ordinary),
        "draws_per_variant": draws,
        "seed_scheme": f"numpy.random.default_rng([{CONTROL_SEED}, variant, draw])",
        "observed": observed,
        "variants": {},
    }
    for v, (name, keys) in enumerate(variants.items()):
        stats: list[dict[str, float]] = []
        sizes: list[int] = []
        for d in range(draws):
            sample = random_game_set(keys, flagged, ordinary, draw_rng(v, d))
            sizes.append(len(sample))
            stats.append(
                exclusion_statistics(sample, stage=f"control:{name}:draw{d:03d}", **context)
            )
            if (d + 1) % 25 == 0:
                _progress(f"variant {name}: {d + 1}/{draws} draws")
        control["variants"][name] = {
            "set_sizes_equal_observed": all(s == len(flagged) for s in sizes),
            "comparison": compare_to_draws(observed, stats),
            "draws": stats,
        }

    results: dict[str, Any] = {
        "evidence_tier": "retrospective_capture_bound",
        "single_penalty": SINGLE_PENALTY,
        "selected_cell": {"offense_ridge": chosen[0], "defense_ridge": chosen[1]},
        "diagonal_best_cell": {
            "offense_ridge": diagonal_best[0],
            "defense_ridge": diagonal_best[1],
        },
        "grid_extensions": extensions,
        "grid_pooled_regular_season_mse": {
            f"{o:g}|{d:g}": v for (o, d), v in sorted(grid_mse.items())
        },
        "folds": fold_results,
        "pooled_regular_season": pooled_result,
        "playoff_P1": playoff_result,
        "final_fit": final_result,
        "random_exclusion_control": control,
        "optimizer": {**log.summary(), "peak_memory_mib": _peak_memory_mib()},
        "fits": log.records,
    }
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "results.json").write_text(json.dumps(results, indent=2, sort_keys=True))
    status = _git("status", "--porcelain")
    manifest = {
        "schema_version": 1,
        "issue": 77,
        "evidence_tier": "retrospective_capture_bound",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "row_set_build_id": pin.build_id,
        "row_set_digests": pin.digests,
        "protocol": {"path": str(protocol), "sha256": _sha256(protocol)},
        "code_commit": _git("rev-parse", "HEAD"),
        "working_tree_clean": status == "",
        "selected_cell": [chosen[0], chosen[1]],
        "penalty_grid": sorted({v for cell in grid_mse for v in cell}),
        "control": {"draws_per_variant": draws, "seed": CONTROL_SEED},
        "versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": __import__("scipy").__version__,
            "duckdb": __import__("duckdb").__version__,
        },
        "runtime_seconds": time.perf_counter() - started,
        "peak_memory_mib": _peak_memory_mib(),
        "outputs": {"results.json": _sha256(output_dir / "results.json")},
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def main(argv: Sequence[str] | None = None) -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("row_dir", type=Path, help="pinned row-set directory")
    cli.add_argument("output_dir", type=Path, help="new directory for results")
    cli.add_argument("--pin-manifest-sha256", required=True, help="manifest digest of the row set")
    cli.add_argument(
        "--protocol",
        type=Path,
        default=Path(__file__).resolve().parents[4]
        / "docs/research/rapm-baseline-controls-protocol.md",
    )
    args = cli.parse_args(argv)
    pin = pin_from_manifest(args.row_dir, args.pin_manifest_sha256)
    manifest = run(args.row_dir, args.output_dir, args.protocol, pin)
    print(
        json.dumps(
            {
                k: manifest[k]
                for k in ("selected_cell", "runtime_seconds", "peak_memory_mib", "outputs")
            }
        )
    )


if __name__ == "__main__":
    main()
