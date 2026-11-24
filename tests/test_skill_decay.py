"""Synthetic checks for stat-specific skill decay and shrinkage (issue #32)."""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import date, timedelta

import duckdb
import numpy as np
import pytest

from bil.features.box import FEATURES, Appearance
from bil.features.skill_decay import (
    BLOCK_NAMES,
    BLOCKS,
    CLOCKS,
    OUTER_BLOCKS,
    DESettings,
    as_of_sums,
    assemble,
    block_of,
    bootstrap_counts,
    clustered_ratio,
    fit,
    fit_blocks,
    league_as_of,
    nll,
    outer_plan,
    possession_exposure,
    predict,
    rows_in,
    seed_for,
)
from bil.features.skill_decay_build import (
    _fit_row,
    check_scope,
    evaluate,
    fit_all,
    select_clocks,
    write_tables,
)
from bil.features.skill_history import loss_terms

FEATURE = {f.code: f for f in FEATURES}
SMALL = DESettings(popsize=6, maxiter=15, polish=False)


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
            "blk": None if rng.random() < 0.03 else int(rng.integers(0, 3)),
            "pf": int(rng.integers(0, 6)),
        }
    )


def season(seed: int = 7, step: int = 4) -> list[Appearance]:
    """Four teams, three players each, a mid-season debut, a layoff and a short playoff run."""
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
                        continue  # layoff
                    if player == "32" and day < date(2023, 1, 10):
                        continue  # mid-season debut
                    rows.append(_appearance(game, day, player, side, other, rng))
        day += timedelta(days=step)
    for i in range(4):
        game = f"00422{i:05d}"
        played = date(2023, 4, 16) + timedelta(days=2 * i)
        for side, other in (("1", "2"), ("2", "1")):
            for slot in range(3):
                rows.append(_appearance(game, played, f"{side}{slot}", side, other, rng))
    return rows


def _brute(
    rows: list[Appearance], target: Appearance, code: str, clock: str, h: float, k: float
) -> float | None:
    """Independent oracle: enumerate earlier pooled appearances and weight them by age."""
    feature = FEATURE[code]
    poss, _ = possession_exposure(rows)
    mine = sorted((r for r in rows if r.player_id == target.player_id), key=lambda r: r.game_date)
    earlier = [r for r in mine if r.game_date < target.game_date]
    league_n = league_d = 0.0
    for r in rows:
        n, d = feature.numerator(r), feature.denominator(r)
        if r.game_date < target.game_date and n is not None and d is not None:
            league_n, league_d = league_n + n, league_d + d / feature.scale
    if league_d <= 0:
        return None
    m = league_n / league_d
    big_n = big_d = 0.0
    for g in earlier:
        n, d = feature.numerator(g), feature.denominator(g)
        if n is None or d is None:
            continue
        between = [r for r in earlier if g.game_date < r.game_date]
        age = {
            "day": (target.game_date - g.game_date).days,
            "games": len(between),
            "possessions": sum(poss[r.key] for r in between),
        }[clock]
        w = 0.5 ** (age / h)
        big_n += w * n
        big_d += w * d / feature.scale
    return (big_n + k * m) / (big_d + k)


@pytest.fixture(scope="module")
def built() -> tuple:  # type: ignore[type-arg]
    rows = season()
    return (rows, *assemble(rows))


@pytest.mark.parametrize("clock", CLOCKS)
@pytest.mark.parametrize("code", ["fg3_pct", "ast_per_36", "blk_per_36"])
def test_prediction_matches_brute_force_oracle(built, clock: str, code: str) -> None:  # type: ignore[no-untyped-def]
    rows, panel, appearances, tables, _, _ = built
    table = tables[code]
    by_key = {r.key: r for r in rows}
    idx = np.flatnonzero(~np.isnan(table.league))[::7]
    h, k = {"day": 21.0, "games": 6.0, "possessions": 400.0}[clock], 3.5
    pred = predict(
        panel, table, appearances, clock, np.array([math.log10(h)]), np.array([math.log10(k)]), idx
    )[0]
    for value, i in zip(pred, idx, strict=True):
        expected = _brute(rows, by_key[appearances.keys[i]], code, clock, h, k)
        assert expected is not None
        assert value == pytest.approx(expected, rel=1e-10, abs=1e-12)


