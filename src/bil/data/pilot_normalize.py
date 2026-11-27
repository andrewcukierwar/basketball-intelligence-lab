"""Build and reconcile one coherent game stream from pinned parser evidence."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import combinations, product
from typing import TypeAlias

from bil.data.pilot_inputs import GameBox, GameIssue, PlayerBox, RawEvent
from bil.data.pilot_parser import ParserEvent, ParserPossession

Row: TypeAlias = dict[str, object]
Rows: TypeAlias = dict[str, list[Row]]
Lineups: TypeAlias = tuple[tuple[int, ...], tuple[int, ...]]
MINUTES_TOLERANCE_MS = 2_000
# V2 clocks show whole seconds and truncate tenths in a period's final minute, so each of a
# player's substitutions there can shift that player's minutes by up to one second.
SUBSECOND_CLOCK_MS = 60_000
TRUNCATION_ALLOWANCE_MS = 1_000
# Largest number of same-clock credit changes considered when matching box plus-minus.
MAX_CREDIT_CHANGES = 3
# Bound on credit-change combinations evaluated for one game.
MAX_CREDIT_COMBINATIONS = 200_000

EVENT_KINDS = {
    1: "shot",
    2: "shot",
    3: "free_throw",
    4: "rebound",
    5: "turnover",
    6: "foul",
    7: "violation",
    8: "substitution",
    9: "timeout",
    10: "jump_ball",
    12: "period_start",
    13: "period_end",
    18: "replay",
}
# Shots, free throws and turnovers: events a feed's offense team describes directly.
LIVE_BALL_TYPES = (1, 2, 3, 5)
# Field-goal attempts (types 1 and 2) and turnovers (5) are evidence of which team controls the
# ball (#138). Free throws, rebounds, fouls, violations and jump balls are not used. See
# docs/data-pilot.md for the ambiguity rules.
# Recorded in a pilot manifest built with the rule, so downstream row builds can enforce it.
CONTROL_OWNERSHIP_RULE = "control-ownership-issue-138-v1"
END_REASONS = {
    1: "made_shot",
    3: "final_free_throw",
    4: "defensive_rebound",
    5: "turnover",
    10: "jump_ball",
    13: "period_end",
}


@dataclass(frozen=True)
class TimedEvent:
    source: ParserEvent
    seq: int
    remaining_ms: int
    elapsed_ms: int
    lineups: Lineups


def period_start_ms(period: int) -> int:
    return min(period - 1, 4) * 720_000 + max(period - 5, 0) * 300_000


def team_lineups(
    event: ParserEvent, teams: tuple[int, int], roster: dict[int, PlayerBox]
) -> Lineups:
    players = event.current_players
    if players.keys() != set(teams):
        raise GameIssue("invalid_lineup_teams", "Lineup teams differ from box", event.event_num)
    sides = []
    for team in teams:
        ids = tuple(sorted(players[team]))
        if len(ids) != 5 or len(set(ids)) != 5:
            raise GameIssue(
                "invalid_lineup_size", "Lineup must have five unique players", event.event_num
            )
        if any(player not in roster or roster[player].team_id != team for player in ids):
            raise GameIssue(
                "invalid_lineup_player", "Lineup player is absent from team box", event.event_num
            )
        sides.append(ids)
    return sides[0], sides[1]


def timed_events(
    parsed: list[ParserEvent], raw: dict[int, RawEvent], game: GameBox, roster: dict[int, PlayerBox]
) -> list[TimedEvent]:
    nums = [event.event_num for event in parsed]
    if not nums or len(nums) != len(raw) or set(nums) != raw.keys():
        raise GameIssue("parser_event_loss", "Parser events do not match the deduplicated source")
    if nums != list(raw):

        def coordinates(event_num: int) -> tuple[str, str]:
            fields = raw[event_num].fields
            return fields["PERIOD"], fields["PCTIMESTRING"]

        if [coordinates(i) for i in nums] != [coordinates(i) for i in raw]:
            raise GameIssue("unsupported_reorder", "Parser moved events across different clocks")

    teams = game.home_id, game.away_id
    result: list[TimedEvent] = []
    state: Lineups | None = None
    for seq, event in enumerate(parsed, 1):
        previous = result[-1] if result else None
        prev_period = previous.source.period if previous is not None else 0
        if event.period <= 0 or event.period not in (prev_period, prev_period + 1):
            raise GameIssue(
                "invalid_period_sequence", "Period sequence is discontinuous", event.event_num
            )
        remaining = round(event.seconds_remaining * 1000)
        duration = period_start_ms(event.period + 1) - period_start_ms(event.period)
        if not 0 <= remaining <= duration:
            raise GameIssue("invalid_clock", "Clock is outside period bounds", event.event_num)
        if event.period != prev_period:
            if event.event_type != 12 or remaining != duration:
                raise GameIssue(
                    "missing_period_start", "Period start is not established", event.event_num
                )
            if previous is not None and previous.remaining_ms != 0:
                raise GameIssue(
                    "missing_period_end", "Earlier period did not end at zero", event.event_num
                )
        elif previous is not None and (event.event_type == 12 or remaining > previous.remaining_ms):
            raise GameIssue(
                "unresolved_clock_reset",
                "Clock or period-start order needs adjudication",
                event.event_num,
            )
        elapsed = period_start_ms(event.period + 1) - remaining
        after = team_lineups(event, teams, roster)
        active = after
        if event.event_type == 8:
            fields = raw[event.event_num].fields
            try:
                team, outgoing, incoming = (
                    int(fields[key]) for key in ("PLAYER1_TEAM_ID", "PLAYER1_ID", "PLAYER2_ID")
                )
            except ValueError as error:
                raise GameIssue(
                    "unresolved_substitution", "Substitution lacks numeric IDs", event.event_num
                ) from error
            if state is None or team not in teams:
                raise GameIssue(
                    "unresolved_substitution",
                    "Substitution lacks a known side or prior lineup",
                    event.event_num,
                )
            active = state
            side = teams.index(team)
            if not (
                outgoing in state[side]
                and incoming not in state[side]
                and set(after[side]) == (set(state[side]) - {outgoing}) | {incoming}
                and after[1 - side] == state[1 - side]
            ):
                raise GameIssue(
                    "unresolved_substitution",
                    "Substitution conflicts with active IDs",
                    event.event_num,
                )
        elif event.period == prev_period and state != after:
            raise GameIssue(
                "implicit_lineup_change", "Lineup changed without a substitution", event.event_num
            )
        state = after
        result.append(TimedEvent(event, seq, remaining, elapsed, active))
    if result[-1].source.period < 4 or result[-1].remaining_ms != 0:
        raise GameIssue(
            "incomplete_game_clock", "Stream ends before the regulation or overtime clock"
        )
    ends = Counter(item.source.period for item in result if item.source.event_type == 13)
    if ends != Counter(range(1, result[-1].source.period + 1)):
        raise GameIssue("missing_period_end", "Expected exactly one end marker in each period")
    if any(item.remaining_ms != 0 for item in result if item.source.event_type == 13):
        raise GameIssue("invalid_period_end", "Period end has a nonzero clock")
    return result


def build_stints(
    events: list[TimedEvent], scope: Row, teams: tuple[int, int]
) -> tuple[list[Row], list[Row], dict[int, int], Counter[int]]:
    seen: dict[tuple[int, tuple[int, ...]], str] = {}
    lineups: list[Row] = []
    stints: list[Row] = []
    by_event: dict[int, int] = {}
    minutes: Counter[int] = Counter()
    start = 0
    while start < len(events):
        first = events[start]
        stop = start + 1
        while stop < len(events):
            item = events[stop]
            if item.source.period != first.source.period or item.lineups != first.lineups:
                break
            stop += 1
        period = first.source.period
        started = (
            period_start_ms(period)
            if start == 0 or events[start - 1].source.period != period
            else events[start - 1].elapsed_ms
        )
        ended = (
            events[stop - 1].elapsed_ms
            if stop < len(events) and events[stop].source.period == period
            else period_start_ms(period + 1)
        )
        stint_seq = len(stints) + 1
        ids = []
        for side, team in enumerate(teams):
            players = first.lineups[side]
            key = team, players
            if key not in seen:
                player_ids = sorted(map(str, players))
                seen[key] = f"{team}:" + "-".join(player_ids)
                lineups.append(
                    {
                        **scope,
                        "lineup_id": seen[key],
                        "team_id": str(team),
                        "player_ids": player_ids,
                    }
                )
            ids.append(seen[key])
            for player in players:
                minutes[player] += ended - started
        stints.append(
            {
                **scope,
                "stint_seq": stint_seq,
                "period": period,
                "start_seq": first.seq,
                "end_seq": stop + 1,
                "start_elapsed_ms": started,
                "end_elapsed_ms": ended,
                "home_lineup_id": ids[0],
                "away_lineup_id": ids[1],
            }
        )
        by_event.update((seq, stint_seq) for seq in range(first.seq, stop + 1))
        start = stop
    return lineups, stints, by_event, minutes


def build_possessions(
    possessions: list[ParserPossession],
    events: list[TimedEvent],
    scope: Row,
    teams: tuple[int, int],
    unresolved: frozenset[int] = frozenset(),
    offense_evidence: dict[int, int] | None = None,
    keep_unresolved: frozenset[int] = frozenset(),
) -> tuple[list[Row], dict[int, tuple[int, int, str]], set[int]]:
    """Build possession rows and map each event sequence to (possession, offense, status).

    An unresolved possession takes the offense that ``offense_evidence`` (a feed's offense
    team by source event number) gives unanimously for its shots, free throws and turnovers,
    unless that would give it the same offense as an adjacent possession in the period or the
    index is in ``keep_unresolved``. Possessions are relabeled in order, so an earlier relabel
    can block a later neighbor; that keeps the result free of repeated offenses. Returns the
    indices relabeled this way.
    """
    by_event_num = {item.source.event_num: item for item in events}
    by_event: dict[int, tuple[int, int, str]] = {}
    rows: list[Row] = []
    members: list[list[TimedEvent]] = []
    prior_end = 1
    for index, position in enumerate(possessions):
        items = [by_event_num[event.event_num] for event in position.events]
        members.append(items)
        first, last = items[0], items[-1]
        if (
            any(item.source.period != first.source.period for item in items)
            or first.seq < prior_end
            or [item.seq for item in items] != list(range(first.seq, last.seq + 1))
        ):
            raise GameIssue(
                "invalid_possession_interval",
                "Possession overlaps or crosses a period",
                last.source.event_num,
            )
        offense = position.offense_team_id
        if offense not in teams:
            raise GameIssue(
                "unknown_possession_offense",
                "Possession offense is absent from box",
                last.source.event_num,
            )
        defense = teams[1 - teams.index(offense)]
        seq = len(rows) + 1
        prior_end = last.seq + 1
        status = "accepted" if last.source.count_as_possession else "excluded"
        if index in unresolved:
            status = "unresolved"
        rows.append(
            {
                **scope,
                "possession_seq": seq,
                "period": first.source.period,
                "start_seq": first.seq,
                "end_seq": prior_end,
                "offense_team_id": str(offense),
                "defense_team_id": str(defense),
                "end_reason": END_REASONS.get(last.source.event_type, "other"),
                "status": status,
            }
        )
        by_event.update((item.seq, (seq, offense, status)) for item in items)
    if not rows or any(
        item.seq not in by_event and item.remaining_ms > 0 and item.source.event_type != 12
        for item in events
    ):
        raise GameIssue("missing_possession_events", "Live-clock events have no possession")
    relabeled: set[int] = set()
    for index in sorted(unresolved - keep_unresolved):
        votes = (
            {
                offense_evidence.get(item.source.event_num)
                for item in members[index]
                if item.source.event_type in LIVE_BALL_TYPES
            }
            if offense_evidence
            else set()
        )
        if len(votes) != 1:
            continue
        team = votes.pop()
        if team not in teams:
            continue
        row = rows[index]
        if any(
            0 <= other < len(rows)
            and rows[other]["period"] == row["period"]
            and rows[other]["offense_team_id"] == str(team)
            for other in (index - 1, index + 1)
        ):
            continue
        row.update(
            offense_team_id=str(team),
            defense_team_id=str(teams[1 - teams.index(team)]),
            status="accepted",
        )
        by_event.update((item.seq, (index + 1, team, "accepted")) for item in members[index])
        relabeled.add(index)
    return rows, by_event, relabeled


@dataclass(frozen=True)
class CreditChoice:
    """Lineup states that existed at a scoring event's clock and could carry its credit."""

    allocation: int
    side: int
    delta: int
    current: TimedEvent
    options: tuple[TimedEvent, ...]


