"""Compare the canonical, period_end_start and no_action row-set variants on common held-out rows.

Implements ``docs/research/rapm-no-action-protocol-v3.md``. Each variant's zero-context RAPM is
fit on that variant's own rows and scored on the same held-out possessions: primary on the
canonical cohort, secondary on the `no_action` cohort and on each variant's own cohort. Everything else
follows the #23 baseline: folds R1 to R4, lambda 4,000, 2,000 game-clustered bootstrap resamples
with seed 2023.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from bil.models.rapm.baseline import (
    BOOTSTRAP_RESAMPLES,
    DEFAULT_PIN,
    SELECTION_FOLDS,
    Observation,
    Scored,
    _git,
    _sha256,
    bootstrap_delta,
    concat,
    fit_observations,
    league_mean,
    pin_from_manifest,
    score,
    split_fold,
    verify_pins,
)
from bil.models.rapm.reference import Possession

RIDGE = 4000.0
Key = tuple[str, int, int]


def load_keyed(row_dir: Path) -> tuple[list[Observation], dict[int, Key]]:
    import duckdb

    rows = (
        duckdb.connect()
        .execute(
            "select game_id, offense_team_id, season_type, offense_player_ids, defense_player_ids,"
            " model_points, game_date, season_start_year, stream_revision, possession_seq"
            " from read_parquet(?) order by game_date, game_id, possession_seq",
            [str(row_dir / "model_row.parquet")],
        )
        .fetchall()
    )
    if {r[7] for r in rows} != {2022}:
        raise ValueError("only the 2022-23 season is in scope")
    observations: list[Observation] = []
    keys: dict[int, Key] = {}
    for game, team, season, off, dfn, points, played, _, revision, seq in rows:
        obs = Observation(
            game,
            team,
            season,
            Possession(tuple(map(int, off)), tuple(map(int, dfn)), points, 1.0, played),
        )
        observations.append(obs)
        keys[id(obs)] = (game, revision, seq)
    return observations, keys


VARIANT_ORDER = ("canonical", "period_end_start", "no_action")
Loaded = dict[str, tuple[list[Observation], dict[int, Key]]]


def _score_block(
    fit_source: Sequence[Observation],
    held_out: tuple[Sequence[Observation], dict[int, Key]],
    cohort: set[Key] | None,
    cutoff: date,
    end: date | None,
) -> Scored:
    """Fit on ``fit_source`` rows before the cutoff and score held-out rows in the block."""
    fit_rows, _ = split_fold(fit_source, cutoff, end)
    source, keys = held_out
    _, block = split_fold(source, cutoff, end)
    chosen = sorted(
        (o for o in block if cohort is None or keys[id(o)] in cohort), key=lambda o: keys[id(o)]
    )
    fit, _ = fit_observations(fit_rows, RIDGE)
    return score(fit, league_mean(fit_rows), chosen)


def pooled(
    fit_source: Sequence[Observation],
    held_out: tuple[Sequence[Observation], dict[int, Key]],
    cohort: set[Key] | None,
) -> Scored:
    return concat([_score_block(fit_source, held_out, cohort, c, e) for c, e in SELECTION_FOLDS])


def _interval(game: Any, delta: Any) -> dict[str, Any]:
    low, high = bootstrap_delta(game, delta, resamples=BOOTSTRAP_RESAMPLES)
    return {"delta": float(delta.mean()), "ci95": [low, high]}


def check_nested(cohorts: dict[str, set[Key]]) -> None:
    if not (cohorts["no_action"] <= cohorts["period_end_start"] <= cohorts["canonical"]):
        raise ValueError(
            "variant cohorts are not nested no_action within period_end_start within canonical"
        )


def check_aligned(first: Scored, second: Scored) -> None:
    if not (np.array_equal(first.y, second.y) and np.array_equal(first.game, second.game)):
        raise ValueError("common cohort rows are not aligned across variants")


def compare(loaded: Loaded) -> dict[str, Any]:
    cohorts = {name: set(keys.values()) for name, (_, keys) in loaded.items()}
    check_nested(cohorts)
    results: dict[str, Any] = {
        "ridge": RIDGE,
        "cohort_sizes_all_rows": {n: len(c) for n, c in cohorts.items()},
    }
    canonical = loaded["canonical"]
    for label, shared in (
        ("primary_common_canonical_cohort", cohorts["canonical"]),
        ("secondary_common_no_action_cohort", cohorts["no_action"]),
        ("tertiary_own_cohort", None),
    ):
        scored: dict[str, Scored] = {}
        for name in VARIANT_ORDER:
            observations, keys = loaded[name]
            held = canonical if shared is not None else (observations, keys)
            scored[name] = pooled(observations, held, shared)
        block: dict[str, Any] = {"possessions": {n: int(s.y.size) for n, s in scored.items()}}
        for name, s in scored.items():
            sq_model = (s.model - s.y) ** 2
            sq_league = (s.league - s.y) ** 2
            block[name] = {
                "mse_model": float(sq_model.mean()),
                "mse_league": float(sq_league.mean()),
                "model_vs_league": _interval(s.game, sq_model - sq_league),
            }
        if shared is not None:
            for first, second in (
                ("period_end_start", "canonical"),
                ("no_action", "canonical"),
                ("no_action", "period_end_start"),
            ):
                a, b = scored[first], scored[second]
                check_aligned(a, b)
                block[f"model_{first}_minus_{second}"] = _interval(
                    a.game, (a.model - a.y) ** 2 - (b.model - b.y) ** 2
                )
        results[label] = block
    return results


def run(dirs: dict[str, Path], pins: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    for name, row_dir in dirs.items():
        verify_pins(row_dir, pins[name])
    results = compare({name: load_keyed(path) for name, path in dirs.items()})
    output_dir.mkdir(parents=True)
    (output_dir / "results.json").write_text(json.dumps(results, indent=2, sort_keys=True))
    manifest = {
        "issue": 82,
        "row_sets": {n: {"dir": str(p), "build_id": pins[n].build_id} for n, p in dirs.items()},
        "code_commit": _git("rev-parse", "HEAD"),
        "working_tree_clean": _git("status", "--porcelain") == "",
        "results_sha256": _sha256(output_dir / "results.json"),
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return results


def main(argv: Sequence[str] | None = None) -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output_dir", type=Path)
    cli.add_argument("--canonical-dir", type=Path, required=True)
    cli.add_argument("--period-end-start-dir", type=Path, required=True)
    cli.add_argument("--no-action-dir", type=Path, required=True)
    cli.add_argument("--canonical-pin", help="manifest SHA-256; defaults to the frozen #59 pin")
    cli.add_argument("--period-end-start-pin", required=True)
    cli.add_argument("--no-action-pin", required=True)
    args = cli.parse_args(argv)
    dirs = {
        "canonical": args.canonical_dir,
        "period_end_start": args.period_end_start_dir,
        "no_action": args.no_action_dir,
    }
    pins = {
        "canonical": (
            pin_from_manifest(dirs["canonical"], args.canonical_pin)
            if args.canonical_pin
            else DEFAULT_PIN
        ),
        "period_end_start": pin_from_manifest(dirs["period_end_start"], args.period_end_start_pin),
        "no_action": pin_from_manifest(dirs["no_action"], args.no_action_pin),
    }
    results = run(dirs, pins, args.output_dir)
    print(json.dumps(results["primary_common_canonical_cohort"], sort_keys=True))


if __name__ == "__main__":
    main()
