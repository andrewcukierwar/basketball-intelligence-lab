"""Synthetic tests for the M1 policy classification and season missingness diagnostics."""

from __future__ import annotations

import csv
import itertools
import json
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pytest

from bil.data import season_quality as sq

TEAMS = ["A", "B", "C", "D", "E", "F"]


def build_season(
    root: Path,
    year: int,
    *,
    quarantined: frozenset[int] = frozenset(),
    overtime: frozenset[int] = frozenset(),
    weak: bool = False,
    unresolved: dict[int, int] | None = None,
    repeats: int = 4,
) -> tuple[Path, Path]:
    """Write a tiny build and snapshot: round-robin games, 4 possessions each, 5 players a side."""
    unresolved = unresolved or {}
    build, snapshot = root / f"build-{year}", root / f"snap-{year}"
    build.mkdir(parents=True)
    snapshot.mkdir(parents=True)
    pairs = list(itertools.permutations(TEAMS, 2)) * repeats
    games, review, poss, events, stints, lineups, box = [], [], [], [], [], [], []
    yy = year % 100
    for i, (home, away) in enumerate(pairs):
        gid = f"002{yy:02d}{i:07d}"
        month = 10 + (i * 4) // len(pairs)  # four months, October to January
        day = date(year + (month > 12), month if month <= 12 else month - 12, 1 + i % 27)
        ok = i not in quarantined
        strata = ["same_clock_free_throw_substitution"]
        if i in overtime:
            strata.append("overtime")
        if weak:
            strata.append("no_livedata")
        games.append((gid, "regular", day, home, away, 100 + i % 3, 98))
        review.append((gid, ok, None if ok else "parser_error", strata))
        for team in (home, away):
            for k in range(5):
                box.append((int(gid), f"{team}{k}", team, 20.0 if k < 5 else 0.0, 10, 4, 2, 3))
        if not ok:
            continue
        for seq in range(4):
            events.append((gid, 1, seq, 2 if seq == 1 else 0, 0))
        n_bad = unresolved.get(i, 0)
        for seq in range(4):
            late = seq == 3 and i in overtime
            status = "unresolved" if seq >= 4 - n_bad else "accepted"
            poss.append((gid, 1, seq, 5 if late else 1, seq, seq + 1, home, status))
        stints.append((gid, 1, 0, 1, 0, 3, 0, 2_160_000, f"{gid}h", f"{gid}a"))
        last = 5 if i in overtime else 1
        stints.append((gid, 1, 1, last, 3, 4, 2_160_000, 2_460_000, f"{gid}h", f"{gid}a"))
        lineups.append((gid, 1, f"{gid}h", home, [f"{home}{k}" for k in range(5)]))
        lineups.append((gid, 1, f"{gid}a", away, [f"{away}{k}" for k in range(5)]))
    con = duckdb.connect()
    specs = {
        "game": (
            "game_id varchar, season_type varchar, game_date date, home_team_id varchar,"
            " away_team_id varchar, home_final smallint, away_final smallint",
            games,
        ),
        "game_review": (
            "game_id varchar, accepted boolean, reason varchar, strata varchar[]",
            review,
        ),
        "possession": (
            "game_id varchar, stream_revision int, possession_seq int, period smallint,"
            " start_seq int, end_seq int, offense_team_id varchar, status varchar",
            poss,
        ),
        "event": (
            "game_id varchar, stream_revision int, seq int, home_delta smallint,"
            " away_delta smallint",
            events,
        ),
        "stint": (
            "game_id varchar, stream_revision int, stint_seq int, period smallint, start_seq int,"
            " end_seq int, start_elapsed_ms int, end_elapsed_ms int, home_lineup_id varchar,"
            " away_lineup_id varchar",
            stints,
        ),
        "lineup": (
            "game_id varchar, stream_revision int, lineup_id varchar, team_id varchar,"
            " player_ids varchar[]",
            lineups,
        ),
    }
    for name, (columns, rows) in specs.items():
        con.execute(f"create table {name} ({columns})")
        if rows:
            width = len(rows[0])
            con.executemany(f"insert into {name} values ({', '.join(['?'] * width)})", rows)
        con.execute(f"copy {name} to '{build / (name + '.parquet')}' (format parquet)")
    con.execute(
        "create table box (game_id bigint, player_id varchar, team_id varchar, min double,"
        " fga int, fta int, oreb int, tov int)"
    )
    con.executemany("insert into box values (?, ?, ?, ?, ?, ?, ?, ?)", box)
    con.execute(f"copy box to '{snapshot / 'player_game_logs.parquet'}' (format parquet)")
    (build / "manifest.json").write_text(json.dumps({"season_start_year": year}))
    return build, snapshot


