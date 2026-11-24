"""Synthetic checks for the #28 RAPM training targets: guards, time, freezing and reliability."""

from __future__ import annotations

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
    k0 = tg.kernel_weights(season, ordinal, 2015, spans, tg.SENSITIVITY_KERNELS[0])
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
            assert fold["evaluation_rows_from"] == cutoff.isoformat()
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
    offense = np.array(["A", "B", "A", "C", "A"])
    codes = tg.team_codes(offense, game)
    assert codes.tolist() == [[0, 1], [1, 0], [0, 1], [2, 0], [0, 2]]
    with pytest.raises(ValueError, match="only one"):
        tg.team_codes(np.array(["A", "A"]), np.array([0, 0], dtype=np.int64))


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
    frozen, _, _, _ = tg.build_target_set(
        rows, teams, origin, tg.PRIMARY_KERNEL, [], penalties=(500.0, 1000.0)
    )
    for field_name, revise in (
        ("y", lambda r: np.where(np.arange(len(r)) == 5, r.y + 100.0, r.y)),
        ("context", lambda r: np.where(np.arange(len(r))[:, None] == 7, r.context * 2, r.context)),
    ):
        revised = replace(rows, **{field_name: revise(rows)})
        with pytest.raises(tg.FrozenTargetError, match="new target version"):
            tg.verify_frozen(frozen, revised, teams)
        new, _, _, _ = tg.build_target_set(
            revised, teams, origin, tg.PRIMARY_KERNEL, [], penalties=(500.0, 1000.0)
        )
        assert new.input_digest != frozen.input_digest


def test_sensitivity_fits_are_never_frozen_targets():
    rows, teams, _ = synthetic((2018,), step=8)
    origin = _origin(rows, 2018)
    with pytest.raises(ValueError, match="sensitivity scenario"):
        tg.build_target_set(rows, teams, origin, tg.POOLED_KERNEL, [], penalties=(1.0, 1.0))
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

    def mean(season: int, playoff: bool) -> float:
        return float(rows.y[(rows.season == season) & (rows.playoff == playoff)].mean())

    # Each season-type level carries its own scoring baseline (here the +10 shift plus the
    # sampled schedule), so the shift cannot load onto the players of one season.
    assert effects[2019 * 2] == pytest.approx(mean(2019, False) - mean(2018, False), abs=0.5)
    assert effects[2019 * 2] == pytest.approx(10.0, abs=4.0)
    assert effects[2018 * 2 + 1] == pytest.approx(mean(2018, True) - mean(2018, False), abs=0.5)
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
        rows, teams, "contiguous", calendar_of(rows), log, bootstrap_replicates=3
    )
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
    # Evaluation labels never read a row before their training origin.
    for season, meta in summary["evaluation_labels"].items():
        assert min(meta["kernel_seasons"]) == int(season)
    assert set(summary["sensitivity"]) == {
        "K0",
        "K730",
        "regular_only",
        "pooled_window",
        "exclude_no_livedata",
    }
    assert summary["sensitivity"]["exclude_no_livedata"]["seasons"] == [2020, 2021, 2022]
    assert set(result.errors) == set(tg.REFERENCES["contiguous"])
    assert "offense|all" in summary["split_half"] and "defense|all" in summary["split_half"]
    assert ms._solver_summary([{**e, "temporal": e["kernel"]} for e in log])["all_converged"]
