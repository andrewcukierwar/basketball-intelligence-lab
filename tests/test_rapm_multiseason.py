"""Synthetic checks for the #26 multi-season RAPM runner: guards, folds, weights and freeze."""

from __future__ import annotations

import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest

pytest.importorskip("numpy")
pytest.importorskip("scipy")

import numpy as np  # noqa: E402

from bil.models.rapm import multiseason as ms  # noqa: E402
from bil.models.rapm.dated import decay_multiplier, fit_dated_prior_rapm  # noqa: E402
from bil.models.rapm.reference import Possession, build_design, fit_prior_rapm  # noqa: E402


def synthetic_rows(seasons: tuple[int, ...], *, seed: int = 7, per_day: int = 1) -> ms.Rows:
    """Six teams of eight players; a game every fourth day of each regular season and playoffs."""
    rng = np.random.default_rng(seed)
    rosters = np.arange(1, 49).reshape(6, 8) * 10
    effects = {int(p): rng.normal(0, 4, size=2) for p in rosters.ravel()}
    columns: dict[str, list] = {
        k: [] for k in ("season", "playoff", "day", "game", "seq", "period")
    }
    offense, defense, y, team, context = [], [], [], [], []
    game_ids: list[str] = []
    for season in seasons:
        days = [(d, False) for d in _days(date(season, 10, 20), date(season + 1, 4, 10))]
        days += [(d, True) for d in _days(date(season + 1, 4, 15), date(season + 1, 6, 10))]
        for day, playoff in days:
            for _ in range(per_day):
                home, away = rng.choice(6, size=2, replace=False)
                game = len(game_ids)
                game_ids.append(f"{season}{game:06d}")
                for seq in range(40):
                    off_team, def_team = (home, away) if seq % 2 == 0 else (away, home)
                    off = rng.choice(rosters[off_team], size=5, replace=False)
                    dfn = rng.choice(rosters[def_team], size=5, replace=False)
                    rate = 1.1 + sum(effects[int(p)][0] for p in off) / 100
                    rate -= sum(effects[int(p)][1] for p in dfn) / 100
                    y.append(100.0 * rng.poisson(max(rate, 0.1)))
                    offense.append(off)
                    defense.append(dfn)
                    team.append(game * 2 + seq % 2)
                    period = 1 + seq // 10 + (1 if seq >= 38 else 0)
                    context.append(
                        [
                            1.0 if off_team == home else -1.0,
                            float(rng.integers(-20, 21)),
                            float(period == 2),
                            float(period == 3),
                            float(period == 4),
                            float(period >= 5),
                            float(seq % 10 == 9),
                            float(seq in (36, 37)),
                        ]
                    )
                    for key, value in zip(
                        columns,
                        (season, playoff, day.toordinal(), game, seq, period),
                        strict=True,
                    ):
                        columns[key].append(value)
    return ms.Rows(
        season=np.array(columns["season"], dtype=np.int64),
        playoff=np.array(columns["playoff"], dtype=bool),
        day=np.array(columns["day"], dtype=np.int64),
        game=np.array(columns["game"], dtype=np.int64),
        game_ids=tuple(game_ids),
        team_game=np.array(team, dtype=np.int64),
        possession_seq=np.array(columns["seq"], dtype=np.int64),
        period=np.array(columns["period"], dtype=np.int64),
        y=np.array(y, dtype=np.float64),
        offense=np.array(offense, dtype=np.int64),
        defense=np.array(defense, dtype=np.int64),
        context=np.array(context, dtype=np.float64),
        no_livedata=np.isin(np.array(columns["season"]), (2018, 2019)),
    )


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=k) for k in range(0, (end - start).days, 4)]


# --- holdout and phase guards -------------------------------------------------------------


@pytest.mark.parametrize("season", [2025, 2026, 2030])
def test_holdout_seasons_are_refused_everywhere(season, tmp_path):
    with pytest.raises(ValueError, match="holdout"):
        ms.check_season(season, range(2000, 2100))
    # The guard fires before any path is built or opened.
    with pytest.raises(ValueError, match="holdout"):
        ms.load_season(tmp_path / "missing", season, range(2000, 2100), tmp_path)
    assert season not in ms.SEASON_PINS


