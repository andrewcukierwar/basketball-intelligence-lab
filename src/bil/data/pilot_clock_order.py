"""Opt-in same-clock rebound ordering rule (ADR-0028).

V2 events are sorted by game clock. Events that share one clock keep an arbitrary tie order, so a
tip or putback attempt entered late can sit after the rebound that follows it. The parser then
meets a rebound whose predecessor is not a missed shot and fails the game.

Rule ``same-clock-v1``, derived from event semantics and applied only inside one clock group:

1. Every rebound follows exactly one missed field goal or free throw. Subs and timeouts between
   them are allowed (the pinned parser repairs those itself).
2. A rebound with no such predecessor is an orphan. Its missed shot is a later missed field goal
   of the same clock group, entered late. Only a missed field goal can be a tip or putback.
3. A shot at this clock is taken by the team that holds the ball. A rebound gives the ball to its
   team, and a made field goal or a turnover gives it to the other team, looking back through
   subs and timeouts. A candidate of another team is excluded. If the ball is not known, the
   remaining checks decide.
4. Candidates are never taken from beyond a period boundary event. Events keep their clocks, and
   only the order inside the group changes. The one remaining candidate is moved directly before
   the orphan rebound.
5. If an orphan has no candidate, or more than one remains (different shooters or teams would
   give materially different event attribution), the whole game is declined and keeps its
   original failure.

Source rows are never edited. The rule changes the order in which the unchanged rows are offered
to the unchanged parser, and every reconciliation check still runs on the result.
"""

from __future__ import annotations

from dataclasses import dataclass

from bil.data.pilot_inputs import RawEvent

RULE_VERSION = "same-clock-v1"
FG_MADE, FG_MISS, FT, REBOUND, TURNOVER = "1", "2", "3", "4", "5"
SKIPPABLE = ("8", "9")  # substitutions and timeouts
JUMP_BALL = "10"
BOUNDARY = ("12", "13")


@dataclass(frozen=True)
class ClockOrder:
    events: dict[int, RawEvent]
    # (period, clock, event moved, rebound it now precedes)
    moves: tuple[tuple[str, str, int, int], ...]


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


def _holder(sequence: list[RawEvent], teams: tuple[str, ...]) -> str | None:
    """The team that holds the ball after the last event, or None when the event does not say.

    Subs and timeouts are looked through. A rebound gives the ball to its team. A made field
    goal or a turnover gives it to the other team. Any other event leaves it unknown.
    """
    for event in reversed(sequence):
        kind = event.fields["EVENTMSGTYPE"]
        if kind in SKIPPABLE:
            continue
        team = _team(event)
        if team not in teams:
            return None
        if kind == REBOUND:
            return team
        if kind in (FG_MADE, TURNOVER):
            others = [other for other in teams if other != team]
            return others[0] if len(others) == 1 else None
        return None
    return None


def _has_miss_before(sequence: list[RawEvent]) -> bool:
    """Whether the last event is a missed shot, as the pinned parser reads it.

    Subs and timeouts are skipped, and so is one jump ball: a rebound after a held-ball tip
    belongs to the shot before the jump ball, which the pinned parser accepts.
    """
    jump_ball_seen = False
    for event in reversed(sequence):
        kind = event.fields["EVENTMSGTYPE"]
        if kind in SKIPPABLE:
            continue
        if kind == JUMP_BALL and not jump_ball_seen:
            jump_ball_seen = True
            continue
        return _is_miss(event)
    return False


def reorder_same_clock(raw: dict[int, RawEvent]) -> ClockOrder | Declined | None:
    """Order same-clock events so each rebound follows a missed shot, or None if none is needed."""
    events = list(raw.values())
    teams = tuple(sorted({event.fields["PLAYER1_TEAM_ID"] for event in events} - {"", "0"}))
    out: list[RawEvent] = []
    moves: list[tuple[str, str, int, int]] = []
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
            holder = _holder(out, teams)
            if holder is not None:
                # A shot at this clock is taken by the team that holds the ball.
                candidates = [
                    position for position in candidates if _team(pending[position]) == holder
                ]
            if not candidates:
                return Declined("no_candidate", key[0], key[1], number)
            if len({_team(pending[position]) for position in candidates}) > 1:
                return Declined("ambiguous_team", key[0], key[1], number)
            if len(candidates) > 1:
                return Declined("ambiguous_candidates", key[0], key[1], number)
            shot = pending.pop(candidates[0])
            out.append(shot)
            out.append(event)
            moves.append((key[0], key[1], int(shot.fields["EVENTNUM"]), number))
    if not moves:
        return None
    return ClockOrder({int(event.fields["EVENTNUM"]): event for event in out}, tuple(moves))
