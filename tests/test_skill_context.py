"""Synthetic checks for context inputs, adjustment fits and the as-of snapshot (issue #33)."""

from __future__ import annotations

from datetime import date, timedelta

import duckdb
import numpy as np
import pytest

from bil.features.box import FEATURE_CODES, FEATURES, Appearance, aggregate
from bil.features.skill_context import (
    FACTOR_COLUMNS,
    FACTORS,
    OPP_K_TEAM_GAMES,
    REFERENCES,
    UNKNOWN_REST_DAYS,
    VARIANTS,
    TeamGame,
    build_context,
    fit_adjustment,
    input_columns,
    inverse_link,
    link_values,
    schedule_inputs,
)
from bil.features.skill_context_build import (
    adjust_block,
    base_fit,
    evaluate,
    fit_rows_for,
    write_tables,
)
from bil.features.skill_decay import (
    OUTER_BLOCKS,
    DESettings,
    assemble,
    predict,
    rows_in,
)
from bil.features.skill_decay_build import fit_all, select_clocks
from bil.features.skill_snapshot import SkillParams, skill_snapshot

SMALL = DESettings(popsize=6, maxiter=15, polish=False)
FEATURE = {f.code: f for f in FEATURES}


def _appearance(
    game: str, day: date, player: str, team: str, opp: str, rng: np.random.Generator
) -> Appearance:
    minutes = float(rng.uniform(4, 40))
    fga = int(rng.integers(0, 20))
    fg3a = int(rng.integers(0, fga + 1))
    fta = int(rng.integers(0, 8))
    return Appearance.from_record(
        {
            "game_id": game,
            "player_id": player,
            "team_id": team,
            "opp_team_id": opp,
            "game_date": day,
            "min": minutes,
            "fgm": int(rng.integers(0, fga + 1)) if fga else 0,
            "fga": fga,
            "fg3m": int(rng.integers(0, fg3a + 1)) if fg3a else 0,
            "fg3a": fg3a,
            "ftm": int(rng.integers(0, fta + 1)) if fta else 0,
            "fta": fta,
            "pts": 0,
            "oreb": int(rng.integers(0, 4)),
            "dreb": int(rng.integers(0, 8)),
            "ast": int(rng.integers(0, 9)),
            "tov": int(rng.integers(0, 5)),
            "stl": int(rng.integers(0, 3)),
            "blk": int(rng.integers(0, 3)),
            "pf": int(rng.integers(0, 6)),
        }
    )


def season(seed: int = 7, step: int = 4) -> list[Appearance]:
    """Four teams, three players each, a layoff and a short playoff run."""
    rng = np.random.default_rng(seed)
    rows: list[Appearance] = []
    number = 0
    day = date(2022, 10, 18)
    while day < date(2023, 4, 10):
        for team, opp in (("1", "2"), ("3", "4")):
            number += 1
            game = f"00222{number:05d}"
            for side, other in ((team, opp), (opp, team)):
                for slot in range(3):
                    player = f"{side}{slot}"
                    if player == "10" and date(2022, 12, 20) <= day < date(2023, 1, 25):
                        continue
                    if player == "32" and day < date(2023, 1, 10):
                        continue
                    rows.append(_appearance(game, day, player, side, other, rng))
        day += timedelta(days=step)
    for i in range(4):
        game = f"00422{i:05d}"
        played = date(2023, 4, 16) + timedelta(days=2 * i)
        for side, other in (("1", "2"), ("2", "1")):
            for slot in range(3):
                rows.append(_appearance(game, played, f"{side}{slot}", side, other, rng))
    return rows


def team_games_of(rows: list[Appearance]) -> list[TeamGame]:
    """Home is the team with the lower id in each synthetic game."""
    seen: dict[str, dict[str, Appearance]] = {}
    for r in rows:
        seen.setdefault(r.game_id, {}).setdefault(r.team_id, r)
    games = []
    for game_id, teams in seen.items():
        home = min(teams)
        for team_id, r in teams.items():
            games.append(TeamGame(game_id, team_id, r.opp_team_id, r.game_date, team_id == home))
    return games