def test_unpinned_and_out_of_phase_seasons_are_refused(tmp_path):
    with pytest.raises(ValueError, match="no pinned"):
        ms.check_season(2017, range(2000, 2025))
    for outer in ms.OUTER_SEASONS:
        with pytest.raises(ValueError, match="not allowed"):
            ms.load_season(tmp_path / "missing", outer, ms.DEV_SEASONS, tmp_path)


def test_parse_frozen_rejects_holdout_or_extra_seasons():
    text = _addendum_text(outer_seasons=[2023, 2024, 2025])
    with pytest.raises(ms.AddendumError, match="2023 and 2024"):
        ms.parse_frozen(text)
    with pytest.raises(ms.AddendumError, match="frozen-config"):
        ms.parse_frozen("no block here")


# --- weights --------------------------------------------------------------------------------


def test_window_and_decay_weights():
    cutoff = date(2022, 12, 1)
    played = [cutoff - timedelta(days=k) for k in (0, 1, 2, 364, 365, 366, 1825, 1826)]
    played.append(cutoff + timedelta(days=3))
    day = np.array([d.toordinal() for d in played], dtype=np.int64)
    w1 = ms.temporal_weights(day, cutoff, ms.TEMPORAL_BY_NAME["W1"])
    assert w1.tolist() == [0, 1, 1, 1, 1, 0, 0, 0, 0]
    w5 = ms.temporal_weights(day, cutoff, ms.TEMPORAL_BY_NAME["W5"])
    assert w5.tolist() == [0, 1, 1, 1, 1, 1, 1, 0, 0]
    h = ms.TEMPORAL_BY_NAME["H180"]
    decayed = ms.temporal_weights(day, cutoff, h)
    for d, w in zip(played, decayed, strict=True):
        age = (cutoff - d).days
        expected = decay_multiplier(age, 180.0) if 1 <= age <= 1825 else 0.0
        assert w == pytest.approx(expected, rel=1e-15, abs=0)


def test_design_matches_reference_layout():
    rows = synthetic_rows((2021,))
    design = ms.build_matrix(rows.offense[:500], rows.defense[:500])
    possessions = [
        Possession(tuple(map(int, o)), tuple(map(int, d)), 1.0)
        for o, d in zip(rows.offense[:500], rows.defense[:500], strict=True)
    ]
    reference = build_design(possessions)
    assert design.player_ids == reference.player_ids
    assert (design.matrix != reference.matrix).nnz == 0
    with pytest.raises(ValueError, match="distinct"):
        bad = rows.offense[:2].copy()
        bad[0, 1] = bad[0, 0]
        ms.build_matrix(bad, rows.defense[:2])


@pytest.mark.parametrize("name", ["W2", "H90", "H365"])
def test_subset_fit_equals_dated_reference(name):
    rows = synthetic_rows((2020, 2021))
    design = ms.build_matrix(rows.offense, rows.defense)
    temporal = ms.TEMPORAL_BY_NAME[name]
    cutoff = date(2022, 2, 1)
    weights = ms.temporal_weights(rows.day, cutoff, temporal)
    index = np.flatnonzero(weights > 0)
    ours = ms.fit_players(design, index, rows.y[index], weights[index], 300.0, 900.0)
    possessions = [
        Possession(
            tuple(map(int, rows.offense[i])),
            tuple(map(int, rows.defense[i])),
            rows.y[i] / 100.0,
            1.0,
            date.fromordinal(int(rows.day[i])),
        )
        for i in index
    ]
    if temporal.half_life_days is None:
        reference = fit_prior_rapm(possessions, offense_ridge=300.0, defense_ridge=900.0)
    else:
        reference = fit_dated_prior_rapm(
            possessions,
            as_of=cutoff,
            half_life_days=temporal.half_life_days,
            offense_ridge=300.0,
            defense_ridge=900.0,
        ).fit
    m = design.size
    assert abs(ours.intercept - reference.intercept) < 1e-8
    for j, p in enumerate(design.player_ids):
        assert abs(ours.effects[j] - reference.offense[p]) < 1e-8
        assert abs(ours.effects[m + j] - reference.defense[p]) < 1e-8


# --- folds -----------------------------------------------------------------------------------


