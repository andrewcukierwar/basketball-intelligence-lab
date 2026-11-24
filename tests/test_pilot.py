"""Synthetic tests for the optional offline data pilot."""

from __future__ import annotations

import csv
import io
import json
import tarfile
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("duckdb")
pytest.importorskip("pbpstats")

import duckdb  # noqa: E402
import requests  # noqa: E402

from bil.data import (  # noqa: E402
    pilot,
    pilot_normalize,  # noqa: E402
    pilot_parser,
    pilot_sources,
    pilot_starters,
)
from bil.data.pilot import compare_periods, summarize_reviews  # noqa: E402
from bil.data.pilot_inputs import (  # noqa: E402
    GameBox,
    GameIssue,
    PlayerBox,
    RawEvent,
    V3Game,
    deduplicate_events,
    v2_substitutions,
    v3_games,
)
from bil.data.pilot_normalize import normalize_game  # noqa: E402
from bil.data.pilot_output import write_tables  # noqa: E402


def test_snapshot_checks_bytes_and_never_overwrites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = tmp_path / "mock.csv"
    content = b"synthetic"
    original.write_bytes(content)
    source = pilot_sources.Source(
        "mock.csv", original.as_uri(), sha256(content).hexdigest(), len(content), "synthetic"
    )
    monkeypatch.setattr(pilot_sources, "season_sources", lambda _year: (source,))
    target = tmp_path / "snapshot"
    captured = pilot_sources.capture_snapshot(target)
    assert pilot_sources.load_snapshot(target) == captured
    with pytest.raises(FileExistsError):
        pilot_sources.capture_snapshot(target)
    assert pilot_sources.load_snapshot(target) == captured

    (target / source.name).write_bytes(b"synthetix")
    with pytest.raises(ValueError, match="Source bytes differ"):
        pilot_sources.load_snapshot(target)


def test_source_duplicates_preserve_locators_and_substitution_signature() -> None:
    fields = {
        "EVENTNUM": "14",
        "EVENTMSGTYPE": "8",
        "PERIOD": "3",
        "PLAYER1_TEAM_ID": "200",
        "PLAYER1_ID": "21",
        "PLAYER2_ID": "26",
    }
    first = RawEvent(fields, [2])
    duplicate = RawEvent(fields.copy(), [3])
    parsed = deduplicate_events([first, duplicate])
    assert parsed[14].row_numbers == [2, 3]
    assert first.row_numbers == [2]
    assert v2_substitutions(parsed) == Counter({("3", "200", "21"): 1})
    with pytest.raises(GameIssue, match="distinct rows") as failure:
        deduplicate_events([first, RawEvent({**fields, "PLAYER2_ID": "27"}, [3])])
    assert failure.value.event_num == 14


@dataclass
class Event:
    event_num: int
    event_type: int
    period: int
    seconds_remaining: float
    current_players: dict[int, list[int]]
    score: dict[int, int]
    team_id: int | None = None
    player1_id: int | None = None
    is_technical_ft: bool = False
    trigger: Event | None = None
    count_as_possession: bool = True

    @property
    def event_for_efficiency_stats(self) -> Event:
        return self.trigger if self.trigger is not None else self


@dataclass
class Possession:
    events: list[Event]
    offense_team_id: int


def synthetic_game() -> tuple[GameBox, dict[int, PlayerBox], list[Event], list[Possession]]:
    home, away = 100, 200
    game = GameBox("0022209999", date(2023, 1, 3), home, away, 3, 0)
    before = {home: [11, 12, 13, 14, 15], away: [21, 22, 23, 24, 25]}
    after = {home: before[home], away: [22, 23, 24, 25, 26]}
    foul = Event(2, 6, 1, 718, before, {}, away)
    events = [
        Event(1, 12, 1, 720, before, {}),
        foul,
        Event(3, 8, 1, 718, after, {}, away, 21),
        Event(4, 3, 1, 718, after, {home: 1}, home, 11, True, foul),
        Event(5, 1, 1, 701, after, {home: 3}, home, 11),
        Event(6, 2, 1, 690, after, {home: 3}, away, 22),
        Event(7, 13, 1, 0, after, {home: 3}),
    ]
    possessions = [Possession(events[:5], home), Possession(events[5:], away)]
    for period in range(2, 5):
        start = len(events) + 1
        period_events = [
            Event(start, 12, period, 720, after, {home: 3}),
            Event(start + 1, 13, period, 0, after, {home: 3}),
        ]
        possessions.append(Possession(period_events, home))
        events.extend(period_events)
    roster = {player: PlayerBox(home, 2_880_000, 3) for player in before[home]}
    roster.update({player: PlayerBox(away, 2_880_000, -3) for player in (22, 23, 24, 25)})
    roster[21] = PlayerBox(away, 2000, -1)
    roster[26] = PlayerBox(away, 2_878_000, -2)
    return game, roster, events, possessions


def test_reconstruct_and_export_substitution_and_technical_point(tmp_path: Path) -> None:
    game, roster, events, possessions = synthetic_game()
    raw = {
        event.event_num: RawEvent(
            {"PLAYER1_TEAM_ID": "200", "PLAYER1_ID": "21", "PLAYER2_ID": "26"}
            if event.event_type == 8
            else {},
            [event.event_num + 1],
        )
        for event in events
    }
    result = normalize_game(game, roster, raw, events, possessions, "synthetic")
    assert compare_periods(events, game, dict.fromkeys(range(1, 5), (3, 0))) == (True, 4)
    assert compare_periods(events, game, {1: (2, 0), 2: (3, 0), 3: (3, 0), 4: (3, 0)}) == (
        False,
        3,
    )
    first, second = result["score_allocation"]
    assert first["possession_seq"] is None and first["credited_stint_seq"] == 1
    assert first["attribution_rule"] == "free_throw_trigger_lineup"
    assert second["possession_seq"] == 1 and second["credited_stint_seq"] == 2
    assert result["stint"][0]["end_seq"] == 4 and result["stint"][1]["start_elapsed_ms"] == 2000

    output = tmp_path / "data"
    output.mkdir()
    with duckdb.connect() as connection:
        artifacts = write_tables(connection, [result], tmp_path, output)
        assert {row["filename"]: row["row_count"] for row in artifacts}["event.parquet"] == len(
            events
        )
        assert connection.execute(
            "SELECT count(*) FROM read_parquet(?) WHERE array_length(player_ids) = 5",
            [str(output / "lineup.parquet")],
        ).fetchone() == (3,)
        assert connection.execute(
            "SELECT count(*) FROM read_parquet(?)", [str(output / "quality_issue.parquet")]
        ).fetchone() == (0,)

    altered = dict(roster)
    altered[21] = PlayerBox(game.away_id, 2000, 0)
    with pytest.raises(GameIssue) as rejected:
        normalize_game(game, altered, raw, events, possessions, "synthetic")
    assert rejected.value.code == "player_plus_minus_mismatch"

    events[5].player1_id = 21
    with pytest.raises(GameIssue) as off_court:
        normalize_game(game, roster, raw, events, possessions, "synthetic")
    assert off_court.value.code == "shooter_outside_lineup"
    events[5].player1_id = 22

    events[2].seconds_remaining = 719
    with pytest.raises(GameIssue) as unresolved:
        normalize_game(game, roster, raw, events, possessions, "synthetic")
    assert unresolved.value.code == "unresolved_clock_reset"