def test_rest_and_back_to_back_from_schedule_only() -> None:
    days = [date(2022, 11, 1), date(2022, 11, 2), date(2022, 11, 5), date(2022, 11, 20)]
    games = [TeamGame(f"g{i}", "A", "B", d, i % 2 == 0) for i, d in enumerate(days)]
    out = schedule_inputs(games)
    first, b2b, three, long = (out[(f"g{i}", "A")] for i in range(4))
    assert not first.rest_known and not first.b2b and first.rest_days == UNKNOWN_REST_DAYS
    assert first.previous_game is None
    assert b2b.b2b and b2b.rest_days == 0 and b2b.previous_game == days[0]
    assert not three.b2b and three.rest_days == 2
    assert long.rest_days == 4  # capped
    assert [out[(f"g{i}", "A")].home for i in range(4)] == [True, False, True, False]
    # Input order does not matter, and a later game never changes an earlier row.
    assert schedule_inputs(games[::-1]) == out
    assert schedule_inputs(games[:2])[("g1", "A")] == out[("g1", "A")]
    with pytest.raises(ValueError, match="two games"):
        schedule_inputs([*games, TeamGame("dup", "A", "B", days[1], True)])


def _tiny() -> tuple[list[Appearance], list[TeamGame]]:
    """Three dates, teams A, B and C with one player each."""

    def row(game: str, day: date, player: str, team: str, opp: str, ast: int) -> Appearance:
        return Appearance.from_record(
            {
                "game_id": game,
                "player_id": player,
                "team_id": team,
                "opp_team_id": opp,
                "game_date": day,
                "min": 36.0,
                "ast": ast,
                "fga": 10,
                "fgm": 5,
                "fg3a": 2,
                "fg3m": 1,
                "fta": 2,
                "ftm": 1,
                "oreb": 1,
                "dreb": 1,
                "tov": 1,
                "stl": 1,
                "blk": 1,
                "pf": 1,
                "pts": 11,
            }
        )

    d1, d2, d3 = date(2023, 1, 1), date(2023, 1, 3), date(2023, 1, 4)
    rows = [
        row("0022200001", d1, "pa", "A", "B", 6),
        row("0022200001", d1, "pb", "B", "A", 2),
        row("0022200002", d2, "pb", "B", "C", 4),
        row("0022200002", d2, "pc", "C", "B", 8),
        row("0022200003", d3, "pa", "A", "C", 0),
        row("0022200003", d3, "pc", "C", "A", 0),
    ]
    games = [
        TeamGame("0022200001", "A", "B", d1, True),
        TeamGame("0022200001", "B", "A", d1, False),
        TeamGame("0022200002", "B", "C", d2, True),
        TeamGame("0022200002", "C", "B", d2, False),
        TeamGame("0022200003", "A", "C", d3, True),
        TeamGame("0022200003", "C", "A", d3, False),
    ]
    return rows, games


def test_opponent_allowed_rate_uses_strictly_earlier_games() -> None:
    rows, games = _tiny()
    keys = [r.key for r in rows]
    inputs = build_context(rows, games, keys)
    i = keys.index(
        "0022200003:pa"
    )  # A hosts C on day 3. C's only earlier game is g2, where B made 4 ast.
    # League before day 3: g1 (6 + 2 ast) and g2 (4 + 8 ast) over four 36-minute units.
    league_n, league_d, team_games = 20.0, 4.0, 4
    m = league_n / league_d
    k = OPP_K_TEAM_GAMES * league_d / team_games
    allowed = (4.0 + k * m) / (1.0 + k)
    assert inputs.opp["ast_per_36"][i] == pytest.approx(np.log(allowed) - np.log(m))
    # Team context for A: its own earlier game g1 (6 ast).
    team = (6.0 + k * m) / (1.0 + k)
    assert inputs.team["ast_per_36"][i] == pytest.approx(np.log(team) - np.log(m))
    # The first date has no earlier evidence: inputs default to zero and no source is recorded.
    j = keys.index("0022200001:pa")
    assert inputs.opp["ast_per_36"][j] == 0.0 and inputs.team["ast_per_36"][j] == 0.0
    assert inputs.trend["ast_per_36"][j] == 0.0
    assert inputs.latest_source()[j] == 0
    assert inputs.latest_source()[i] == date(2023, 1, 3).toordinal()
    assert inputs.cutoff_violations() == 0