def test_development_folds_never_see_later_rows():
    rows = synthetic_rows(ms.DEV_SEASONS + ms.OUTER_SEASONS)
    design = ms.build_matrix(rows.offense, rows.defense)
    blocks = [b for s in ms.DEV_SCORED_SEASONS for b in ms.season_blocks(rows, s)]
    assert [b.label for b in blocks] == [
        f"{s}-{n}" for s in ms.DEV_SCORED_SEASONS for n in ("R1", "R2", "R3", "R4", "P")
    ]
    analysis = ms.Analysis(rows, design, ms.Scenario("t", np.ones(len(rows), bool)), blocks, [])
    for block in blocks:
        scored = analysis.scored(block)
        assert rows.day[scored].min() >= block.cutoff.toordinal()
        assert rows.day[scored].max() < ms.DEV_END.toordinal()
        assert set(rows.season[scored].tolist()) == {block.season}
        for temporal in ms.TEMPORAL:
            index, _ = analysis.window(block.cutoff, temporal)
            assert rows.day[index].max() < block.cutoff.toordinal()
            assert rows.season[index].max() <= block.season
            assert not set(rows.game[index].tolist()) & set(rows.game[scored].tolist())
    # The development phase refuses rows from outer-validation seasons outright.
    with pytest.raises(ValueError, match="2018-19 through 2022-23"):
        ms.run_development(rows, design, [])


def test_playoff_block_fits_on_the_whole_regular_season():
    rows = synthetic_rows((2021, 2022))
    block = ms.season_blocks(rows, 2022)[-1]
    assert block.role == "playoffs"
    assert block.cutoff == date.fromordinal(
        int(rows.day[rows.playoff & (rows.season == 2022)].min())
    )
    regular = (rows.season == 2022) & ~rows.playoff
    assert rows.day[regular].max() < block.cutoff.toordinal()


def test_penalty_search_finds_the_minimum_of_a_bowl():
    def bowl(o: float, d: float) -> float:
        return (np.log2(o / 8000)) ** 2 + (np.log2(d / 64000)) ** 2

    (offense, defense), memo = ms.search_penalties(bowl)
    assert (offense, defense) == (8000.0, 64000.0)
    assert memo[(offense, defense)] == 0


def test_calibration_of_a_perfect_rate_model():
    rng = np.random.default_rng(3)
    prediction = rng.uniform(80, 140, size=20000)
    y = 100.0 * rng.poisson(prediction / 100)
    game = np.arange(20000) // 50
    result = ms.calibration(y, prediction, game, resamples=200)
    low, high = result["slope_ci95_game"]
    assert low < 1.0 < high
    assert len(result["quantile_bins"]) == ms.CALIBRATION_BINS


# --- the two phases end to end ------------------------------------------------------------


def test_development_and_outer_phases_run_on_synthetic_rows():
    dev_rows = synthetic_rows(ms.DEV_SEASONS)
    design = ms.build_matrix(dev_rows.offense, dev_rows.defense)
    results = ms.run_development(dev_rows, design, log := [])
    assert log and all(e["stop"] in {0, 1, 2, 4, 5} for e in log)
    selected = results["selected"]
    assert selected["temporal"] in ms.TEMPORAL_BY_NAME
    assert set(results["scenarios"]) == {
        "primary",
        "exclude_2018_19",
        "exclude_2021_22",
        "exclude_overtime",
        "exclude_no_livedata",
    }
    assert results["scenarios"]["exclude_2021_22"]["blocks_scored"] == [
        f"2022-{n}" for n in ("R1", "R2", "R3", "R4", "P")
    ]
    # One season of history is empty at the 2022-23 opening cutoff once 2021-22 is removed.
    assert "W1" in results["scenarios"]["exclude_2021_22"]["search"]["infeasible"]
    assert results["scenarios"]["primary"]["search"]["infeasible"] == []
    summary = ms.sensitivity_summary(results)
    assert set(summary) == set(results["scenarios"]) - {"primary"}
    assert max(results["scenarios"]["primary"]["oracle_max_abs_diff"].values()) < 1e-6
    # Search fits only ever used rows dated before 2023-07-01.
    assert max(date.fromisoformat(e["cutoff"]) for e in log) <= ms.DEV_END

    all_rows = synthetic_rows(ms.DEV_SEASONS + ms.OUTER_SEASONS)
    config = ms.parse_frozen(
        _addendum_text(
            temporal=selected["temporal"],
            offense=selected["offense_ridge"],
            defense=selected["defense_ridge"],
        )
    )
    outer = ms.run_outer(all_rows, ms.build_matrix(all_rows.offense, all_rows.defense), config, [])
    assert set(outer["sets"]) == {
        "2023_regular",
        "2023_playoffs",
        "2024_regular",
        "2024_playoffs",
        "pooled_regular",
        "pooled_playoffs",
    }
    pooled = outer["sets"]["pooled_regular"]
    assert pooled["possessions"] == int(
        (np.isin(all_rows.season, (2023, 2024)) & ~all_rows.playoff).sum()
    )
    assert "ci95_week" in pooled["comparisons"]["rapm_minus_league"]