def test_strata_distinguish_comparison_from_game_acceptance() -> None:
    base = {
        "season_type": "regular",
        "accepted": False,
        "reason": "player_plus_minus_mismatch",
        "strata": ["overtime"],
        "v3_periods_reconciled": 5,
        "v3_box_final_match": True,
        "v3_periods_match": True,
        "v3_substitutions_match": True,
    }
    report = summarize_reviews(
        [
            base,
            {**base, "v3_periods_match": False},
            {**base, "v3_periods_match": None, "v3_periods_reconciled": 0},
        ]
    )
    strata = report["comparison_strata"]
    assert isinstance(strata, dict)
    overtime = strata["regular:overtime"]
    assert overtime["quarantined"] == 3 and overtime["v3_periods_checked"] == 2
    assert overtime["v3_periods_matched"] == overtime["v3_periods_mismatched"] == 1
    assert overtime["v3_periods_not_checked"] == 1


def test_build_routes_duckdb_spills_to_private_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "snapshot.json").write_text("{}", encoding="utf-8")
    output = tmp_path / "output"

    def games(
        connection: duckdb.DuckDBPyConnection, *args: object, **options: object
    ) -> list[object]:
        staging = args[3]
        assert isinstance(staging, Path)
        assert staging.parent == output.parent
        assert connection.execute("SELECT current_setting('temp_directory')").fetchone() == (
            str(staging / "duckdb-spill"),
        )
        assert args[-1] == 2023 and options == {"order_repair": False}
        return []

    monkeypatch.setattr(
        pilot, "load_snapshot", lambda _path: {"artifacts": [], "season_start_year": 2023}
    )
    monkeypatch.setattr(pilot, "_season_games", games)
    pilot.build_pilot(tmp_path, output, "0" * 40)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["output", "snapshot.json"]


def test_offline_parser_blocks_library_network_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    game, _, _, _ = synthetic_game()

    def request(*args: object) -> None:
        requests.get("https://invalid.example")

    monkeypatch.setattr(pilot_parser, "StatsNbaPossessionLoader", request)
    with pytest.raises(GameIssue) as rejected:
        pilot_parser.parse_game(
            game,
            {1: RawEvent({"EVENTNUM": "1"}, [2])},
            {game.home_id: [], game.away_id: []},
            tmp_path,
        )
    assert rejected.value.code == "offline_parser_request"


def test_v3_order_follows_action_ids_and_keeps_first_event_number(tmp_path: Path) -> None:
    fields = ["gameId", "actionId", "actionNumber", "period", "teamId", "personId"]
    fields += ["actionType", "subType", "scoreHome", "scoreAway"]
    rows = [
        ["22200001", "3", "9", "1", "", "", "Turnover", "", "", ""],
        ["22200001", "1", "2", "1", "", "", "period", "start", "", ""],
        ["22200001", "4", "9", "1", "", "", "", "", "", ""],
        ["22200001", "2", "7", "1", "", "", "Made Shot", "", "", ""],
        ["22200001", "5", "11", "1", "", "", "period", "end", "2", "0"],
    ]
    text = io.StringIO()
    writer = csv.writer(text)
    writer.writerow(fields)
    writer.writerows(rows)
    data = text.getvalue().encode()
    archive = tmp_path / "v3.tar.xz"
    with tarfile.open(archive, "w:xz") as bundle:
        member = tarfile.TarInfo("v3.csv")
        member.size = len(data)
        bundle.addfile(member, io.BytesIO(data))
    game = v3_games(archive)["0022200001"]
    assert game.order == [2, 7, 9, 11]
    assert game.periods == {1: (2, 0)}


class FakeLoader:
    def __init__(self, event_nums: list[int]) -> None:
        self.source_data = {"resultSets": [{"headers": ["GAME_ID", "EVENTNUM"], "rowSet": []}]}
        self.source_data["resultSets"][0]["rowSet"] = [["g", num] for num in event_nums]
        self.saved = 0

    def _save_data_to_file(self) -> None:
        self.saved += 1


def test_archived_order_replaces_live_reorder_only_for_identical_events() -> None:
    applied: list[bool] = []
    reorder = pilot_parser._archived_order([1, 3, 2], applied)
    loader = FakeLoader([1, 2, 3])
    reorder(loader)
    assert [row[1] for row in loader.source_data["resultSets"][0]["rowSet"]] == [1, 3, 2]
    assert loader.saved == 1 and applied == [True]

    for order in ([1, 3], [1, 3, 2, 4], [1, 3, 3]):
        blocked: list[bool] = []
        with pytest.raises(GameIssue) as rejected:
            pilot_parser._archived_order(order, blocked)(FakeLoader([1, 2, 3]))
        assert rejected.value.code == "unresolved_event_order" and not blocked


def test_starter_candidates_extend_or_trim_partial_sets() -> None:
    roster = {player: PlayerBox(100, 60_000, 0) for player in range(1, 9)}
    roster[9] = PlayerBox(100, 0, 0)
    roster[21] = PlayerBox(200, 60_000, 0)
    assert pilot_starters.candidate_starters(100, (1, 2, 3, 4), roster) == [
        (1, 2, 3, 4, player) for player in (5, 6, 7, 8)
    ]
    assert len(pilot_starters.candidate_starters(100, (1, 2, 3), roster)) == 10
    assert pilot_starters.candidate_starters(100, (1, 2, 3, 4, 5, 6), roster)[0] == (1, 2, 3, 4, 5)
    assert len(pilot_starters.candidate_starters(100, (1, 2, 3, 4, 5, 6), roster)) == 6


def test_choose_starters_requires_one_reconstruction() -> None:
    roster = {player: PlayerBox(100, 60_000, 0) for player in range(1, 8)}
    gap = pilot_parser.StarterGap(5, {100: (1, 2, 3, 4)})

    def attempt_with(correct: set[int], same: bool) -> Callable[[pilot_parser.Starters], str]:
        def attempt(starters: pilot_parser.Starters) -> str:
            if not starters:
                raise gap
            chosen = starters[(5, 100)]
            if chosen[-1] not in correct:
                raise GameIssue("player_minutes_mismatch", "wrong starter")
            return "same" if same else str(chosen)

        return attempt

    choice = pilot_starters.choose_starters(attempt_with({6}, False), roster, str)
    assert choice.starters == {(5, 100): (1, 2, 3, 4, 6)} and choice.candidates_tried == 3
    assert not choice.immaterial
    assert pilot_starters.choose_starters(attempt_with({5, 7}, True), roster, str).immaterial
    for correct, code in ((set(), "unresolved_starters"), ({5, 7}, "ambiguous_starters")):
        with pytest.raises(GameIssue) as rejected:
            pilot_starters.choose_starters(attempt_with(correct, False), roster, str)
        assert rejected.value.code == code


def test_conflicting_score_leaves_possession_unresolved(tmp_path: Path) -> None:
    game, roster, events, possessions = synthetic_game()
    raw = {
        event.event_num: RawEvent(
            {"PLAYER1_TEAM_ID": "200", "PLAYER1_ID": "21", "PLAYER2_ID": "26"}
            if event.event_type == 8
            else {},
            [event.event_num + 1],
        )
        for event in events
    }
    # Give the home team's made-shot possession to the away team.
    possessions[0] = Possession(possessions[0].events, game.away_id)
    rows = normalize_game(game, roster, raw, events, possessions, "fixture")
    statuses = [row["status"] for row in rows["possession"]]
    assert statuses[0] == "unresolved" and statuses.count("unresolved") == 1
    reasons = [row["possession_reason"] for row in rows["score_allocation"]]
    assert reasons == ["unassigned_dead_ball", "unresolved"]
    assert all(row["possession_seq"] is None for row in rows["score_allocation"])

    flagged = normalize_game(game, roster, raw, events, possessions, "fixture", frozenset({1}))
    assert [row["status"] for row in flagged["possession"]][:2] == ["unresolved", "unresolved"]


@dataclass
class LinkedPossession:
    offense_team_id: int
    events: list[object]
    previous_possession: LinkedPossession | None = None
    next_possession: LinkedPossession | None = None


