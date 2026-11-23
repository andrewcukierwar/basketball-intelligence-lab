"""Synthetic tests for the optional offline data pilot."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path

import pytest

pytest.importorskip("duckdb")
pytest.importorskip("pbpstats")

import duckdb  # noqa: E402
import requests  # noqa: E402

from bil.data import pilot_parser, pilot_sources  # noqa: E402
from bil.data.pilot import compare_periods, summarize_reviews  # noqa: E402
from bil.data.pilot_inputs import (  # noqa: E402
    GameBox,
    GameIssue,
    PlayerBox,
    RawEvent,
    deduplicate_events,
    v2_substitutions,
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
