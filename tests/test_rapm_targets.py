"""Synthetic checks for the #28 RAPM training targets: guards, time, freezing and reliability."""

from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

pytest.importorskip("numpy")
pytest.importorskip("scipy")

import numpy as np  # noqa: E402

from bil.models.rapm import multiseason as ms  # noqa: E402
from bil.models.rapm import targets as tg  # noqa: E402

TEAMS = 6
ROSTER = 8


def synthetic(
    seasons: tuple[int, ...],
    *,
    seed: int = 11,
    step: int = 4,
    possessions: int = 40,
    shift: dict[int, float] | None = None,
    effects_sd: float = 4.0,
) -> tuple[ms.Rows, np.ndarray, dict[int, np.ndarray]]:
    """Six teams of eight players, a game every ``step`` days in each regular season and playoffs.

    Returns the rows, the (offense, defense) team codes and the true (offense, defense) effect of
    each player in points per 100. ``shift`` adds a season-level scoring change.
    """
    rng = np.random.default_rng(seed)
    rosters = np.arange(1, TEAMS * ROSTER + 1).reshape(TEAMS, ROSTER) * 10
    effects = {int(p): rng.normal(0, effects_sd, size=2) for p in rosters.ravel()}
    cols: dict[str, list] = {k: [] for k in ("season", "playoff", "day", "game", "seq", "period")}
    offense, defense, y, team_game, context, clubs = [], [], [], [], [], []
    game_ids: list[str] = []
    for season in seasons:
        days = [(d, False) for d in _days(date(season, 10, 20), date(season + 1, 4, 10), step)]
        days += [(d, True) for d in _days(date(season + 1, 4, 15), date(season + 1, 6, 10), step)]
        for day, playoff in days:
            home, away = rng.choice(TEAMS, size=2, replace=False)
            game = len(game_ids)
            game_ids.append(f"00{season}{game:06d}")
            for seq in range(possessions):
                off_team, def_team = (home, away) if seq % 2 == 0 else (away, home)
                off = rng.choice(rosters[off_team], size=5, replace=False)
                dfn = rng.choice(rosters[def_team], size=5, replace=False)
                rate = 110.0 + (shift or {}).get(season, 0.0)
                rate += sum(effects[int(p)][0] for p in off) - sum(effects[int(p)][1] for p in dfn)
                y.append(100.0 * rng.poisson(max(rate, 10.0) / 100.0))
                offense.append(off)
                defense.append(dfn)
                team_game.append(game * 2 + seq % 2)
                clubs.append((off_team, def_team))
                period = 1 + min(seq * 4 // possessions, 3)
                context.append(
                    [
                        1.0 if off_team == home else -1.0,
                        float(rng.integers(-20, 21)),
                        float(period == 2),
                        float(period == 3),
                        float(period == 4),
                        0.0,
                        float(seq % 10 == 9),
                        0.0,
                    ]
                )
                for key, value in zip(
                    cols, (season, playoff, day.toordinal(), game, seq, period), strict=True
                ):
                    cols[key].append(value)
    rows = ms.Rows(
        season=np.array(cols["season"], dtype=np.int64),
        playoff=np.array(cols["playoff"], dtype=bool),
        day=np.array(cols["day"], dtype=np.int64),
        game=np.array(cols["game"], dtype=np.int64),
        game_ids=tuple(game_ids),
        team_game=np.array(team_game, dtype=np.int64),
        possession_seq=np.array(cols["seq"], dtype=np.int64),
        period=np.array(cols["period"], dtype=np.int64),
        y=np.array(y, dtype=np.float64),
        offense=np.array(offense, dtype=np.int64),
        defense=np.array(defense, dtype=np.int64),
        context=np.array(context, dtype=np.float64),
        no_livedata=np.isin(np.array(cols["season"]), (2018, 2019)),
    )
    return rows, np.array(clubs, dtype=np.int64), effects


def _days(start: date, end: date, step: int) -> list[date]:
    return [start + timedelta(days=k) for k in range(0, (end - start).days, step)]


def calendar_of(rows: ms.Rows) -> dict[int, tuple[date, date]]:
    out = {}
    for s in np.unique(rows.season).tolist():
        days = rows.day[rows.season == s]
        out[int(s)] = (date.fromordinal(int(days.min())), date.fromordinal(int(days.max())))
    return out


def concat(a: ms.Rows, b: ms.Rows) -> ms.Rows:
    """Append ``b`` (with its games renumbered after ``a``'s)."""
    games = len(a.game_ids)
    return ms.Rows(
        season=np.concatenate([a.season, b.season]),
        playoff=np.concatenate([a.playoff, b.playoff]),
        day=np.concatenate([a.day, b.day]),
        game=np.concatenate([a.game, b.game + games]),
        game_ids=a.game_ids + b.game_ids,
        team_game=np.concatenate([a.team_game, b.team_game + 2 * games]),
        possession_seq=np.concatenate([a.possession_seq, b.possession_seq]),
        period=np.concatenate([a.period, b.period]),
        y=np.concatenate([a.y, b.y]),
        offense=np.concatenate([a.offense, b.offense]),
        defense=np.concatenate([a.defense, b.defense]),
        context=np.concatenate([a.context, b.context]),
        no_livedata=np.concatenate([a.no_livedata, b.no_livedata]),
    )


# --- guards ------------------------------------------------------------------------------------


@pytest.mark.parametrize("season", [2025, 2026, 2030])
def test_holdout_seasons_are_refused(season, tmp_path):
    with pytest.raises(ValueError, match="holdout"):
        tg.check_target_season(season)
    with pytest.raises(ValueError, match="holdout"):
        ms.load_season(tmp_path, season, range(2000, 2100), tmp_path, tg.TARGET_PINS)


@pytest.mark.parametrize("season", [2004, 2008, 2012, 2017, 2023, 2024])
def test_unauthorized_seasons_are_refused(season, tmp_path):
    with pytest.raises(ValueError, match="not an authorized"):
        tg.check_target_season(season)
    with pytest.raises(ValueError, match="not allowed|no pinned"):
        ms.load_season(tmp_path, season, tg.AUTHORIZED_SEASONS, tmp_path, tg.TARGET_PINS)


def test_pins_cover_exactly_the_authorized_seasons():
    assert set(tg.TARGET_PINS) == set(tg.AUTHORIZED_SEASONS)
    assert set(tg.VERIFICATION_GROUP) == set(tg.AUTHORIZED_SEASONS)
    assert tg.REFERENCES["contiguous"] == (2018, 2019, 2020, 2021, 2022)
    assert 2017 not in tg.REFERENCES["extended"]
    # The #26 pins keep their row set; the history seasons name their own.
    assert tg.TARGET_PINS[2018].row_set == ms.ROW_SET_VERSION == "issue-93-v1"
    assert tg.TARGET_PINS[2005].row_set == "issue-97-rows-v1"


def test_check_strata_refuses_repairs_and_group_mismatch():
    tg.check_strata(2020, {"_accepted_games": 10, "overtime": 2})
    tg.check_strata(2005, {"_accepted_games": 10, "no_livedata": 10, "no_datanba": 10})
    tg.check_strata(2016, {"_accepted_games": 10, "no_livedata": 10})
    with pytest.raises(ValueError, match="repaired"):
        tg.check_strata(2020, {"_accepted_games": 10, tg.REPAIRED_STRATUM: 1})
    with pytest.raises(ValueError, match="verification group"):
        tg.check_strata(2018, {"_accepted_games": 10, "no_livedata": 9})
    with pytest.raises(ValueError, match="verification group"):
        tg.check_strata(2015, {"_accepted_games": 10, "no_livedata": 10})


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_runner_refuses_without_committed_protocol_on_clean_tree(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    protocol = repo / "protocol.md"
    protocol.write_text("frozen\n")
    digest = ms._sha256(protocol)
    output = tmp_path / "out"
    with pytest.raises(tg.ProtocolError, match="not committed"):
        tg.main_run(tmp_path, output, protocol, digest, repo)
    _git(repo, "add", "protocol.md")
    _git(repo, "commit", "-qm", "protocol")
    with pytest.raises(tg.ProtocolError, match="does not match"):
        tg.main_run(tmp_path, output, protocol, "0" * 64, repo)
    with pytest.raises(tg.ProtocolError, match="requires"):
        tg.main_run(tmp_path, output, protocol, None, repo)
    (repo / "stray.txt").write_text("dirty")
    with pytest.raises(tg.ProtocolError, match="not clean"):
        tg.main_run(tmp_path, output, protocol, digest, repo)
    assert not output.exists()
    (repo / "stray.txt").unlink()
    assert tg.verify_protocol(protocol, digest, repo)["sha256"] == digest
    with pytest.raises(tg.ProtocolError, match="no run state"):
        tg.main_run(tmp_path, output, protocol, digest, repo, resume=True)


# --- time ----------------------------------------------------------------------------------------


def test_kernel_uses_real_elapsed_time_across_gaps():
    season = np.array([2007, 2015, 2015, 2016, 2016], dtype=np.int64)
    day = np.array(
        [
            date(2008, 6, 1),
            date(2015, 11, 1),
            date(2016, 6, 1),
            date(2016, 11, 1),
            date(2018, 6, 10),
        ]
    )
    ordinal = np.array([d.toordinal() for d in day], dtype=np.int64)
    spans = tg.season_spans(season, ordinal)
    w = tg.kernel_weights(season, ordinal, 2015, spans, tg.PRIMARY_KERNEL)
    gap = (date(2016, 11, 1) - date(2016, 6, 1)).days
    assert w[1] == w[2] == 1.0
    assert w[3] == pytest.approx(0.5 ** (gap / 365))
    assert w[4] == 0.0  # beyond the 730-day cap
    assert w[0] == 0.0  # 2007-08 is more than seven years away, not one season
    # Relabelling the seasons as adjacent integers changes nothing: only dates count.
    relabelled = np.array([2014, 2015, 2015, 2016, 2016], dtype=np.int64)
    spans2 = tg.season_spans(relabelled, ordinal)
    assert np.array_equal(
        tg.kernel_weights(relabelled, ordinal, 2015, spans2, tg.PRIMARY_KERNEL), w
    )
    # Two-sided: 2016-17 is weighted for a 2015-16 label once it is eligible.
    backward = tg.kernel_weights(season, ordinal, 2016, spans, tg.PRIMARY_KERNEL)
    assert backward[2] == pytest.approx(0.5 ** (gap / 365))
    k0 = tg.kernel_weights(season, ordinal, 2015, spans, tg.SEASON_ONLY_KERNEL)
    assert k0.tolist() == [0.0, 1.0, 1.0, 0.0, 0.0]


def test_overlapping_seasons_are_refused():
    season = np.array([2019, 2020], dtype=np.int64)
    day = np.array([date(2020, 10, 1).toordinal(), date(2020, 9, 1).toordinal()])
    with pytest.raises(ValueError, match="overlap"):
        tg.season_spans(season, day)


def _calendar() -> dict[int, tuple[date, date]]:
    out = {s: (date(s, 10, 25), date(s + 1, 6, 15)) for s in tg.AUTHORIZED_SEASONS}
    out[2019] = (date(2019, 10, 22), date(2020, 10, 11))  # the bubble
    out[2020] = (date(2020, 12, 22), date(2021, 7, 20))
    return out


def test_origins_close_each_eligible_season_and_mark_gaps_unavailable():
    origins = tg.origin_schedule("extended", _calendar())
    assert [o.closes_season for o in origins] == list(tg.AUTHORIZED_SEASONS)
    by = {o.closes_season: o.cutoff for o in origins}
    assert by[2019] == date(2020, 10, 12) and by[2020] == date(2021, 7, 21)
    assert by[2022] <= tg.DATA_END
    gaps = tg.unavailable_origins("extended")
    assert [g["season"] for g in gaps] == [2008, 2009, 2010, 2011, 2012, 2013, 2014, 2017]
    assert {g["season"]: g["latest_available_origin_closes"] for g in gaps}[2017] == 2016
    assert tg.unavailable_origins("contiguous") == []
    bad = _calendar()
    bad[2020] = (date(2020, 10, 1), date(2021, 7, 20))
    with pytest.raises(ValueError, match="inside the next season"):
        tg.origin_schedule("contiguous", bad)


def test_chronological_registration_trains_only_on_earlier_target_sets():
    reg = tg.chronological_registration(_calendar())
    for reference, entry in reg.items():
        seasons = tg.REFERENCES[reference]
        assert entry["first_season_unavailable"]["season"] == seasons[0]
        for fold in entry["folds"]:
            e = fold["evaluation_season"]
            assert all(s < e for s in fold["training_seasons"])
            cutoff = date.fromisoformat(fold["training_target_set"].split("@")[1])
            assert cutoff <= _calendar()[e][0]
            assert fold["evaluation_label_rows"] == f"season {e} only"
            assert "evaluation_K0" in fold["evaluation_label"]
    extended = {f["evaluation_season"]: f for f in reg["extended"]["folds"]}
    assert extended[2015]["training_seasons"] == [2005, 2006, 2007]
    assert extended[2018]["training_seasons"][-1] == 2016


def test_game_folds_are_deterministic_and_whole_games():
    ids = tuple(f"002{i:07d}" for i in range(200))
    a = tg.game_folds(ids)
    assert np.array_equal(a, tg.game_folds(ids))
    assert set(a.tolist()) == set(range(tg.CV_FOLDS))
    rows, teams, _ = synthetic((2018,), step=8)
    od = tg.origin_data(rows, teams, np.ones(len(rows), dtype=bool), [])
    for g in range(len(od.rows.game_ids)):
        assert np.unique(od.folds[od.rows.game == g]).size == 1


def test_team_codes_pair_the_two_offenses():
    game = np.array([0, 0, 0, 1, 1], dtype=np.int64)
    offense = np.array(["1610612737", "1610612738", "1610612737", "1610612760", "1610612737"])
    codes = tg.team_codes(offense, game)
    a, b, c = 1610612737, 1610612738, 1610612760
    assert codes.tolist() == [[a, b], [b, a], [a, b], [c, a], [a, c]]
    # Raw IDs: a game's codes do not depend on which other games are loaded.
    assert tg.team_codes(offense[3:], np.array([0, 0], dtype=np.int64)).tolist() == [[c, a], [a, c]]
    with pytest.raises(ValueError, match="only one"):
        tg.team_codes(np.array(["1", "1"]), np.array([0, 0], dtype=np.int64))


# --- freezing ------------------------------------------------------------------------------------


def _origin(rows: ms.Rows, closes: int) -> tg.Origin:
    last = int(rows.day[rows.season == closes].max())
    return tg.Origin("contiguous", closes, date.fromordinal(last + 1))


def test_later_rows_cannot_change_a_frozen_target():
    rows, teams, _ = synthetic((2018, 2019), step=8)
    later, later_teams, _ = synthetic((2020,), seed=99, step=8)
    later = replace(later, offense=later.offense + 1000, y=later.y * 3)  # new players, outcomes
    origin = _origin(rows, 2019)
    frozen, tables, _, _ = tg.build_target_set(rows, teams, origin, tg.PRIMARY_KERNEL, [])
    combined = concat(rows, later)
    combined_teams = np.concatenate([teams, later_teams])
    again, tables2, od2, _ = tg.build_target_set(
        combined, combined_teams, origin, tg.PRIMARY_KERNEL, []
    )
    assert again == frozen
    assert frozen.artifact_label == tg.ARTIFACT_LABEL == "partial-history methodology replication"
    for season in tables:
        for name in tg.LABEL_FIELDS:
            assert np.array_equal(tables[season][name], tables2[season][name])
    assert int(od2.rows.day.max()) < origin.cutoff.toordinal()
    tg.verify_frozen(frozen, combined, combined_teams)
    # Reordering the rows changes nothing either.
    order = np.random.default_rng(3).permutation(len(combined))
    shuffled = tg.subset_rows(combined, np.ones(len(combined), dtype=bool))
    shuffled = replace(
        shuffled,
        **{
            name: getattr(shuffled, name)[order]
            for name in (
                "season playoff day game team_game possession_seq period y offense defense "
                "context no_livedata"
            ).split()
        },
    )
    tg.verify_frozen(frozen, shuffled, combined_teams[order])


def test_a_revised_earlier_row_is_detected_and_needs_a_new_version():
    rows, teams, _ = synthetic((2018, 2019), step=8)
    origin = _origin(rows, 2019)
    frozen, _, _, _ = tg.build_target_set(rows, teams, origin, tg.PRIMARY_KERNEL, [])
    for field_name, revise in (
        ("y", lambda r: np.where(np.arange(len(r)) == 5, r.y + 100.0, r.y)),
        ("context", lambda r: np.where(np.arange(len(r))[:, None] == 7, r.context * 2, r.context)),
    ):
        revised = replace(rows, **{field_name: revise(rows)})
        with pytest.raises(tg.FrozenTargetError, match="new target version"):
            tg.verify_frozen(frozen, revised, teams)
        new, _, _, _ = tg.build_target_set(
            revised, teams, origin, tg.PRIMARY_KERNEL, [], penalties=(500.0, 1000.0), scenario="x"
        )
        assert new.input_digest != frozen.input_digest


def test_sensitivity_fits_are_never_frozen_targets():
    rows, teams, _ = synthetic((2018,), step=8)
    origin = _origin(rows, 2018)
    for kwargs in (
        {"kernel": tg.POOLED_KERNEL},
        {"kernel": tg.PRIMARY_KERNEL, "penalties": (1.0, 1.0)},
        {"kernel": tg.PRIMARY_KERNEL, "offset_mode": "two_stage"},
        {"kernel": tg.PRIMARY_KERNEL, "available": ~rows.playoff},
    ):
        with pytest.raises(ValueError, match="must name its scenario"):
            tg.build_target_set(rows, teams, origin, log=[], **kwargs)
    record, _, _, _ = tg.build_target_set(
        rows, teams, origin, tg.POOLED_KERNEL, [], penalties=(1.0, 1.0), scenario="pooled"
    )
    with pytest.raises(tg.FrozenTargetError, match="only primary"):
        tg.verify_frozen(record, rows, teams)


# --- estimation ----------------------------------------------------------------------------------


def test_cross_validation_never_fits_a_held_out_game():
    rows, teams, _ = synthetic((2018, 2019), step=8)
    od = tg.origin_data(rows, teams, np.ones(len(rows), dtype=bool), [])
    value = tg.cv_mse(od, tg.PRIMARY_KERNEL, 1000.0, 2000.0)
    assert np.isfinite(value) and value > 0
    cv_fits = [e for e in od.log if e["note"].startswith("cv")]
    assert len(cv_fits) == 2 * tg.CV_FOLDS
    for k in range(tg.CV_FOLDS):
        fit = tg.fit_season(od, 2018, tg.PRIMARY_KERNEL, 1000.0, 2000.0, keep=od.folds != k)
        assert not np.any(od.folds[fit.index] == k)


def test_offense_and_defense_labels_recover_separate_effects():
    rows, teams, effects = synthetic((2018,), step=1, possessions=60, seed=5, effects_sd=6.0)
    od = tg.origin_data(rows, teams, np.ones(len(rows), dtype=bool), [])
    fit = tg.fit_season(od, 2018, tg.PRIMARY_KERNEL, 200.0, 200.0)
    table = tg.labels(od, fit)
    true_off = np.array([effects[int(p)][0] for p in table["player_id"]])
    true_def = np.array([effects[int(p)][1] for p in table["player_id"]])
    # Positive offense scores more; positive defense prevents points.
    assert np.corrcoef(table["offense"], true_off)[0, 1] > 0.8
    assert np.corrcoef(table["defense"], true_def)[0, 1] > 0.8
    assert abs(np.corrcoef(table["offense"], true_def)[0, 1]) < 0.4
    assert np.allclose(table["total"], table["offense"] + table["defense"])
    for role in ("offense", "defense"):
        mean = np.average(table[role], weights=table[f"{role}_possessions"])
        assert abs(mean) < 1e-9


def test_season_levels_absorb_an_era_scoring_shift():
    rows, teams, _ = synthetic((2018, 2019), step=1, possessions=60, shift={2019: 10.0}, seed=8)
    od = tg.origin_data(rows, teams, np.ones(len(rows), dtype=bool), [])
    fit = tg.fit_season(od, 2018, tg.PRIMARY_KERNEL, 1000.0, 1000.0)
    effects = dict(zip(fit.offset.levels[1:], fit.offset.level_effects, strict=True))

    # The 2019 regular-season level carries the +10 shift (fitted jointly with the players),
    # so the shift cannot load onto the players of one season.
    assert effects[2019 * 2] == pytest.approx(10.0, abs=2.5)
    # The labels of the target season are centred whatever the level of a neighbouring season.
    table = tg.labels(od, fit)
    assert abs(np.average(table["offense"], weights=table["offense_possessions"])) < 1e-9


def test_split_halves_share_no_game():
    rows, teams, _ = synthetic((2018, 2019), step=4)
    od = tg.origin_data(rows, teams, np.ones(len(rows), dtype=bool), [])
    first, second = ms.split_halves(od.rows, np.arange(len(od.rows), dtype=np.int64))
    assert not np.any(first & second) and np.all(first | second)
    assert not set(od.rows.game[first].tolist()) & set(od.rows.game[second].tolist())
    pairs = tg.split_half_reliability(od, tg.PRIMARY_KERNEL, (500.0, 1000.0))
    assert set(pairs) == {2018, 2019}
    assert all(p.first.size == p.second.size for r in pairs.values() for p in r.values())


def test_input_digest_ignores_row_order_but_not_content():
    rows, teams, _ = synthetic((2018,), step=16)
    digest = tg.input_digest(rows, teams)
    flipped = replace(rows, game_ids=rows.game_ids)  # same object content
    assert tg.input_digest(flipped, teams) == digest
    swapped = teams[:, ::-1].copy()
    assert tg.input_digest(rows, swapped) != digest


def test_run_reference_end_to_end_on_synthetic_seasons():
    rows, teams, _ = synthetic(tg.REFERENCES["contiguous"], step=12, possessions=30, seed=21)
    log: list[dict] = []
    result = tg.run_reference(
        rows,
        teams,
        "contiguous",
        calendar_of(rows),
        log,
        bootstrap_replicates=3,
        provenance={"code_commit": "c" * 40, "protocol_sha256": "p" * 64},
    )
    assert all(f.code_commit == "c" * 40 and f.protocol_sha256 == "p" * 64 for f in result.frozen)
    summary = result.summary
    assert summary["artifact_label"] == tg.ARTIFACT_LABEL
    assert len(result.frozen) == 5
    assert [f.closes_season for f in result.frozen] == list(tg.REFERENCES["contiguous"])
    for f in result.frozen:
        tg.verify_frozen(f, rows, teams)
        assert max(f.seasons) == f.closes_season
    # Labels at an origin only exist for seasons it closes or earlier.
    for key, by_season in result.tables.items():
        cutoff = date.fromisoformat(key.split("@")[1])
        assert all(calendar_of(rows)[s][1] < cutoff for s in by_season)
    # The first season's label at its own origin is one-sided; at the final origin it is not.
    first_key = result.frozen[0].cutoff
    assert summary["origins"][f"contiguous@{first_key}"]["fits"]["2018"]["forward_support"] is False
    final = summary["origins"][summary["final_origin"]]["fits"]
    assert final["2018"]["forward_support"] is True
    assert final["2022"]["forward_support"] is False
    # Evaluation labels use only their own season's rows, with their own CV penalties.
    evaluation = summary["evaluation_labels"]
    assert evaluation["scenario"] == "evaluation_K0" and evaluation["cv_mse"]
    assert set(result.eval_tables) == set(tg.REFERENCES["contiguous"])
    for season, table in result.eval_tables.items():
        assert set(table["kernel_seasons"].tolist()) == {str(season)}
        assert not table["forward_support"].any()
    assert set(evaluation["year_to_year"]) == {
        "2018->2019",
        "2019->2020",
        "2020->2021",
        "2021->2022",
    }
    # Revisions are reported as frozen and under the final penalties.
    assert set(summary["label_revision_vs_final"]) == set(
        summary["label_revision_vs_final_fixed_penalties"]
    )
    final_tables = result.tables[summary["final_origin"]]
    assert final_tables[2018]["forward_support"].all()
    assert set(final_tables[2018]["kernel_seasons"].tolist()) == {"2018;2019;2020"}
    assert set(summary["sensitivity"]) == {
        "K730",
        "regular_only",
        "pooled_window",
        "exclude_no_livedata",
        "two_stage_offset",
    }
    assert summary["sensitivity"]["two_stage_offset"]["offset_mode"] == "two_stage"
    assert all(f.offset_mode == "joint" and f.fold_salt == tg.FOLD_SALT for f in result.frozen)
    assert summary["sensitivity"]["exclude_no_livedata"]["seasons"] == [2020, 2021, 2022]
    assert set(result.errors) == set(tg.REFERENCES["contiguous"])
    assert "offense|all" in summary["split_half"] and "defense|all" in summary["split_half"]
    assert ms._solver_summary([{**e, "temporal": e["kernel"]} for e in log])["all_converged"]


# --- joint context fit ---------------------------------------------------------------------------


def _dense_joint(rows, index, weights, unpenalized, offense_ridge, defense_ridge):
    """Independent oracle: dense normal equations over [1, C, offense, -defense]."""
    ids = np.unique(np.concatenate([rows.offense[index].ravel(), rows.defense[index].ravel()]))
    m = ids.size
    x = np.zeros((index.size, 2 * m))
    for row, i in enumerate(index):
        x[row, np.searchsorted(ids, rows.offense[i])] = 1.0
        x[row, m + np.searchsorted(ids, rows.defense[i])] = -1.0
    full = np.column_stack([np.ones(index.size), unpenalized, x])
    k = 1 + unpenalized.shape[1]
    penalty = np.concatenate([np.zeros(k), np.full(m, offense_ridge), np.full(m, defense_ridge)])
    lhs = full.T @ (weights[:, None] * full) + np.diag(penalty)
    theta = np.linalg.solve(lhs, full.T @ (weights * rows.y[index]))
    return ids, theta[0], theta[1:k], theta[k : k + m], theta[k + m :]


def test_joint_fit_matches_a_dense_oracle():
    rows, teams, _ = synthetic((2018, 2019), step=8, possessions=30, seed=4)
    od = tg.origin_data(rows, teams, np.ones(len(rows), dtype=bool), [])
    weights = od.kernel(2018, tg.PRIMARY_KERNEL)
    index = np.flatnonzero(weights > 0)
    w = weights[index]
    levels, dummies = tg.level_columns(od.level[index])
    unpenalized = np.column_stack([od.rows.context[index], dummies])
    unpenalized = unpenalized[:, np.any(unpenalized != 0, axis=0)]
    for ridges in ((300.0, 600.0), (2000.0, 500.0), (50.0, 50.0)):
        fit, gamma = tg.fit_joint(od.design, index, od.rows.y[index], w, unpenalized, *ridges)
        ids, intercept, g, off, dfn = _dense_joint(od.rows, index, w, unpenalized, *ridges)
        position = np.searchsorted(np.asarray(od.design.player_ids), ids)
        m = od.design.size
        assert fit.intercept == pytest.approx(intercept, abs=1e-7)
        assert np.allclose(gamma, g, atol=1e-7)
        assert np.allclose(fit.effects[:m][position], off, atol=1e-7)
        assert np.allclose(fit.effects[m:][position], dfn, atol=1e-7)
        delta = max(
            abs(fit.intercept - intercept),
            float(np.max(np.abs(gamma - g))),
            float(np.max(np.abs(fit.effects[:m][position] - off))),
            float(np.max(np.abs(fit.effects[m:][position] - dfn))),
        )
        assert delta < 1e-7
    # Through fit_season the same columns (levels included) give the same answer.
    season_fit = tg.fit_season(od, 2018, tg.PRIMARY_KERNEL, 300.0, 600.0)
    oracle = _dense_joint(od.rows, index, w, unpenalized, 300.0, 600.0)
    assert season_fit.players.intercept == pytest.approx(oracle[1], abs=1e-7)


def test_joint_fit_keeps_player_quality_out_of_correlated_context():
    rows, teams, effects = synthetic((2018,), step=1, possessions=60, seed=12, effects_sd=6.0)
    # A context flag that is on when the offensive lineup is strong (like "leading" or "closing
    # lineup"). Its true effect is zero, so a coefficient on it is borrowed player quality.
    quality = np.array([sum(effects[int(p)][0] for p in lineup) for lineup in rows.offense])
    context = rows.context.copy()
    context[:, 7] = (quality > np.median(quality)).astype(float)
    rows = replace(rows, context=context)
    coefficient, accuracy = {}, {}
    for mode in ("joint", "two_stage"):
        od = tg.origin_data(rows, teams, np.ones(len(rows), dtype=bool), [], offset_mode=mode)
        fit = tg.fit_season(od, 2018, tg.PRIMARY_KERNEL, 200.0, 200.0)
        table = tg.labels(od, fit)
        truth = np.array([effects[int(p)][0] for p in table["player_id"]])
        coefficient[mode] = abs(float(fit.offset.context[7]))
        accuracy[mode] = float(np.corrcoef(table["offense"], truth)[0, 1])
    assert coefficient["joint"] < coefficient["two_stage"] / 2
    assert accuracy["joint"] > accuracy["two_stage"] + 0.1


# --- protocol §10: failures are recorded, never fatal; checkpoints resume identically -----------


def _contiguous_rows():
    return synthetic(tg.REFERENCES["contiguous"], step=12, possessions=30, seed=21)


def test_a_failed_fit_marks_its_stage_unavailable_and_the_run_continues(monkeypatch):
    rows, teams, _ = _contiguous_rows()
    calendar = calendar_of(rows)
    second = tg.origin_schedule("contiguous", calendar)[1]
    real_select = tg.select_penalties
    real_fit = tg.fit_season

    def select(od, kernel):
        if od.label == second.key and kernel == tg.PRIMARY_KERNEL:
            raise ValueError("unpenalized columns are collinear with each other or the intercept")
        return real_select(od, kernel)

    def fit(od, target, *args, **kwargs):
        note = kwargs.get("note", "")
        if note == "boot1" or (note == "half2" and target == 2020):
            raise np.linalg.LinAlgError("singular")
        return real_fit(od, target, *args, **kwargs)

    monkeypatch.setattr(tg, "select_penalties", select)
    monkeypatch.setattr(tg, "fit_season", fit)
    result = tg.run_reference(rows, teams, "contiguous", calendar, [], bootstrap_replicates=3)
    summary = result.summary
    assert [f["origin"] for f in summary["failed_origins"]] == [second.key]
    assert "collinear" in summary["failed_origins"][0]["reason"]
    assert second.key not in result.tables and len(result.frozen) == 4
    stages = {f["stage"] for f in summary["failures"]}
    assert f"contiguous/origin/{second.key}" in stages
    assert "contiguous/split_half/2020" in stages
    assert summary["split_half_seasons"] == [2018, 2019, 2021, 2022]
    for season in tg.REFERENCES["contiguous"]:
        boot = summary["bootstrap"][str(season)]
        assert len(boot["failed_replicates"]) == 1 and "replicate 1" in boot["failed_replicates"][0]
        assert boot["min_replicates_with_label"] <= 2
    # Nothing is substituted for the failed origin, and the later analyses still ran.
    assert not any(
        k.endswith(second.cutoff.isoformat()) for k in summary["label_revision_vs_final"]
    )
    assert summary["evaluation_labels"]["cv_mse"] and summary["sensitivity"]


def test_a_failed_final_origin_leaves_the_final_analyses_unavailable(monkeypatch):
    rows, teams, _ = _contiguous_rows()
    calendar = calendar_of(rows)
    final = tg.origin_schedule("contiguous", calendar)[-1]
    real_select = tg.select_penalties

    def select(od, kernel):
        if od.label == final.key:
            raise RuntimeError("joint RAPM solve is not finite")
        return real_select(od, kernel)

    monkeypatch.setattr(tg, "select_penalties", select)
    result = tg.run_reference(rows, teams, "contiguous", calendar, [], bootstrap_replicates=2)
    assert result.summary["final_analyses"].startswith("unavailable")
    assert len(result.frozen) == 4 and not result.eval_tables and not result.errors


def test_leakage_guards_are_never_swallowed(monkeypatch):
    rows, teams, _ = _contiguous_rows()

    def broken(*args, **kwargs):
        raise AssertionError("a fit row is not strictly before its cutoff")

    monkeypatch.setattr(tg, "select_penalties", broken)
    with pytest.raises(AssertionError, match="strictly before"):
        tg.run_reference(rows, teams, "contiguous", calendar_of(rows), [], bootstrap_replicates=2)


def _dump(result):
    return json.dumps(result.summary, sort_keys=True, default=repr)


def test_resumed_checkpoints_reproduce_the_run_exactly(tmp_path, monkeypatch):
    rows, teams, _ = _contiguous_rows()
    calendar = calendar_of(rows)
    first_log: list[dict] = []
    first = tg.run_reference(
        rows,
        teams,
        "contiguous",
        calendar,
        first_log,
        bootstrap_replicates=2,
        checkpoints=tg.Checkpoints(tmp_path / "checkpoints", first_log),
    )
    progress = (tmp_path / "progress.jsonl").read_text().splitlines()
    assert progress and all(json.loads(line)["status"] == "computed" for line in progress)
    # Simulate an interruption: drop some stages, then resume. Completed stages are reloaded
    # (fits are not repeated) and the dropped ones recomputed to the same values.
    files = sorted((tmp_path / "checkpoints").glob("*.pkl"))
    for path in files[::3]:
        path.unlink()
    resumed_log: list[dict] = []
    resumed = tg.run_reference(
        rows,
        teams,
        "contiguous",
        calendar,
        resumed_log,
        bootstrap_replicates=2,
        checkpoints=tg.Checkpoints(tmp_path / "checkpoints", resumed_log),
    )
    assert _dump(resumed) == _dump(first)
    assert [f.label_digests for f in resumed.frozen] == [f.label_digests for f in first.frozen]
    assert len(resumed_log) == len(first_log)
    statuses = {
        json.loads(line)["status"]
        for line in (tmp_path / "progress.jsonl").read_text().splitlines()
    }
    assert statuses == {"computed", "resumed"}

    # With every stage checkpointed, a resume performs no fit at all.
    def no_fit(*args, **kwargs):
        raise AssertionError("a resumed stage was refitted")

    monkeypatch.setattr(tg, "fit_joint", no_fit)
    again_log: list[dict] = []
    again = tg.run_reference(
        rows,
        teams,
        "contiguous",
        calendar,
        again_log,
        bootstrap_replicates=2,
        checkpoints=tg.Checkpoints(tmp_path / "checkpoints", again_log),
    )
    assert _dump(again) == _dump(first)