def test_back_to_back_possessions_are_recorded_not_raised() -> None:
    chain = [LinkedPossession(team, []) for team in (100, 200, 200, 100, 100)]
    for before, after in zip(chain, chain[1:], strict=False):
        before.next_possession, after.previous_possession = after, before

    class FlagrantFoul(pilot_parser.Foul):  # type: ignore[misc]
        is_flagrant = True

    FlagrantFoul.__abstractmethods__ = frozenset()
    # pbpstats exempts a pair when the earlier possession or the one before it has a flagrant.
    chain[1].events.append(object.__new__(FlagrantFoul))
    flagged: set[int] = set()

    class Loader:
        items = chain

    pilot_parser._record_back_to_back(flagged)(Loader())
    # The 200-200 pair is exempt because of the flagrant foul; the 100-100 pair is flagged.
    assert flagged == {3, 4}


def test_same_offense_pairs_require_unresolved_rows_or_a_nearby_flagrant(tmp_path: Path) -> None:
    from bil.data.pilot_check import _same_offense_violations

    raw = b"GAME_ID,EVENTNUM,EVENTMSGTYPE,EVENTMSGACTIONTYPE\n22200001,50,6,14\n22200001,51,6,1\n"
    with tarfile.open(tmp_path / "nbastats_2022.tar.xz", "w:xz") as archive:
        member = tarfile.TarInfo("events.csv")
        member.size = len(raw)
        archive.addfile(member, io.BytesIO(raw))

    with duckdb.connect() as connection:
        connection.execute(
            """
            create table possession as
            select '0022200001' as game_id, 1 as stream_revision, * from (values
                (1, 1, 1, 3, '100', 'accepted'),
                (2, 1, 4, 6, '200', 'accepted'),
                (3, 1, 6, 8, '200', 'excluded'),
                (4, 2, 8, 10, '200', 'accepted')
            ) as rows(possession_seq, period, start_seq, end_seq, offense_team_id, status);

            create table event as
            select '0022200001' as game_id, 1 as stream_revision,
                   2 as seq, 'foul' as kind, '50' as source_event_id;
            """
        )
        # A flagrant in the possession before the earlier one is an exemption.
        assert _same_offense_violations(connection, tmp_path) == 0
        connection.execute("update event set seq = 4")
        assert _same_offense_violations(connection, tmp_path) == 0
        connection.execute("update event set source_event_id = '51'")
        assert _same_offense_violations(connection, tmp_path) == 1
        connection.execute("update event set seq = 3, source_event_id = '50'")
        assert _same_offense_violations(connection, tmp_path) == 1
        connection.execute("update event set seq = 6")
        assert _same_offense_violations(connection, tmp_path) == 1
        connection.execute("update possession set status = 'unresolved' where possession_seq = 3")
        assert _same_offense_violations(connection, tmp_path) == 1
        connection.execute("update possession set status = 'unresolved' where possession_seq = 2")
        assert _same_offense_violations(connection, tmp_path) == 0


def test_box_credit_search_moves_only_same_clock_credit(monkeypatch: pytest.MonkeyPatch) -> None:
    from bil.data.pilot_normalize import CreditChoice, TimedEvent, choose_box_credits

    before = ((1, 2, 3, 4, 5), (21, 22, 23, 24, 25))
    after = ((1, 2, 3, 4, 6), (21, 22, 23, 24, 25))
    events = [
        TimedEvent(Event(n, 3, 1, 600, {}, {}), n, 600_000, 120_000, lineup)  # type: ignore[arg-type]
        for n, lineup in ((1, before), (2, after))
    ]
    roster = {player: PlayerBox(100, 0, 0) for player in range(1, 7)}
    roster.update({player: PlayerBox(200, 0, 0) for player in range(21, 26)})
    pm = Counter({player: 1 for player in range(1, 6)})
    pm.update({player: -1 for player in range(21, 26)})
    choice = CreditChoice(0, 0, 1, events[0], tuple(events))

    # The box credits the point to the lineup after the same-clock substitution.
    roster.update({player: PlayerBox(100, 0, 1) for player in (1, 2, 3, 4, 6)})
    roster.update({player: PlayerBox(200, 0, -1) for player in range(21, 26)})
    assert choose_box_credits(pm, roster, [choice]) == [(choice, events[1])]

    # Two credit choices at different clocks that each reproduce the box are ambiguous.
    later = [
        TimedEvent(item.source, item.seq + 10, 500_000, 220_000, item.lineups) for item in events
    ]
    second = CreditChoice(1, 0, 1, later[0], tuple(later))
    with pytest.raises(GameIssue, match="2 same-clock credit sets"):
        choose_box_credits(pm, roster, [choice, second])

    monkeypatch.setattr(pilot_normalize, "MAX_CREDIT_COMBINATIONS", 0)
    with pytest.raises(GameIssue, match="exceeded 0 combinations"):
        choose_box_credits(pm, roster, [choice])
    monkeypatch.undo()

    roster[6] = PlayerBox(100, 0, 3)
    with pytest.raises(GameIssue, match="2 players"):
        choose_box_credits(pm, roster, [choice])


def test_minutes_tolerance_grows_with_truncated_substitution_clocks() -> None:
    from bil.data.pilot_normalize import reconcile_minutes

    roster = {7: PlayerBox(100, 600_000, 0)}
    minutes = Counter({7: 603_500})
    with pytest.raises(GameIssue, match="1 players"):
        reconcile_minutes(minutes, roster)
    with pytest.raises(GameIssue):
        reconcile_minutes(minutes, roster, Counter({7: 1}))
    reconcile_minutes(minutes, roster, Counter({7: 2}))


def test_check_build_passes_synthetic_output_and_catches_defects(tmp_path: Path) -> None:
    from bil.data.pilot_check import check_build

    game, roster, events, possessions = synthetic_game()
    raw = {
        event.event_num: RawEvent(
            {"PLAYER1_TEAM_ID": "200", "PLAYER1_ID": "21", "PLAYER2_ID": "26"}
            if event.event_type == 8
            else {},
            [event.event_num + 1],
        )
        for event in events
    }
    rows = normalize_game(game, roster, raw, events, possessions, "synthetic")
    source: pilot_sources.Artifact = {  # type: ignore[typeddict-item]
        "artifact_id": "box",
        "retrieved_at": "2026-11-23T00:00:00+00:00",
    }
    when = "2026-11-23T00:00:00+00:00"
    rows["game"] = [pilot._game_row(game, "regular", source, when)]
    rows["game_stream"] = [
        {
            "game_id": game.game_id,
            **pilot._version(when, [source], []),
            "official_game_revision": 1,
            "parser_version": "synthetic",
            "reconciliation_view_id": "synthetic",
            "observed_date": game.played_date.isoformat(),
            "complete": True,
            "quality": "accepted",
            "event_count": len(rows["event"]),
        }
    ]
    rows["game_review"] = [
        {
            "game_id": game.game_id,
            "season_type": "regular",
            "accepted": True,
            "reason": None,
            "strata": [],
            "v3_periods_reconciled": 4,
            "v3_box_final_match": True,
            "v3_periods_match": True,
            "v3_substitutions_match": True,
        }
    ]
    rows["quality_issue"] = []

    def build(box: dict[int, PlayerBox], name: str) -> Path:
        output, snapshot = tmp_path / name, tmp_path / f"{name}-snapshot"
        staging = tmp_path / f"{name}-staging"
        for folder in (output, snapshot, staging):
            folder.mkdir()
        with duckdb.connect() as connection:
            artifacts = write_tables(connection, [rows], staging, output)
            connection.execute(
                "CREATE TABLE logs (game_id VARCHAR, player_id BIGINT, min DOUBLE, plus_minus BIGINT)"
            )
            for player, entry in box.items():
                connection.execute(
                    "INSERT INTO logs VALUES (?, ?, ?, ?)",
                    [game.game_id, player, entry.minutes_ms / 60_000, entry.plus_minus],
                )
            connection.execute(
                "COPY logs TO ? (FORMAT PARQUET)", [str(snapshot / "player_game_logs.parquet")]
            )
        (output / "manifest.json").write_text(
            json.dumps({"output_artifacts": artifacts, "season_start_year": 2022}),
            encoding="utf-8",
        )
        return output

    output = build(roster, "valid")
    assert not any(check_build(output, tmp_path / "valid-snapshot").values())

    altered = dict(roster)
    altered[26] = PlayerBox(game.away_id, 2_870_000, -1)
    failed = check_build(build(altered, "altered"), tmp_path / "altered-snapshot")
    assert failed["player_plus_minus_exact"] == 1
    assert failed["player_minutes_within_tolerance"] == 1
    assert sum(failed.values()) == 2

    # Record a shooter who is on neither the actual nor the credited lineup.
    rows["event_actor"].append(
        {
            "game_id": game.game_id,
            "stream_revision": 1,
            "seq": rows["score_allocation"][1]["seq"],
            "slot": 1,
            "role": "shooter",
            "player_id": "26",
            "team_id": str(game.home_id),
            "source_slot": "PLAYER1_ID",
            "raw_actor_id": "26",
        }
    )
    moved = check_build(build(roster, "moved"), tmp_path / "moved-snapshot")
    assert moved["credited_lineup_contains_shooter"] == 1
    assert moved["shooters_on_court"] == 1


