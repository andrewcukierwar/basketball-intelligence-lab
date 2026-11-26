import json
from datetime import date, timedelta

import numpy as np
import pytest

from bil.features.box import Appearance
from bil.models.expected_impact import SpmFit
from bil.models.expected_impact_outer import (
    evaluate,
    lineup_min,
    outer_logs,
    parse_config,
    verdicts,
)
from bil.models.rapm.multiseason import AddendumError, Analysis, Rows, Scenario, build_matrix
from bil.models.spm import CODES, LinearPrior

FGA, STL = CODES.index("fga_per_36"), CODES.index("stl_per_36")
SHA = "a" * 64


def config() -> dict:
    return {
        "issue": 36,
        "outer_seasons": [2023, 2024],
        "dev_manifest_sha256": SHA,
        "protocol_sha256": SHA,
        "spm_fit": "final_contiguous_fit.json",
        "spm_fit_sha256": SHA,
        "primary_comparator": "rapm_context",
        "models": {
            "ei": {"window": "W2", "offense_ridge": 30.0, "defense_ridge": 30.0},
            "ei_zero_prior": {"window": "W2", "offense_ridge": 30.0, "defense_ridge": 30.0},
            "rapm": {"window": "W2", "offense_ridge": 20.0, "defense_ridge": 40.0},
            "rapm_context": {"window": "W2", "offense_ridge": 20.0, "defense_ridge": 40.0},
            "league": {"window": "W1"},
            "context": {"window": "W1"},
        },
        "box_logs": {str(s): {"snapshot": "x", "sha256": SHA} for s in (2022, 2023, 2024)},
    }


def wrap(value: dict) -> str:
    return f"# Addendum\n\n<!-- frozen-config -->\n```json\n{json.dumps(value)}\n```\n"


def test_config_parser_refuses_wrong_scope():
    assert parse_config(wrap(config()))["models"]["ei"]["offense_ridge"] == 30.0
    for change in (
        {"issue": 35},
        {"outer_seasons": [2023, 2025]},
        {"spm_fit_sha256": "short"},
        {"box_logs": {"2023": {}, "2024": {}}},
    ):
        with pytest.raises(AddendumError):
            parse_config(wrap({**config(), **change}))
    bad = config()
    bad["models"]["ei"]["offense_ridge"] = -1.0
    with pytest.raises(AddendumError):
        parse_config(wrap(bad))


def test_holdout_box_logs_refuse_before_any_path(tmp_path):
    with pytest.raises(ValueError, match="holdout"):
        outer_logs(tmp_path, 2025, {"snapshot": "x", "sha256": SHA})


def test_verdict_rule_needs_interval_and_both_seasons():
    def entry(delta, low, high):
        return {"delta": delta, "ci95_game": [low, high]}

    results = {
        "pooled_regular": {
            "ei_delta_vs": {
                "a": entry(-2, -3, -1),
                "b": entry(-2, -3, -1),
                "c": entry(1, 0.5, 2),
                "d": entry(-1, -2, 0.5),
            },
            "2023": {
                "ei_delta_vs": {
                    "a": entry(-1, 0, 0),
                    "b": entry(0.5, 0, 0),
                    "c": entry(1, 0, 0),
                    "d": entry(-1, 0, 0),
                }
            },
            "2024": {
                "ei_delta_vs": {
                    "a": entry(-3, 0, 0),
                    "b": entry(-4, 0, 0),
                    "c": entry(1, 0, 0),
                    "d": entry(-1, 0, 0),
                }
            },
        }
    }
    out = verdicts(results, "a")
    assert out == {
        "a": "ei_better",
        "b": "inconclusive",
        "c": "ei_worse",
        "d": "inconclusive",
        "primary_comparator": "a",
    }


def test_lineup_min_uses_sorted_design_ids_only():
    offense = np.array([[1, 2, 3, 4, 5]])
    defense = np.array([[6, 7, 8, 9, 10]])
    rows = Rows(
        season=np.array([2023]),
        playoff=np.array([False]),
        day=np.array([1]),
        game=np.array([0]),
        game_ids=("g",),
        team_game=np.array([0]),
        possession_seq=np.array([0]),
        period=np.array([1]),
        y=np.array([100.0]),
        offense=offense,
        defense=defense,
        context=np.zeros((1, 1)),
        no_livedata=np.array([False]),
    )
    values = np.concatenate([np.arange(10, 0, -1, dtype=float), [-99.0]])  # extra box-only last
    assert lineup_min(values, rows, np.array([0]), tuple(range(1, 11))).tolist() == [1.0]