def same_clock_states(
    events: list[TimedEvent], index: int, side: int, shooter: int | None
) -> tuple[TimedEvent, ...]:
    """Return one event per distinct lineup state at this event's clock.

    The pool is every event at the same period and elapsed time, plus the next event, which
    carries the state after a substitution that ends the clock group. Only states with the
    shooter on court for the scoring side qualify.
    """
    item = events[index]

    def same(other: TimedEvent) -> bool:
        return other.source.period == item.source.period and other.elapsed_ms == item.elapsed_ms

    low = index
    while low > 0 and same(events[low - 1]):
        low -= 1
    high = index
    while high + 1 < len(events) and same(events[high + 1]):
        high += 1
    pool = events[low : high + 1]
    if high + 1 < len(events) and events[high + 1].source.period == item.source.period:
        pool.append(events[high + 1])
    states: dict[Lineups, TimedEvent] = {}
    for other in pool:
        if shooter in other.lineups[side]:
            states.setdefault(other.lineups, other)
    return tuple(states.values())


def located(artifact_id: str, line: int) -> dict[str, str]:
    return {"artifact_id": artifact_id, "locator": f"csv-record:{line}"}


def score_and_events(
    events: list[TimedEvent],
    raw: dict[int, RawEvent],
    scope: Row,
    game: GameBox,
    roster: dict[int, PlayerBox],
    by_stint: dict[int, int],
    by_possession: dict[int, tuple[int, int, str]],
    artifact_id: str,
    control_ownership: bool = False,
    control_conflicts: set[int] | None = None,
    score_conflicts: set[int] | None = None,
) -> tuple[list[Row], list[Row], list[Row], Counter[int], set[int], list[CreditChoice]]:
    teams = game.home_id, game.away_id
    if control_conflicts is None:
        control_conflicts = set()
    if score_conflicts is None:
        score_conflicts = set()
    conflicts: set[int] = set()
    choices: list[CreditChoice] = []
    free_throw_clocks = {
        (item.source.period, item.elapsed_ms, getattr(item.source, "team_id", None))
        for item in events
        if item.source.event_type == 3
    }

    def controls(item: TimedEvent, team: int) -> bool:
        """Whether this event is decisive evidence that ``team`` controls the ball.

        A turnover recorded at a clock where the opponent shoots free throws is part of a
        dead-ball cluster, such as an and-one, and is treated as ambiguous.
        """
        if item.source.event_type in (1, 2):
            return True
        opponent = teams[1 - teams.index(team)]
        return item.source.event_type == 5 and (
            (item.source.period, item.elapsed_ms, opponent) not in free_throw_clocks
        )

    points = [0, 0]
    canonical: list[Row] = []
    actors: list[Row] = []
    allocations: list[Row] = []
    pm: Counter[int] = Counter()
    by_num = {item.source.event_num: item for item in events}
    for index, item in enumerate(events):
        event = item.source
        row = raw[event.event_num]
        fields = row.fields
        team = getattr(event, "team_id", None)
        shooter = getattr(event, "player1_id", None)
        if event.event_type in (1, 2, 3) and (
            team not in teams or shooter not in item.lineups[teams.index(team)]
        ):
            raise GameIssue(
                "shooter_outside_lineup",
                "Shot or free-throw shooter is unresolved or not on court",
                event.event_num,
            )
        if control_ownership and team in teams and controls(item, team):
            # A field-goal attempt or turnover is made by the team in control (#138). An
            # accepted possession that the parser gave to the other team stays unresolved,
            # as a contradicting score does below.
            held = by_possession.get(item.seq)
            if held is not None and held[2] == "accepted" and held[1] != team:
                conflicts.add(held[0])
                control_conflicts.add(held[0])
        totals = [event.score.get(side, 0) for side in teams]
        deltas = [totals[i] - points[i] for i in range(2)]
        points = totals
        canonical.append(
            {
                **scope,
                "seq": item.seq,
                "period": event.period,
                "remaining_ms": item.remaining_ms,
                "elapsed_ms": item.elapsed_ms,
                "observed_at": None,
                "kind": EVENT_KINDS.get(event.event_type, "other"),
                "team_id": str(team) if team in teams else None,
                "home_delta": deltas[0],
                "away_delta": deltas[1],
                "revises_seq": None,
                "source_event_id": str(event.event_num),
                "source_refs": [located(artifact_id, line) for line in row.row_numbers],
            }
        )
        for slot in (1, 2, 3):
            raw_id = fields.get(f"PLAYER{slot}_ID", "")
            raw_team = fields.get(f"PLAYER{slot}_TEAM_ID", "")
            person = int(raw_id) if raw_id.isascii() and raw_id.isdecimal() else 0
            if not person and raw_id in ("", "0", "NA") and raw_team in ("", "0", "NA"):
                continue
            role = "other"
            if event.event_type == 8 and slot <= 2:
                role = ("sub_out", "sub_in")[slot - 1]
            elif event.event_type in (1, 2, 3) and slot == 1:
                role = "shooter"
            team_id = roster[person].team_id if person in roster else None
            if team_id is None and raw_team in tuple(map(str, teams)):
                team_id = int(raw_team)
            actors.append(
                {
                    **scope,
                    "seq": item.seq,
                    "slot": slot,
                    "role": role,
                    "player_id": str(person) if person in roster else None,
                    "team_id": str(team_id) if team_id is not None else None,
                    "source_slot": f"PLAYER{slot}_ID",
                    "raw_actor_id": raw_id or None,
                }
            )
        for side, delta in enumerate(deltas):
            if not delta:
                continue
            if delta < 0 or event.event_type not in (1, 3) or teams[side] != team:
                raise GameIssue(
                    "unresolved_score_event",
                    "Score delta lacks a supported made shot",
                    event.event_num,
                )
            exempt = event.event_type == 3 and (
                getattr(event, "is_technical_ft", False) or getattr(event, "is_flagrant_ft", False)
            )
            poss = by_possession.get(item.seq)
            # Points inside a possession whose offense is unresolved stay in the ledger
            # without a possession, as the contract's unresolved reason requires.
            unsure = not exempt and poss is not None and poss[2] == "unresolved"
            if unsure:
                poss = None
            if not exempt and not unsure and (poss is None or poss[1] != team):
                if poss is None:
                    raise GameIssue(
                        "unresolved_score_allocation",
                        "Scoring event lies outside every possession",
                        event.event_num,
                    )
                # The parser gave this possession to the other team. Leave its offense
                # unresolved rather than credit points against the recorded control.
                conflicts.add(poss[0])
                score_conflicts.add(poss[0])
            credit = item
            if event.event_type == 3:
                trigger = getattr(event, "event_for_efficiency_stats", event)
                attributed = by_num.get(trigger.event_num)
                if (
                    attributed is not None
                    and attributed.source.period == event.period
                    and attributed.elapsed_ms == item.elapsed_ms
                    and shooter in attributed.lineups[side]
                ):
                    credit = attributed
            allocations.append(
                {
                    **scope,
                    "seq": item.seq,
                    "scoring_team_id": str(team),
                    "points_delta": delta,
                    "possession_seq": poss[0] if poss is not None and not exempt else None,
                    "credited_stint_seq": by_stint[credit.seq],
                    "possession_reason": (
                        "unassigned_dead_ball"
                        if exempt
                        else "unresolved"
                        if unsure
                        else "control_possession"
                    ),
                    "attribution_rule": (
                        "scoring_event_lineup" if credit is item else "free_throw_trigger_lineup"
                    ),
                }
            )
            options = same_clock_states(events, index, side, shooter)
            if len(options) > 1 and credit.lineups in {option.lineups for option in options}:
                choices.append(CreditChoice(len(allocations) - 1, side, delta, credit, options))
            for player in credit.lineups[side]:
                pm[player] += delta
            for player in credit.lineups[1 - side]:
                pm[player] -= delta
    if points != [game.home_points, game.away_points]:
        raise GameIssue("final_score_mismatch", "Parsed scoring does not match the game box")
    return canonical, actors, allocations, pm, conflicts, choices