def _v3_archive(path: Path, rows: list[list[str]]) -> None:
    fields = ["gameId", "actionId", "actionNumber", "period", "teamId", "personId"]
    fields += ["actionType", "subType", "scoreHome", "scoreAway"]
    text = io.StringIO()
    writer = csv.writer(text)
    writer.writerow(fields)
    writer.writerows(rows)
    data = text.getvalue().encode()
    with tarfile.open(path, "w:xz") as bundle:
        member = tarfile.TarInfo("v3.csv")
        member.size = len(data)
        bundle.addfile(member, io.BytesIO(data))


def test_evidence_comparisons_count_agreement_on_synthetic_tables(tmp_path: Path) -> None:
    from bil.data import pilot_evidence

    with duckdb.connect() as connection:
        connection.execute(
            """
            create table game_review as select '0022200001' as game_id,
              ['inferred_starters'] as strata;
            create table ours as select * from (values
              ('0022200001', 2, 2, '100', 720.0, 750.0, 720000, 750000, ['1','2','3','4','5']),
              ('0022200001', 1, 1, '100', 0.0, 720.0, 0, 720000, ['1','2','3','4','6']))
              t(game_id, stint_seq, period, team, t0, t1, start_elapsed_ms, end_elapsed_ms, ids);
            create table bentes as select * from (values
              ('0022200001', 720, 740, ['1','2','3','4','5']),
              ('0022200001', 740, 750, ['1','2','3','4','7']),
              ('0022200001', 0, 720, ['1','2','3','4','6'])) t(game_id, t0, t1, ids);
            create table quality_issue as select '0022200001' as game_id,
              'inferred_starters' as code, 'period 2 team 100: 1,2,3,4,5' as detail;
            create table cdnnba as select * from (values
              ('0022200001', '0', 'substitution', 'out', '6', '100', '2', 'PT12M00.00S', '0',
               '', '', '1'),
              ('0022200001', '0', 'substitution', 'in', '5', '100', '2', 'PT12M00.00S', '0',
               '', '', '2'),
              ('0022200001', '10', 'shot', '', '1', '100', '2', 'PT11M50.00S', '100', '', '', '3'),
              ('0022200001', '12', 'turnover', '', '1', '100', '2', 'PT11M40.00S', '100',
               '', '', '4'),
              ('0022200001', '20', 'period', 'end', '0', '0', '1', 'PT00M00.00S', '0',
               '30', '20', '5'),
              ('0022200001', '21', 'period', 'end', '0', '0', '2', 'PT00M00.00S', '0',
               '50', '40', '6'))
              t(gameId, actionNumber, actionType, subType, personId, teamId, period, clock,
                possession, scoreHome, scoreAway, orderNumber);
            create table event as select * from (values
              ('0022200001', 1, 'shot', '10'), ('0022200001', 2, 'turnover', '12'),
              ('0022200001', 3, 'shot', '11'))
              t(game_id, seq, kind, source_event_id);
            create table possession as select * from (values
              ('0022200001', 1, 1, 3, '100', 'accepted'),
              ('0022200001', 2, 3, 4, '200', 'unresolved'))
              t(game_id, possession_seq, start_seq, end_seq, offense_team_id, status);
            create table datanba as select * from (values
              ('0022200001', '10', '100', '1', '1', '30', '20'),
              ('0022200001', '12', '200', '3', '2', '50', '41'),
              ('0022200001', '11', '100', '2', '2', '50', '41'))
              t(GAME_ID, evt, oftid, ord, PERIOD, hs, vs);
            create table pbpstats as select * from (values
              ('0022200001', '1', '12:00', '11:40', 'B'), ('0022200001', '1', '12:00', '11:40', 'B'))
              t(GAMEID, PERIOD, STARTTIME, ENDTIME, OPPONENT);
            """
        )
        lineups = pilot_evidence.lineup_agreement(connection)
        assert lineups["build_games_covered"] == "1 of 1"
        assert lineups["disagreements_over_2s"] != []
        assert abs(float(str(lineups["time_share"])) - 740 / 750) < 1e-9

        starters = pilot_evidence.starter_agreement(connection)
        assert starters["bentes_agree"] == 1 and starters["livedata_agree"] == 1
        assert starters["disagreements"] == []

        offense = pilot_evidence.possession_agreement(connection)
        # The turnover's data.nba offense contradicts possession 1, but liveData agrees.
        assert offense["datanba"] == {
            "accepted": {"events": 2, "agree": 1},
            "unresolved": {"events": 1, "agree": 0},
        }
        assert offense["cdnnba"] == {"accepted": {"events": 2, "agree": 2}}
        counts = offense["possession_counts_vs_pbpstats"]
        assert isinstance(counts, dict) and counts["equal"] == 1

        order = pilot_evidence.order_agreement(connection)
        assert order["v2_file_order"] == {"games": 1, "games_with_descents": 1, "descents": 1}

        # V3 alone is wrong in period 1; data.nba alone is wrong in period 2.
        for suffix in ("", "_po"):
            _v3_archive(
                tmp_path / f"nbastatsv3{suffix}_2022.tar.xz",
                [
                    ["22200001", "1", "20", "1", "", "", "period", "end", "31", "20"],
                    ["22200001", "2", "21", "2", "", "", "period", "end", "50", "40"],
                ]
                if not suffix
                else [],
            )
        scores = pilot_evidence.period_score_agreement(connection, tmp_path)
        assert scores["games_where_v3_alone_differs"] == ["0022200001"]
        assert scores["games_where_datanba_alone_differs"] == ["0022200001"]
        assert scores["periods_compared"] == 2


def _csv_archive(path: Path, header: list[str], rows: list[list[str]]) -> None:
    text = io.StringIO()
    writer = csv.writer(text)
    writer.writerow(header)
    writer.writerows(rows)
    data = text.getvalue().encode()
    with tarfile.open(path, "w:xz") as bundle:
        member = tarfile.TarInfo("feed.csv")
        member.size = len(data)
        bundle.addfile(member, io.BytesIO(data))