def synthetic_outer():
    rng = np.random.default_rng(7)
    start, end = date(2021, 9, 1), date(2025, 6, 20)
    days = [start + timedelta(days=d) for d in range(0, (end - start).days, 6)]
    offense, defense, day, game, y, season, playoff = [], [], [], [], [], [], []
    for g, d in enumerate(days):
        if d.month in (7, 8, 9):
            continue
        year = d.year if d.month >= 7 else d.year - 1
        for _ in range(12):
            players = rng.choice(np.arange(1, 15), 10, replace=False)
            offense.append(players[:5])
            defense.append(players[5:])
            day.append(d.toordinal())
            game.append(g)
            y.append(100.0 * rng.choice([0, 1, 2, 3]))
            season.append(year)
            playoff.append(d.month in (5, 6))
    n = len(y)
    games = sorted(set(game))
    remap = {g: i for i, g in enumerate(games)}
    game_index = np.asarray([remap[g] for g in game], dtype=np.int64)
    rows = Rows(
        season=np.asarray(season, dtype=np.int64),
        playoff=np.asarray(playoff),
        day=np.asarray(day, dtype=np.int64),
        game=game_index,
        game_ids=tuple(f"g{g}" for g in games),
        team_game=game_index * 2 + (np.arange(n) % 2),
        possession_seq=np.arange(n),
        period=np.ones(n, dtype=np.int64),
        y=np.asarray(y),
        offense=np.asarray(offense, dtype=np.int64),
        defense=np.asarray(defense, dtype=np.int64),
        context=np.column_stack([rng.normal(size=n), np.zeros(n)]),
        no_livedata=np.zeros(n, dtype=bool),
    )
    logs: dict[int, list[Appearance]] = {2022: [], 2023: [], 2024: []}
    for i, d in enumerate(days):
        year = d.year if d.month >= 7 else d.year - 1
        if year in logs:
            for player in range(1, 13):
                logs[year].append(
                    Appearance.from_record(
                        {
                            "game_id": f"00222{i:05d}",
                            "game_date": d,
                            "player_id": player,
                            "team_id": 1,
                            "opp_team_id": 2,
                            "min": 30,
                            "fga": int(4 + player % 7),
                            "stl": int(player % 3),
                        }
                    )
                )
    return rows, logs


def test_evaluate_end_to_end_on_synthetic_outer_seasons():
    rows, logs = synthetic_outer()
    analysis = Analysis(
        rows,
        build_matrix(rows.offense, rows.defense),
        Scenario("primary", np.ones(len(rows), dtype=bool)),
        [],
        [],
    )
    spm = SpmFit(
        (
            LinearPrior((FGA,), np.array([8.0]), np.array([2.0]), np.array([1.0]), 0.1),
            LinearPrior((STL,), np.array([1.0]), np.array([0.5]), np.array([0.5]), -0.1),
        ),
        "fit",
        "contiguous@2023-06-13",
    )
    results, snapshots, predictions = evaluate(
        rows, analysis, parse_config(wrap(config())), spm, logs
    )
    assert len(snapshots) == 11 and snapshots[-1].cutoff == date(2025, 7, 1)
    regular = results["pooled_regular"]
    assert set(regular["ei_delta_vs"]) == {
        "ei_offense_only",
        "ei_defense_only",
        "spm_only",
        "ei_zero_prior",
        "rapm",
        "rapm_context",
        "league",
        "context",
    }
    assert regular["possessions"] == int(((rows.season >= 2023) & ~rows.playoff).sum())
    assert set(regular["team_game_rmse"]) == set(regular["mse"])
    assert "some_player_prior_fallback" in regular  # players 13 and 14 have no box lines
    assert results["stability"]["season_start_year_over_year"]["players"] >= 0
    assert len(predictions["ei"]) == int((rows.season >= 2023).sum())
    for audit in results["eligibility"].values():
        assert audit["window_last"] < audit["cutoff"]
        assert audit["box_last"] is None or audit["box_last"] < audit["cutoff"]
