"""Opt-in event-order repair from the archived data.nba.com ``ord`` sequence (ADR-0023, proposed).

V2 rows are sorted by game clock. A late-entered stat correction keeps its original clock, so V2
can place it before an event that really preceded it (a turnover before the offensive rebound
that came first). data.nba.com ``ord`` records the sequence in which events were entered.
Following that sequence restores the action order, but then some clocks break the monotone
clock order. Which events are "displaced" is a minimal-removal choice, so a displaced event
may carry a clock that is later or earlier than its predecessor's, and a re-clocked event moves
by that difference in either direction (measured: 42% move earlier, by up to 47 s, and a few
later by minutes; replays move most). Each displaced event takes its predecessor's clock, so
every repaired stream has monotone clocks. Every other event keeps its V2 clock, and every
reconciliation still runs on the repaired stream. Because the clocks are monotone by
construction, ``unsupported_reorder`` and ``unresolved_clock_reset`` cannot fire on the
displaced events: no check is relaxed, but those two lose discriminating power on repaired
games. Minutes, plus-minus, lineup and score reconciliation remain the safeguards.
"""

from __future__ import annotations

from dataclasses import dataclass

from bil.data.pilot_inputs import RawEvent

PERIOD_START, PERIOD_END = "12", "13"


@dataclass(frozen=True)
class OrderRepair:
    events: dict[int, RawEvent]
    # Event number -> (V2 clock text, assigned clock text, seconds of game time the event moved
    # later (positive) or earlier (negative)).
    clamped: dict[int, tuple[str, str, float]]
    repositioned: int


def clock_seconds(text: str) -> float:
    """Seconds left on a V2 ``PCTIMESTRING`` such as ``11:46`` or ``0:37.5``."""
    minutes, seconds = text.split(":")
    return int(minutes) * 60 + float(seconds)


def ord_sequence(raw: dict[int, RawEvent], order: dict[int, int]) -> list[int] | None:
    """V2 event numbers in data.nba order, or None unless that order is complete and unambiguous.

    The feed must give every V2 event a distinct ``ord``, and periods must not interleave.
    """
    if not order or raw.keys() - order.keys():
        return None
    values = [order[event_num] for event_num in raw]
    if len(set(values)) != len(values):
        return None
    sequence = sorted(raw, key=order.__getitem__)
    periods = [int(raw[event_num].fields["PERIOD"]) for event_num in sequence]
    if periods != sorted(periods):
        return None
    return sequence


def _kept_positions(clocks: list[float], numbers: list[int]) -> set[int]:
    """Positions of the longest non-increasing run of clocks, entered earliest on a tie.

    Among runs of equal length, keep the one whose events have the lowest event numbers, so the
    events dropped are the latest entered (a stat correction takes the next free number).
    """
    count = len(clocks)
    if all(later <= earlier for earlier, later in zip(clocks, clocks[1:], strict=False)):
        return set(range(count))
    best: list[tuple[int, int]] = []  # (run length, minus the sum of event numbers)
    previous = [-1] * count
    for position in range(count):
        best.append((1, -numbers[position]))
        for before in range(position):
            if clocks[before] >= clocks[position]:
                length, weight = best[before]
                candidate = (length + 1, weight - numbers[position])
                if candidate > best[position]:
                    best[position] = candidate
                    previous[position] = before
    end = max(range(count), key=lambda position: (best[position], -position))
    kept: set[int] = set()
    while end != -1:
        kept.add(end)
        end = previous[end]
    return kept


def displaced_events(raw: dict[int, RawEvent], sequence: list[int]) -> list[int]:
    """Events whose V2 clock breaks the monotone clock of the data.nba sequence, in sequence order.

    Per period, the longest non-increasing run of clocks is kept, and the other events are the
    displaced (late-entered) ones. V2 itself is clock-sorted, so it has no such events.
    """
    displaced: list[int] = []
    by_period: dict[str, list[int]] = {}
    for event_num in sequence:
        by_period.setdefault(raw[event_num].fields["PERIOD"], []).append(event_num)
    for numbers in by_period.values():
        clocks = [clock_seconds(raw[n].fields["PCTIMESTRING"]) for n in numbers]
        kept = _kept_positions(clocks, numbers)
        displaced += [n for position, n in enumerate(numbers) if position not in kept]
    return displaced


def repair_order(raw: dict[int, RawEvent], order: dict[int, int]) -> OrderRepair | None:
    """Reorder V2 events by data.nba ``ord`` and re-clock late-entered events, or return None.

    Returns None when ``ord`` does not cover the events exactly, when a period boundary event
    would need re-clocking, or when the order already agrees with a clock-sorted V2 stream and
    needs no repair (so the caller can keep its ordinary path).
    """
    sequence = ord_sequence(raw, order)
    if sequence is None:
        return None
    events: dict[int, RawEvent] = {}
    clamped: dict[int, tuple[str, str, float]] = {}
    by_period: dict[str, list[int]] = {}
    for event_num in sequence:
        by_period.setdefault(raw[event_num].fields["PERIOD"], []).append(event_num)
    for numbers in by_period.values():
        clocks = [clock_seconds(raw[n].fields["PCTIMESTRING"]) for n in numbers]
        kept = _kept_positions(clocks, numbers)
        assigned = ""
        for position, event_num in enumerate(numbers):
            source = raw[event_num]
            clock = source.fields["PCTIMESTRING"]
            if position in kept:
                events[event_num] = source
                assigned = clock
                continue
            boundary = source.fields["EVENTMSGTYPE"] in (PERIOD_START, PERIOD_END)
            if position == 0 or boundary or not assigned:
                return None
            fields = dict(source.fields)
            fields["PCTIMESTRING"] = assigned
            events[event_num] = RawEvent(fields, list(source.row_numbers))
            clamped[event_num] = (clock, assigned, clock_seconds(clock) - clock_seconds(assigned))
    if list(events) == list(raw) and not clamped:
        return None
    moved = sum(new != old for new, old in zip(events, raw, strict=True))
    return OrderRepair(events, clamped, moved)
