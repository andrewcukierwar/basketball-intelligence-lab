from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pytest

from bil.features.box import Appearance
from bil.models.expected_impact import (
    SpmFit,
    fit_informed,
    prepare,
    ratings,
    spm_fit,
    spm_only,
)
from bil.models.rapm.multiseason import Analysis, Rows, Scenario, build_matrix
from bil.models.rapm.reference import Possession, fit_prior_rapm
from bil.models.spm import CODES, LinearPrior

FGA, STL = CODES.index("fga_per_36"), CODES.index("stl_per_36")
CUTOFF = date(2021, 10, 1)
ROOKIE = 99
CONFIG = {"window": "W2", "offense_ridge": 30.0, "defense_ridge": 60.0}


def spm(origin: str = "contiguous@2021-07-21") -> SpmFit:
    offense = LinearPrior((FGA,), np.array([10.0]), np.array([3.0]), np.array([1.5]), -0.5)
    defense = LinearPrior((STL,), np.array([1.0]), np.array([0.5]), np.array([0.8]), 0.2)
    return SpmFit((offense, defense), "fit-x", origin)


def synthetic(seed: int = 3) -> tuple[Rows, list[Appearance]]:
    rng = np.random.default_rng(seed)
    days = [CUTOFF - timedelta(days=30) + timedelta(days=i) for i in range(40)]
    offense, defense, day, game, y = [], [], [], [], []
    for g, d in enumerate(days):
        pool = np.arange(1, 13) if d < CUTOFF else np.append(np.arange(1, 12), ROOKIE)
        for _ in range(20):
            players = rng.choice(pool, 10, replace=False)
            offense.append(players[:5])
            defense.append(players[5:])
            day.append(d.toordinal())
            game.append(g)
            y.append(100.0 * rng.choice([0, 1, 2, 3]))
    n = len(y)
    rows = Rows(
        season=np.full(n, 2021),
        playoff=np.zeros(n, dtype=bool),
        day=np.asarray(day, dtype=np.int64),
        game=np.asarray(game, dtype=np.int64),
        game_ids=tuple(f"g{i}" for i in range(len(days))),
        team_game=np.asarray(game, dtype=np.int64) * 2,
        possession_seq=np.arange(n),
        period=np.ones(n, dtype=np.int64),
        y=np.asarray(y),
        offense=np.asarray(offense, dtype=np.int64),
        defense=np.asarray(defense, dtype=np.int64),
        context=np.column_stack([rng.normal(size=n), np.zeros(n)]),
        no_livedata=np.zeros(n, dtype=bool),
    )
    appearances = [
        Appearance.from_record(
            {
                "game_id": f"00221{i:05d}",
                "game_date": d,
                "player_id": player,
                "team_id": 100,
                "opp_team_id": 200,
                "min": 36,
                "fga": int(5 + player + i % 3),
                "stl": int(player % 3),
            }
        )
        for i, d in enumerate(days)
        for player in range(1, 12)
    ]
    return rows, appearances


def analysis(rows: Rows) -> Analysis:
    design = build_matrix(rows.offense, rows.defense)
    return Analysis(rows, design, Scenario("primary", np.ones(len(rows), dtype=bool)), [], [])


def snapshot(rows: Rows, appearances: list[Appearance]):
    a = analysis(rows)
    prepared = prepare(a, CUTOFF, spm(), [], appearances)
    fit = fit_informed(a, prepared, CONFIG["offense_ridge"], CONFIG["defense_ridge"], "t")
    return a, prepared, fit, ratings(prepared, fit, a.design, CONFIG)


def test_residual_fit_equals_prior_centered_reference():
    rows, appearances = synthetic()
    rows = replace(rows, context=np.zeros_like(rows.context))
    a, prepared, fit, snap = snapshot(rows, appearances)
    window = prepared.index
    m = a.design.size
    priors = {int(p): prepared.priors[i] for i, p in enumerate(prepared.player_ids[:m])}
    reference = fit_prior_rapm(
        [
            Possession(
                tuple(map(int, rows.offense[i])), tuple(map(int, rows.defense[i])), rows.y[i] / 100
            )
            for i in window
        ],
        offense_ridge=CONFIG["offense_ridge"],
        defense_ridge=CONFIG["defense_ridge"],
        offense_prior={p: v[0] for p, v in priors.items()},
        defense_prior={p: v[1] for p, v in priors.items()},
    )
    for i, player in enumerate(snap.player_ids):
        if int(player) in reference.offense:
            assert snap.rating[i, 0] == pytest.approx(reference.offense[int(player)], abs=1e-6)
            assert snap.rating[i, 1] == pytest.approx(reference.defense[int(player)], abs=1e-6)
    signed = a.design.players[window] @ np.concatenate([snap.rating[:m, 0], snap.rating[:m, 1]])
    ours = fit.intercept + signed
    theirs = reference.intercept + signed
    np.testing.assert_allclose(ours, theirs, atol=1e-6)


