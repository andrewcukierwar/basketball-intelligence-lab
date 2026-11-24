"""Hand-calculated and synthetic checks for skill histories and baselines (issue #31)."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bil.evaluation.eligibility import Revision, eastern_origin
from bil.features.box import FEATURES, MS_PER_36, Appearance
from bil.features.skill_history import (
    BASELINES,
    LAST_N,
    Scorer,
    SkillRow,
    history_bucket,
    loss_terms,
    season_start_year,
    skill_rows,
    strict_prior_counts,
)

FEATURE = {f.code: f for f in FEATURES}


def _row(
    game: str,
    day: str,
    player: str = "1",
    *,
    minutes: float = 36,
    ast: int | None = 0,
    fg3m: int | None = 1,
    fg3a: int | None = 2,
    fta: int | None = 0,
    ftm: int | None = 0,
    kind: str | None = None,
) -> Appearance:
    return Appearance.from_record(
        {
            "game_id": game,
            "player_id": player,
            "team_id": "10",
            "opp_team_id": "20",
            "game_date": day,
            "min": minutes,
            "fgm": 3,
            "fga": 6,
            "fg3m": fg3m,
            "fg3a": fg3a,
            "ftm": ftm,
            "fta": fta,
            "pts": 7,
            "oreb": 0,
            "dreb": 1,
            "ast": ast,
            "tov": 0,
            "stl": 0,
            "blk": 0,
            "pf": 1,
            **({"season_type": kind} if kind else {}),
        }
    )


def _by_key(rows: list[Appearance]) -> dict[tuple[str, str], dict[str, SkillRow]]:
    return {
        (op.row.game_id, op.row.player_id): {sk.feature.code: sk for sk in skills}
        for op, skills in skill_rows(rows)
    }


def _reference(rows: list[Appearance], target: Appearance, code: str) -> dict[str, float | None]:
    """Independent brute-force baselines from raw rows strictly before the target's date."""
    feature = FEATURE[code]
    year = season_start_year(target.game_id)

    def usable(pool: list[Appearance]) -> list[tuple[int, int, Appearance]]:
        found = []
        for r in sorted(pool, key=lambda r: (r.game_date, r.game_id)):
            n, d = feature.numerator(r), feature.denominator(r)
            if n is not None and d is not None:
                found.append((n, d, r))
        return found

    earlier = [
        r
        for r in rows
        if r.player_id == target.player_id
        and r.season_type == target.season_type
        and r.game_date < target.game_date
    ]

    def ratio(items: list[tuple[float, float]]) -> float | None:
        d = sum(x[1] for x in items)
        return sum(x[0] for x in items) * feature.scale / d if d > 0 else None

    career = usable(earlier)
    in_season = [c for c in career if season_start_year(c[2].game_id) == year]
    pooled = usable(
        [
            r
            for r in rows
            if r.season_type == target.season_type
            and r.game_date < target.game_date
            and season_start_year(r.game_id) == year
        ]
    )
    out: dict[str, float | None] = {
        "career_to_date": ratio([(n, d) for n, d, _ in career]),
        "season_to_date": ratio([(n, d) for n, d, _ in in_season]),
        f"last_{LAST_N}": ratio([(n, d) for n, d, _ in career[-LAST_N:]]),
        "league_to_date": ratio([(n, d) for n, d, _ in pooled]),
    }
    for half in (30, 90):
        weights = [
            (n * w, d * w)
            for n, d, r in career
            for w in [0.5 ** ((target.game_date - r.game_date).days / half)]
        ]
        out[f"decay_{half}d"] = ratio(weights) if sum(d for _, d, _ in career) > 0 else None
    return out


def _synthetic() -> list[Appearance]:
    rows = []
    start = date(2022, 10, 20)
    for i in range(40):
        day = (start + timedelta(days=3 * i)).isoformat()
        for player in ("1", "2", "3"):
            if (i + int(player)) % 5 == 0:
                continue  # irregular appearances
            rows.append(
                _row(
                    f"00222{i:03d}{player}0",
                    day,
                    player,
                    minutes=20 + 3 * int(player) + i % 4,
                    ast=(i * int(player)) % 7,
                    fg3m=i % 3,
                    fg3a=2 + i % 3,
                    fta=i % 2,
                    ftm=0,
                )
            )
    # same-day second game for player 1 (early tip) and a later-season game
    rows.append(_row("0022200999", "2022-11-02", "1", ast=9))
    rows.append(_row("0022300001", "2023-10-24", "1", ast=1))
    rows.append(_row("0022300002", "2023-10-24", "2", ast=2))
    return rows