def test_margin_band_and_flag_rule() -> None:
    assert [sq.margin_band(m) for m in (0, 5, 6, 10, 11, 20, 21, 60)] == [
        "0-5",
        "0-5",
        "6-10",
        "6-10",
        "11-20",
        "11-20",
        "21+",
        "21+",
    ]
    assert sq.flag(0.001, 3.0, 5) == "systematic"
    assert sq.flag(0.001, 1.5, 5) == "watch"  # significant but a small effect
    assert sq.flag(0.001, 3.0, 2) == "watch"  # too few events for a systematic call
    assert sq.flag(0.2, 5.0, 9) == "none"


def test_permutation_test_detects_concentration_and_is_deterministic() -> None:
    cells = np.repeat(np.eye(4), 25, axis=0)  # 100 games in 4 cells of 25
    exposure = np.ones(100)
    clustered = np.zeros(100)
    clustered[:10] = 1.0
    spread = np.zeros(100)
    spread[[0, 25, 50, 75, 1, 26, 51, 76, 2, 27]] = 1.0
    rng = np.random.default_rng
    stat, p_value, observed, expected = sq.permutation_test(
        clustered, exposure, cells, rng(1), 2000
    )
    assert observed.tolist() == [10, 0, 0, 0]
    assert expected.tolist() == [2.5, 2.5, 2.5, 2.5]
    assert stat == pytest.approx(22.5 + 2.5 + 2.5 + 2.5)
    assert p_value < 0.01
    assert sq.permutation_test(clustered, exposure, cells, rng(1), 2000)[1] == p_value
    assert sq.permutation_test(spread, exposure, cells, rng(1), 2000)[1] > 0.2


def test_m1_classification_separates_hard_limits_from_warnings(tmp_path: Path) -> None:
    # 120 games; 3 overtime games of which 1 is quarantined; 119 of 120 accepted overall.
    build, snap = build_season(
        tmp_path, 2018, quarantined=frozenset({0}), overtime=frozenset({0, 1, 2}), repeats=4
    )
    season = sq.load_season(build, snap)
    result = sq.m1_classification(season)
    assert result.hard_failures == []
    assert result.original_status == "fail"  # the overtime stratum is 2 of 3
    assert result.revised_status == "meets_with_warnings"
    assert any("overtime" in w for w in result.warnings)
    # More quarantines than the 3% floor allows is a hard failure under both policies.
    build, snap = build_season(tmp_path, 2019, quarantined=frozenset(range(10)), repeats=4)
    result = sq.m1_classification(sq.load_season(build, snap))
    assert result.revised_status == "fails_hard_limit"
    assert result.original_status == "fail"
    # The season-wide unresolved limit is a hard gate.
    build, snap = build_season(tmp_path, 2020, unresolved={5: 4, 6: 4, 7: 4})
    result = sq.m1_classification(sq.load_season(build, snap))
    assert result.revised_status == "fails_hard_limit"
    # A clean season meets, and a failing invariant count is a hard failure.
    build, snap = build_season(tmp_path, 2021)
    clean = sq.load_season(build, snap)
    assert sq.m1_classification(clean).revised_status == "meets"
    assert sq.m1_classification(clean, invariants_failed=1).revised_status == "fails_hard_limit"


def test_unresolved_rate_above_limit_by_season_type_is_only_a_warning(tmp_path: Path) -> None:
    # Playoff-style: one season type above 0.1% while the whole season stays within it needs
    # two season types, so check the whole-season rate with a rate that is only a warning.
    build, snap = build_season(tmp_path, 2022, unresolved={5: 1})
    result = sq.m1_classification(sq.load_season(build, snap))
    by_type = {u["season_type"]: u for u in result.unresolved}
    assert by_type["regular"]["unresolved"] == 1
    assert by_type["season"]["possessions"] == by_type["regular"]["possessions"]
    # 1 of 480 possessions is 0.21%, above 0.1% for the season, so a hard failure.
    assert result.revised_status == "fails_hard_limit"