def test_league_trend_window_covering_all_history_is_zero() -> None:
    rows, games = _tiny()
    keys = [r.key for r in rows]
    inputs = build_context(rows, games, keys)
    assert inputs.trend["ast_per_36"][keys.index("0022200003:pa")] == 0.0


def test_later_games_cannot_move_earlier_inputs() -> None:
    rows = season()
    games = team_games_of(rows)
    cut = date(2023, 2, 15)
    earlier_keys = [r.key for r in rows if r.game_date < cut]
    full = build_context(rows, games, earlier_keys)
    truncated = build_context(
        [r for r in rows if r.game_date < cut],
        [g for g in games if g.game_date < cut],
        earlier_keys,
    )
    assert full.cutoff_violations() == 0
    for name in ("home", "b2b", "rest_days", "league_source", "opp_source", "team_source"):
        np.testing.assert_array_equal(getattr(full, name), getattr(truncated, name))
    for code in FEATURE_CODES:
        for family in ("opp", "team", "trend"):
            np.testing.assert_allclose(
                getattr(full, family)[code], getattr(truncated, family)[code], atol=1e-12
            )
    rng = np.random.default_rng(99)
    rewritten = [
        _appearance(r.game_id, r.game_date, r.player_id, r.team_id, r.opp_team_id, rng)
        if r.game_date >= cut
        else r
        for r in rows
    ]
    again = build_context(rewritten, games, earlier_keys)
    for code in FEATURE_CODES:
        for family in ("opp", "team", "trend"):
            np.testing.assert_allclose(
                getattr(full, family)[code], getattr(again, family)[code], atol=1e-12
            )


def test_cutoff_violation_is_detected() -> None:
    rows, games = _tiny()
    inputs = build_context(rows, games, [r.key for r in rows])
    inputs.opp_source[0] = inputs.played[0]
    assert inputs.cutoff_violations() == 1


@pytest.mark.parametrize("code", ["ast_per_36", "fg3_pct"])
def test_adjustment_recovers_planted_effect_and_null(code: str) -> None:
    feature = FEATURE[code]
    rng = np.random.default_rng(3)
    n = 40_000
    home = (rng.random(n) < 0.5).astype(np.float64)
    base = np.full(n, 0.35 if feature.scale == 1 else 5.0)
    offset = link_values(feature, base)
    effect = 0.2
    truth = inverse_link(feature, offset + effect * (home - 0.5))
    exposure = np.full(n, 8.0 if feature.scale == 1 else 1.0)
    numerator = (
        rng.binomial(8, truth).astype(np.float64)
        if feature.scale == 1
        else rng.poisson(truth * exposure).astype(np.float64)
    )
    columns = {"home": home, "opp": rng.normal(size=n)}
    rows = np.arange(n)
    fitted = fit_adjustment(feature, ("home", "opp"), columns, rows, offset, numerator, exposure)
    beta = dict(zip(fitted.terms, fitted.beta, strict=True))
    assert beta["home"] == pytest.approx(effect * float(home.std()), abs=0.03)
    assert abs(beta["opp"]) < 0.02
    assert fitted.success
    flat = fit_adjustment(
        feature, ("opp",), {"opp": np.zeros(n)}, rows, offset, numerator, exposure
    )
    assert flat.terms == ()


