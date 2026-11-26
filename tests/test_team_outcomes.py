from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pytest

from bil.features.box import Appearance
from bil.models.team_outcomes import (
    BoxIndex,
    Game,
    Snapshot,
    calibration,
    oracle_minutes,
    paired,
    project_minutes,
    ridge_team_ratings,
    team_net,
    verdict,
)

START = date(2023, 10, 20)


def line(game: int, day: date, player: int, team: str, minutes: float) -> Appearance:
    return Appearance.from_record(
        {
            "game_id": f"00223{game:05d}",
            "game_date": day,
            "player_id": player,
            "team_id": team,
            "opp_team_id": "Z",
            "min": minutes,
        }
    )


def season_logs() -> dict[int, list[Appearance]]:
    current = []
    for g in range(12):
        day = START + timedelta(days=2 * g)
        for player, minutes in ((1, 36), (2, 30), (3, 24), (4, 20), (5, 18), (6, 12)):
            current.append(line(g, day, player, "A", minutes))
    previous = [line(900, date(2023, 4, 1), 7, "A", 40), line(900, date(2023, 4, 1), 8, "A", 10)]
    return {2023: current, 2022: previous}


def test_projection_uses_only_earlier_games_and_rescales():
    logs = season_logs()
    day = START + timedelta(days=2 * 11)  # game 11 is on this date
    base = project_minutes(BoxIndex.build(logs), 2023, "A", day)
    assert base.games_used == 10 and not base.previous_season
    assert sum(base.minutes.values()) == pytest.approx(240.0)
    poisoned = {
        2023: [
            replace(row, minutes_ms=48 * 60_000) if row.game_date >= day else row
            for row in logs[2023]
        ]
        + [line(11, day, 99, "A", 48), line(50, day + timedelta(days=5), 98, "A", 48)],
        2022: logs[2022],
    }
    assert project_minutes(BoxIndex.build(poisoned), 2023, "A", day) == base
    assert 99 in oracle_minutes(BoxIndex.build(poisoned), "0022300011", "A")


def test_opening_game_falls_back_to_previous_season():
    projection = project_minutes(BoxIndex.build(season_logs()), 2023, "A", START)
    assert projection.previous_season and projection.games_used == 1
    assert projection.minutes == pytest.approx({7: 192.0, 8: 48.0})


def test_player_whose_latest_earlier_line_is_elsewhere_is_dropped():
    logs = season_logs()
    day = START + timedelta(days=30)
    logs[2023].append(line(70, day - timedelta(days=1), 2, "B", 30))
    projection = project_minutes(BoxIndex.build(logs), 2023, "A", day)
    assert 2 not in projection.minutes and projection.roster_drops == 1


def test_team_net_and_cold_share():
    snapshot = Snapshot(START, {1: 2.0, 2: -1.0}, 0.5, "s")
    net, cold = team_net({1: 48.0, 2: 96.0, 3: 96.0}, snapshot)
    assert net == pytest.approx(2.0 - 2.0 + 1.0)
    assert cold == pytest.approx(96 / 240)


def test_ridge_recovers_team_strengths_from_earlier_games_only():
    truth = {"A": 3.0, "B": 0.0, "C": -3.0}
    teams = sorted(truth)
    games = []
    for k in range(60):
        h, a = teams[k % 3], teams[(k + 1) % 3]
        day = START + timedelta(days=k)
        games.append(Game(f"g{k}", 2023, day, False, h, a, (h, a), 2.5 + truth[h] - truth[a]))
    cutoff = START + timedelta(days=60)
    late = Game("late", 2023, cutoff, False, "C", "A", ("C", "A"), 500.0)
    home, ratings = ridge_team_ratings([*games, late], cutoff, teams, 1e6, 1e-6)
    assert home == pytest.approx(2.5, abs=1e-4)
    assert ratings["A"] - ratings["C"] == pytest.approx(6.0, abs=1e-4)


def test_paired_verdict_and_calibration():
    rng = np.random.default_rng(0)
    margin = rng.normal(2, 12, size=400)
    good = margin + rng.normal(0, 4, size=400)
    bad = np.full(400, 2.0)
    prob_good = np.clip(1 / (1 + np.exp(-good / 6)), 1e-6, 1 - 1e-6)
    prob_bad = np.full(400, 0.55)
    week = np.repeat(np.arange(40), 10)
    out = paired(margin, (good, prob_good), (bad, prob_bad), {"game": np.arange(400), "week": week})
    assert out["rmse_delta"] < 0 and out["rmse_ci95_game"][1] < 0
    assert verdict(out, [out, out], "rmse") == "ei_better"
    won = (rng.random(4000) < 0.5).astype(float)
    p = np.full(4000, 0.5) + rng.normal(0, 1e-3, 4000)
    result = calibration(p, won)
    assert len(result["bins"]) == 10 and abs(result["intercept"]) < 0.2
