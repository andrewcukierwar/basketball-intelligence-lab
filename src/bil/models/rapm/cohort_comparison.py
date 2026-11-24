"""Compare row-set variants A, B and C on a common held-out cohort (issue #82).

Implements ``docs/research/rapm-no-action-protocol-v2.md``. Each variant's zero-context RAPM is
fit on that variant's own rows and scored on the same held-out possessions: primary on the
strictest cohort (rows eligible under A), secondary on each variant's own cohort. Everything else
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


def _score_block(
    observations: Sequence[Observation],
    keys: dict[int, Key],
    cohort: set[Key] | None,
    cutoff: date,
    end: date | None,
) -> Scored:
    fit_rows, block = split_fold(observations, cutoff, end)
    fit, _ = fit_observations(fit_rows, RIDGE)
    block = sorted(
        (o for o in block if cohort is None or keys[id(o)] in cohort), key=lambda o: keys[id(o)]
    )
    return score(fit, league_mean(fit_rows), block)


def pooled(
    observations: Sequence[Observation], keys: dict[int, Key], cohort: set[Key] | None
) -> Scored:
    parts = [_score_block(observations, keys, cohort, c, e) for c, e in SELECTION_FOLDS]
    return concat(parts)


def _interval(game: Any, delta: Any) -> dict[str, Any]:
    low, high = bootstrap_delta(game, delta, resamples=BOOTSTRAP_RESAMPLES)
    return {"delta": float(delta.mean()), "ci95": [low, high]}


def run(dirs: dict[str, Path], pins: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    for name, row_dir in dirs.items():
        verify_pins(row_dir, pins[name])
    loaded = {name: load_keyed(path) for name, path in dirs.items()}
    cohorts = {name: set(keys.values()) for name, (_, keys) in loaded.items()}
    if not (cohorts["A"] <= cohorts["B"] <= cohorts["C"]):
        raise ValueError("variant cohorts are not nested A within B within C")
    results: dict[str, Any] = {
        "ridge": RIDGE,
        "cohort_sizes_all_rows": {n: len(c) for n, c in cohorts.items()},
    }
    for label, shared in (
        ("primary_common_A_cohort", cohorts["A"]),
        ("secondary_own_cohort", None),
    ):
        scored: dict[str, Scored] = {}
        for name, (observations, keys) in loaded.items():
            cohort = shared
            scored[name] = pooled(observations, keys, cohort)
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
            for first, second in (("B", "C"), ("A", "C"), ("A", "B")):
                a, b = scored[first], scored[second]
                if not np.array_equal(a.y, b.y):
                    raise ValueError("common cohort rows are not aligned across variants")
                block[f"model_{first}_minus_{second}"] = _interval(
                    a.game, (a.model - a.y) ** 2 - (b.model - b.y) ** 2
                )
        results[label] = block
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
    for name in "ABC":
        cli.add_argument(f"--{name}-dir", type=Path, required=True)
    cli.add_argument("--A-pin", required=True)
    cli.add_argument("--B-pin", required=True)
    cli.add_argument("--C-pin", help="manifest SHA-256; defaults to the frozen #59 pin")
    args = cli.parse_args(argv)
    dirs = {n: getattr(args, f"{n}_dir") for n in "ABC"}
    pins = {
        "A": pin_from_manifest(dirs["A"], args.A_pin),
        "B": pin_from_manifest(dirs["B"], args.B_pin),
        "C": pin_from_manifest(dirs["C"], args.C_pin) if args.C_pin else DEFAULT_PIN,
    }
    results = run(dirs, pins, args.output_dir)
    print(json.dumps(results["primary_common_A_cohort"], sort_keys=True))


if __name__ == "__main__":
    main()