def test_reduces_to_31_baselines_and_cold_rows_get_league(built) -> None:  # type: ignore[no-untyped-def]
    _, panel, appearances, tables, _, _ = built
    table = tables["fga_per_36"]
    idx = np.flatnonzero(~np.isnan(table.league))
    tiny = np.array([-14.0])
    decay30 = predict(panel, table, appearances, "day", np.array([math.log10(30)]), tiny, idx)[0]
    career = predict(panel, table, appearances, "games", np.array([14.0]), tiny, idx)[0]
    has = ~np.isnan(table.baselines["decay_30d"][idx])
    np.testing.assert_allclose(decay30[has], table.baselines["decay_30d"][idx][has], rtol=1e-9)
    np.testing.assert_allclose(career[has], table.baselines["career_to_date"][idx][has], rtol=1e-9)
    cold = table.covered_games[idx] == 0
    assert cold.any()
    shrunk = predict(panel, table, appearances, "day", np.array([1.0]), np.array([1.0]), idx)[0]
    np.testing.assert_allclose(shrunk[cold], table.league[idx][cold])
    # Huge k pulls every player to the league reference.
    huge = predict(panel, table, appearances, "day", np.array([1.0]), np.array([12.0]), idx)[0]
    np.testing.assert_allclose(huge, table.league[idx], rtol=1e-6)


def test_vectorized_loss_matches_loss_terms(built) -> None:  # type: ignore[no-untyped-def]
    _, _, _, tables, _, _ = built
    for code in ("fg2_pct", "fg3_share", "ast_per_36"):
        table = tables[code]
        idx = np.flatnonzero(table.observed)[:200]
        pred = np.linspace(0.0, 1.0 if table.scale == 1 else 12.0, idx.size)
        ours = nll(table.feature, table.target_num[idx], table.target_den[idx], pred)
        theirs = [
            loss_terms(table.feature, int(table.target_num[i]), int(table.target_den[i]), float(p))
            for i, p in zip(idx, pred, strict=True)
        ]
        np.testing.assert_allclose(ours, theirs, rtol=1e-12)


def test_possession_exposure_by_hand() -> None:
    rng = np.random.default_rng(0)
    a = replace(
        _appearance("0022200001", date(2022, 11, 1), "1", "1", "2", rng),
        fga=10,
        fta=5,
        oreb=2,
        tov=3,
        minutes_ms=24 * 60_000,
    )
    b = replace(
        _appearance("0022200001", date(2022, 11, 1), "2", "2", "1", rng),
        fga=8,
        fta=0,
        oreb=1,
        tov=1,
        minutes_ms=48 * 60_000,
    )
    c = replace(_appearance("0022200002", date(2022, 11, 2), "3", "3", "4", rng), tov=None)
    d = _appearance("0022200002", date(2022, 11, 2), "4", "4", "3", rng)
    poss, fallbacks = possession_exposure([a, b, c, d])
    team_a, team_b = 10 + 0.44 * 5 - 2 + 3, 8 - 1 + 1
    game = (team_a + team_b) / 2
    # One player per team: team minutes / 5 is the player's own minutes / 5.
    assert poss[a.key] == pytest.approx(game * 5)
    assert poss[b.key] == pytest.approx(game * 5)
    assert fallbacks == 2
    assert poss[c.key] == pytest.approx(100 * c.minutes_ms / (48 * 60_000))


def test_pooled_playoff_history(built) -> None:  # type: ignore[no-untyped-def]
    _, _, appearances, tables, _, _ = built
    first_playoff = [i for i, k in enumerate(appearances.season_type) if k == "playoffs"][:6]
    table = tables["ast_per_36"]
    assert all(table.covered_games[i] > 0 for i in first_playoff)
    assert all(not np.isnan(table.league[i]) for i in first_playoff)
    assert {appearances.block[i] for i in first_playoff} == {"P"}