# --- the outer runner refuses without a committed frozen addendum -------------------------


def _addendum_text(
    *, temporal="W2", offense=4000.0, defense=8000.0, outer_seasons=(2023, 2024)
) -> str:
    import json

    block = {
        "issue": 26,
        "outer_seasons": list(outer_seasons),
        "dev_manifest_sha256": "a" * 64,
        "protocol_sha256": "b" * 64,
        "primary": {"temporal": temporal, "offense_ridge": offense, "defense_ridge": defense},
        "league_temporal": "W1",
        "context_temporal": "W1",
    }
    return f"# Addendum\n\n<!-- frozen-config -->\n```json\n{json.dumps(block)}\n```\n"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "test")
    (tmp_path / "addendum.md").write_text(_addendum_text())
    _git(tmp_path, "add", "addendum.md")
    _git(tmp_path, "commit", "-q", "-m", "freeze")
    return tmp_path


def test_outer_refuses_without_an_addendum(repo):
    for path, sha in ((None, None), (repo / "addendum.md", None), (repo / "nope.md", "0" * 64)):
        with pytest.raises(ms.AddendumError):
            ms.outer_main(repo / "missing", repo / "out", path, sha, None, repo=repo)
    assert not (repo / "out").exists()


def test_outer_refuses_a_wrong_digest_uncommitted_or_dirty_addendum(repo):
    addendum = repo / "addendum.md"
    good = ms._sha256(addendum)
    assert ms.verify_addendum(addendum, good, repo)["committed"]
    with pytest.raises(ms.AddendumError, match="does not match"):
        ms.verify_addendum(addendum, "f" * 64, repo)
    other = repo / "other.md"
    other.write_text(_addendum_text())
    with pytest.raises(ms.AddendumError, match="not committed"):
        ms.verify_addendum(other, ms._sha256(other), repo)
    other.unlink()
    addendum.write_text(_addendum_text(temporal="W5"))
    with pytest.raises(ms.AddendumError, match="differs from the committed"):
        ms.verify_addendum(addendum, ms._sha256(addendum), repo)
    _git(repo, "checkout", "--", "addendum.md")
    (repo / "stray.txt").write_text("x")
    with pytest.raises(ms.AddendumError, match="not clean"):
        ms.verify_addendum(addendum, good, repo)
    with pytest.raises(ms.AddendumError):
        ms.outer_main(repo / "missing", repo / "out", addendum, good, None, repo=repo)
    assert not (repo / "out").exists()


def test_outer_refuses_a_development_manifest_mismatch(repo):
    addendum = repo / "addendum.md"
    manifest = repo / "dev.json"
    manifest.write_text("{}")
    _git(repo, "add", "dev.json")
    _git(repo, "commit", "-q", "-m", "dev")
    with pytest.raises(ms.AddendumError, match="development manifest"):
        ms.outer_main(
            repo / "missing", repo / "out", addendum, ms._sha256(addendum), manifest, repo=repo
        )


def test_scenarios_remove_the_declared_rows():
    rows = synthetic_rows((2018, 2021, 2022))
    names = {s.name: s.available for s in ms.scenario_masks(rows)}
    assert not names["exclude_2018_19"][rows.season == 2018].any()
    assert not names["exclude_2021_22"][rows.season == 2021].any()
    assert not names["exclude_overtime"][rows.period >= 5].any()
    assert not names["exclude_no_livedata"][rows.no_livedata].any()
    assert names["primary"].all()