def test_variant_tables_are_consistent() -> None:
    assert set(REFERENCES) == set(VARIANTS) - {"agnostic"}
    assert set(FACTOR_COLUMNS) == set(FACTORS)
    assert VARIANTS["full"] == FACTORS
    for factor in FACTORS:
        assert set(VARIANTS[f"drop_{factor}"]) == set(FACTORS) - {factor}


@pytest.fixture(scope="module")
def built():  # type: ignore[no-untyped-def]
    rows = season()
    panel, appearances, tables, _, _ = assemble(rows)
    inputs = build_context(rows, team_games_of(rows), appearances.keys)
    subset = {c: tables[c] for c in ("fg3_pct", "stl_per_36")}
    fits = fit_all(panel, appearances, subset, SMALL)
    selections = select_clocks(panel, appearances, subset, fits)
    chosen = {(s["outer_block"], s["feature_code"]): s["selected_clock"] for s in selections}
    return rows, panel, appearances, subset, inputs, fits, chosen


def test_end_to_end_variants_scores_and_cold_rows(built, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _, panel, appearances, subset, inputs, fits, chosen = built
    out = evaluate(panel, appearances, subset, inputs, fits, chosen, replicates=40)
    assert out["predictions"] and out["coefficients"]
    names = {f"pred_{v}" for v in VARIANTS}
    for r in out["predictions"]:
        assert names <= set(r)
        assert all(r[n] is not None and np.isfinite(r[n]) for n in names)
        assert r["outer_block"] in OUTER_BLOCKS
    assert any(r["covered_games"] == 0 for r in out["predictions"])
    deltas = [
        s
        for s in out["scores"]
        if s["block"] == "pooled"
        and s["variant"] == "full"
        and s["reference"] == "agnostic"
        and s["cohort"] == "common/all"
    ]
    assert deltas
    for s in deltas:
        assert s["delta_ll_game_low"] <= s["log_loss"] + 1e-12 <= s["delta_ll_game_high"] + 2e-12
        assert s["delta_ll_player_low"] is not None
    assert {s["cohort"] for s in out["scores"]} >= {"common/all", "rookie_cold/all"}
    assert len({frozenset(s) for s in out["scores"]}) == 1
    staging, output = tmp_path / "staging", tmp_path / "out"
    staging.mkdir()
    output.mkdir()
    with duckdb.connect() as connection:
        artifacts = write_tables(
            connection,
            {k: out[k] for k in ("predictions", "scores", "coefficients")},
            staging,
            output,
        )
    assert artifacts["scores"]["row_count"] == len(out["scores"])


def test_context_fit_ignores_scored_block_outcomes(built) -> None:  # type: ignore[no-untyped-def]
    rows, panel, appearances, subset, inputs, fits, chosen = built
    table = subset["stl_per_36"]
    block = "M4"
    base = base_fit(fits, chosen, block, "stl_per_36")
    fit_rows = fit_rows_for(appearances, table, block)
    assert all(appearances.played[i] < date(2023, 2, 1) for i in fit_rows)
    first = adjust_block(
        panel, appearances, table, inputs, base, block, rows_in(appearances, table, [block])
    )
    # Rewrite every box line from the scored block onward: the fitted coefficients cannot change.
    rng = np.random.default_rng(5)
    cut = date(2023, 2, 1)
    rewritten = [
        _appearance(r.game_id, r.game_date, r.player_id, r.team_id, r.opp_team_id, rng)
        if r.game_date >= cut
        else r
        for r in rows
    ]
    panel2, appearances2, tables2, _, _ = assemble(rewritten)
    inputs2 = build_context(rewritten, team_games_of(rewritten), appearances2.keys)
    table2 = tables2["stl_per_36"]
    second = adjust_block(
        panel2, appearances2, table2, inputs2, base, block, rows_in(appearances2, table2, [block])
    )
    assert len(first[1]) == len(second[1]) > 0
    for a, b in zip(first[1], second[1], strict=True):
        assert a["term"] == b["term"]
        assert a["coefficient"] == pytest.approx(b["coefficient"], abs=1e-9)


def test_snapshot_alignment_with_box_feature_codes() -> None:
    rows = season()
    params = {c: SkillParams("day", 1e9, 0.0) for c in FEATURE_CODES}
    as_of = date(2023, 2, 10)
    snapshot = skill_snapshot(rows, params, as_of)
    assert {s.feature_code for s in snapshot} == set(FEATURE_CODES)
    groups = {f.code: f.group for f in FEATURES}
    units = {f.code: "fraction" if f.scale == 1 else "per_36_minutes" for f in FEATURES}
    for s in snapshot:
        assert s.feature_group == groups[s.feature_code] and s.unit == units[s.feature_code]
    # With no shrinkage and no decay the estimate is the #62 aggregate rate of the earlier rows.
    checked = 0
    for player in ("10", "21", "30"):
        view = aggregate(r for r in rows if r.player_id == player and r.game_date < as_of).values()
        for s in snapshot:
            if s.player_id != player:
                continue
            value = view[s.feature_code].value
            if value is not None:
                assert s.estimate == pytest.approx(value, rel=1e-6)
                assert s.covered_games == view[s.feature_code].covered_appearances
                checked += 1
    assert checked >= 3 * len(FEATURE_CODES) - 3
    keys = [(s.player_id, s.feature_code) for s in snapshot]
    assert len(keys) == len(set(keys))
    first = [s.feature_code for s in snapshot if s.player_id == snapshot[0].player_id]
    assert first == list(FEATURE_CODES)


def test_snapshot_cutoff_and_equivalence_with_next_game_state() -> None:
    rows = season()
    params = {
        c: SkillParams("games", 6.0, 2.0) if c == "stl_per_36" else SkillParams("day", 25.0, 1.5)
        for c in FEATURE_CODES
    }
    as_of = date(2023, 1, 30)
    snapshot = skill_snapshot(rows, params, as_of)
    base = {(s.player_id, s.feature_code): s for s in snapshot}
    # Games on or after the as-of date never move the snapshot, even if rewritten.
    rng = np.random.default_rng(1)
    rewritten = [
        _appearance(r.game_id, r.game_date, r.player_id, r.team_id, r.opp_team_id, rng)
        if r.game_date >= as_of
        else r
        for r in rows
    ]
    assert skill_snapshot(rewritten, params, as_of) == snapshot
    assert skill_snapshot([r for r in rows if r.game_date < as_of], params, as_of) == snapshot
    assert skill_snapshot(rows, params, date(2022, 10, 18)) == []
    # It equals the #32 prediction state of a game played on the as-of date.
    panel, appearances, tables, _, _ = assemble(rows)
    on_date = [i for i, d in enumerate(appearances.played) if d == as_of]
    if not on_date:
        as_of_next = min(d for d in appearances.played if d >= as_of)
        pytest.skip(f"no synthetic game on {as_of}; next is {as_of_next}")
    for code in ("ast_per_36", "stl_per_36"):
        param = params[code]
        for i in on_date:
            got = base[(appearances.player[i], code)]
            pred = predict(
                panel,
                tables[code],
                appearances,
                param.clock,
                np.array([np.log10(param.half_life)]),
                np.array([np.log10(param.k)]),
                np.array([i]),
            )[0, 0]
            assert got.estimate == pytest.approx(pred)


def test_snapshot_requires_every_feature_code() -> None:
    rows = season(step=20)
    with pytest.raises(ValueError, match="No parameters"):
        skill_snapshot(rows, {"fg2_pct": SkillParams("day", 10.0, 1.0)}, date(2023, 2, 1))
    with pytest.raises(ValueError, match="Unknown clock"):
        SkillParams("hours", 1.0, 1.0)


def test_input_columns_cover_every_factor_term(built) -> None:  # type: ignore[no-untyped-def]
    inputs = built[4]
    columns = input_columns(inputs, "fg3_pct")
    for terms in FACTOR_COLUMNS.values():
        assert set(terms) <= set(columns)