def truncated_boundaries(events: list[TimedEvent], raw: dict[int, RawEvent]) -> Counter[int]:
    """Count each player's substitutions at a truncated sub-minute clock."""
    counts: Counter[int] = Counter()
    for item in events:
        if item.source.event_type == 8 and 0 < item.remaining_ms < SUBSECOND_CLOCK_MS:
            fields = raw[item.source.event_num].fields
            for key in ("PLAYER1_ID", "PLAYER2_ID"):
                counts[int(fields[key])] += 1
    return counts


def reconcile_minutes(
    minutes: Counter[int], roster: dict[int, PlayerBox], truncated: Counter[int] | None = None
) -> None:
    """Compare minutes within 2,000 ms plus one second per truncated substitution clock."""
    counts = truncated or Counter()
    errors = {player: abs(minutes[player] - box.minutes_ms) for player, box in roster.items()}
    differing = sum(
        error > MINUTES_TOLERANCE_MS + TRUNCATION_ALLOWANCE_MS * counts[player]
        for player, error in errors.items()
    )
    if differing:
        raise GameIssue(
            "player_minutes_mismatch", f"{differing} players; max {max(errors.values())} ms"
        )


def _credit_change(choice: CreditChoice, option: TimedEvent) -> Counter[int]:
    change: Counter[int] = Counter()
    for sign, state in ((1, option), (-1, choice.current)):
        for player in state.lineups[choice.side]:
            change[player] += sign * choice.delta
        for player in state.lineups[1 - choice.side]:
            change[player] -= sign * choice.delta
    return change


