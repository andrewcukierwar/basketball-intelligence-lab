from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from bil.features.box import Appearance
from bil.models.spm import CANDIDATES, CODES, fit_candidate
from bil.models.tracking_spm import (
    MODELS,
    TRACK,
    TRACK_REGULAR,
    TrackingGame,
    dated_tracking,
    link_tracking,
    predict_all,
    rates,
    tracking_matrix,
    tracking_pins,
    tracking_window,
)

START = date(2019, 10, 22)


def box(game: str, player: int, team: str, minutes: float, day: date = START) -> Appearance:
    return Appearance.from_record(
        {
            "game_id": game,
            "game_date": day,
            "player_id": player,
            "team_id": team,
            "opp_team_id": "9",
            "min": minutes,
        }
    )


def test_pins_cover_the_registered_seasons():
    pins = tracking_pins(Path(__file__).parents[1] / "docs/research/nba-tracking-audit-assets.csv")
    for season in range(2018, 2023):
        assert pins[season][0] == f"game_matchups_{season + 1}.parquet"


def test_linkage_requires_positive_minutes_same_team_and_valid_quantities():
    appearances = [
        box("0021900001", 1, "10", 30),
        box("0021900001", 2, "10", 0),
        box("0041900001", 3, "10", 20, START + timedelta(days=180)),
    ]
    totals = [
        ("0021900001", 1, 10, (20.0, 1.0, 6.0, 3.0)),
        ("0021900001", 1, 11, (5.0, 0.0, 1.0, 0.0)),  # wrong team
        ("0021900001", 2, 10, (5.0, 0.0, 1.0, 0.0)),  # zero minutes
        ("0021900002", 1, 10, (5.0, 0.0, 1.0, 0.0)),  # no box line
        ("0041900001", 3, 10, (10.0, 0.0, 2.0, 3.0)),  # makes above attempts
        ("0041900001", 3, 10, (float("nan"), 0.0, 2.0, 1.0)),
    ]
    games, drops = link_tracking(totals, appearances)
    assert drops == {"unlinked": 3, "invalid_quantities": 2}
    assert games == [TrackingGame(START, 1, False, (20.0, 1.0, 6.0, 3.0))]


def test_rates_keep_unknown_opportunities_null():
    out = rates(np.array([[50.0, 2.0, 10.0, 4.0], [10.0, 1.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0]]))
    assert out[0] == pytest.approx([4.0, 20.0, 0.4])
    assert out[1, :2] == pytest.approx([10.0, 0.0]) and np.isnan(out[1, 2])
    assert np.isnan(out[2]).all()


def games() -> list[TrackingGame]:
    return [
        TrackingGame(START + timedelta(days=k), 7, k == 9, (20.0, float(k % 2), 5.0, 2.0))
        for k in range(10)
    ]


def test_windows_and_dated_views_use_only_earlier_games():
    cutoff = START + timedelta(days=5)
    base = tracking_matrix(tracking_window(games(), cutoff), [7, 8])
    poisoned = [
        TrackingGame(g.day, g.player, g.playoff, (1.0, 1.0, 1.0, 1.0)) if g.day >= cutoff else g
        for g in games()
    ] + [TrackingGame(cutoff, 8, False, (9.0, 9.0, 9.0, 9.0))]
    assert np.array_equal(
        tracking_matrix(tracking_window(poisoned, cutoff), [7, 8]), base, equal_nan=True
    )
    assert np.isnan(base[1]).all()
    days = [START + timedelta(days=k) for k in (0, 5, 10)]
    clean = [tracking_matrix(view, [7]).copy() for _, view in dated_tracking([], games(), days)]
    dirty = [tracking_matrix(view, [7]).copy() for _, view in dated_tracking([], poisoned, days)]
    assert np.isnan(clean[0]).all()
    assert np.array_equal(clean[1], dirty[1])
    assert not np.array_equal(clean[2], dirty[2])
    # The playoff game on day 9 enters the pooled columns only.
    pooled, regular = clean[2][0, :3], clean[2][0, 3:]
    assert pooled[1] == pytest.approx(25.0) and regular[1] == pytest.approx(25.0)
    assert pooled[0] == pytest.approx(100 * 5 / 200) and regular[0] == pytest.approx(100 * 4 / 180)


def synthetic(n: int = 300) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(38)
    values = rng.normal(size=(n, len(CODES) + 6))
    values[: n // 10, TRACK + TRACK_REGULAR] = np.nan
    labels = np.column_stack((values[:, 0], 0.5 * values[:, TRACK[1]] + values[:, 10]))
    labels[np.isnan(labels)] = 0.0
    exposure = rng.uniform(300, 3000, size=(n, 2))
    return values, labels, exposure, np.ones(n, dtype=bool)


def test_full_matches_box_only_fit_and_tracking_falls_back_to_full_defense():
    values, labels, exposure, support = synthetic()
    models = {
        name: fit_candidate(values, labels, exposure, support, c) for name, c in MODELS.items()
    }
    reference = fit_candidate(
        values[:, : len(CODES)], labels, exposure, support, CANDIDATES["full"]
    )
    for ours, theirs in zip(models["full"], reference, strict=True):
        assert np.array_equal(ours.coefficients, theirs.coefficients)
    out = predict_all(models, values)
    assert np.array_equal(out["full_tracking"][:, 0], out["full"][:, 0])
    untracked = slice(0, len(values) // 10)
    assert np.array_equal(out["full_tracking"][untracked, 1], out["full"][untracked, 1])
    assert not np.allclose(out["full_tracking"][30:, 1], out["full"][30:, 1])
    assert (
        models["full_tracking"][1].record(CODES + ("a", "b", "c", "d", "e", "f"))["features"][-1]
        == "c"
    )


def test_reporting_path_pools_weeks_and_contrasts_players():
    from bil.models.tracking_spm import COURT_NAMES, court_pool, k0_contrasts

    rng = np.random.default_rng(1)
    blocks = [np.column_stack((np.full(20, 50.0), rng.uniform(60, 70, (20, len(COURT_NAMES)))))]
    pooled = court_pool(blocks)
    assert pooled["possessions"] == 1000 and len(pooled["deltas"]) == 4
    low, high = pooled["deltas"]["context_full_minus_context"]["interval"]
    assert low <= pooled["deltas"]["context_full_minus_context"]["delta"] <= high
    assert court_pool([np.empty((0, 8))]) == {"possessions": 0}
    errors = {name: rng.normal(size=(50, 3)) for name in MODELS}
    out = k0_contrasts(errors, np.repeat(np.arange(25), 2))
    assert out["distinct_players"] == 25 and set(out["minus_full"]) == set(MODELS) - {"full"}
    assert k0_contrasts(errors, np.array([], dtype=np.int64)) == {"player_seasons": 0}
