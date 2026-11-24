"""Hand-calculated checks for the box-score feature views (issue #62, contract #63)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from bil.evaluation.eligibility import Revision, eastern_origin
from bil.features.box import (
    FEATURE_CODES,
    Appearance,
    Provenance,
    aggregate,
    capture_bound_revisions,
    dated_retrospective,
    history_rows,
    same_window,
    strict_history,
)

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "box_features" / "pilot_windows.json").read_text()
)
ROWS = [Appearance.from_record(row) for row in FIXTURE["appearances"]]
CAPTURE = Provenance(
    "fixture@0",
    datetime.fromisoformat(FIXTURE["source_capture_at"].replace("Z", "+00:00")),
    "fixture",
)


def _eligible(case: dict[str, Any]) -> list[Appearance]:
    types = case["season_types"]
    if case["mode"] == "same_window":
        return same_window(
            ROWS,
            date.fromisoformat(case["start_date"]),
            date.fromisoformat(case["end_date"]),
            types,
        )
    rating = date.fromisoformat(case["rating_date"])
    if case["mode"] == "dated_retrospective":
        return dated_retrospective(ROWS, rating, types)
    usable, _ = strict_history(ROWS, capture_bound_revisions(ROWS, CAPTURE), rating, types)
    return usable


@pytest.mark.parametrize(
    "case",
    FIXTURE["cases"],
    ids=lambda c: f"{c['mode']}-{c.get('rating_date', c.get('start_date'))}",
)
def test_fixture_cases(case: dict[str, Any]) -> None:
    eligible = _eligible(case)
    assert sorted(r.game_id for r in eligible) == case["eligible_game_ids"]
    accumulator = aggregate(eligible)
    summary = accumulator.summary()
    assert summary["minutes_ms"] == case["minutes_ms"]
    assert summary["points"] == case["points"]
    values = accumulator.values()
    for code, expected in case["features"].items():
        got = values[code]
        assert (got.numerator, got.denominator) == (expected["numerator"], expected["denominator"])
        assert got.covered_appearances == expected["covered_appearances"]
        if expected["value"] is None:
            assert got.value is None
        else:
            assert got.value == pytest.approx(expected["value"])


def test_strict_cutoff_is_new_york_midnight() -> None:
    assert FIXTURE["cases"][-1]["effective_cutoff"] == eastern_origin(
        date(2023, 1, 11)
    ).isoformat().replace("+00:00", "Z")


def test_feature_set_and_missing_component_isolated() -> None:
    values = aggregate(ROWS[:3]).values()
    assert tuple(values) == FEATURE_CODES
    # ast is missing for one of three appearances: covered 2 of 3, minutes only from those two.
    ast = values["ast_per_36"]
    assert (ast.covered_appearances, ast.eligible_appearances) == (2, 3)
    assert ast.coverage == pytest.approx(2 / 3)
    # fg2: (3-1)+(2-0)+(5-2)=7 over (6-2)+(4-0)+(9-4)=13
    assert (values["fg2_pct"].numerator, values["fg2_pct"].denominator) == (7, 13)
    # A known zero denominator leaves the rate unavailable but keeps components.
    assert aggregate([ROWS[1]]).values()["ft_pct"].value is None
    assert aggregate([ROWS[1]]).values()["ft_pct"].numerator == 0


def test_players_with_two_teams_pool_across_teams() -> None:
    assert {r.team_id for r in ROWS[:3]} == {"100", "200"}
    assert aggregate(ROWS[:3]).summary()["games_with_time"] == 3


def _row(
    game: str, day: str, player: str = "1", fg3m: int = 1, kind: str | None = None
) -> Appearance:
    return Appearance.from_record(
        {
            "game_id": game,
            "player_id": player,
            "team_id": "10",
            "opp_team_id": "20",
            "game_date": day,
            "min": 30,
            "fgm": 2,
            "fga": 4,
            "fg3m": fg3m,
            "fg3a": 2,
            "ftm": 0,
            "fta": 0,
            "pts": 4 + fg3m - 1,
            "oreb": 0,
            "dreb": 1,
            "ast": 1,
            "tov": 0,
            "stl": 0,
            "blk": 0,
            "pf": 1,
            **({"season_type": kind} if kind else {}),
        }
    )


def test_asof_excludes_same_day_and_future_games() -> None:
    # Two games on the same date (e.g. an early tip) never see each other, nor later games.
    rows = [
        _row("0022200001", "2023-01-01"),
        _row("0022200002", "2023-01-02", fg3m=0),
        _row("0022200003", "2023-01-02", fg3m=0),
        _row("0022200004", "2023-01-03", fg3m=2),
    ]
    got = {r.game_id: (v["fg3_pct"], s) for r, v, s in history_rows(rows)}
    assert got["0022200001"][0].eligible_appearances == 0
    assert got["0022200001"][0].value is None  # cold start keeps a null row
    assert got["0022200001"][1]["minutes_ms"] is None
    for same_day in ("0022200002", "0022200003"):
        feature = got[same_day][0]
        assert (feature.numerator, feature.denominator) == (1, 2)
        assert feature.eligible_appearances == 1
    last = got["0022200004"][0]
    assert (last.numerator, last.denominator, last.eligible_appearances) == (1, 6, 3)


def test_asof_history_is_separated_by_season_type() -> None:
    rows = [_row("0022200001", "2023-04-01"), _row("0042200001", "2023-04-20", kind="playoffs")]
    got = {r.game_id: v["fg3_pct"].eligible_appearances for r, v, _ in history_rows(rows)}
    assert got == {"0022200001": 0, "0042200001": 0}


def test_strict_requires_published_finalized_evidence_before_cutoff() -> None:
    rows = [_row("0022200001", "2023-01-01"), _row("0022200002", "2023-01-02")]
    cutoff = eastern_origin(date(2023, 1, 2))
    base = capture_bound_revisions(rows, CAPTURE)
    assert strict_history(rows, base, date(2023, 1, 2), ["regular"])[0] == []

    def published(row: Appearance, available: datetime, finalized: datetime) -> Revision:
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

    early = datetime(2023, 1, 2, 3, tzinfo=UTC)
    revisions = {
        rows[0].key: published(rows[0], early, early),
        rows[1].key: published(rows[1], early, early),
    }
    usable, _ = strict_history(rows, revisions, date(2023, 1, 2), ["regular"])
    assert [r.game_id for r in usable] == ["0022200001"]  # same-day game stays out
    late = published(rows[0], cutoff.replace(hour=cutoff.hour + 1), early)
    assert (
        strict_history(rows, {**revisions, rows[0].key: late}, date(2023, 1, 2), ["regular"])[0]
        == []
    )
    after = published(rows[0], early, cutoff)  # finalized exactly at C is not strictly before C
    assert (
        strict_history(rows, {**revisions, rows[0].key: after}, date(2023, 1, 2), ["regular"])[0]
        == []
    )


def test_build_on_synthetic_logs(tmp_path: Path) -> None:
    duckdb = pytest.importorskip("duckdb")
    from bil.data.pilot_sources import sha256_file
    from bil.features.box_build import PLAYER_LOG, TEAM_LOG, build_box_features

    source = tmp_path / "source"
    source.mkdir()
    team_sql = (
        "SELECT * FROM (VALUES "
        "(2023, '0022200001', '10', '20', DATE '2023-01-01', true), "
        "(2023, '0022200001', '20', '10', DATE '2023-01-01', false), "
        "(2023, '0022200002', '10', '20', DATE '2023-01-02', true), "
        "(2023, '0022200002', '20', '10', DATE '2023-01-02', false)) "
        "t(season, game_id, team_id, opp_team_id, game_date, home)"
    )
    player_values = []
    for game, day in (("0022200001", "2023-01-01"), ("0022200002", "2023-01-02")):
        player_values.append(
            f"(2023, '{game}', '7', '10', '20', DATE '{day}', 30.0, 2, 4, 1, 2, 0, 0, 5, 1, 1, 2, 0, 0, 0, 1, 2)"
        )
    player_sql = (
        "SELECT * FROM (VALUES " + ", ".join(player_values) + ") t(season, game_id, player_id, "
        "team_id, opp_team_id, game_date, min, fgm, fga, fg3m, fg3a, ftm, fta, pts, oreb, dreb, "
        "reb, ast, tov, stl, blk, pf)"
    )
    for name, sql in ((TEAM_LOG, team_sql), (PLAYER_LOG, player_sql)):
        duckdb.sql(sql).write_parquet(str(source / name))
    snapshot: Any = {
        "artifacts": [
            {
                "name": name,
                "artifact_id": f"{name}@{sha256_file(source / name)}",
                "sha256": sha256_file(source / name),
                "retrieved_at": "2026-11-23T18:04:04+00:00",
            }
            for name in (TEAM_LOG, PLAYER_LOG)
        ]
    }
    (source / "snapshot.json").write_text("{}")
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="violate the feature contract"):
        # pts 5 != 2*2+1+0 would be 5; reb 3 != 1+2 holds; break reb to force a violation
        bad = tmp_path / "bad"
        bad.mkdir()
        duckdb.sql(team_sql).write_parquet(str(bad / TEAM_LOG))
        duckdb.sql(player_sql.replace("30.0, 2, 4", "30.0, 9, 4")).write_parquet(
            str(bad / PLAYER_LOG)
        )
        (bad / "snapshot.json").write_text("{}")
        build_box_features(bad, tmp_path / "bad-out", "0" * 40, snapshot=snapshot)
    manifest = build_box_features(source, out, "0" * 40, snapshot=snapshot)
    observed = manifest["reconciliation"]["observed"]
    assert observed["appearances"] == 2
    assert observed["same_window_sql_mismatches"] == 0
    assert observed["asof_prior_count_mismatches"] == 0
    assert (
        manifest["views"]["asof_strict_features"]["cohort_status"]
        == "unavailable_historical_strict"
    )
    rows = duckdb.sql(
        f"SELECT game_id, eligible_appearances, numerator, denominator FROM '{out}/asof_retrospective_features.parquet' "
        "WHERE feature_code = 'fg3_pct' ORDER BY game_id"
    ).fetchall()
    assert rows == [("0022200001", 0, None, None), ("0022200002", 1, 1, 2)]
    strict = duckdb.sql(
        f"SELECT max(eligible_appearances) FROM '{out}/asof_strict_features.parquet'"
    ).fetchall()
    assert strict == [(0,)]