def test_fold_nesting_never_tunes_on_scored_blocks() -> None:
    for block in OUTER_BLOCKS:
        plan = outer_plan(block)
        k = BLOCK_NAMES.index(block)
        for fit_index, validation in plan.inner:
            assert validation not in fit_blocks(fit_index)
            assert BLOCK_NAMES.index(validation) < k
            assert all(
                BLOCK_NAMES.index(b) < BLOCK_NAMES.index(validation) for b in fit_blocks(fit_index)
            )
        assert block not in fit_blocks(plan.final_fit)
        assert all(BLOCK_NAMES.index(b) < k for b in fit_blocks(plan.final_fit))
    assert block_of(date(2023, 4, 9), "regular") == "M5"
    assert block_of(date(2023, 4, 16), "playoffs") == "P"
    assert block_of(date(2023, 4, 16), "regular") is None
    assert BLOCKS[-1][2] == date(2023, 4, 10)


def test_scored_block_outcomes_cannot_move_fits() -> None:
    rows = season(seed=3, step=6)
    poisoned = [
        replace(r, ast=(r.ast or 0) + 25) if r.game_date >= date(2023, 1, 1) else r for r in rows
    ]
    clean, dirty = assemble(rows), assemble(poisoned)
    for j in (0, 1, 2):
        a = fit(clean[0], clean[2]["ast_per_36"], clean[1], "day", j, SMALL)
        b = fit(dirty[0], dirty[2]["ast_per_36"], dirty[1], "day", j, SMALL)
        assert (a.log10_half_life, a.log10_k, a.objective) == (
            b.log10_half_life,
            b.log10_k,
            b.objective,
        )
    a3 = fit(clean[0], clean[2]["ast_per_36"], clean[1], "day", 3, SMALL)
    b3 = fit(dirty[0], dirty[2]["ast_per_36"], dirty[1], "day", 3, SMALL)
    assert a3.objective != b3.objective


def test_seed_reproducibility_and_bounds(built) -> None:  # type: ignore[no-untyped-def]
    _, panel, appearances, tables, _, _ = built
    first = fit(panel, tables["fg3_pct"], appearances, "possessions", 2, SMALL)
    second = fit(panel, tables["fg3_pct"], appearances, "possessions", 2, SMALL)
    assert first == second
    assert first.seed == seed_for(1, "possessions", 2) == 32_000 + 100 + 20 + 2
    assert 1.5 <= first.log10_half_life <= 5.0 and -2.0 <= first.log10_k <= 4.0
    assert first.rows == rows_in(appearances, tables["fg3_pct"], fit_blocks(2)).size


def test_as_of_snapshot_matches_next_game_state(built) -> None:  # type: ignore[no-untyped-def]
    rows, panel, appearances, tables, _, _ = built
    table = tables["dreb_per_36"]
    cutoff = date(2023, 1, 1)
    # The first appearance on or after the cutoff sees exactly the as-of state for exposure clocks.
    for clock in ("games", "possessions"):
        h = 5.0 if clock == "games" else 300.0
        sums = as_of_sums(panel, table.x, clock, h, cutoff)
        league = league_as_of(table, panel, cutoff)
        assert league is not None
        for p, player in enumerate(panel.players[:4]):
            i = next(
                i
                for i, k in enumerate(appearances.keys)
                if appearances.player[i] == player and appearances.played[i] >= cutoff
            )
            if appearances.played[i] != min(d for d in appearances.played if d >= cutoff):
                continue
            pred = predict(
                panel,
                table,
                appearances,
                clock,
                np.array([math.log10(h)]),
                np.array([0.0]),
                np.array([i]),
            )[0, 0]
            assert pred == pytest.approx((sums[0, p] + table.league[i]) / (sums[1, p] + 1.0))
            assert table.league[i] == pytest.approx(league)
    day_sums = as_of_sums(panel, table.x, "day", 10.0, cutoff)
    p = 0
    earlier = [
        r
        for r in rows
        if r.player_id == panel.players[p] and r.game_date < cutoff and r.dreb is not None
    ]
    expected = sum(r.dreb * 0.5 ** ((cutoff - r.game_date).days / 10.0) for r in earlier)  # type: ignore[operator]
    assert day_sums[0, p] == pytest.approx(expected)