def test_cross_feeds_read_period_scores_starter_moves_and_offense(tmp_path: Path) -> None:
    from bil.data.pilot_inputs import cross_feeds

    live_header = ["gameId", "period", "orderNumber", "actionType", "subType", "clock"]
    live_header += ["teamId", "personId", "scoreHome", "scoreAway"]
    _csv_archive(
        tmp_path / "live.tar.xz",
        live_header,
        [
            ["22200001", "1", "10", "period", "end", "PT00M00.00S", "", "", "30", "20"],
            ["22200001", "2", "20", "substitution", "out", "PT12M00.00S", "100", "6", "", ""],
            ["22200001", "2", "21", "substitution", "in", "PT12M00.00S", "100", "5", "", ""],
            ["22200001", "2", "30", "substitution", "out", "PT11M00.00S", "100", "5", "", ""],
        ],
    )
    _csv_archive(
        tmp_path / "datanba.tar.xz",
        ["GAME_ID", "evt", "oftid", "ord", "PERIOD", "hs", "vs"],
        [
            ["22200001", "7", "100", "70", "1", "30", "20"],
            ["22200001", "8", "0", "80", "1", "", ""],
        ],
    )
    feed = cross_feeds(tmp_path / "live.tar.xz", tmp_path / "datanba.tar.xz")["0022200001"]
    assert feed.has_livedata and feed.live_periods == {1: (30, 20)}
    assert feed.datanba_periods == {1: (30, 20)} and feed.offense == {7: 100}
    # Only substitutions at the period's starting clock count as between-period moves.
    assert feed.between_periods == {(2, 100): (frozenset({6}), frozenset({5}))}


def test_livedata_starters_require_consistency_with_period_events() -> None:
    @dataclass
    class PeriodEnd:
        current_players: dict[int, list[int]]
        event_type: int = 13

    closing = PeriodEnd({100: [1, 2, 3, 4, 6]})
    moves = {(2, 100): (frozenset({6}), frozenset({5}))}
    propagate = pilot_parser._propagated_starters
    assert propagate(closing, 100, 2, (1, 2, 3, 4), moves) == (1, 2, 3, 4, 5)
    assert propagate(closing, 100, 2, (1, 2, 3, 4, 5, 9), moves) == (1, 2, 3, 4, 5)
    # Events naming a player the substitutions remove, or the first period, are not settled.
    assert propagate(closing, 100, 2, (1, 2, 3, 6), moves) is None
    assert propagate(closing, 100, 1, (1, 2, 3, 4), moves) is None
    assert propagate(PeriodEnd({100: [1, 2, 3, 4, 6]}, 12), 100, 2, (1, 2, 3, 4), moves) is None
    # Too few event-identified starters to trust the feed.
    assert propagate(closing, 100, 2, (1, 2), moves) is None
    # A set of six that lacks the substituted player cannot contain the feed's lineup.
    assert propagate(closing, 100, 2, (1, 2, 3, 4, 7, 8), moves) is None


def test_period_defect_needs_both_feeds_to_confirm_every_disputed_period() -> None:
    from bil.data.pilot import v3_alone_differs
    from bil.data.pilot_inputs import CrossFeed

    ours = {1: (30, 20), 2: (50, 40)}
    v3 = {1: (31, 20), 2: (50, 40)}
    both = CrossFeed(live_periods=dict(ours), datanba_periods=dict(ours))
    assert v3_alone_differs(ours, v3, both)
    assert not v3_alone_differs(ours, v3, CrossFeed(live_periods=dict(ours)))
    assert not v3_alone_differs(ours, dict(ours), both)
    # A period missing from V2 and from both feeds is not evidence of a V3 defect.
    assert not v3_alone_differs({1: (30, 20)}, {1: (30, 20), 2: (50, 40)}, CrossFeed())


def test_unresolved_possession_takes_unanimous_feed_offense_without_repeating() -> None:
    game, roster, events, possessions = synthetic_game()
    raw = {
        event.event_num: RawEvent(
            {"PLAYER1_TEAM_ID": "200", "PLAYER1_ID": "21", "PLAYER2_ID": "26"}
            if event.event_type == 8
            else {},
            [event.event_num + 1],
        )
        for event in events
    }
    # The second possession holds the away team's missed shot (event 6).
    report: dict[str, int] = {}
    rows = normalize_game(
        game, roster, raw, events, possessions, "fixture", frozenset({1}), {6: 200}, report
    )
    assert rows["possession"][1]["status"] == "accepted" and report["relabeled_possessions"] == 1
    # A label that repeats the previous possession's offense stays unresolved.
    rows = normalize_game(
        game, roster, raw, events, possessions, "fixture", frozenset({1}), {6: 100}, report
    )
    assert rows["possession"][1]["status"] == "unresolved" and report["relabeled_possessions"] == 0


def test_season_sources_follow_each_provider_year_convention() -> None:
    sources = {source.name: source for source in pilot_sources.season_sources(2023)}
    # Shufinskiy names by starting year; Bill Mill by ending year under a season-neutral name.
    expected = {"nbastats_2023.tar.xz", "nbastatsv3_po_2023.tar.xz", "datanba_po_2023.tar.xz"}
    assert expected <= set(sources)
    team = sources["team_game_logs.parquet"]
    assert team.uri.endswith("/team_game_logs/season=2024/data.parquet")
    assert team.local_name == "team_game_logs_2024.parquet"
    evidence = [source.name for source in pilot_sources.season_evidence_sources(2024)]
    assert evidence[-2:] == [
        "lineup_stats_regular_2025.parquet",
        "lineup_stats_playoffs_2025.parquet",
    ]
    assert "pbpstats_po_2024.tar.xz" in evidence
    # Every season pins distinct bytes for every input.
    digests = [
        source.sha256
        for year in pilot_sources.SEASONS
        for source in pilot_sources.season_sources(year)
    ]
    assert len(set(digests)) == len(digests)


@pytest.mark.parametrize("year", [2025, 2026, 2000])
def test_unpinned_and_holdout_seasons_are_refused(tmp_path: Path, year: int) -> None:
    for make in (pilot_sources.season_sources, pilot_sources.season_evidence_sources):
        with pytest.raises(ValueError, match="holdout" if year >= 2025 else "No pinned"):
            make(year)
    target = tmp_path / "snapshot"
    with pytest.raises(ValueError):
        pilot_sources.capture_snapshot(target, season_start_year=year, local=tmp_path)
    assert not target.exists()
    # A snapshot that records a refused season is rejected before any payload is read.
    target.mkdir()
    record = {
        "schema_version": 1,
        "season_start_year": year,
        "attribution": pilot_sources.ATTRIBUTION,
        "terms": pilot_sources.NBA_TERMS,
        "artifacts": [],
    }
    (target / "snapshot.json").write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError):
        pilot_sources.load_snapshot(target)