def test_quarantine_concentration_is_flagged_and_uniform_is_not(tmp_path: Path) -> None:
    # Quarantine eight games that all involve team A and all fall in the first month.
    pairs = list(itertools.permutations(TEAMS, 2)) * 8
    chosen = frozenset([i for i, p in enumerate(pairs) if "A" in p][:10])
    build, snap = build_season(tmp_path / "x", 2018, quarantined=chosen, repeats=8)
    season = sq.load_season(build, snap)
    _cells, tests, causes = sq.quarantine_missingness(season, seed=1, permutations=1000)
    team = next(t for t in tests if t["dimension"] == "team" and t["season_type"] == "regular")
    assert team["flag"] == "systematic"
    assert team["max_lift_cell"] == "A"
    assert causes[0]["cause"] == "parser_error"
    assert causes[0]["games"] == 10
    # Quarantines spread evenly across games are not flagged.
    spread = frozenset(range(0, len(pairs), 8))
    build, snap = build_season(tmp_path / "y", 2018, quarantined=spread, repeats=8)
    _cells, tests, _causes = sq.quarantine_missingness(
        sq.load_season(build, snap), seed=1, permutations=1000
    )
    assert all(t["flag"] != "systematic" for t in tests)


def test_unresolved_rate_ratio_flags_the_period(tmp_path: Path) -> None:
    # Every unresolved possession is the overtime possession of an overtime game.
    overtime = frozenset(range(0, 240, 2))
    build, snap = build_season(
        tmp_path, 2018, repeats=8, overtime=overtime, unresolved={i: 1 for i in overtime}
    )
    season = sq.load_season(build, snap)
    _cells, tests, _conc = sq.unresolved_missingness(season, seed=1, replicates=300)
    period = next(t for t in tests if t["dimension"] == "unresolved_period")
    assert period["max_lift_cell"] == "OT"
    assert period["flag"] == "systematic"


def test_sensitivity_counts_and_players(tmp_path: Path) -> None:
    ot = frozenset({0, 1, 2})
    builds = [
        build_season(tmp_path, 2018, overtime=ot, weak=True),
        build_season(tmp_path, 2019, quarantined=frozenset({3}), overtime=ot),
        build_season(tmp_path, 2021),
    ]
    seasons = [sq.load_season(b, s) for b, s in builds]
    rows = {r["scenario"]: r for r in sq.sensitivity(seasons, (2018, 2019, 2021))}
    assert rows["baseline"]["games"] == 120 + 119 + 120
    assert rows["baseline"]["possessions"] == 4 * 359
    assert rows["baseline"]["players"] == 30
    assert rows["exclude_2018_19"]["games_change"] == -120
    assert rows["exclude_2021_22"]["games"] == 239
    # The three overtime games of each of the two overtime seasons lose one possession each.
    assert rows["exclude_overtime_periods"]["possessions_change"] == -6
    assert rows["exclude_overtime_games"]["games_change"] == -6
    assert rows["exclude_weaker_verification_games"]["games_change"] == -120
    assert rows["exclude_all_three"]["games"] == 119
    assert rows["exclude_all_three"]["possessions"] == 4 * 119 - 3


def test_run_writes_deterministic_aggregates_and_refuses_to_overwrite(tmp_path: Path) -> None:
    builds = [
        build_season(tmp_path / "in", 2018, quarantined=frozenset({1, 7}), overtime=frozenset({1})),
        build_season(tmp_path / "in", 2019),
    ]
    first, second = tmp_path / "out1", tmp_path / "out2"
    for target in (first, second):
        sq.run(builds, target, permutations=200, replicates=100, primary_years=(2018, 2019))
    names = sorted(p.name for p in first.iterdir())
    assert "m1_classification.csv" in names and "sensitivity.csv" in names
    assert "summary.json" in names
    for name in names:
        assert (first / name).read_bytes() == (second / name).read_bytes()
    with (first / "m1_classification.csv").open() as source:
        rows = list(csv.DictReader(source))
    assert [r["season"] for r in rows] == ["2018-19", "2019-20"]
    with pytest.raises(FileExistsError):
        sq.run(builds, first)
