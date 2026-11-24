"""Synthetic cases for each safeguard of the order-repair-v2 rule (ADR-0029, proposed)."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest

from bil.data import pilot
from bil.data.pilot_inputs import CrossFeed, GameBox, GameIssue, PlayerBox, RawEvent, V3Game
from bil.data.pilot_order_v2 import (
    EVIDENCE_REBOUND,
    EVIDENCE_V3,
    DeclinedV2,
    RepairedV2,
    repair_order_v2,
    write_order_repair_log,
)


def event(num: int, kind: str, clock: str, period: str = "1") -> tuple[int, RawEvent]:
    fields = {"EVENTMSGTYPE": kind, "PCTIMESTRING": clock, "PERIOD": period}
    return num, RawEvent(fields, [num])


def stream(*events: tuple[int, RawEvent]) -> dict[int, RawEvent]:
    return dict(events)


# V2 sorts by clock: start, miss (0:37), late turnover stamped 0:37, rebound (0:31), end.
LATE_TURNOVER = stream(
    event(1, "12", "12:00"),
    event(2, "2", "0:37"),
    event(9, "5", "0:37"),
    event(3, "4", "0:31"),
    event(4, "13", "0:00"),
)
ENTERED = {1: 10, 2: 20, 3: 30, 9: 35, 4: 40}
V3_AGREES = [1, 2, 3, 9, 4]
V3_SAME_AS_V2 = [1, 2, 9, 3, 4]


def test_corrected_clock_is_the_nearest_valid_neighbour_and_raw_is_untouched() -> None:
    result = repair_order_v2(LATE_TURNOVER, ENTERED, V3_AGREES)
    assert isinstance(result, RepairedV2)
    assert list(result.events) == [1, 2, 3, 9, 4]
    (change,) = result.modifications
    assert (change.original_clock, change.corrected_clock, change.shift_seconds) == (
        "0:37",
        "0:31",
        6.0,
    )
    assert change.evidence == EVIDENCE_V3
    assert LATE_TURNOVER[9].fields["PCTIMESTRING"] == "0:37"  # raw record not mutated
    assert result.events[9].row_numbers == [9]


def test_a_stale_clock_inside_the_valid_interval_is_not_moved_further_than_needed() -> None:
    # The late turnover is stamped earlier in game time than the rebound it follows (0:40 vs 0:31
    # remaining is a later stamp), so the nearest valid clock is the successor's, not a neighbour's.
    raw = stream(
        event(1, "12", "12:00"),
        event(2, "2", "0:50"),
        event(9, "5", "0:45"),
        event(3, "4", "0:40"),
        event(4, "13", "0:00"),
    )
    # ord: miss, turnover, rebound entered 3rd..., turnover entered after the rebound
    result = repair_order_v2(raw, {1: 1, 2: 2, 3: 3, 9: 4, 4: 5}, [1, 2, 3, 9, 4])
    assert isinstance(result, RepairedV2)
    assert result.modifications[0].corrected_clock == "0:40"
    assert result.modifications[0].shift_seconds == 5.0


def test_a_shift_over_24_seconds_is_rejected_never_truncated() -> None:
    raw = stream(
        event(1, "12", "12:00"),
        event(2, "2", "10:00"),
        event(3, "1", "9:00"),
        event(4, "13", "0:00"),
    )
    # The made shot is stamped 9:00 but entered before the miss at 10:00: moving it is +60 s.
    entered = {1: 1, 3: 2, 2: 3, 4: 4}
    result = repair_order_v2(raw, entered, [1, 3, 2, 4])
    assert isinstance(result, DeclinedV2)
    assert result.reason == "shift_over_ceiling"
    assert max(abs(m.shift_seconds) for m in result.proposed) > 24
    # The rejected correction is logged in full, so it was not truncated to 24 s.
    assert {abs(m.shift_seconds) for m in result.proposed} == {60.0}


def test_replays_are_separate_and_never_anchor_or_distort_the_solve() -> None:
    raw = stream(
        event(1, "12", "12:00"),
        event(7, "18", "5:00"),  # replay: stamped long before, entered last, huge "shift"
        event(2, "2", "0:37"),
        event(9, "5", "0:37"),
        event(3, "4", "0:31"),
        event(4, "13", "0:00"),
    )
    entered = {1: 10, 2: 20, 3: 30, 9: 35, 4: 40, 7: 45}
    result = repair_order_v2(raw, entered, V3_AGREES)
    assert isinstance(result, RepairedV2)
    assert [m.event_num for m in result.modifications] == [9]
    assert result.metadata_events == 1
    assert result.events[7].fields["PCTIMESTRING"] == "5:00"  # replay clock is never rewritten
    assert list(result.events) == [1, 7, 2, 3, 9, 4]


def test_a_displaced_replay_alone_needs_no_repair() -> None:
    raw = stream(event(1, "12", "12:00"), event(7, "18", "5:00"), event(4, "13", "0:00"))
    assert repair_order_v2(raw, {1: 1, 4: 2, 7: 3}, []) is None


def test_a_substantive_move_without_corroboration_declines_the_repair() -> None:
    result = repair_order_v2(LATE_TURNOVER, ENTERED, V3_SAME_AS_V2)
    assert isinstance(result, DeclinedV2) and result.reason == "uncorroborated"
    assert result.proposed[0].evidence == "none"
    assert isinstance(repair_order_v2(LATE_TURNOVER, ENTERED, None), DeclinedV2)


def test_a_rebound_that_follows_a_missed_shot_is_corroborated_without_v3() -> None:
    raw = stream(
        event(1, "12", "12:00"),
        event(9, "4", "0:40"),  # rebound entered after the miss but stamped before it
        event(2, "2", "0:37"),
        event(4, "13", "0:00"),
    )
    entered = {1: 1, 2: 2, 9: 3, 4: 4}
    result = repair_order_v2(raw, entered, [1, 9, 2, 4])  # V3 follows V2 order
    assert isinstance(result, RepairedV2)
    assert result.modifications[0].evidence == EVIDENCE_REBOUND
    # A rebound that does not follow a miss gets no such corroboration.
    noshot = stream(
        event(1, "12", "12:00"),
        event(9, "4", "0:40"),
        event(2, "1", "0:37"),
        event(4, "13", "0:00"),
    )
    declined = repair_order_v2(noshot, entered, [1, 9, 2, 4])
    assert isinstance(declined, DeclinedV2) and declined.reason == "uncorroborated"


def test_boundary_events_and_incomplete_orders_decline() -> None:
    boundary = repair_order_v2(LATE_TURNOVER, {1: 10, 2: 20, 3: 30, 9: 35, 4: 5}, V3_AGREES)
    assert isinstance(boundary, DeclinedV2) and boundary.reason == "boundary_event_displaced"
    missing = repair_order_v2(LATE_TURNOVER, {1: 10, 2: 20, 3: 30, 9: 35}, V3_AGREES)
    assert isinstance(missing, DeclinedV2) and missing.reason == "incomplete_entry_order"


def test_a_clock_sorted_entry_order_needs_no_repair() -> None:
    assert repair_order_v2(LATE_TURNOVER, {1: 10, 2: 20, 9: 25, 3: 30, 4: 40}, V3_AGREES) is None


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    game = GameBox("0021700001", date(2017, 10, 20), 100, 200, 0, 0)
    roster = {1: PlayerBox(100, 0, 0)}
    raw_events = [
        RawEvent(dict(e.fields, EVENTNUM=str(n), HOMEDESCRIPTION="", VISITORDESCRIPTION=""), [n])
        for n, e in LATE_TURNOVER.items()
    ]

    def build(accepts_unrepaired: bool, v3: list[int], repair: bool) -> tuple[dict, dict]:
        def parse_game(
            _game: object, stream: dict[int, RawEvent], *args: object, **kwargs: object
        ) -> object:
            if not accepts_unrepaired and stream[9].fields["PCTIMESTRING"] != "0:31":
                raise GameIssue("parser_error", "V2 order fails")
            return SimpleNamespace(
                events=[SimpleNamespace(event_num=n) for n in stream],
                possessions=[],
                unresolved_possessions=0,
                v3_order=False,
                livedata_starters=frozenset(),
            )

        def normalize_game(*args: object) -> pilot.Rows:
            return {"possession": [], "score_allocation": [], "event": []}

        monkeypatch.setattr(pilot, "parse_game", parse_game)
        monkeypatch.setattr(pilot, "normalize_game", normalize_game)
        monkeypatch.setattr(pilot, "compare_periods", lambda *_: (True, 1))
        artifact = {
            "artifact_id": "x",
            "name": "x",
            "uri": "",
            "source_id": "s",
            "upstream_namespace": "nba",
            "source_revision": None,
            "sha256": "0",
            "size_bytes": 0,
            "retrieved_at": "2026-11-23T00:00:00+00:00",
            "rights_ref": "x",
        }
        rows = pilot._build_game(
            game,
            roster,
            raw_events,
            {},
            V3Game({1: (0, 0)}, Counter(), v3),
            [artifact] * 7,
            tmp_path,
            "h",
            "2026-11-23T00:00:00+00:00",
            CrossFeed(has_livedata=True, order=ENTERED),
            2017,
            order_repair_v2=repair,
        )
        logs = [r for r in rows["quality_issue"] if r["code"].startswith("order_repair_v2")]
        return rows["game_review"][0], {"logs": logs, "rows": rows}

    return build


def test_accepted_games_are_never_touched(harness) -> None:  # type: ignore[no-untyped-def]
    review, extra = harness(True, V3_AGREES, True)
    assert review["accepted"] is True
    assert "datanba_event_order_v2" not in review["strata"] and extra["logs"] == []


def test_a_failed_game_is_repaired_into_the_lower_trust_stratum_with_a_complete_log(
    harness, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    review, extra = harness(False, V3_AGREES, True)
    assert review["accepted"] is True and "datanba_event_order_v2" in review["strata"]
    assert "datanba_event_order" not in review["strata"]
    (log,) = extra["logs"]
    detail = json.loads(log["detail"])
    (change,) = detail["modifications"]
    assert change == {
        "event_num": 9,
        "event_type": "5",
        "period": 1,
        "original_clock": "0:37",
        "corrected_clock": "0:31",
        "shift_s": 6.0,
        "justification": change["justification"],
        "evidence": EVIDENCE_V3,
    }
    assert change["justification"]
    quality = tmp_path / "quality_issue.parquet"
    with duckdb.connect() as connection:
        rows = [
            {**r, "source_refs": []}
            | {"game_id": r["game_id"], "stream_revision": 1, "event_seq": None}
            for r in extra["rows"]["quality_issue"]
        ]
        connection.execute(
            "create table q(game_id varchar, issue_seq int, code varchar, detail varchar)"
        )
        for r in rows:
            connection.execute(
                "insert into q values (?, ?, ?, ?)",
                [r["game_id"], r["issue_seq"], r["code"], r["detail"]],
            )
        connection.execute(f"copy q to '{quality}' (format parquet)")
        summary = write_order_repair_log(connection, tmp_path)
    with (tmp_path / "order_repair_v2_log.csv").open(newline="") as handle:
        (record,) = list(csv.DictReader(handle))
    assert record["original_clock"] == "0:37" and record["shift_s"] == "6.0"
    assert record["event_type"] == "5" and record["evidence"] == EVIDENCE_V3
    assert summary["games"] == {"applied": 1}


def test_an_uncorroborated_repair_keeps_the_quarantine_and_logs_the_decline(
    harness,
) -> None:  # type: ignore[no-untyped-def]
    review, extra = harness(False, V3_SAME_AS_V2, True)
    assert review["accepted"] is False and review["reason"] == "parser_error"
    (log,) = extra["logs"]
    assert log["code"] == "order_repair_v2_declined"
    assert json.loads(log["detail"])["reason"].startswith("uncorroborated")


def test_the_repair_is_off_by_default(harness) -> None:  # type: ignore[no-untyped-def]
    review, extra = harness(False, V3_AGREES, False)
    assert review["accepted"] is False and extra["logs"] == []


def _described(num: int, kind: str, clock: str, text: str) -> tuple[int, RawEvent]:
    _, base = event(num, kind, clock)
    base.fields.update(PLAYER1_ID="7", PLAYER1_TEAM_ID="100", HOMEDESCRIPTION=text)
    return num, base


def test_description_counters_that_run_backwards_decline_the_repair() -> None:
    def build(second: str) -> dict[int, RawEvent]:
        return stream(
            event(1, "12", "12:00"),
            _described(9, "4", "0:40", "Smith REBOUND (Off:0 Def:2)"),
            event(2, "2", "0:37"),
            _described(5, "4", "0:20", f"Smith REBOUND {second}"),
            event(4, "13", "0:00"),
        )

    entered = {1: 1, 2: 2, 9: 3, 5: 4, 4: 5}
    v3 = [1, 9, 2, 5, 4]
    declined = repair_order_v2(build("(Off:0 Def:1)"), entered, v3)
    assert isinstance(declined, DeclinedV2) and declined.reason == "counter_inversion"
    assert isinstance(repair_order_v2(build("(Off:0 Def:3)"), entered, v3), RepairedV2)


def test_jump_balls_need_corroboration() -> None:
    raw = stream(
        event(1, "12", "12:00"),
        event(9, "10", "0:40"),
        event(2, "2", "0:37"),
        event(4, "13", "0:00"),
    )
    result = repair_order_v2(raw, {1: 1, 2: 2, 9: 3, 4: 4}, [1, 9, 2, 4])
    assert isinstance(result, DeclinedV2) and result.reason == "uncorroborated"


def test_an_unresolved_possession_at_a_moved_event_rejects_the_repair() -> None:
    repaired = repair_order_v2(LATE_TURNOVER, ENTERED, V3_AGREES)
    assert isinstance(repaired, RepairedV2)
    rows = {
        "event": [{"seq": 3, "source_event_id": "9"}],
        "possession": [{"status": "unresolved", "start_seq": 2, "end_seq": 5}],
    }
    with pytest.raises(GameIssue):
        pilot._reject_unresolved_at_moved_events(rows, repaired)  # type: ignore[arg-type]
    rows["possession"][0]["status"] = "accepted"
    pilot._reject_unresolved_at_moved_events(rows, repaired)  # type: ignore[arg-type]