def test_every_baseline_matches_brute_force_and_uses_only_earlier_dates() -> None:
    rows = _synthetic()
    assert len({r.game_id for r in rows}) == len(rows)
    results = _by_key(rows)
    assert len(results) == len(rows)
    for r in rows:
        for code, skill in results[(r.game_id, r.player_id)].items():
            reference = _reference(rows, r, code)
            assert set(skill.predictions) == set(BASELINES)
            for name, value in reference.items():
                got = skill.predictions[name]
                if value is None:
                    assert got is None, (r.game_id, code, name)
                else:
                    assert got == pytest.approx(value, rel=1e-9), (r.game_id, code, name)


def test_same_day_games_never_reach_each_other_or_the_league_pool() -> None:
    rows = [
        _row("0022200001", "2023-01-01", "1", ast=4),
        _row("0022200002", "2023-01-02", "1", ast=10),
        _row("0022200003", "2023-01-02", "1", ast=20),  # same-day early tip
        _row("0022200004", "2023-01-02", "2", ast=30),
        _row("0022200005", "2023-01-03", "1", ast=0),
    ]
    results = _by_key(rows)
    for game in ("0022200002", "0022200003"):
        pred = results[(game, "1")]["ast_per_36"].predictions
        assert pred["career_to_date"] == pytest.approx(4.0)
        assert pred["league_to_date"] == pytest.approx(4.0)
    assert results[("0022200004", "2")]["ast_per_36"].predictions["career_to_date"] is None
    assert results[("0022200004", "2")]["ast_per_36"].history_status == "no_prior_history"
    after = results[("0022200005", "1")]["ast_per_36"].predictions
    assert after["career_to_date"] == pytest.approx((4 + 10 + 20) / 3)
    assert after["league_to_date"] == pytest.approx((4 + 10 + 20 + 30) / 4)
    first = results[("0022200001", "1")]["ast_per_36"]
    assert first.predictions["league_to_date"] is None  # nothing earlier in the league either


def test_target_is_the_games_own_observed_rate() -> None:
    results = _by_key([_row("0022200001", "2023-01-01", ast=3, minutes=18)])
    sk = results[("0022200001", "1")]["ast_per_36"]
    assert (sk.target_numerator, sk.target_denominator) == (3, 18 * 60_000)
    assert sk.target_rate == pytest.approx(6.0)
    assert sk.weight == pytest.approx(0.5)  # 18 minutes in 36-minute units
    fraction = results[("0022200001", "1")]["fg3_pct"]
    assert fraction.target_rate == pytest.approx(0.5)
    assert fraction.weight == 2  # attempts


def test_rookie_zero_exposure_and_missing_cases() -> None:
    rows = [
        _row("0022200001", "2023-01-01", fta=0, ast=None),  # known zero FTA; missing assists
        _row("0022200002", "2023-01-02", fta=0, minutes=0),  # zero minutes, no events
        _row("0022200003", "2023-01-03", fta=2, ftm=1),
        _row("0022200004", "2023-01-04", fta=0),
    ]
    results = _by_key(rows)
    first = results[("0022200001", "1")]
    assert first["ft_pct"].history_status == "no_prior_history"
    assert first["ft_pct"].target_status == "zero_exposure"
    assert first["ft_pct"].target_rate is None and first["ft_pct"].weight == 0
    assert first["ast_per_36"].target_status == "missing_component"
    second = results[("0022200002", "1")]
    assert second["ft_pct"].history_status == "zero_exposure_history"  # covered, zero attempts
    assert second["ft_pct"].predictions["career_to_date"] is None
    assert second["ast_per_36"].history_status == "no_covered_history"  # earlier assists missing
    assert second["ast_per_36"].predictions["career_to_date"] is None
    assert second["ast_per_36"].career_covered_games == 0
    assert second["fga_per_36"].target_status == "zero_exposure"  # zero known minutes
    third = results[("0022200003", "1")]
    assert third["ft_pct"].history_status == "zero_exposure_history"
    assert third["fga_per_36"].predictions["career_to_date"] == pytest.approx(
        12.0
    )  # the zero-minute row adds 6 FGA and no time
    fourth = results[("0022200004", "1")]
    assert fourth["ft_pct"].history_status == "has_history"
    assert fourth["ft_pct"].predictions["career_to_date"] == pytest.approx(0.5)
    assert fourth["ast_per_36"].history_status == "has_history"
    assert fourth["ast_per_36"].career_covered_games == 2  # games 2 and 3; game 1 is missing