def test_clustered_bootstrap() -> None:
    counts = bootstrap_counts(5, 400, 1)
    assert (counts.sum(axis=1) == 5).all()
    assert (bootstrap_counts(5, 400, 1) == counts).all()
    cluster = np.array([0, 0, 1, 2, 3, 4, 4])
    diff = np.array([1.0, -1.0, 0.5, 0.2, -0.3, 0.1, 0.1])
    weight = np.array([1.0, 2.0, 1.0, 1.0, 1.0, 1.0, 3.0])
    point, low, high = clustered_ratio(cluster, diff, weight, counts)
    assert point == pytest.approx(diff.sum() / weight.sum())
    assert low <= point <= high
    constant = clustered_ratio(cluster, 0.5 * weight, weight, counts)
    assert constant == pytest.approx((0.5, 0.5, 0.5))


def test_scope_guard_rejects_other_seasons() -> None:
    rows = season(step=20)
    check_scope(rows)
    with pytest.raises(ValueError, match="outside"):
        check_scope([*rows, replace(rows[0], game_id="0022300001")])
    with pytest.raises(ValueError, match="outside"):
        check_scope([replace(rows[0], game_date=date(2023, 7, 1))])


def test_end_to_end_evaluation_small(tmp_path) -> None:  # type: ignore[no-untyped-def]
    rows = season(seed=11, step=6)
    panel, appearances, tables, _, _ = assemble(rows)
    subset = {c: tables[c] for c in ("fg3_pct", "stl_per_36")}
    fits = fit_all(panel, appearances, subset, SMALL)
    assert len(fits) == 2 * len(CLOCKS) * 6
    selections = select_clocks(panel, appearances, subset, fits)
    assert {s["outer_block"] for s in selections} == set(OUTER_BLOCKS)
    for s in selections:
        assert s["selected_clock"] == min(CLOCKS, key=lambda c: s[f"inner_loss_{c}"])
    out = evaluate(panel, appearances, subset, fits, selections, replicates=50)
    assert out["predictions"] and out["snapshots"] and out["exclusions"]
    deltas = [
        s for s in out["scores"] if s["reference"] == "league_to_date" and s["block"] == "pooled"
    ]
    assert deltas
    for s in deltas:
        if s["delta_log_loss_low"] is not None:
            assert (
                s["delta_log_loss_low"] <= s["log_loss"] + 1e-12 <= s["delta_log_loss_high"] + 2e-12
            )
    cold = [
        s
        for s in out["scores"]
        if s["cohort"] == "rookie_cold/all"
        and s["reference"] == "league_to_date"
        and s["forecaster"] == "model"
    ]
    assert cold and all(s["log_loss"] == pytest.approx(0.0, abs=1e-12) for s in cold)
    reasons = {e["reason"] for e in out["exclusions"]}
    assert "primary_common" in reasons
    assert all(p["outer_block"] in OUTER_BLOCKS for p in out["predictions"])
    staging, output = tmp_path / "staging", tmp_path / "out"
    staging.mkdir()
    output.mkdir()
    tables_out = {
        "fits": [_fit_row(f) for f in fits.values()],
        "clock_selection": selections,
        **out,
    }
    with duckdb.connect() as connection:
        artifacts = write_tables(connection, tables_out, staging, output)
        for name, rows_out in tables_out.items():
            written = connection.execute(
                "SELECT count(*) FROM read_parquet(?)", [str(output / artifacts[name]["filename"])]
            ).fetchall()[0][0]
            assert written == len(rows_out)