def choose_box_credits(
    pm: Counter[int], roster: dict[int, PlayerBox], choices: list[CreditChoice]
) -> list[tuple[CreditChoice, TimedEvent]]:
    """Find the unique smallest set of same-clock credit changes that matches box plus-minus.

    Actual lineups and minutes are unchanged. Only which same-clock lineup state carries a
    scoring event's official plus-minus credit may change. Raise when no set or several
    sets of the smallest size reproduce every player's box value.
    """
    gap = {player: box.plus_minus - pm[player] for player, box in roster.items()}
    gap = {player: value for player, value in gap.items() if value}
    if not gap:
        return []
    moves = [
        (choice, option, _credit_change(choice, option))
        for choice in choices
        for option in choice.options
        if option.lineups != choice.current.lineups
    ]
    by_choice: dict[int, list[tuple[CreditChoice, TimedEvent, Counter[int]]]] = {}
    for move in moves:
        by_choice.setdefault(move[0].allocation, []).append(move)
    groups = list(by_choice.values())
    evaluated = 0
    for size in range(1, MAX_CREDIT_CHANGES + 1):
        found = []
        for chosen in combinations(groups, size):
            for picked in product(*chosen):
                evaluated += 1
                if evaluated > MAX_CREDIT_COMBINATIONS:
                    raise GameIssue(
                        "player_plus_minus_mismatch",
                        f"{len(gap)} players; credit search exceeded "
                        f"{MAX_CREDIT_COMBINATIONS} combinations",
                    )
                total: Counter[int] = Counter()
                for _, _, change in picked:
                    total.update(change)
                if {player: value for player, value in total.items() if value} == gap:
                    found.append([(choice, option) for choice, option, _ in picked])
        # Solutions that move credit between scores at the same clock, for the same side and
        # points, to the same lineup state cannot be told apart. Accept the earliest of them.
        signatures = {
            tuple(
                sorted(
                    (
                        choice.current.source.period,
                        choice.current.elapsed_ms,
                        choice.side,
                        choice.delta,
                        option.lineups,
                    )
                    for choice, option in solution
                )
            )
            for solution in found
        }
        if len(signatures) == 1:
            return min(found, key=lambda solution: sorted(c.allocation for c, _ in solution))
        if found:
            raise GameIssue(
                "player_plus_minus_mismatch",
                f"{len(gap)} players; {len(found)} same-clock credit sets match the box",
            )
    raise GameIssue("player_plus_minus_mismatch", f"{len(gap)} players")