def test_rookie_without_history_or_window_keeps_intercept_prior():
    rows, appearances = synthetic()
    a, prepared, _, snap = snapshot(rows, appearances)
    i = int(np.flatnonzero(snap.player_ids == ROOKIE)[0])
    assert not snap.box_history[i]
    assert snap.prior[i].tolist() == [-0.5, 0.2]
    assert snap.deviation[i].tolist() == [0.0, 0.0]
    assert snap.exposure[i] == 0
    assert prepared.audit["prior_fallback_players"] >= 1
    # Player 12 played before the cutoff but has no box line, so only the prior falls back.
    j = int(np.flatnonzero(snap.player_ids == 12)[0])
    assert not snap.box_history[j] and snap.exposure[j] > 0 and snap.deviation[j, 0] != 0


def test_all_zero_context_column_gets_zero_coefficient():
    rows, appearances = synthetic()
    _, prepared, _, _ = snapshot(rows, appearances)
    assert prepared.gamma[1] == 0 and prepared.gamma[0] != 0
    assert prepared.audit["context_zero_columns"] == 1


def test_later_rows_and_box_lines_cannot_change_a_snapshot():
    rows, appearances = synthetic()
    *_, base = snapshot(rows, appearances)
    later = rows.day >= CUTOFF.toordinal()
    poisoned_rows = replace(rows, y=np.where(later, 999.0, rows.y))
    poisoned_box = [
        replace(row, fga=60, stl=9) if row.game_date >= CUTOFF else row for row in appearances
    ] + [
        Appearance.from_record(
            {
                "game_id": "0022199999",
                "game_date": CUTOFF,
                "player_id": ROOKIE,
                "team_id": 1,
                "opp_team_id": 2,
                "min": 40,
                "fga": 30,
                "stl": 5,
            }
        )
    ]
    *_, poisoned = snapshot(poisoned_rows, poisoned_box)
    assert poisoned.snapshot_id == base.snapshot_id
    np.testing.assert_array_equal(poisoned.rating, base.rating)

    earlier_rows = replace(rows, y=np.where(np.arange(len(rows)) == 0, rows.y + 100, rows.y))
    assert snapshot(earlier_rows, appearances)[3].snapshot_id != base.snapshot_id
    earlier_box = [replace(appearances[0], fga=40), *appearances[1:]]
    assert snapshot(rows, earlier_box)[3].snapshot_id != base.snapshot_id


def test_spm_origin_must_precede_the_cutoff():
    rows, appearances = synthetic()
    with pytest.raises(ValueError, match="origin"):
        prepare(analysis(rows), CUTOFF, spm("contiguous@2021-10-01"), [], appearances)


def test_spm_record_round_trip_and_spm_only_prediction():
    fit = spm()
    record = {
        "fit_id": fit.fit_id,
        "origin": fit.origin,
        "candidates": {"full": {"offense": fit.pair[0].record(), "defense": fit.pair[1].record()}},
    }
    rebuilt = spm_fit(record)
    values = np.full((3, len(CODES)), np.nan)
    values[:, FGA] = [4.0, 10.0, np.nan]
    values[:, STL] = [0.0, 2.0, 1.0]
    for old, new in zip(fit.pair, rebuilt.pair, strict=True):
        np.testing.assert_array_equal(old.predict(values), new.predict(values))
    rows, appearances = synthetic()
    a, prepared, _, _ = snapshot(rows, appearances)
    scored = np.flatnonzero(rows.day >= CUTOFF.toordinal())
    expected_offset = np.asarray(
        a.design.players[scored]
        @ np.concatenate([prepared.priors[: a.design.size, 0], prepared.priors[: a.design.size, 1]])
    )
    prediction = spm_only(a, prepared, scored)
    residual = prediction - rows.context[scored] @ prepared.gamma - expected_offset
    assert np.ptp(residual) == pytest.approx(0.0, abs=1e-9)
