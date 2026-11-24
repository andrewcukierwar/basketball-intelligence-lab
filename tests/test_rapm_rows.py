"""Hand-adjudicated and synthetic checks for the historical RAPM row builder."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("duckdb")

import duckdb  # noqa: E402

from bil.data.pilot_output import write_tables  # noqa: E402
from bil.data.pilot_sources import sha256_file  # noqa: E402
from bil.data.rapm_rows import build_rows  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "rapm" / "historical_rows.json"
COMMIT = "a" * 40
WHEN = "2026-01-01T00:00:00+00:00"
VERSION = {
    "revision": 1,
    "available_at": WHEN,
    "availability_basis": "capture_bound",
    "ingested_at": WHEN,
    "source_refs": [],
    "change": "upsert",
}
Mutation = Callable[[dict[str, Any]], None]


def _game_tables(data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    game = data["game"]
    revision = game["stream_revision"]
    scope = {"game_id": game["game_id"], "stream_revision": revision}
    quiet = set(data.get("no_action_seqs", []))
    events = [
        {
            **scope,
            "seq": row["start_seq"],
            "period": row["period"],
            "remaining_ms": None,
            "elapsed_ms": None,
            "observed_at": WHEN,
            "kind": data.get("first_kinds", {}).get(str(row["possession_seq"]), "shot"),
            "team_id": row["offense_team_id"],
            "home_delta": None,
            "away_delta": None,
            "revises_seq": None,
            "source_event_id": None,
            "source_refs": [],
        }
        for row in data["possessions"]
        if row["possession_seq"] not in quiet
    ]
    return {
        "event": events,
        "game": [
            {
                "game_id": game["game_id"],
                **VERSION,
                "league": "NBA",
                "season_start_year": data.get("season_start_year", 2022),
                "season_type": "regular",
                "game_date": "2022-10-18",
                "date_basis": "played",
                "home_team_id": game["home_team_id"],
                "away_team_id": game["away_team_id"],
                "neutral_site": None,
                "status": "final",
                "scheduled_tip_at": None,
                "actual_tip_at": None,
                "finalized_at": None,
                "home_final": game["home_final"],
                "away_final": game["away_final"],
            }
        ],
        "game_stream": [
            {
                "game_id": game["game_id"],
                **VERSION,
                "official_game_revision": 1,
                "parser_version": "test",
                "reconciliation_view_id": "test",
                "observed_date": "2022-10-18",
                "complete": True,
                "quality": "accepted",
                "event_count": 15,
            }
        ],
        "game_review": [
            {
                "game_id": game["game_id"],
                "season_type": "regular",
                "accepted": True,
                "reason": None,
                "strata": ["technical_free_throw", "overtime"],
                "v3_periods_reconciled": 4,
                "v3_box_final_match": True,
                "v3_periods_match": True,
                "v3_substitutions_match": True,
            }
        ],
        "lineup": [{**scope, **row, "player_ids": row["player_ids"]} for row in data["lineups"]],
        "stint": [{**scope, **row} for row in data["stints"]],
        "possession": [{**scope, "end_reason": "test", **row} for row in data["possessions"]],
        "score_allocation": [
            {**scope, "attribution_rule": "test", **row} for row in data["score_allocations"]
        ],
    }


def _quarantined_game(season: int = 2022) -> dict[str, list[dict[str, Any]]]:
    base = _game_tables(json.loads(FIXTURE.read_text(encoding="utf-8")))
    game = {**base["game"][0], "game_id": "0022200002", "home_final": 0, "away_final": 0}
    game["season_start_year"] = season
    game["home_team_id"] = game["away_team_id"] = None  # ADR-0017: quarantined, no home flag
    stream = {**base["game_stream"][0], "game_id": "0022200002", "complete": False}
    stream["quality"] = "quarantined"
    review = {**base["game_review"][0], "game_id": "0022200002", "accepted": False}
    review["reason"] = "parser_error"
    review["strata"] = []
    return {"game": [game], "game_stream": [stream], "game_review": [review]}


def _pilot(
    tmp_path: Path, mutate: Mutation | None = None, season: int | None = 2022
) -> tuple[Path, str]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if mutate:
        mutate(data)
    pilot = tmp_path / "pilot"
    pilot.mkdir()
    staging = tmp_path / "staging"
    staging.mkdir()
    with duckdb.connect() as connection:
        connection.execute("SET TimeZone = 'UTC'")
        artifacts = write_tables(
            connection,
            [_game_tables(data), _quarantined_game(data.get("season_start_year", 2022))],
            staging,
            pilot,
        )
    manifest = {
        "code_commit": COMMIT,
        "parser": "test",
        "availability": "retrospective_capture_bound",
        "source_snapshot_sha256": "b" * 64,
        "output_artifacts": artifacts,
    }
    if season is not None:
        manifest["season_start_year"] = season
    (pilot / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return pilot, sha256_file(pilot / "manifest.json")


def _read(path: Path, sql: str) -> list[tuple[Any, ...]]:
    return duckdb.connect().execute(sql.replace("@", str(path))).fetchall()


def test_fixture_dispositions_rows_and_totals(tmp_path: Path) -> None:
    pilot, pin = _pilot(tmp_path)
    output = tmp_path / "out"
    manifest = build_rows(pilot, output, COMMIT, pin)
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))["expected"]

    dispositions = _read(
        output,
        "select possession_seq, reason, control_points, exposure "
        "from '@/possession_disposition.parquet' order by 1",
    )
    assert dispositions == [
        (row["possession_seq"], row["reason"], row["control_points"], row["exposure"])
        for row in expected["dispositions"]
    ]
    rows = _read(
        output,
        "select possession_seq, offense_lineup_id, defense_lineup_id, model_points, exposure, "
        "weight from '@/model_row.parquet' order by 1",
    )
    assert rows == [
        (
            row["possession_seq"],
            row["offense_lineup_id"],
            row["defense_lineup_id"],
            row["model_points"],
            row["exposure"],
            float(row["weight"]),
        )
        for row in expected["model_rows"]
    ]
    game = json.loads(FIXTURE.read_text(encoding="utf-8"))["game"]
    totals = _read(
        output,
        "select home_modeled_points, home_other_control_points, home_unassigned_dead_ball_points,"
        " home_unresolved_points, home_final, home_model_offense_exposure,"
        " away_modeled_points, away_other_control_points, away_unassigned_dead_ball_points,"
        " away_unresolved_points, away_final, away_model_offense_exposure"
        " from '@/game_reconciliation.parquet' where accepted",
    )[0]
    for offset, team in ((0, game["home_team_id"]), (6, game["away_team_id"])):
        want = next(row for row in expected["team_totals"] if row["team_id"] == team)
        assert totals[offset : offset + 6] == (
            want["modeled_points"],
            want["other_control_points"],
            want["unassigned_dead_ball_points"],
            want["unresolved_points"],
            want["final_points"],
            want["model_offense_exposure"],
        )
    assert not any(manifest["identity_violations"].values())  # type: ignore[attr-defined]


def test_row_content_provenance_and_manifest(tmp_path: Path) -> None:
    pilot, pin = _pilot(tmp_path)
    output = tmp_path / "out"
    manifest = build_rows(pilot, output, COMMIT, pin)
    row = _read(
        output,
        "select game_revision, game_date::varchar, season_type, offense_player_ids, "
        "defense_player_ids, stream_availability_basis, period, start_seq, end_seq "
        "from '@/model_row.parquet' where possession_seq = 6",
    )[0]
    assert row == (
        1,
        "2022-10-18",
        "regular",
        ["21", "22", "23", "24", "25"],
        ["11", "12", "13", "14", "17"],
        "capture_bound",
        1,
        13,
        15,
    )
    games = _read(
        output,
        "select game_id, accepted, quarantine_reason, possessions, allocations "
        "from '@/game_reconciliation.parquet' order by 1",
    )
    assert games == [("0022200002", False, "parser_error", 0, 0), ("0022209999", True, None, 6, 6)]

    recorded = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert recorded["pilot_manifest_sha256"] == pin
    assert recorded["unit_exposure"] == "one_full_opportunity_per_eligible_possession"
    assert recorded["evidence_tier"] == "retrospective_capture_bound"
    for artifact in recorded["output_artifacts"]:
        assert sha256_file(output / artifact["filename"]) == artifact["sha256"]
    summary = recorded["reconciliation"]
    assert summary["all|all"]["games_expected"] == 2
    assert summary["all|all"]["games_quarantined"] == 1
    assert summary["regular|overtime"]["eligible_possessions"] == 3
    assert summary["regular|overtime"]["multiple_lineups_control_points"] == 3
    assert summary["regular|overtime"]["score_unresolved_points"] == 2
    assert summary["regular|technical_free_throw"]["score_modeled_points"] == 4
    assert summary["all|all"]["final_points"] == 12
    assert not (output / ".staging").exists()
    assert manifest["build_id"] == recorded["build_id"]


def test_rebuild_is_content_addressed(tmp_path: Path) -> None:
    pilot, pin = _pilot(tmp_path)
    first = build_rows(pilot, tmp_path / "one", COMMIT, pin)
    second = build_rows(pilot, tmp_path / "two", "c" * 40, pin)
    assert first["build_id"] == second["build_id"]
    assert [row["sha256"] for row in first["output_artifacts"]] == [  # type: ignore[attr-defined]
        row["sha256"]
        for row in second["output_artifacts"]  # type: ignore[attr-defined]
    ]


def test_requires_pinned_manifest_and_commit(tmp_path: Path) -> None:
    pilot, pin = _pilot(tmp_path)
    with pytest.raises(ValueError, match="pinned digest"):
        build_rows(pilot, tmp_path / "out", COMMIT, "0" * 64)
    with pytest.raises(ValueError, match="full Git commit"):
        build_rows(pilot, tmp_path / "out", "abc", pin)
    assert not (tmp_path / "out").exists()


def test_table_that_differs_from_manifest_is_rejected(tmp_path: Path) -> None:
    pilot, pin = _pilot(tmp_path)
    with (pilot / "possession.parquet").open("ab") as handle:
        handle.write(b"x")
    with pytest.raises(ValueError, match="possession differs"):
        build_rows(pilot, tmp_path / "out", COMMIT, pin)


def _duplicate_score(data: dict[str, Any]) -> None:
    data["score_allocations"].append(copy.deepcopy(data["score_allocations"][0]))
    data["game"]["home_final"] += 2


def _no_action(data: dict[str, Any]) -> None:
    data["no_action_seqs"] = [5]


def _equal_gap_and_overlap(data: dict[str, Any]) -> None:
    """Possession 5 spans seqs 10-13. Its stints still cover three seqs: overlap 1, gap 1."""
    stints = data["stints"]
    last = stints.pop()
    template = {**last, "end_elapsed_ms": last["start_elapsed_ms"]}
    stints += [
        {**template, "stint_seq": 3, "start_seq": 6, "end_seq": 11},
        {**template, "stint_seq": 4, "start_seq": 10, "end_seq": 12},
        {**template, "stint_seq": 5, "start_seq": 13, "end_seq": 15},
    ]


def _period_end_start(data: dict[str, Any]) -> None:
    data["first_kinds"] = {"5": "period_end"}


def _stint_gap(data: dict[str, Any]) -> None:
    data["stints"][2]["start_seq"] = 7
    data["stints"][2]["end_seq"] = 15


def _final_score_gap(data: dict[str, Any]) -> None:
    data["game"]["away_final"] += 1


def _control_by_defense(data: dict[str, Any]) -> None:
    data["score_allocations"][0]["scoring_team_id"] = "200"
    data["game"]["home_final"] -= 2
    data["game"]["away_final"] += 2


def _unlinked_control(data: dict[str, Any]) -> None:
    data["score_allocations"][0]["possession_seq"] = None


def _link_to_missing_possession(data: dict[str, Any]) -> None:
    data["score_allocations"][0]["possession_seq"] = 99


def _repeated_player(data: dict[str, Any]) -> None:
    data["lineups"][1]["player_ids"][4] = "11"


def _shared_player(data: dict[str, Any]) -> None:
    data["lineups"][3]["player_ids"][4] = "11"


@pytest.mark.parametrize(
    ("mutation", "check"),
    [
        (_duplicate_score, "score_allocations_classified_once"),
        (_equal_gap_and_overlap, r"failed.*\{'stints_contiguous_within_period': 2\}"),
        (_stint_gap, "accepted_possessions_covered_once_by_actual_stints"),
        (_final_score_gap, "allocations_reconcile_to_final_score_by_side"),
        (_control_by_defense, "control_points_scored_by_offense"),
        (_unlinked_control, "score_allocations_classified_once"),
        (_link_to_missing_possession, "score_allocations_classified_once"),
        (_repeated_player, "lineups_have_five_distinct_positive_ids"),
        (_shared_player, "model_rows_unique_unit_weight_and_valid_points"),
    ],
)
def test_pilot_ledger_gaps_block_the_build(tmp_path: Path, mutation: Mutation, check: str) -> None:
    pilot, pin = _pilot(tmp_path, mutation)
    output = tmp_path / "out"
    with pytest.raises(ValueError, match=check):
        build_rows(pilot, output, COMMIT, pin)
    assert not output.exists()


def test_no_action_possession_is_excluded_but_kept_in_the_ledger(tmp_path: Path) -> None:
    pilot, pin = _pilot(tmp_path, _no_action)
    output = tmp_path / "out"
    manifest = build_rows(pilot, output, COMMIT, pin, "no_action")
    assert manifest["variant"] == "no_action"
    rows = _read(
        output,
        "select possession_seq, reason, exposure, control_points, action_events, "
        "offense_lineup_id is null from '@/possession_disposition.parquet' order by 1",
    )
    assert rows[4] == (5, "no_action", 0, 0, 0, True)
    assert all(row[4] == 1 for row in rows if row[0] != 5)
    assert _read(output, "select possession_seq from '@/model_row.parquet' order by 1") == [
        (1,),
        (6,),
    ]
    games = _read(
        output,
        "select no_action, eligible, home_modeled_points + away_modeled_points "
        "from '@/game_reconciliation.parquet' where accepted",
    )
    assert games == [(1, 2, 4)]
    summary = manifest["reconciliation"]
    assert summary["all|all"]["no_action_possessions"] == 1  # type: ignore[index]
    assert not any(manifest["identity_violations"].values())  # type: ignore[attr-defined]


def test_ineligible_dispositions_carry_no_lineup_ids(tmp_path: Path) -> None:
    pilot, pin = _pilot(tmp_path)
    output = tmp_path / "out"
    build_rows(pilot, output, COMMIT, pin)
    rows = _read(
        output,
        "select reason, exposure, offense_lineup_id is null, defense_lineup_id is null "
        "from '@/possession_disposition.parquet' order by possession_seq",
    )
    assert [(r[0], r[1]) for r in rows] == [
        ("eligible", 1),
        ("multiple_lineups", 0),
        ("pilot_excluded", 0),
        ("unresolved_control", 0),
        ("eligible", 1),
        ("eligible", 1),
    ]
    assert [(r[2], r[3]) for r in rows] == [(e, e) for e in (False, True, True, True, False, False)]


def test_period_end_start_variant_excludes_only_those_possessions(tmp_path: Path) -> None:
    pilot, pin = _pilot(tmp_path, _period_end_start)
    output = tmp_path / "out"
    manifest = build_rows(pilot, output, COMMIT, pin, "period_end_start")
    assert manifest["variant"] == "period_end_start"
    rows = _read(
        output,
        "select possession_seq, reason, exposure, offense_lineup_id is null "
        "from '@/possession_disposition.parquet' order by 1",
    )
    assert rows[4] == (5, "period_end_start", 0, True)
    assert [r[1] for r in rows if r[0] != 5] == [
        "eligible",
        "multiple_lineups",
        "pilot_excluded",
        "unresolved_control",
        "eligible",
    ]
    assert _read(output, "select possession_seq from '@/model_row.parquet' order by 1") == [
        (1,),
        (6,),
    ]
    assert manifest["reconciliation"]["all|all"]["period_end_start_possessions"] == 1  # type: ignore[index]
    assert not any(manifest["identity_violations"].values())  # type: ignore[attr-defined]


def test_canonical_is_the_default_and_keeps_every_pilot_eligible_possession(tmp_path: Path) -> None:
    def both(data: dict[str, Any]) -> None:
        _no_action(data)
        _period_end_start(data)
        data["first_kinds"] = {}

    pilot, pin = _pilot(tmp_path, both)
    default = build_rows(pilot, tmp_path / "d", COMMIT, pin)
    assert default["variant"] == "canonical"
    assert default["reconciliation"]["all|all"]["eligible_possessions"] == 3  # type: ignore[index]
    shifted = build_rows(pilot, tmp_path / "p", COMMIT, pin, "period_end_start")
    assert shifted["reconciliation"]["all|all"]["eligible_possessions"] == 3  # type: ignore[index]
    dropped = build_rows(pilot, tmp_path / "n", COMMIT, pin, "no_action")
    assert dropped["reconciliation"]["all|all"]["eligible_possessions"] == 2  # type: ignore[index]
    assert dropped["build_id"] != default["build_id"]
    assert shifted["build_id"] != default["build_id"]
    with pytest.raises(ValueError, match="variant"):
        build_rows(pilot, tmp_path / "x", COMMIT, pin, "Z")


@pytest.mark.parametrize("season", [2018, 2021, 2023, 2024])
def test_any_pinned_season_builds_from_its_manifest(tmp_path: Path, season: int) -> None:
    def set_season(data: dict[str, Any]) -> None:
        data["season_start_year"] = season

    pilot, pin = _pilot(tmp_path, set_season, season)
    manifest = build_rows(pilot, tmp_path / "out", COMMIT, pin)
    assert manifest["season_start_year"] == season
    assert manifest["reconciliation"]["all|all"]["eligible_possessions"] == 3  # type: ignore[index]


def test_manifest_season_must_match_the_game_ledger(tmp_path: Path) -> None:
    pilot, pin = _pilot(tmp_path, season=2019)
    with pytest.raises(ValueError, match="stream_status_matches_review"):
        build_rows(pilot, tmp_path / "out", COMMIT, pin)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("season", [2025, 2026, 2005, 1999])
def test_holdout_and_unpinned_seasons_are_refused(tmp_path: Path, season: int) -> None:
    pilot, pin = _pilot(tmp_path, season=season)
    with pytest.raises(ValueError, match="holdout|No pinned sources"):
        build_rows(pilot, tmp_path / "out", COMMIT, pin)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("season", [None, "2022", True])
def test_manifest_must_name_an_integer_season(tmp_path: Path, season: object) -> None:
    pilot, _ = _pilot(tmp_path, season=None)
    path = pilot / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if season is not None:
        manifest["season_start_year"] = season
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="season_start_year"):
        build_rows(pilot, tmp_path / "out", COMMIT, sha256_file(path))