def normalize_game(
    game: GameBox,
    roster: dict[int, PlayerBox],
    raw: dict[int, RawEvent],
    parsed_events: list[ParserEvent],
    parsed_possessions: list[ParserPossession],
    artifact_id: str,
    unresolved_possessions: frozenset[int] = frozenset(),
    offense_evidence: dict[int, int] | None = None,
    report: dict[str, int] | None = None,
    control_ownership: bool = False,
) -> Rows:
    """Normalize one game's parsed stream into the canonical pilot tables.

    With ``control_ownership`` (#138), an accepted possession that contains a decisive
    field-goal attempt or turnover by the other team is left unresolved, as one that a score
    contradicts is. ``report`` then counts as ``control_conflicts`` the possessions left
    unresolved by control evidence alone, not those a score also contradicts.
    """
    scope: Row = {"game_id": game.game_id, "stream_revision": 1}
    teams = game.home_id, game.away_id
    events = timed_events(parsed_events, raw, game, roster)
    lineups, stints, by_stint, minutes = build_stints(events, scope, teams)
    unresolved, keep = set(unresolved_possessions), set[int]()
    control_conflicts: set[int] = set()
    score_conflicts: set[int] = set()
    for _ in range(4):
        possessions, by_poss, relabeled = build_possessions(
            parsed_possessions,
            events,
            scope,
            teams,
            frozenset(unresolved),
            offense_evidence,
            frozenset(keep),
        )
        canonical, actors, allocations, pm, conflicts, choices = score_and_events(
            events,
            raw,
            scope,
            game,
            roster,
            by_stint,
            by_poss,
            artifact_id,
            control_ownership,
            control_conflicts,
            score_conflicts,
        )
        if not conflicts:
            break
        # Possession sequence numbers are one-based parser possession indices. A relabeled
        # possession that a score contradicts stays unresolved.
        indices = {seq - 1 for seq in conflicts}
        keep |= indices & relabeled
        unresolved |= indices
    else:
        raise GameIssue("unresolved_score_allocation", "Possession conflicts persist")
    if report is not None:
        report["relabeled_possessions"] = len(relabeled)
        if control_ownership:
            report["control_conflicts"] = sum(
                possessions[seq - 1]["status"] == "unresolved"
                for seq in control_conflicts - score_conflicts
            )
    reconcile_minutes(minutes, roster, truncated_boundaries(events, raw))
    for choice, option in choose_box_credits(pm, roster, choices):
        allocation = allocations[choice.allocation]
        allocation["credited_stint_seq"] = by_stint[option.seq]
        allocation["attribution_rule"] = "same_clock_box_credit"
    return {
        "event": canonical,
        "event_actor": actors,
        "lineup": lineups,
        "stint": stints,
        "possession": possessions,
        "score_allocation": allocations,
    }
