"""Opt-in same-clock rebound ordering rule (ADR-0028).

V2 events are sorted by game clock. Events that share one clock keep an arbitrary tie order, so a
tip or putback attempt entered late can sit after the rebound that follows it. The parser then
meets a rebound whose predecessor is not a missed shot and fails the game.

Rule ``same-clock-v1``, derived from event semantics and applied only inside one clock group:

1. Every rebound follows exactly one missed field goal or free throw. Subs and timeouts between
   them are allowed (the pinned parser repairs those itself).
2. A rebound with no such predecessor is an orphan. Its missed shot is a later missed field goal
   of the same clock group, entered late. Only a missed field goal can be a tip or putback.
3. A shot at the same clock as the previous rebound is taken by the team that holds the ball, so
   the shot's team must equal the team of the rebound before it. This selects among candidates.
4. Candidates are never taken from beyond a period boundary event. Events keep their clocks, and
   only the order inside the group changes. The earliest candidate in V2 order is moved directly
   before the orphan rebound.
5. If an orphan has no candidate, or candidates of different teams remain, the whole game is
   declined and keeps its original failure (ambiguous: materially different readings).

Source rows are never edited. The rule changes the order in which the unchanged rows are offered
to the unchanged parser, and every reconciliation check still runs on the result.
"""

from __future__ import annotations

from dataclasses import dataclass

from bil.data.pilot_inputs import RawEvent

RULE_VERSION = "same-clock-v1"
FG_MISS, FT, REBOUND = "2", "3", "4"
SKIPPABLE = ("8", "9")  # substitutions and timeouts
BOUNDARY = ("12", "13")


@dataclass(frozen=True)
class ClockOrder:
    events: dict[int, RawEvent]
    # (period, clock, event moved, rebound it now precedes, same-team candidates considered)
    moves: tuple[tuple[str, str, int, int, int], ...]


@dataclass(frozen=True)
class Declined:
    reason: str
    period: str
    clock: str
    rebound: int


def _description(event: RawEvent) -> str:
    fields = event.fields
    return fields["HOMEDESCRIPTION"] + fields["VISITORDESCRIPTION"] + fields["NEUTRALDESCRIPTION"]


def _is_miss(event: RawEvent) -> bool:
    kind = event.fields["EVENTMSGTYPE"]
    if kind == FG_MISS:
        return True
    # The pinned parser treats a free throw as made unless its text holds "MISS ".
    return kind == FT and "MISS " in _description(event)


def _team(event: RawEvent) -> str:
    return event.fields["PLAYER1_TEAM_ID"] or event.fields["PLAYER1_ID"]


def _has_miss_before(sequence: list[RawEvent]) -> bool:
    """Whether the last event is a missed shot, looking back over subs and timeouts."""
    for event in reversed(sequence):
        if event.fields["EVENTMSGTYPE"] in SKIPPABLE:
            continue
        return _is_miss(event)
    return False


def reorder_same_clock(raw: dict[int, RawEvent]) -> ClockOrder | Declined | None:
    """Order same-clock events so each rebound follows a missed shot, or None if none is needed."""
    events = list(raw.values())
    out: list[RawEvent] = []
    moves: list[tuple[str, str, int, int, int]] = []
    index = 0
    while index < len(events):
        stop = index
        key = (events[index].fields["PERIOD"], events[index].fields["PCTIMESTRING"])
        while (
            stop < len(events)
            and (
                events[stop].fields["PERIOD"],
                events[stop].fields["PCTIMESTRING"],
            )
            == key
        ):
            stop += 1
        group = events[index:stop]
        index = stop
        pending = list(group)
        while pending:
            event = pending.pop(0)
            if event.fields["EVENTMSGTYPE"] != REBOUND or _has_miss_before(out):
                out.append(event)
                continue
            number = int(event.fields["EVENTNUM"])
            boundary = next(
                (
                    position
                    for position, item in enumerate(pending)
                    if item.fields["EVENTMSGTYPE"] in BOUNDARY
                ),
                len(pending),
            )
            candidates = [
                position
                for position, item in enumerate(pending[:boundary])
                if item.fields["EVENTMSGTYPE"] == FG_MISS
            ]
            previous = out[-1] if out and out[-1].fields["EVENTMSGTYPE"] == REBOUND else None
            if previous is not None and _team(previous):
                candidates = [
                    position
                    for position in candidates
                    if _team(pending[position]) == _team(previous)
                ]
            if not candidates:
                return Declined("no_candidate", key[0], key[1], number)
            if len({_team(pending[position]) for position in candidates}) > 1:
                return Declined("ambiguous_team", key[0], key[1], number)
            shot = pending.pop(candidates[0])
            out.append(shot)
            out.append(event)
            moves.append((key[0], key[1], int(shot.fields["EVENTNUM"]), number, len(candidates)))
    if not moves:
        return None
    return ClockOrder({int(event.fields["EVENTNUM"]): event for event in out}, tuple(moves))