def test_recency_weights_hand_calculation() -> None:
    rows = [
        _row("0022200001", "2023-01-01", ast=6),
        _row("0022200002", "2023-01-31", ast=0),
        _row("0022200003", "2023-03-02", ast=0),
    ]
    pred = _by_key(rows)[("0022200003", "1")]["ast_per_36"].predictions
    # Half-life 30 days: ages 60 and 30 days weight 0.25 and 0.5 over equal 36-minute exposure.
    assert pred["decay_30d"] == pytest.approx(6 * 0.25 / 0.75)
    weight90 = (0.5 ** (60 / 90), 0.5 ** (30 / 90))
    assert pred["decay_90d"] == pytest.approx(6 * weight90[0] / sum(weight90))
    assert pred["career_to_date"] == pytest.approx(3.0)
    assert pred["last_10"] == pytest.approx(3.0)


def test_last_n_drops_games_beyond_the_window_and_counts_covered_games_only() -> None:
    rows = [
        _row(f"00222{i:05d}", f"2023-01-{i + 1:02d}", ast=100 if i == 0 else 1) for i in range(13)
    ]
    rows[3] = _row("0022200003", "2023-01-04", ast=None)  # uncovered games take no window slot
    last = _by_key(rows)[("0022200012", "1")]["ast_per_36"]
    assert last.predictions["last_10"] == pytest.approx(1.0)  # the 100-assist game fell out
    assert last.predictions["career_to_date"] > 5
    assert last.career_covered_games == 11  # 12 earlier games, one missing component


def test_season_boundary_resets_season_to_date_but_not_career_or_league_scope() -> None:
    rows = [
        _row("0022200001", "2023-04-01", "1", ast=6),
        _row("0022200002", "2023-04-02", "2", ast=12),
        _row("0022300001", "2023-10-25", "1", ast=0),
        _row("0022300002", "2023-10-26", "1", ast=3),
    ]
    results = _by_key(rows)
    opening = results[("0022300001", "1")]["ast_per_36"]
    assert opening.opportunity.season == 2023
    assert opening.opportunity.career_prior_appearances == 1
    assert opening.opportunity.season_prior_appearances == 0
    assert opening.history_status == "has_history"
    assert opening.predictions["career_to_date"] == pytest.approx(6.0)
    assert opening.predictions["season_to_date"] is None
    assert opening.predictions["league_to_date"] is None  # league pool restarts each season
    second = results[("0022300002", "1")]["ast_per_36"]
    assert second.predictions["career_to_date"] == pytest.approx(3.0)
    assert second.predictions["season_to_date"] == pytest.approx(0.0)
    assert second.predictions["league_to_date"] == pytest.approx(0.0)
    assert second.career_covered_games == 2 and second.season_covered_games == 1
    # The decayed baseline carries the old season across the offseason gap.
    assert second.predictions["decay_90d"] is not None


def test_career_equals_season_to_date_within_one_season() -> None:
    for skills in _by_key([r for r in _synthetic() if r.game_date < date(2023, 1, 1)]).values():
        for sk in skills.values():
            assert sk.predictions["career_to_date"] == sk.predictions["season_to_date"]


def test_playoff_history_is_separate_from_regular_season_history() -> None:
    rows = [
        _row("0022200001", "2023-04-01", ast=6),
        _row("0042200101", "2023-04-20", ast=2, kind="playoffs"),
    ]
    playoff = _by_key(rows)[("0042200101", "1")]["ast_per_36"]
    assert playoff.history_status == "no_prior_history"
    assert playoff.predictions["career_to_date"] is None


