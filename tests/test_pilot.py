"""Synthetic tests for the optional offline data pilot."""

from __future__ import annotations

import csv
import io
import tarfile
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path

import pytest

pytest.importorskip("duckdb")
pytest.importorskip("pbpstats")

import duckdb  # noqa: E402
import requests  # noqa: E402

from bil.data import pilot, pilot_parser, pilot_sources, pilot_starters  # noqa: E402
from bil.data.pilot import compare_periods, summarize_reviews  # noqa: E402
from bil.data.pilot_inputs import (  # noqa: E402
    GameBox,
    GameIssue,
    PlayerBox,
    RawEvent,
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
    monkeypatch.setattr(pilot_sources, "SOURCES", (source,))
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

    def games(connection: duckdb.DuckDBPyConnection, *args: object) -> list[object]:
        staging = args[3]
        assert isinstance(staging, Path)
        assert staging.parent == output.parent
        assert connection.execute("SELECT current_setting('temp_directory')").fetchone() == (
            str(staging / "duckdb-spill"),
        )
        return []

    monkeypatch.setattr(pilot, "load_snapshot", lambda _path: {"artifacts": []})
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
