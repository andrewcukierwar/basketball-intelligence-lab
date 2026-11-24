"""Context-column solver, covariate timing and scoring checks for the #24 ablations."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

pytest.importorskip("numpy")
pytest.importorskip("scipy")

import numpy as np  # noqa: E402

from bil.models.rapm.baseline import Observation  # noqa: E402
from bil.models.rapm.context import fit_context_only, fit_context_rapm  # noqa: E402
from bil.models.rapm.context_ablation import (  # noqa: E402
    Block,
    ContextRows,
    feature_columns,
    fit_variant,
    fold_masks,
    late_blowout,
    paired,
    predict_variant,
    verdict,
)
from bil.models.rapm.reference import Possession, build_design, fit_rapm  # noqa: E402
from bil.models.rapm.synthetic import expected_rate, generate_possessions  # noqa: E402


def _max_diff(a, b):
    return max(
        abs(a.intercept - b.intercept),
        max(abs(a.offense[p] - b.offense[p]) for p in a.offense),
        max(abs(a.defense[p] - b.defense[p]) for p in a.defense),
    )


def _dense_oracle(rows, z, ridge, offset=None):
    design = build_design(rows)
    players = design.matrix[:, 1:].toarray()
    x = np.column_stack((np.ones(len(rows)), z, players))
    penalty = np.r_[np.zeros(1 + z.shape[1]), np.full(players.shape[1], ridge)]
    y = design.response - (0 if offset is None else offset)
    w = design.weights
    beta = np.linalg.solve(x.T @ (w[:, None] * x) + np.diag(penalty), x.T @ (w * y))
    n = len(design.player_ids)
    k = 1 + z.shape[1]
    return beta[:k], beta[k : k + n], beta[k + n :], design.player_ids


def test_zero_context_reproduces_the_reference_solver():
    rows = generate_possessions(500, seed=11, noisy=True)
    weighted = [replace(r, weight=1.0 + (i % 3) / 2) for i, r in enumerate(rows)]
    for sample in (rows, weighted):
        assert (
            _max_diff(fit_rapm(sample, ridge=40.0), fit_context_rapm(sample, ridge=40.0).players())
            < 1e-9
        )


def test_context_columns_agree_with_a_dense_oracle():
    rows = generate_possessions(700, seed=12, noisy=True)
    rows = [replace(r, weight=0.5 + (i % 4) / 4) for i, r in enumerate(rows)]
    rng = np.random.default_rng(3)
    z = np.column_stack((rng.choice([-1.0, 1.0], 700), rng.normal(size=700), rng.random(700) < 0.1))
    fit = fit_context_rapm(rows, z, ridge=25.0)
    fixed, offense, defense, ids = _dense_oracle(rows, z, 25.0)
    assert abs(fit.intercept - fixed[0]) < 1e-8
    np.testing.assert_allclose(fit.context, fixed[1:], atol=1e-8)
    np.testing.assert_allclose([fit.offense[p] for p in ids], offense, atol=1e-8)
    np.testing.assert_allclose([fit.defense[p] for p in ids], defense, atol=1e-8)


def test_offset_equals_fitted_control_when_context_is_balanced_across_lineups():
    # Every lineup pair appears once at home (+1) and once away (-1), so the context column is
    # orthogonal to the intercept and every player column. The offset and fitted control coincide.
    base = generate_possessions(300, seed=13, noisy=True)
    rows, z = [], []
    for row in base:
        for side in (1.0, -1.0):
            rows.append(replace(row, points=row.points + 0.03 * (side + 1)))
            z.append([side])
    z = np.array(z)
    fitted = fit_context_rapm(rows, z, ridge=30.0)
    y = np.array([100 * r.points for r in rows])
    _, gamma = fit_context_only(y, z)
    offset = fit_context_rapm(rows, ridge=30.0, offset=z @ gamma)
    np.testing.assert_allclose(fitted.context, gamma, atol=1e-9)
    assert _max_diff(fitted.players(), offset.players()) < 1e-8


def test_fitted_control_recovers_a_confounded_context_effect_that_an_offset_biases():
    # Strong lineups play at home more often. Noiseless points with a +4 home effect.
    rng = np.random.default_rng(14)
    rows, z = [], []
    for row in generate_possessions(3000, seed=14):
        strength = sum(row.offense) - sum(row.defense)
        home = 1.0 if rng.random() < (0.8 if strength > 0 else 0.2) else -1.0
        rate = expected_rate(row.offense, row.defense) + 4.0 * home
        rows.append(replace(row, points=rate / 100))
        z.append([home])
    z = np.array(z)
    fitted = fit_context_rapm(rows, z, ridge=1e-3)
    assert abs(fitted.context[0] - 4.0) < 1e-4
    y = np.array([100 * r.points for r in rows])
    _, gamma = fit_context_only(y, z)
    assert abs(gamma[0] - 4.0) > 0.5  # the context-only offset absorbs player strength


def test_collinear_context_is_rejected():
    rows = generate_possessions(50, seed=15)
    with pytest.raises(ValueError, match="collinear"):
        fit_context_rapm(rows, np.ones((50, 1)), ridge=10.0)
    with pytest.raises(ValueError, match="shape"):
        fit_context_rapm(rows, np.ones((49, 1)), ridge=10.0)


def test_scaling_all_weights_is_equivalent_to_scaling_the_penalty():
    rows = generate_possessions(400, seed=16, noisy=True)
    doubled = [replace(r, weight=2.0) for r in rows]
    a = fit_context_rapm(rows, ridge=50.0)
    b = fit_context_rapm(doubled, ridge=100.0)
    c = fit_context_rapm(doubled, ridge=50.0)
    assert _max_diff(a.players(), b.players()) < 1e-9
    assert _max_diff(a.players(), c.players()) > 1e-3  # unnormalized weights change the fit


# --- covariate timing on a synthetic ledger ---------------------------------------------

duckdb = pytest.importorskip("duckdb")

HOME, AWAY = "100", "200"
HOME_IDS = [str(i) for i in range(1, 6)]
AWAY_IDS = [str(i) for i in range(6, 11)]
# (seq, elapsed_ms, home_delta, away_delta)
EVENTS = [
    (1, 0, 0, 0),  # period start
    (2, 20_000, 2, 0),  # home scores: possession 1
    (3, 40_000, 0, 3),  # away scores: possession 2
    (4, 60_000, 0, 0),  # home miss: possession 3 starts here
    (5, 70_000, 1, 0),  # home free throw inside possession 3
    (6, 715_000, 0, 2),  # away scores late: possession 4
    (7, 720_000, 0, 0),  # period end
]
# (possession_seq, period, start_seq, end_seq, offense)
POSSESSIONS = [(1, 1, 1, 3), (2, 1, 3, 4), (3, 1, 4, 6), (4, 1, 6, 7)]
OFFENSE = {1: HOME, 2: AWAY, 3: HOME, 4: AWAY}
ALLOCATIONS = [(2, HOME, 2, 1), (3, AWAY, 3, 2), (5, HOME, 1, 3), (6, AWAY, 2, 4)]


def _ledger(events=EVENTS, allocations=ALLOCATIONS):
    from bil.models.rapm.context_ablation import read_context, timing_audit

    con = duckdb.connect()
    con.execute(
        "CREATE TABLE event (game_id VARCHAR, stream_revision INTEGER, seq INTEGER, "
        "elapsed_ms INTEGER, home_delta SMALLINT, away_delta SMALLINT)"
    )
    con.executemany("INSERT INTO event VALUES ('g1', 1, ?, ?, ?, ?)", events)
    con.execute(
        "CREATE TABLE game AS SELECT 'g1' AS game_id, 1 AS revision, '100' AS home_team_id, "
        "'200' AS away_team_id, NULL::BOOLEAN AS neutral_site, 2022 AS season_start_year"
    )
    con.execute(
        "CREATE TABLE score_allocation (game_id VARCHAR, stream_revision INTEGER, seq INTEGER, "
        "scoring_team_id VARCHAR, points_delta SMALLINT, possession_seq INTEGER, "
        "possession_reason VARCHAR)"
    )
    con.executemany(
        "INSERT INTO score_allocation VALUES ('g1', 1, ?, ?, ?, ?, 'control_possession')",
        allocations,
    )
    con.execute(
        "CREATE TABLE model_row (game_id VARCHAR, stream_revision INTEGER, game_revision INTEGER, "
        "game_date DATE, season_start_year SMALLINT, season_type VARCHAR, possession_seq INTEGER, "
        "period SMALLINT, start_seq INTEGER, end_seq INTEGER, offense_team_id VARCHAR, "
        "offense_player_ids VARCHAR[], defense_player_ids VARCHAR[], model_points DOUBLE)"
    )
    points = {p: sum(a[2] for a in allocations if a[3] == p) for p, *_ in POSSESSIONS}
    for seq, period, start, end in POSSESSIONS:
        home = OFFENSE[seq] == HOME
        con.execute(
            "INSERT INTO model_row VALUES ('g1', 1, 1, DATE '2023-01-02', 2022, 'regular', "
            "?, ?, ?, ?, ?, ?, ?, ?)",
            [
                seq,
                period,
                start,
                end,
                OFFENSE[seq],
                HOME_IDS if home else AWAY_IDS,
                AWAY_IDS if home else HOME_IDS,
                float(points[seq]),
            ],
        )
    rows, raw = read_context(con)
    return rows, timing_audit(con, raw)


def test_covariates_use_only_events_before_the_possession_starts():
    rows, audit = _ledger()
    # Offense-minus-defense margin before each possession: 0-0 at the start, the away offense
    # trails 0-2, the home offense trails 2-3, then 3-3 after the home free throw at seq 5.
    np.testing.assert_array_equal(rows.margin, [0, -2, -1, 0])
    np.testing.assert_array_equal(rows.elapsed_ms, [0, 20_000, 40_000, 70_000])
    np.testing.assert_array_equal(rows.offense_home, [True, False, True, False])
    assert audit["own_points_sequenced_before_start"] == 0
    assert audit["event_and_allocation_scores_disagree"] == 0
    assert audit["prior_clock_after_first_event"] == 0
    assert audit["possessions_without_prior_event"] == 1


def test_changing_events_at_or_after_the_start_never_changes_that_possession():
    base, _ = _ledger()
    # Rewrite every event from possession 3's first event onward.
    mutated = [e if e[0] < 4 else (e[0], e[1] + 1000, e[2] + 5, e[3] + 7) for e in EVENTS]
    changed, _ = _ledger(events=mutated)
    assert changed.margin[2] == base.margin[2] and changed.elapsed_ms[2] == base.elapsed_ms[2]
    assert changed.margin[:3].tolist() == base.margin[:3].tolist()
    assert changed.margin[3] != base.margin[3]  # a later possession does see the change


def test_audit_flags_own_points_sequenced_before_the_start():
    # Possession 3's free throw recorded at seq 3, before its start_seq 4: an outcome leak.
    leaked = [a if a[3] != 3 else (3, HOME, 1, 3) for a in ALLOCATIONS]
    _, audit = _ledger(allocations=leaked)
    assert audit["own_points_sequenced_before_start"] == 1


# --- features, folds and scoring ----------------------------------------------------------


def _rows(margins, periods, elapsed, home, neutral=None):
    n = len(margins)
    obs = [
        Observation(f"g{i}", "t", "regular", Possession((1, 2, 3, 4, 5), (6, 7, 8, 9, 10), 1.0))
        for i in range(n)
    ]
    return ContextRows(
        observations=obs,
        dates=[date(2023, 1, 1)] * n,
        offense_home=np.array(home),
        neutral=np.array(neutral or [False] * n),
        neutral_unknown=np.zeros(n, dtype=bool),
        margin=np.array(margins, dtype=float),
        period=np.array(periods, dtype=np.int64),
        elapsed_ms=np.array(elapsed, dtype=float),
    )


def test_feature_columns_and_late_blowout():
    rows = _rows(
        margins=[25, -20, 19, 0, -30],
        periods=[4, 5, 4, 2, 3],
        elapsed=[2_870_000, 3_100_000, 2_200_000, 1_430_000, 1_500_000],
        home=[True, False, True, True, False],
        neutral=[False, False, False, True, False],
    )
    cols = feature_columns(rows)
    np.testing.assert_array_equal(cols["offense_home"], [1, -1, 1, 0, -1])
    np.testing.assert_array_equal(cols["margin_clipped"], [20, -20, 19, 0, -20])
    np.testing.assert_array_equal(cols["overtime"], [0, 1, 0, 0, 0])
    # 10 s left in Q4; 80 s left in OT1; 680 s left in Q4; 10 s left in Q2; 660 s left in Q3.
    np.testing.assert_array_equal(cols["end_of_period"], [1, 0, 0, 1, 0])
    np.testing.assert_array_equal(cols["final_two_minutes"], [1, 1, 0, 0, 0])
    np.testing.assert_array_equal(cols["margin_15_inf"], [1, 0, 1, 0, 0])
    np.testing.assert_array_equal(late_blowout(rows), [True, True, False, False, False])


def test_fold_masks_are_strictly_chronological():
    dates = [date(2023, 1, 1) + timedelta(days=d) for d in range(10)]
    fit, scored = fold_masks(dates, date(2023, 1, 5), date(2023, 1, 8))
    assert fit.tolist() == [True] * 4 + [False] * 6
    assert scored.tolist() == [False] * 4 + [True] * 3 + [False] * 3


def test_blowout_variants_change_only_the_fit_weights():
    base = generate_possessions(600, seed=17, noisy=True)
    obs = [Observation(f"g{i // 10}", "t", "regular", r) for i, r in enumerate(base)]
    rows = ContextRows(
        observations=obs,
        dates=[date(2023, 1, 1)] * 600,
        offense_home=np.arange(600) % 2 == 0,
        neutral=np.zeros(600, dtype=bool),
        neutral_unknown=np.ones(600, dtype=bool),
        margin=np.where(np.arange(600) % 7 == 0, 25.0, 0.0),
        period=np.full(600, 4, dtype=np.int64),
        elapsed_ms=np.full(600, 2_500_000.0),
    )
    everything = np.ones(600, dtype=bool)
    drop = fit_variant("W_drop", rows, everything, ridge=20.0)
    expected = fit_rapm(
        [o.possession for o, b in zip(obs, late_blowout(rows)) if not b], ridge=20.0
    )
    assert _max_diff(drop.players, expected) < 1e-9
    half = fit_variant("W_half", rows, everything, ridge=20.0)
    assert 0 < _max_diff(half.players, fit_variant("C0", rows, everything, ridge=20.0).players)
    # Fitted and offset predictions include the context term.
    fitted = fit_variant("H_fit", rows, everything, ridge=20.0)
    prediction = predict_variant(fitted, rows, everything)
    assert prediction.shape == (600,)


def test_paired_delta_and_verdict_rule():
    y = np.array([0.0, 100.0, 200.0, 0.0])
    block = Block(
        y,
        {"C0": np.full(4, 75.0), "better": y + 1.0, "league": np.full(4, 75.0)},
        np.array([0, 0, 1, 1]),
        np.array([0, 1, 2, 3]),
        np.array([False, True, False, True]),
    )
    result = paired(block, "better", "C0", resamples=200)
    assert result["delta"] < 0 and result["ci95"][1] < 0
    assert verdict(result) == "supported"
    assert verdict({"delta": 0.5, "ci95": [-1.0, 2.0]}) == "rejected"
    assert verdict({"delta": -0.5, "ci95": [-1.0, 2.0]}) == "inconclusive"
    sub = block.subset(block.blowout)
    assert sub.game.tolist() == [0, 1] and sub.y.tolist() == [100.0, 0.0]


def test_runner_end_to_end_on_synthetic_rows(tmp_path, monkeypatch):
    import json

    from bil.models.rapm import context_ablation

    rng = np.random.default_rng(18)
    base = generate_possessions(3000, seed=18, noisy=True)
    start = date(2022, 10, 18)
    obs, dates = [], []
    for i, row in enumerate(base):
        game = i // 15
        played = start + timedelta(days=game)
        dates.append(played)
        season = "playoffs" if played >= date(2023, 4, 15) else "regular"
        obs.append(
            Observation(f"g{game:04d}", f"t{i % 2}", season, replace(row, played_date=played))
        )
    period = rng.integers(1, 6, size=3000).astype(np.int64)
    rows = ContextRows(
        observations=obs,
        dates=dates,
        offense_home=np.arange(3000) % 2 == 0,
        neutral=np.zeros(3000, dtype=bool),
        neutral_unknown=np.ones(3000, dtype=bool),
        margin=rng.integers(-30, 31, size=3000).astype(float),
        period=period,
        elapsed_ms=context_ablation.period_start_ms(period) + rng.integers(0, 300_000, 3000),
    )
    monkeypatch.setattr(context_ablation, "load", lambda *_: (rows, {"synthetic": 0}))
    protocol = tmp_path / "protocol.md"
    protocol.write_text("synthetic")
    manifest = context_ablation.run(tmp_path, tmp_path, tmp_path / "out", protocol)
    results = json.loads((tmp_path / "out" / "results.json").read_text())
    assert results["optimizer"]["all_converged"]
    assert max(results["zero_context_vs_reference_solver_max_abs_diff"].values()) < 1e-8
    assert set(results["verdicts_regular_season_pooled_vs_C0"]) == {
        n for n, _, _ in context_ablation.VARIANTS[1:]
    }
    assert results["scored_sets"]["playoffs"]["possessions"] > 0
    assert manifest["issue"] == 24


def test_period_clock_boundaries_include_overtime():
    from bil.models.rapm.context_ablation import period_end_ms, period_start_ms

    periods = np.array([1, 4, 5, 6], dtype=np.int64)
    np.testing.assert_array_equal(period_start_ms(periods), [0, 2_160_000, 2_880_000, 3_180_000])
    np.testing.assert_array_equal(
        period_end_ms(periods), [720_000, 2_880_000, 3_180_000, 3_480_000]
    )
