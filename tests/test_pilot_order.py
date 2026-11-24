"""Synthetic cases for the opt-in data.nba event-order repair (ADR-0023, proposed)."""

from __future__ import annotations

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
