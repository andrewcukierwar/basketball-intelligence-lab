"""Synthetic cases for the opt-in data.nba event-order repair (ADR-0023, proposed)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from bil.data.pilot_inputs import RawEvent
from bil.data.pilot_order import displaced_events, ord_sequence, repair_order


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


def test_late_entered_event_follows_entry_order_and_takes_its_predecessors_clock() -> None:
    entered = {1: 10, 2: 20, 3: 30, 9: 35, 4: 40}
    repaired = repair_order(LATE_TURNOVER, entered)
    assert repaired is not None
    assert list(repaired.events) == [1, 2, 3, 9, 4]
    assert repaired.events[9].fields["PCTIMESTRING"] == "0:31"
    assert repaired.clamped == {9: ("0:37", "0:31", 6.0)}
    assert repaired.repositioned == 2
    # Inputs are untouched and other events keep their V2 clocks and source rows.
    assert LATE_TURNOVER[9].fields["PCTIMESTRING"] == "0:37"
    assert repaired.events[3] is LATE_TURNOVER[3]
    assert repaired.events[9].row_numbers == [9]


def test_displaced_events_are_the_clock_breaking_entries() -> None:
    entered = {1: 10, 2: 20, 3: 30, 9: 35, 4: 40}
    sequence = ord_sequence(LATE_TURNOVER, entered)
    assert sequence == [1, 2, 3, 9, 4]
    assert displaced_events(LATE_TURNOVER, sequence) == [9]


def test_repair_needs_a_complete_unambiguous_entry_order() -> None:
    assert repair_order(LATE_TURNOVER, {}) is None
    assert repair_order(LATE_TURNOVER, {1: 10, 2: 20, 3: 30, 9: 35}) is None  # event 4 missing
    assert repair_order(LATE_TURNOVER, {1: 10, 2: 20, 3: 30, 9: 30, 4: 40}) is None  # tied ord
    interleaved = stream(event(1, "12", "12:00"), event(2, "12", "12:00", "2"))
    assert ord_sequence(interleaved, {1: 20, 2: 10}) is None  # periods out of order


def test_a_clock_sorted_entry_order_needs_no_repair() -> None:
    assert repair_order(LATE_TURNOVER, {1: 10, 2: 20, 9: 25, 3: 30, 4: 40}) is None


def test_period_boundary_events_are_never_reclocked() -> None:
    entered = {1: 10, 2: 20, 3: 30, 9: 35, 4: 5}  # period end entered before the period starts
    assert repair_order(LATE_TURNOVER, entered) is None


def test_second_use_replacing_a_v3_primary_choice_clears_the_v3_primary_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import date
    from types import SimpleNamespace

    from bil.data import pilot
    from bil.data.pilot_inputs import CrossFeed, GameBox, GameIssue, PlayerBox, V3Game

    game = GameBox("0021700001", date(2017, 10, 20), 100, 200, 0, 0)
    roster = {1: PlayerBox(100, 0, 0)}
    raw_events = [
        RawEvent(dict(e.fields, EVENTNUM=str(n), HOMEDESCRIPTION="", VISITORDESCRIPTION=""), [n])
        for n, e in LATE_TURNOVER.items()
    ]
    reference = V3Game({1: (0, 0)}, Counter(), list(LATE_TURNOVER))
    unresolved = {"repaired": 1, "v3": 3}

    def parse_game(
        _game: object, stream: dict[int, RawEvent], *args: object, **kwargs: object
    ) -> object:
        repaired = stream[9].fields["PCTIMESTRING"] == "0:31"
        if kwargs.get("primary_order") is None and not repaired:
            raise GameIssue("parser_error", "V2 order fails")
        parsed = [SimpleNamespace(event_num=n) for n in stream]
        return SimpleNamespace(
            events=parsed,
            possessions=[],
            unresolved_possessions=0,
            v3_order=False,
            livedata_starters=frozenset(),
            repaired=repaired,
        )

    def normalize_game(*args: object) -> pilot.Rows:
        result = args[3]
        count = unresolved["repaired" if getattr(result, "repaired", False) else "v3"]
        return {
            "possession": [{"status": "unresolved"}] * count,
            "score_allocation": [],
            "event": [],
        }

    class Parsed(list):  # events list that remembers the parse flag
        repaired = False

    def fake_parse(
        game_box: object, stream: dict[int, RawEvent], *args: object, **kwargs: object
    ) -> object:
        result = parse_game(game_box, stream, *args, **kwargs)
        events = Parsed(result.events)  # type: ignore[attr-defined]
        events.repaired = result.repaired  # type: ignore[attr-defined]
        result.events = events  # type: ignore[attr-defined]
        return result

    def fake_normalize(
        g: object, r: object, raw: object, events: object, *args: object
    ) -> pilot.Rows:
        return normalize_game(
            g, r, raw, SimpleNamespace(repaired=getattr(events, "repaired", False))
        )

    monkeypatch.setattr(pilot, "parse_game", fake_parse)
    monkeypatch.setattr(pilot, "normalize_game", fake_normalize)
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
    entered = {1: 10, 2: 20, 3: 30, 9: 35, 4: 40}

    def labels(repair: bool) -> list[str]:
        rows = pilot._build_game(
            game,
            roster,
            raw_events,
            {},
            reference,
            [artifact] * 7,
            tmp_path,
            "h",
            "2026-11-23T00:00:00+00:00",
            CrossFeed(has_livedata=True, order=entered),
            2017,
            order_repair=repair,
        )
        review = rows["game_review"][0]
        assert review["accepted"] is True, review
        return review["strata"]

    plain = labels(False)
    assert "v3_primary_order" in plain and "datanba_event_order" not in plain
    both = labels(True)
    assert "datanba_event_order" in both and "v3_primary_order" not in both