def test_scorer_hand_calculation_and_chronological_order() -> None:
    rows = [
        _row("0022200001", "2023-01-01", "1", ast=6, minutes=36, fg3m=1, fg3a=2),
        _row("0022200002", "2023-01-02", "1", ast=0, minutes=18, fg3m=0, fg3a=2),
        _row("0022200003", "2023-01-03", "1", ast=3, minutes=36, fg3m=2, fg3a=2),
        _row("0022200004", "2023-01-03", "2", ast=1),  # no history: cold start, league only
    ]
    scorer = Scorer()
    for _, skills in skill_rows(rows):
        scorer.add(skills)
    cells = {
        (s["cohort_set"], s["dim"], s["dim_value"], s["feature_code"], s["baseline"]): s
        for s in scorer.table()
    }
    # Common set needs league history and player history: only the last game qualifies for all
    # six baselines; the second game has no zero-division-free league baseline until game 1 ends.
    ast_career = cells[("common", "all", "all", "ast_per_36", "career_to_date")]
    # Game 2: career 6.0, target 0.0, weight 0.5. Game 3: career 6*2160000/(54*60000) = 4.0,
    # target 3.0, weight 1.
    expected = (0.5 * 36.0 + 1.0 * 1.0) / 1.5
    assert ast_career["rows"] == 2
    assert ast_career["weighted_mse"] == pytest.approx(expected)
    assert cells[("common", "month", "2023-01", "ast_per_36", "career_to_date")]["rows"] == 2
    fg3 = cells[("common", "all", "all", "fg3_pct", "career_to_date")]
    # Game 2: pred .5 target 0 (2 attempts); game 3: pred .25 target 1 (2 attempts).
    assert fg3["weighted_mse"] == pytest.approx((2 * 0.25 + 2 * 0.5625) / 4)
    nll = -(0 * math.log(0.5) + 2 * math.log(0.5)) - (2 * math.log(0.25))
    assert fg3["log_loss"] == pytest.approx(nll / 4)
    assert cells[("cold", "all", "all", "ast_per_36", "league_to_date")]["rows"] == 1
    with pytest.raises(ValueError, match="chronological"):
        scorer.add(next(skill_rows(rows[:1]))[1])


def test_loss_terms_and_history_bucket() -> None:
    fg3 = FEATURE["fg3_pct"]
    assert loss_terms(fg3, 1, 2, 0.5) == pytest.approx(-2 * math.log(0.5))
    assert math.isfinite(loss_terms(fg3, 1, 2, 0.0))  # clipped
    ast = FEATURE["ast_per_36"]
    lam = 2.0 * (18 * 60_000) / MS_PER_36
    assert loss_terms(ast, 3, 18 * 60_000, 2.0) == pytest.approx(lam - 3 * math.log(lam))
    assert [history_bucket(n) for n in (1, 4, 5, 19, 20, 60)] == [
        "1-4",
        "1-4",
        "5-19",
        "5-19",
        "20+",
        "20+",
    ]


def _published(row: Appearance, available: datetime, finalized: datetime) -> Revision:
    return Revision(
        key=row.key,
        revision=1,
        source_artifact_id="a",
        content_sha256=row.content_sha256(),
        kind="observation",
        availability_basis="published",
        available_at=available,
        evidence_ref="e",
        observed_date=row.game_date,
        finalized_at=finalized,
    )


def test_strict_prior_counts_follow_revision_evidence() -> None:
    rows = [
        _row("0022200001", "2023-01-01"),
        _row("0022200002", "2023-01-02"),
        _row("0022200003", "2023-01-03"),
    ]
    early = datetime(2023, 1, 1, 12, tzinfo=UTC)
    revisions = {r.key: _published(r, early, early) for r in rows}
    assert [strict_prior_counts(rows, revisions)[r.key] for r in rows] == [0, 1, 2]
    cutoff = eastern_origin(date(2023, 1, 3))
    late = _published(rows[0], cutoff + timedelta(hours=1), early)
    assert [strict_prior_counts(rows, {**revisions, rows[0].key: late})[r.key] for r in rows] == [
        0,
        0,
        1,
    ]
    retracted = Revision(**{**revisions[rows[1].key].__dict__, "revision": 2, "change": "retract"})
    counts = strict_prior_counts(
        rows,
        {rows[1].key: retracted, **{r.key: revisions[r.key] for r in rows if r is not rows[1]}},
    )
    assert counts[rows[2].key] == 1