def test_local_capture_copies_verified_bytes_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def offline(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("local capture must not open a network connection")

    monkeypatch.setattr(pilot_sources, "urlopen", offline)
    local = tmp_path / "audit"
    local.mkdir()
    content = b"box"
    (local / "team_game_logs_2024.parquet").write_bytes(content)
    source = pilot_sources.Source(
        "team_game_logs.parquet",
        "https://example.invalid/team",
        sha256(content).hexdigest(),
        len(content),
        "synthetic",
        local_name="team_game_logs_2024.parquet",
    )
    target = tmp_path / "snapshot"
    captured = pilot_sources.capture_snapshot(target, (source,), 2023, local)
    assert (target / "team_game_logs.parquet").read_bytes() == content
    assert captured["season_start_year"] == 2023
    assert captured["local_capture"].endswith("audit")
    assert captured["artifacts"][0]["retrieved_at"].endswith("+00:00")
    assert pilot_sources.load_snapshot(target, (source,), 2023) == captured
    with pytest.raises(ValueError, match="Invalid source snapshot"):
        pilot_sources.load_snapshot(target, (source,), 2024)

    # Changed or missing local bytes fail and leave no partial snapshot behind.
    (local / "team_game_logs_2024.parquet").write_bytes(b"bot")
    with pytest.raises(ValueError, match="Source bytes differ"):
        pilot_sources.capture_snapshot(tmp_path / "changed", (source,), 2023, local)
    (local / "team_game_logs_2024.parquet").unlink()
    with pytest.raises(FileNotFoundError, match="team_game_logs_2024.parquet"):
        pilot_sources.capture_snapshot(tmp_path / "missing", (source,), 2023, local)
    assert not (tmp_path / "changed").exists() and not (tmp_path / "missing").exists()


def test_box_logs_without_home_flags_wait_for_v2_designation(tmp_path: Path) -> None:
    from bil.data.pilot_inputs import box_scores, designate_home

    with duckdb.connect() as connection:
        connection.execute(
            """
            copy (select * from (values
                ('0022400001', date '2024-11-02', '300', '200', null::boolean, 98),
                ('0022400001', date '2024-11-02', '200', '300', null::boolean, 118),
                ('0022400002', date '2024-11-03', '200', '300', true, 100),
                ('0022400002', date '2024-11-03', '300', '200', false, 90))
              t(game_id, game_date, team_id, opp_team_id, home, pts))
            to '{}' (format parquet);
            copy (select * from (values
                ('0022400001', '21', '200', 48.0, 20), ('0022400001', '31', '300', 48.0, -20),
                ('0022400002', '21', '200', 48.0, 10), ('0022400002', '31', '300', 48.0, -10))
              t(game_id, player_id, team_id, min, plus_minus))
            to '{}' (format parquet);
            """.format(tmp_path / "team_game_logs.parquet", tmp_path / "player_game_logs.parquet")
        )
        games, _ = box_scores(connection, tmp_path)
    # A single null flag is still a conflict, but two give a provisional order by team ID.
    provisional = games["0022400001"]
    assert not provisional.home_designated
    assert (provisional.home_id, provisional.away_id, provisional.home_points) == (200, 300, 118)
    assert games["0022400002"].home_designated

    def event(team: str, home: str, visitor: str) -> RawEvent:
        fields = {"PLAYER1_TEAM_ID": team, "HOMEDESCRIPTION": home, "VISITORDESCRIPTION": visitor}
        return RawEvent(fields, [2])

    # V2 puts team 300's actions in the home column, so the provisional order is swapped.
    events = [event("300", "Shot", ""), event("200", "", "Rebound"), event("", "", "Timeout")]
    designated = designate_home(provisional, events)
    assert designated is not None and designated.home_designated
    assert (designated.home_id, designated.away_id) == (300, 200)
    assert (designated.home_points, designated.away_points) == (98, 118)
    # Contradictory or one-sided evidence designates nothing.
    assert designate_home(provisional, [*events, event("300", "", "Foul")]) is None
    assert designate_home(provisional, events[:1]) is None
    assert designate_home(provisional, [event("300", "A", ""), event("200", "B", "")]) is None


def test_undesignated_box_game_quarantines_without_v2_evidence(tmp_path: Path) -> None:
    game, roster, _, _ = synthetic_game()
    provisional = GameBox(
        game.game_id, game.played_date, game.home_id, game.away_id, 1, 2, home_designated=False
    )
    artifact = {
        "artifact_id": "fixture",
        "name": "fixture",
        "uri": "",
        "source_id": "synthetic",
        "upstream_namespace": "nba",
        "source_revision": None,
        "sha256": "0",
        "size_bytes": 0,
        "retrieved_at": "2026-11-23T00:00:00+00:00",
        "rights_ref": "x",
    }
    rows = pilot._build_game(
        provisional,
        roster,
        [
            RawEvent(
                {
                    "EVENTNUM": "1",
                    "EVENTMSGTYPE": "12",
                    "PERIOD": "1",
                    "PCTIMESTRING": "12:00",
                    "HOMEDESCRIPTION": "",
                    "VISITORDESCRIPTION": "",
                },
                [2],
            )
        ],
        {},
        None,
        [artifact] * 7,  # type: ignore[list-item]
        tmp_path,
        "hash",
        "2026-11-23T00:00:00+00:00",
        season_start_year=2024,
    )
    review = rows["game_review"][0]
    assert review["reason"] == "unresolved_home_designation" and review["accepted"] is False
    assert rows["game"][0]["season_start_year"] == 2024
    # The provisional team-ID orientation is not exported as fact.
    assert all(
        rows["game"][0][field] is None
        for field in ("home_team_id", "away_team_id", "home_final", "away_final")
    )


def test_checks_and_evidence_read_the_recorded_season_files(tmp_path: Path) -> None:
    from bil.data import pilot_evidence
    from bil.data.pilot_check import _same_offense_violations

    # Only 2023–24 files exist, so reading a 2022 name would fail.
    raw = b"GAME_ID,EVENTNUM,EVENTMSGTYPE,EVENTMSGACTIONTYPE\n22300001,50,6,14\n"
    with tarfile.open(tmp_path / "nbastats_2023.tar.xz", "w:xz") as archive:
        member = tarfile.TarInfo("events.csv")
        member.size = len(raw)
        archive.addfile(member, io.BytesIO(raw))
    for suffix in ("", "_po"):
        _v3_archive(
            tmp_path / f"nbastatsv3{suffix}_2023.tar.xz",
            [] if suffix else [["22300001", "1", "20", "1", "", "", "period", "end", "31", "20"]],
        )
    for name, (game_key, columns) in pilot_evidence.FEEDS.items():
        for suffix in ("", "_po"):
            row = ["22300001" if column == game_key else "" for column in columns]
            _csv_archive(tmp_path / f"{name}{suffix}_2023.tar.xz", list(columns), [row])
    with duckdb.connect() as connection:
        for name in pilot_sources.lineup_stat_names(2023):
            connection.execute(
                "copy (select '0022300001' as game_id, 0 as secs_game_start, "
                "720 as secs_game_end, '1 A, 2 B, 3 C, 4 D, 5 E' as lineup_team) "
                f"to '{tmp_path / name}' (format parquet)"
            )
        connection.execute(
            """
            create table possession as
            select '0022300001' as game_id, 1 as stream_revision, * from (values
                (1, 1, 1, 3, '100', 'accepted'), (2, 1, 3, 6, '100', 'accepted')
            ) as rows(possession_seq, period, start_seq, end_seq, offense_team_id, status);
            create table event as
            select '0022300001' as game_id, 1 as stream_revision,
                   1 as seq, 'foul' as kind, '50' as source_event_id;
            """
        )
        # The flagrant foul is found in the 2023–24 V2 archive.
        assert _same_offense_violations(connection, tmp_path, 2023) == 0
        pilot_evidence.stage_feeds(connection, tmp_path, tmp_path, 2023)
        staged = connection.execute("select game_id, ids from bentes").fetchall()
        assert staged == [("0022300001", ["1", "2", "3", "4", "5"])] * 2
        assert connection.execute("select GAMEID from pbpstats limit 1").fetchone() == (
            "0022300001",
        )
        scores = pilot_evidence.period_score_agreement(connection, tmp_path, 2023)
        assert scores["periods_compared"] == 0


def test_seasons_before_livedata_pin_every_other_feed() -> None:
    assert pilot_sources.SEASONS == (
        2002,
        2004,
        2005,
        2006,
        2007,
        2010,
        2012,
        2013,
        2014,
        2015,
        2016,
        2017,
        2018,
        2019,
        2020,
        2021,
        2022,
        2023,
        2024,
    )
    for year in pilot_sources.SEASONS:
        names = [source.name for source in pilot_sources.season_sources(year)]
        evidence = [source.name for source in pilot_sources.season_evidence_sources(year)]
        live = pilot_sources.has_livedata(year)
        data_nba = pilot_sources.has_datanba(year)
        assert live == (year >= 2020)
        assert data_nba == (year >= 2016)
        assert pilot_sources.datanba_has_order(year) == (year >= 2017)
        # V2, V3 and shot detail in both season types and both box logs are always required.
        # liveData and data.nba are pinned only where the provider archived them.
        assert len(names) == 8 + 2 * live + 2 * data_nba
        assert len(evidence) == 4 + 2 * live + 2 * data_nba
        assert (f"cdnnba_po_{year}.tar.xz" in names) is live
        assert (f"cdnnba_{year}.tar.xz" in evidence) is live
        assert (f"datanba_po_{year}.tar.xz" in names) is data_nba
        assert (f"datanba_{year}.tar.xz" in evidence) is data_nba
        assert f"pbpstats_{year}.tar.xz" in evidence
    team = {s.name: s for s in pilot_sources.season_sources(2019)}["team_game_logs.parquet"]
    assert team.local_name == "team_game_logs_2020.parquet"


def test_cross_feeds_without_livedata_keep_datanba_evidence(tmp_path: Path) -> None:
    from bil.data.pilot_inputs import cross_feeds

    _csv_archive(
        tmp_path / "datanba.tar.xz",
        ["GAME_ID", "evt", "oftid", "ord", "PERIOD", "hs", "vs"],
        [["21700001", "7", "100", "70", "1", "30", "20"]],
    )
    feed = cross_feeds(None, tmp_path / "datanba.tar.xz")["0021700001"]
    assert not feed.has_livedata and not feed.live_periods and not feed.between_periods
    assert feed.datanba_periods == {1: (30, 20)} and feed.offense == {7: 100}


def test_cross_feeds_without_ord_keep_offense_but_no_scores_or_order(tmp_path: Path) -> None:
    from bil.data.pilot_inputs import cross_feeds

    # The first two data.nba archives (2016–17) have offense keys and no ``ord`` column.
    _csv_archive(
        tmp_path / "datanba.tar.xz",
        ["GAME_ID", "evt", "oftid", "PERIOD", "hs", "vs"],
        [["21600001", "7", "100", "1", "30", "20"]],
    )
    feed = cross_feeds(None, tmp_path / "datanba.tar.xz")["0021600001"]
    assert feed.offense == {7: 100}
    assert feed.datanba_periods == {} and feed.order == {}


def test_cross_feeds_require_ord_where_the_pinned_season_has_it(tmp_path: Path) -> None:
    from bil.data.pilot_inputs import cross_feeds

    _csv_archive(
        tmp_path / "datanba.tar.xz",
        ["GAME_ID", "evt", "oftid", "PERIOD", "hs", "vs"],
        [["21700001", "7", "100", "1", "30", "20"]],
    )
    with pytest.raises(ValueError, match="ord column"):
        cross_feeds(None, tmp_path / "datanba.tar.xz", expect_order=True)
    assert cross_feeds(None, tmp_path / "datanba.tar.xz")["0021700001"].offense == {7: 100}


def test_cross_feeds_without_any_archive_have_no_evidence() -> None:
    from bil.data.pilot_inputs import cross_feeds

    assert cross_feeds(None, None) == {}


def test_pins_match_the_issue_51_register_for_every_pinned_season() -> None:
    register = Path(__file__).parents[1] / "docs" / "research"

    def rows(name: str) -> list[dict[str, str]]:
        with (register / f"nba-feed-coverage-{name}.csv").open(encoding="utf-8") as stream:
            return list(csv.DictReader(stream))

    archive = {
        (int(row["start_year"]), row["file"]): (row["sha256"], int(row["artifact_bytes"]))
        for row in rows("shufinskiy")
        if row["availability"] == "measured"
    }
    box = {
        (int(row["start_year"]), row["file"]): (row["sha256"], int(row["artifact_bytes"]))
        for row in rows("box")
        if row["availability"] == "measured"
    }
    lineups = {
        row["file"]: (row["sha256"], int(row["artifact_bytes"]))
        for row in rows("bentes")
        if row["feed"] == "lineup_stats" and row["availability"] == "measured"
    }
    for year in pilot_sources.SEASONS:
        for source in (
            *pilot_sources.season_sources(year),
            *pilot_sources.season_evidence_sources(year),
        ):
            if source.publisher == "shufinskiy":
                expected = archive[(year, source.name)]
            elif source.publisher == "billmill":
                assert source.local_name is not None
                expected = box[(year, source.local_name)]
            else:
                expected = lineups[source.name]
            assert (source.sha256, source.size_bytes) == expected, (year, source.name)


def test_games_without_livedata_carry_a_weaker_verification_stratum(tmp_path: Path) -> None:
    from bil.data.pilot_inputs import CrossFeed

    game, roster, _, _ = synthetic_game()
    artifact = {
        "artifact_id": "fixture",
        "name": "fixture",
        "uri": "",
        "source_id": "synthetic",
        "upstream_namespace": "nba",
        "source_revision": None,
        "sha256": "0",
        "size_bytes": 0,
        "retrieved_at": "2026-11-23T00:00:00+00:00",
        "rights_ref": "x",
    }

    def review(cross: CrossFeed | None) -> dict[str, object]:
        rows = pilot._build_game(
            game,
            roster,
            [],
            {},
            None,
            [artifact] * 6,  # type: ignore[list-item]
            tmp_path,
            "hash",
            "2026-11-23T00:00:00+00:00",
            cross,
            2017,
        )
        return rows["game_review"][0]

    absent = review(None)
    assert absent["reason"] == "missing_v2_game"
    assert "no_livedata" in absent["strata"]  # type: ignore[operator]
    present = review(CrossFeed(has_livedata=True))
    assert "no_livedata" not in present["strata"]  # type: ignore[operator]


def test_evidence_without_livedata_compares_v3_with_datanba_only(tmp_path: Path) -> None:
    from bil.data import pilot_evidence

    for suffix in ("", "_po"):
        _v3_archive(
            tmp_path / f"nbastatsv3{suffix}_2017.tar.xz",
            [] if suffix else [["21700001", "1", "20", "1", "", "", "period", "end", "31", "20"]],
        )
        for name, (game_key, columns) in pilot_evidence.FEEDS.items():
            if name == "cdnnba":
                continue  # Absent before 2020–21; reading it would fail.
            row = ["21700001" if column == game_key else "" for column in columns]
            if name == "datanba" and not suffix:
                values = {"evt": "20", "ord": "5", "PERIOD": "1", "hs": "31", "vs": "20"}
                row = [values.get(column, value) for column, value in zip(columns, row)]
            _csv_archive(tmp_path / f"{name}{suffix}_2017.tar.xz", list(columns), [row])
    with duckdb.connect() as connection:
        for name in pilot_sources.lineup_stat_names(2017):
            connection.execute(
                "copy (select '0021700001' as game_id, 0 as secs_game_start, "
                "720 as secs_game_end, '1 A, 2 B, 3 C, 4 D, 5 E' as lineup_team) "
                f"to '{tmp_path / name}' (format parquet)"
            )
        pilot_evidence.stage_feeds(connection, tmp_path, tmp_path, 2017)
        assert connection.execute("select count(*) from cdnnba").fetchone() == (0,)
        scores = pilot_evidence.period_score_agreement(connection, tmp_path, 2017)
        assert scores["periods_compared"] == 0
        assert scores["v3_datanba_periods_compared"] == 1 and scores["v3_equals_datanba"] == 1


def _season_build(root: Path, year: int, games: list[tuple[str, str]], lineup_team: str) -> Path:
    """Write a minimal build and snapshot: one lineup per game, player 7 traded after game 1."""
    build, snapshot = root / f"build-{year}", root / f"snapshot-{year}"
    build.mkdir()
    snapshot.mkdir()
    (snapshot / "snapshot.json").write_text("{}", "utf-8")
    recorded = {"season_start_year": year, "source_snapshot_sha256": sha256(b"{}").hexdigest()}
    (build / "manifest.json").write_text(json.dumps(recorded), "utf-8")
    values = ", ".join(
        f"('{game_id}', {year}, '{'regular' if game_id[:3] == '002' else 'playoffs'}', "
        f"date '{played}', '100', '200')"
        for game_id, played in games
    )
    teams = [lineup_team] + ["300"] * (len(games) - 1)
    with duckdb.connect() as connection:
        connection.execute(
            f"copy (select * from (values {values}) t(game_id, season_start_year, season_type, "
            f"game_date, home_team_id, away_team_id)) to '{build / 'game.parquet'}' (format parquet)"
        )
        lineups = ", ".join(f"('{g}', '{t}', ['7'])" for (g, _), t in zip(games, teams))
        connection.execute(
            f"copy (select * from (values {lineups}) t(game_id, team_id, player_ids)) "
            f"to '{build / 'lineup.parquet'}' (format parquet)"
        )
        box = ", ".join(f"('{g}', '7', '{t}')" for (g, _), t in zip(games, ["100", "300"]))
        connection.execute(
            f"copy (select * from (values {box}) t(game_id, player_id, team_id)) "
            f"to '{snapshot / 'player_game_logs.parquet'}' (format parquet)"
        )
    return build


def test_cross_season_checks_cover_identity_chronology_and_trades(tmp_path: Path) -> None:
    from bil.data.pilot_check import check_seasons

    good = [
        (
            _season_build(
                tmp_path, 2017, [("0021700001", "2017-10-17"), ("0041700001", "2018-04-14")], "100"
            ),
            2017,
        ),
        (
            _season_build(
                tmp_path, 2018, [("0021800001", "2018-10-16"), ("0041800001", "2019-04-13")], "100"
            ),
            2018,
        ),
    ]
    pairs = [(build, tmp_path / f"snapshot-{year}") for build, year in good]
    violations, roster = check_seasons(pairs)
    assert set(violations.values()) == {0}
    # Player 7 moves from team 100 to team 300 within each season.
    assert roster["player_seasons_with_several_box_teams"] == 2
    assert roster["player_seasons_on_court_for_several_teams"] == 2
    assert roster["players_in_several_seasons"] == 1

    # A wrong season code, overlapping seasons, an early playoff date and a lineup team that
    # differs from the box are each counted.
    bad = _season_build(
        tmp_path, 2019, [("0021800002", "2019-04-20"), ("0041900001", "2019-04-01")], "200"
    )
    violations, _ = check_seasons([*pairs, (bad, tmp_path / "snapshot-2019")])
    assert violations["game_id_encodes_season_and_type"] == 1
    assert violations["seasons_in_date_order"] == 1
    assert violations["playoffs_after_each_team_regular_season"] == 2
    assert violations["lineup_team_matches_player_box"] == 1
    assert violations["game_ids_unique_across_seasons"] == 0


def _designation_review(
    tmp_path: Path, v3_final: tuple[int, int]
) -> tuple[dict[str, Any], dict[str, Any]]:
    game, roster, _, _ = synthetic_game()
    provisional = GameBox(
        game.game_id, game.played_date, game.home_id, game.away_id, 3, 0, home_designated=False
    )
    artifact = {
        "artifact_id": "fixture",
        "name": "fixture",
        "uri": "",
        "source_id": "synthetic",
        "upstream_namespace": "nba",
        "source_revision": None,
        "sha256": "0",
        "size_bytes": 0,
        "retrieved_at": "2026-11-23T00:00:00+00:00",
        "rights_ref": "x",
    }

    def event(num: str, team: str, home: str, visitor: str) -> RawEvent:
        fields = {
            "EVENTNUM": num,
            "EVENTMSGTYPE": "2",
            "PERIOD": "1",
            "PCTIMESTRING": "11:00",
            "PLAYER1_TEAM_ID": team,
            "HOMEDESCRIPTION": home,
            "VISITORDESCRIPTION": visitor,
        }
        return RawEvent(fields, [int(num) + 1])

    # V2 puts team 200's actions in the home column, so the box's provisional order is swapped.
    events = [event("1", "200", "Miss", ""), event("2", "100", "", "Miss")]
    reference = V3Game({1: v3_final}, Counter())
    rows = pilot._build_game(
        provisional,
        roster,
        events,
        {},
        reference,
        [artifact] * 7,  # type: ignore[list-item]
        tmp_path,
        "hash",
        "2026-11-23T00:00:00+00:00",
    )
    return rows["game_review"][0], rows["game"][0]


def test_v2_home_designation_is_accepted_when_v3_confirms_it(tmp_path: Path) -> None:
    review, game_row = _designation_review(tmp_path, (0, 3))
    assert "v2_home_designation" in review["strata"]
    assert review["v3_box_final_match"] is True
    assert review["reason"] != "unresolved_home_designation"
    assert (game_row["home_team_id"], game_row["away_team_id"]) == ("200", "100")
    assert (game_row["home_final"], game_row["away_final"]) == (0, 3)


def test_v2_home_designation_contradicted_by_v3_quarantines(tmp_path: Path) -> None:
    review, game_row = _designation_review(tmp_path, (3, 0))
    assert "v2_home_designation" in review["strata"]
    assert review["reason"] == "v3_box_final_mismatch" and review["accepted"] is False
    assert review["v3_box_final_match"] is False
    # The orientation V2 designated is kept; only an undesignated game is nulled.
    assert game_row["home_team_id"] == "200"


def test_check_refuses_holdout_manifests_and_mismatched_snapshots(tmp_path: Path) -> None:
    from bil.data.pilot_check import check_build, check_seasons

    holdout = tmp_path / "holdout"
    holdout.mkdir()
    (holdout / "manifest.json").write_text(json.dumps({"season_start_year": 2025}), "utf-8")
    with pytest.raises(ValueError, match="holdout"):
        check_build(holdout, tmp_path)

    build = _season_build(tmp_path, 2017, [("0021700001", "2017-10-17")], "100")
    snapshot = tmp_path / "snapshot-2017"
    (snapshot / "snapshot.json").write_text("{}", "utf-8")
    manifest = json.loads((build / "manifest.json").read_text(encoding="utf-8"))
    manifest["source_snapshot_sha256"] = sha256(b"{}").hexdigest()
    (build / "manifest.json").write_text(json.dumps(manifest), "utf-8")
    check_seasons([(build, snapshot)])  # a matching digest passes
    (snapshot / "snapshot.json").write_text('{"changed": true}', "utf-8")
    with pytest.raises(ValueError, match="not made from the snapshot"):
        check_seasons([(build, snapshot)])


def test_starter_check_requires_livedata_coverage_where_pinned() -> None:
    from bil.data import pilot_evidence

    def run(year: int) -> dict[str, object]:
        with duckdb.connect() as connection:
            connection.execute(
                """
                create table quality_issue as select * from (values
                  ('0022200001', 'inferred_starters', 'period 2 team 100: 1,2,3,4,5'))
                  t(game_id, code, detail);
                create table bentes_team as select * from (values
                  ('0022200001', 720, '100', ['1', '2', '3', '4', '5']))
                  t(game_id, t0, team, ids);
                create table cdnnba (gameId varchar, actionType varchar, subType varchar,
                  personId varchar, period varchar, clock varchar, teamId varchar);
                create table ours (game_id varchar, team varchar, period int, stint_seq int,
                  ids varchar[]);
                """
            )
            return pilot_evidence.starter_agreement(connection, year)

    assert run(2017)["livedata_unavailable"] == 1
    with pytest.raises(ValueError, match="liveData is pinned"):
        run(2022)
