"""Adjudicate a narrow archived V2 free-throw text defect before parsing."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass

from bil.data.pilot_inputs import GameBox, PlayerBox, RawEvent

RULE_VERSION = "free-throw-miss-v1"
TRIPS = {"10": (1, 1), "11": (1, 2), "12": (2, 2), "13": (1, 3), "14": (2, 3), "15": (3, 3)}
DESCRIPTIONS = ("HOMEDESCRIPTION", "VISITORDESCRIPTION", "NEUTRALDESCRIPTION")
SCORE = re.compile(r"([0-9]+) - ([0-9]+)")


@dataclass(frozen=True)
class Miss:
    shot: int
    rebound: int
    shooter: int
    description_field: str


@dataclass(frozen=True)
class MissEvidence:
    misses: tuple[Miss, ...]
    # One per shooter. Report the box counts that make the game-level inference unique.
    box_totals: tuple[tuple[int, int, int], ...]

    def parser_events(self, raw: dict[int, RawEvent]) -> dict[int, RawEvent]:
        """Supply the pinned parser a miss marker, leaving the archived records untouched."""
        parser_rows = raw.copy()
        for miss in self.misses:
            original = raw[miss.shot]
            fields = original.fields.copy()
            fields[miss.description_field] = "MISS " + fields[miss.description_field]
            parser_rows[miss.shot] = RawEvent(fields, original.row_numbers)
        return parser_rows


def infer_missing_misses(
    raw: dict[int, RawEvent], game: GameBox, roster: Mapping[int, PlayerBox]
) -> MissEvidence | None:
    """Return supported miss annotations, or decline when a shooter's attempts disagree."""
    sequence = [(number, event.fields) for number, event in raw.items()]
    teams = {str(game.home_id), str(game.away_id)}
    attempts: dict[int, list[tuple[int, dict[str, str]]]] = defaultdict(list)
    candidates: dict[int, list[Miss]] = defaultdict(list)
    made_free_throws: set[int] = set()
    previous_score: tuple[int, int] | None = (0, 0)
    for index, (number, event) in enumerate(sequence):
        kind = event["EVENTMSGTYPE"]
        team = event["PLAYER1_TEAM_ID"]
        if value := event["SCORE"]:
            match = SCORE.fullmatch(value)
            score = (int(match[1]), int(match[2])) if match is not None else None
            if kind == "3" and team in teams and previous_score is not None:
                away, home = previous_score
                expected = (away + 1, home) if team == str(game.away_id) else (away, home + 1)
                if score == expected:
                    made_free_throws.add(number)
            previous_score = score
        if kind != "3" or not event["PLAYER1_ID"].isdigit():
            continue
        shooter = int(event["PLAYER1_ID"])
        attempts[shooter].append((number, event))
        slot = TRIPS.get(event["EVENTMSGACTIONTYPE"])
        if slot is None or event["SCORE"] or index + 1 == len(sequence):
            continue
        attempt, total = slot
        if team not in teams or not event["PCTIMESTRING"]:
            continue
        field = "HOMEDESCRIPTION" if team == str(game.home_id) else "VISITORDESCRIPTION"
        if event[field] != f"Free Throw {attempt} of {total}" or any(
            event[key] for key in DESCRIPTIONS if key != field
        ):
            continue
        rebound_num, rebound = sequence[index + 1]
        clock = event["PERIOD"], event["PCTIMESTRING"]
        rebound_team = rebound["PLAYER1_ID"]
        if (
            rebound["EVENTMSGTYPE"] != "4"
            or rebound["EVENTMSGACTIONTYPE"] not in {"0", "1"}
            or rebound_team not in teams
            or rebound["PLAYER1_TEAM_ID"] not in {"", rebound_team}
            or (rebound["PERIOD"], rebound["PCTIMESTRING"]) != clock
        ):
            continue
        if attempt < total:
            # Between attempts the same team's rebound is a dead-ball record. Require the next
            # attempt of the same trip at this clock to establish that interpretation.
            if index + 2 == len(sequence):
                continue
            following = sequence[index + 2][1]
            if (
                rebound_team != team
                or following["EVENTMSGTYPE"] != "3"
                or TRIPS.get(following["EVENTMSGACTIONTYPE"]) != (attempt + 1, total)
                or following["PLAYER1_ID"] != event["PLAYER1_ID"]
                or following["PLAYER1_TEAM_ID"] != team
                or (following["PERIOD"], following["PCTIMESTRING"]) != clock
            ):
                continue
        candidates[shooter].append(Miss(number, rebound_num, shooter, field))

    supported = []
    box_totals = []
    for shooter, misses in sorted(candidates.items()):
        player = roster.get(shooter)
        if (
            player is None
            or player.free_throws_made is None
            or player.free_throws_attempted != len(attempts[shooter])
            or any(
                raw[miss.shot].fields["PLAYER1_TEAM_ID"] != str(player.team_id) for miss in misses
            )
        ):
            return None
        patched = {miss.shot for miss in misses}
        makes = 0
        for number, event in attempts[shooter]:
            marker = "MISS " in "".join(event[field] for field in DESCRIPTIONS)
            score = event["SCORE"]
            if not score and (marker or number in patched):
                continue
            if not marker and number in made_free_throws:
                makes += 1
            else:
                return None
        if makes != player.free_throws_made:
            return None
        supported.extend(misses)
        box_totals.append((shooter, makes, len(attempts[shooter])))
    if not supported:
        return None
    return MissEvidence(tuple(supported), tuple(box_totals))