def _write_source(tmp_path: Path, name: str, ast_second: int = 0) -> tuple[Path, Any]:
    duckdb = pytest.importorskip("duckdb")
    from bil.data.pilot_sources import sha256_file
    from bil.features.box_build import PLAYER_LOG, TEAM_LOG

    source = tmp_path / name
    source.mkdir()
    games = (
        ("0022200001", "2023-01-01"),
        ("0022200002", "2023-01-02"),
        ("0022200003", "2023-01-03"),
    )
    team_values = ", ".join(
        f"(2023, '{g}', '10', '20', DATE '{d}', true), (2023, '{g}', '20', '10', DATE '{d}', false)"
        for g, d in games
    )
    duckdb.sql(
        f"SELECT * FROM (VALUES {team_values}) t(season, game_id, team_id, opp_team_id, game_date, home)"
    ).write_parquet(str(source / TEAM_LOG))
    values = []
    for index, (game, day) in enumerate(games):
        for player in ("7", "8"):
            ast = ast_second if (index == 1 and player == "7") else index
            values.append(
                f"(2023, '{game}', '{player}', '10', '20', DATE '{day}', {20 + index}.0, 2, 4, 1, 2, "
                f"0, 0, 5, 1, 1, 2, {ast}, 0, 0, 1, 2)"
            )
    duckdb.sql(
        f"SELECT * FROM (VALUES {', '.join(values)}) t(season, game_id, player_id, team_id, "
        "opp_team_id, game_date, min, fgm, fga, fg3m, fg3a, ftm, fta, pts, oreb, dreb, reb, ast, "
        "tov, stl, blk, pf)"
    ).write_parquet(str(source / PLAYER_LOG))
    (source / "snapshot.json").write_text("{}")
    snapshot: Any = {
        "artifacts": [
            {
                "name": n,
                "artifact_id": f"{n}@{sha256_file(source / n)}",
                "sha256": sha256_file(source / n),
                "retrieved_at": "2026-11-23T18:04:04+00:00",
            }
            for n in (TEAM_LOG, PLAYER_LOG)
        ]
    }
    return source, snapshot


def test_build_reconciles_and_freezes_against_source_revisions(tmp_path: Path) -> None:
    pytest.importorskip("duckdb")
    from bil.features.skill_build import build_skill_histories

    source, snapshot = _write_source(tmp_path, "source")
    manifest = build_skill_histories(
        source, tmp_path / "out", "0" * 40, snapshot=snapshot, expected=None
    )
    observed = manifest["reconciliation"]["observed"]
    assert manifest["reconciliation"]["failed_checks"] == []
    assert observed["skill_rows"] == 6 * 13
    for key in (
        "baseline_sql_mismatches",
        "league_sql_mismatches",
        "target_sql_mismatches",
        "score_sql_mismatches",
        "strict_rows_with_history",
    ):
        assert observed[key] == 0
    regular = manifest["coverage"]["regular"]
    assert regular["appearances"] == 6
    assert (
        regular["appearances_without_prior_history"],
        regular["players"],
        regular["players_with_any_prior_history"],
        regular["games"],
        regular["games_where_no_player_has_history"],
    ) == (2, 2, 2, 3, 1)
    assert manifest["freeze"]["strict"]["cohort_status"] == "unavailable_historical_strict"
    assert manifest["baselines"]["tuned"] is False

    # A revised source value changes the frozen opportunity digest, snapshot IDs and content ID.
    revised_source, revised_snapshot = _write_source(tmp_path, "revised", ast_second=5)
    revised = build_skill_histories(
        revised_source, tmp_path / "out2", "0" * 40, snapshot=revised_snapshot, expected=None
    )
    assert revised["freeze"]["appearance_digest"] != manifest["freeze"]["appearance_digest"]
    assert revised["freeze"]["opportunity_digest"] != manifest["freeze"]["opportunity_digest"]
    assert revised["snapshot_ids"] != manifest["snapshot_ids"]
    assert revised["content_id"] != manifest["content_id"]
    # Equal histories on unchanged inputs give an identical frozen opportunity digest.
    again = build_skill_histories(
        source, tmp_path / "out3", "0" * 40, snapshot=snapshot, expected=None
    )
    assert again["freeze"]["opportunity_digest"] == manifest["freeze"]["opportunity_digest"]
    assert again["content_id"] == manifest["content_id"]


@pytest.mark.parametrize("seed", ["prediction", "target"])
def test_seeded_mismatch_fails_and_removes_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, seed: str
) -> None:
    pytest.importorskip("duckdb")
    from bil.features import skill_build

    source, snapshot = _write_source(tmp_path, "source")
    real = skill_build.skill_rows

    def seeded(rows: Any) -> Any:
        from dataclasses import replace

        for opportunity, skills in real(rows):
            changed = []
            for sk in skills:
                if sk.feature.code == "ast_per_36":
                    if seed == "prediction" and sk.predictions["career_to_date"] is not None:
                        sk = replace(
                            sk,
                            predictions={
                                **sk.predictions,
                                "career_to_date": sk.predictions["career_to_date"] + 1,
                            },
                        )
                    if seed == "target":
                        sk = replace(sk, target_numerator=(sk.target_numerator or 0) + 1)
                changed.append(sk)
            yield opportunity, changed

    monkeypatch.setattr(skill_build, "skill_rows", seeded)
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="Reconciliation failed"):
        skill_build.build_skill_histories(source, out, "0" * 40, snapshot=snapshot, expected=None)
    assert not out.exists()
