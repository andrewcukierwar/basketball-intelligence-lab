"""Split-penalty oracle, grid selection, scoring equivalence and random-control determinism."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import date, timedelta

import pytest

pytest.importorskip("numpy")
pytest.importorskip("scipy")

import numpy as np  # noqa: E402

from bil.models.rapm import fit_rapm, fit_split_rapm_diagnostics  # noqa: E402
from bil.models.rapm.baseline import Observation, league_mean, score, split_fold  # noqa: E402
from bil.models.rapm.baseline_controls import (  # noqa: E402
    FitLog,
    block_of,
    compare_scored,
    compare_to_draws,
    draw_rng,
    empirical_tail,
    exclusion_statistics,
    prepare_held_out,
    random_game_set,
    score_held_out,
    select_grid,
    squared_error_sum,
)
from bil.models.rapm.synthetic import generate_possessions  # noqa: E402

START = date(2023, 1, 1)
PER_GAME = 10


def observations(games=40, seed=11):
    rows = generate_possessions(games * PER_GAME, seed=seed, noisy=True)
    out = []
    for i, row in enumerate(rows):
        game = i // PER_GAME
        kind = "playoffs" if game >= games - 6 else "regular"
        played = START + timedelta(days=game // 2)
        out.append(
            Observation(f"g{game:03d}", f"t{game % 2}", kind, replace(row, played_date=played))
        )
    return out


def dense_split_oracle(rows, offense_ridge, defense_ridge):
    ids = sorted({p for r in rows for p in (*r.offense, *r.defense)})
    matrix = np.array(
        [[1, *(p in r.offense for p in ids), *(-int(p in r.defense) for p in ids)] for r in rows],
        dtype=float,
    )
    response = np.array([100 * r.points for r in rows])
    penalty = np.diag(np.sqrt(np.repeat([offense_ridge, defense_ridge], len(ids))))
    augmented = np.vstack([matrix, np.pad(penalty, ((0, 0), (1, 0)))])
    target = np.concatenate([response, np.zeros(2 * len(ids))])
    return ids, np.linalg.lstsq(augmented, target, rcond=None)[0]


@pytest.mark.parametrize("penalties", [(40.0, 40.0), (15.0, 400.0), (900.0, 30.0)])
def test_split_penalty_matches_dense_oracle_and_reports_diagnostics(penalties):
    rows = [o.possession for o in observations(games=12)]
    ids, expected = dense_split_oracle(rows, *penalties)
    fit, info = fit_split_rapm_diagnostics(
        rows, offense_ridge=penalties[0], defense_ridge=penalties[1]
    )
    actual = np.array(
        [fit.intercept, *(fit.offense[p] for p in ids), *(fit.defense[p] for p in ids)]
    )
    np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-7)
    assert info["stop"] in {0, 1, 2, 4, 5}
    assert info["iterations"] > 0 and info["condition_estimate"] >= 1
    assert info["scaled_residual_norm"] >= 0


def test_equal_split_penalties_are_the_shared_penalty_fit():
    rows = [o.possession for o in observations(games=12)]
    fit, _ = fit_split_rapm_diagnostics(rows, offense_ridge=25.0, defense_ridge=25.0)
    assert fit == fit_rapm(rows, ridge=25.0)
    with pytest.raises(ValueError):
        fit_split_rapm_diagnostics(rows, offense_ridge=0.0, defense_ridge=25.0)


def test_fit_log_records_every_fit():
    log = FitLog()
    rows = observations(games=8)
    log.fit(rows, (30.0, 90.0), stage="selection", fold="R1")
    log.fit(rows, (30.0, 30.0), stage="final", fold="single")
    assert [r["stage"] for r in log.records] == ["selection", "final"]
    assert {"stop", "iterations", "condition_estimate", "fit_seconds", "rows"} <= set(
        log.records[0]
    )
    summary = log.summary()
    assert summary["fits"] == 2 and summary["all_converged"]


def test_vectorized_scoring_matches_baseline_score():
    rows = observations(games=30)
    fit_rows, scored_rows = split_fold(rows, START + timedelta(days=10), None)
    fit = FitLog().fit(fit_rows, (50.0, 200.0), stage="t")
    expected = score(fit, 107.0, scored_rows)
    actual = score_held_out(fit, 107.0, prepare_held_out(scored_rows))
    for name in (
        "y",
        "model",
        "league",
        "offense_only",
        "defense_only",
        "game",
        "team_game",
        "unseen",
    ):
        np.testing.assert_allclose(getattr(actual, name), getattr(expected, name), atol=1e-9)
    assert compare_scored(actual, actual)["delta"] == 0.0


def test_grid_selection_extends_off_an_edge_and_stops_when_interior():
    def surface(cell):
        return (np.log2(cell[0] / 125) ** 2) + (np.log2(cell[1] / 3000) ** 2)

    best, scores, extensions = select_grid(
        surface, (500.0, 1000.0, 2000.0), (1000.0, 2000.0, 4000.0)
    )
    assert best == (125.0, 2000.0) or best[0] <= 250.0
    assert extensions.count("offense:low") >= 2
    assert min(o for o, _ in scores) < 500.0

    def interior(cell):
        return 0.0 if cell == (2.0, 2.0) else 1.0

    assert select_grid(interior, (1.0, 2.0, 4.0), (1.0, 2.0, 4.0))[2] == []
    flat, _, _ = select_grid(lambda cell: 1.0, (1.0, 2.0), (1.0, 2.0), max_extensions=0)
    assert flat == (1.0, 1.0)


def test_random_game_sets_are_deterministic_matched_and_ordinary():
    games = [f"g{i:03d}" for i in range(60)]
    keys = {g: ("playoffs" if i >= 50 else "regular", i % 3) for i, g in enumerate(games)}
    observed = frozenset({"g000", "g001", "g004", "g051", "g052"})
    ordinary = frozenset(games) - observed
    first = random_game_set(keys, observed, ordinary, draw_rng(1, 7))
    again = random_game_set(keys, observed, ordinary, draw_rng(1, 7))
    other = random_game_set(keys, observed, ordinary, draw_rng(1, 8))
    assert first == again and first != other
    assert not first & observed
    assert Counter(keys[g] for g in first) == Counter(keys[g] for g in observed)
    with pytest.raises(ValueError):
        random_game_set(keys, observed, frozenset({"g002"}), draw_rng(0, 0))


def test_empirical_tail_and_comparison_to_draws():
    pairs = [(-1.0, 0.1), (0.5, 0.2), (2.0, 0.3), (-3.0, 0.4)]
    draws = [
        {"possessions_removed": 100.0 + i, "mse_delta_regular": d, "total_rms_shift": s}
        for i, (d, s) in enumerate(pairs)
    ]
    assert empirical_tail(0.4, [0.1, 0.2, 0.3, 0.4], two_sided=False) == pytest.approx(2 / 5)
    assert empirical_tail(-2.5, [-1.0, 0.5, 2.0, -3.0], two_sided=True) == pytest.approx(2 / 5)
    observed = {"possessions_removed": 101.0, "mse_delta_regular": 1.0, "total_rms_shift": 0.25}
    result = compare_to_draws(observed, draws)
    assert result["all_draws"]["draws"] == 4
    assert result["all_draws"]["total_rms_shift"]["empirical_p"] == pytest.approx(3 / 5)
    assert result["draws_within_10pct_of_observed_possessions"]["draws"] == 4


def test_block_of_uses_the_frozen_boundaries():
    assert block_of(date(2022, 10, 20)) == 0
    assert block_of(date(2022, 12, 15)) == 1
    assert block_of(date(2023, 4, 15)) == 5


def test_exclusion_statistics_are_reproducible_and_null_for_an_empty_set():
    rows = observations(games=40)
    cell = (60.0, 60.0)
    log = FitLog()

    def block(cutoff, end):
        fit_rows, scored_rows = split_fold(
            rows,
            START + timedelta(days=cutoff),
            None if end is None else START + timedelta(days=end),
        )
        return fit_rows, prepare_held_out(scored_rows)

    folds = [block(6, 10), block(10, 14)]
    playoff = block(17, None)
    full_squared, count = 0.0, 0
    for fit_rows, held in folds:
        scored = score_held_out(log.fit(fit_rows, cell, stage="full"), league_mean(fit_rows), held)
        full_squared += squared_error_sum(scored)
        count += scored.y.size
    p_scored = score_held_out(
        log.fit(playoff[0], cell, stage="full"), league_mean(playoff[0]), playoff[1]
    )
    context = {
        "log": log,
        "folds": folds,
        "playoff": playoff,
        "observations": rows,
        "full_regular_squared_error": full_squared,
        "full_regular_count": count,
        "full_playoff_mse": float(np.mean((p_scored.model - p_scored.y) ** 2)),
        "full_final": log.fit(rows, cell, stage="full"),
        "cell": cell,
    }
    none = exclusion_statistics(frozenset(), stage="x", **context)
    assert none["possessions_removed"] == 0
    assert none["total_rms_shift"] == pytest.approx(0, abs=1e-8)
    assert none["mse_delta_regular"] == pytest.approx(0, abs=1e-8)
    some = frozenset({"g003", "g004", "g030"})
    first = exclusion_statistics(some, stage="x", **context)
    assert first == exclusion_statistics(some, stage="x", **context)
    assert first["possessions_removed"] == 30
    assert first["total_rms_shift"] > 0
