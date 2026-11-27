"""V2-schema play-by-play events rebuilt from V3 actions and NBA liveData (#133).

The NBA retired the V2 play-by-play endpoint, and the pinned archive has no V2 file from
2025–26. This module rebuilds, for one game, the V2 rows the pilot build reads from the
archived V3 actions, with liveData supplying the secondary players V3 does not carry. V3
actionNumber is the V2 EVENTNUM, and liveData uses the same numbering.

Only the fields the parser and the build read are rebuilt (event and action types, period,
clock, descriptions, the three player slots and their teams, score and video flag). Names,
cities, wall-clock times and person types other than the ones derived below stay empty.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Container, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from bil.data.pilot_inputs import GameIssue, RawEvent, archive_rows, nba_game_id

EVENT_SOURCE_VERSION = "v3-live-events-2"
V2_HEADERS = (
    "GAME_ID",
    "EVENTNUM",
    "EVENTMSGTYPE",
    "EVENTMSGACTIONTYPE",
    "PERIOD",
    "WCTIMESTRING",
    "PCTIMESTRING",
    "HOMEDESCRIPTION",
    "NEUTRALDESCRIPTION",
    "VISITORDESCRIPTION",
    "SCORE",
    "SCOREMARGIN",
    *(
        f"{prefix}{n}{suffix}"
        for n in (1, 2, 3)
        for prefix, suffix in (
            ("PERSON", "TYPE"),
            ("PLAYER", "_ID"),
            ("PLAYER", "_NAME"),
            ("PLAYER", "_TEAM_ID"),
            ("PLAYER", "_TEAM_CITY"),
            ("PLAYER", "_TEAM_NICKNAME"),
            ("PLAYER", "_TEAM_ABBREVIATION"),
        )
    ),
    "VIDEO_AVAILABLE_FLAG",
)
# V3 (actionType, subType) to V2 (EVENTMSGTYPE, EVENTMSGACTIONTYPE). Learned on the
# development seasons 2020–21 to 2022–23, where both feeds exist: each pair maps to one V2
# code in every joined event except one-off source quirks. Unknown pairs quarantine the game.
ACTION_TYPES: dict[tuple[str, str], tuple[int, int]] = {
    ("Rebound", "Unknown"): (4, 0),
    ("Substitution", ""): (8, 0),
    ("Missed Shot", "Jump Shot"): (2, 1),
    ("Made Shot", "Jump Shot"): (1, 1),
    ("Foul", "Shooting"): (6, 2),
    ("Free Throw", "Free Throw 1 of 2"): (3, 11),
    ("Free Throw", "Free Throw 2 of 2"): (3, 12),
    ("Missed Shot", "Pullup Jump shot"): (2, 79),
    ("Foul", "Personal"): (6, 1),
    ("Timeout", "Regular"): (9, 1),
    ("Turnover", "Bad Pass"): (5, 1),
    ("Made Shot", "Pullup Jump shot"): (1, 79),
    ("Missed Shot", "Driving Layup Shot"): (2, 6),
    ("Made Shot", "Driving Layup Shot"): (1, 6),
    ("Turnover", "Lost Ball"): (5, 2),
    ("Missed Shot", "Step Back Jump shot"): (2, 80),
    ("Free Throw", "Free Throw 1 of 1"): (3, 10),
    ("Rebound", "Normal Rebound"): (4, 1),
    ("Missed Shot", "Driving Floating Jump Shot"): (2, 101),
    ("period", "start"): (12, 0),
    ("period", "end"): (13, 0),
    ("Made Shot", "Driving Floating Jump Shot"): (1, 101),
    ("Turnover", "Offensive Foul Turnover"): (5, 37),
    ("Made Shot", "Step Back Jump shot"): (1, 80),
    ("Turnover", "Out of Bounds - Bad Pass Turnover"): (5, 45),
    ("Missed Shot", "Layup Shot"): (2, 5),
    ("Made Shot", "Cutting Layup Shot"): (1, 98),
    ("Made Shot", "Layup Shot"): (1, 5),
    ("Made Shot", "Running Layup Shot"): (1, 41),
    ("Made Shot", "Driving Finger Roll Layup Shot"): (1, 75),
    ("Foul", "Offensive"): (6, 4),
    ("Made Shot", "Cutting Dunk Shot"): (1, 108),
    ("Foul", "Loose Ball"): (6, 3),
    ("Missed Shot", "Floating Jump shot"): (2, 78),
    ("Missed Shot", "Fadeaway Jump Shot"): (2, 63),
    ("Missed Shot", "Tip Layup Shot"): (2, 97),
    ("Made Shot", "Putback Layup Shot"): (1, 72),
    ("Made Shot", "Tip Layup Shot"): (1, 97),
    ("Made Shot", "Floating Jump shot"): (1, 78),
    ("Missed Shot", "Running Layup Shot"): (2, 41),
    ("Made Shot", "Running Dunk Shot"): (1, 50),
    ("Turnover", "Traveling"): (5, 4),
    ("Jump Ball", ""): (10, 0),
    ("Foul", "Personal Take"): (6, 28),
    ("Missed Shot", "Running Jump Shot"): (2, 2),
    ("Missed Shot", "Driving Finger Roll Layup Shot"): (2, 75),
    ("Missed Shot", "Turnaround Jump Shot"): (2, 47),
    ("Turnover", "Out of Bounds Lost Ball Turnover"): (5, 40),
    ("Missed Shot", "Turnaround Fadeaway shot"): (2, 86),
    ("Missed Shot", "Cutting Layup Shot"): (2, 98),
    ("Turnover", "Shot Clock Turnover"): (5, 11),
    ("Made Shot", "Fadeaway Jump Shot"): (1, 63),
    ("Made Shot", "Alley Oop Dunk Shot"): (1, 52),
    ("Made Shot", "Driving Floating Bank Jump Shot"): (1, 102),
    ("Made Shot", "Driving Dunk Shot"): (1, 9),
    ("Made Shot", "Dunk Shot"): (1, 7),
    ("Missed Shot", "Driving Floating Bank Jump Shot"): (2, 102),
    ("Free Throw", "Free Throw Technical"): (3, 16),
    ("Made Shot", "Running Jump Shot"): (1, 2),
    ("Made Shot", "Turnaround Fadeaway shot"): (1, 86),
    ("Made Shot", "Turnaround Jump Shot"): (1, 47),
    ("Missed Shot", "Running Pull-Up Jump Shot"): (2, 103),
    ("Made Shot", "Driving Reverse Layup Shot"): (1, 73),
    ("Foul", "Offensive Charge"): (6, 26),
    ("Made Shot", "Turnaround Hook Shot"): (1, 58),
    ("Missed Shot", "Turnaround Hook Shot"): (2, 58),
    ("Missed Shot", "Putback Layup Shot"): (2, 72),
    ("Missed Shot", "Hook Shot"): (2, 3),
    ("Made Shot", "Hook Shot"): (1, 3),
    ("Violation", "Kicked Ball"): (7, 5),
    ("Made Shot", "Running Finger Roll Layup Shot"): (1, 76),
    ("Made Shot", "Reverse Layup Shot"): (1, 44),
    ("Missed Shot", "Driving Reverse Layup Shot"): (2, 73),
    ("Foul", "Technical"): (6, 11),
    ("Turnover", "Step Out of Bounds Turnover"): (5, 39),
    ("Made Shot", "Running Pull-Up Jump Shot"): (1, 103),
    ("Free Throw", "Free Throw 1 of 3"): (3, 13),
    ("Free Throw", "Free Throw 2 of 3"): (3, 14),
    ("Free Throw", "Free Throw 3 of 3"): (3, 15),
    ("Instant Replay", "Support Ruling"): (18, 0),
    ("Missed Shot", "Driving Hook Shot"): (2, 57),
    ("Made Shot", "Tip Dunk Shot"): (1, 107),
    ("Made Shot", "Alley Oop Layup shot"): (1, 43),
    ("Violation", "Defensive Goaltending"): (7, 2),
    ("Made Shot", "Driving Hook Shot"): (1, 57),
    ("Made Shot", "Cutting Finger Roll Layup Shot"): (1, 99),
    ("Violation", "Delay Of Game"): (7, 1),
    ("Missed Shot", "Reverse Layup Shot"): (2, 44),
    ("Made Shot", "Putback Dunk Shot"): (1, 87),
    ("Foul", "Defense 3 Second"): (6, 17),
    ("Instant Replay", "Coach Challenge Overturn Ruling"): (18, 5),
    ("Made Shot", "Running Reverse Layup Shot"): (1, 74),
    ("Missed Shot", "Driving Dunk Shot"): (2, 9),
    ("Instant Replay", "Overturn Ruling"): (18, 1),
    ("Made Shot", "Running Alley Oop Dunk Shot"): (1, 106),
    ("Missed Shot", "Alley Oop Layup shot"): (2, 43),
    ("Missed Shot", "Running Finger Roll Layup Shot"): (2, 76),
    ("Made Shot", "Jump Bank Shot"): (1, 66),
    ("Made Shot", "Finger Roll Layup Shot"): (1, 71),
    ("Missed Shot", "Jump Bank Shot"): (2, 66),
    ("Missed Shot", "Cutting Dunk Shot"): (2, 108),
    ("Missed Shot", "Dunk Shot"): (2, 7),
    ("Instant Replay", "Coach Challenge Ruling Stands"): (18, 6),
    ("Made Shot", "Turnaround Fadeaway Bank Jump Shot"): (1, 105),
    ("Turnover", "Backcourt Turnover"): (5, 13),
    ("Timeout", "Coach Challenge"): (9, 7),
    ("Instant Replay", "Ruling Stands"): (18, 3),
    ("Missed Shot", "Alley Oop Dunk Shot"): (2, 52),
    ("Foul", "Flagrant Type 1"): (6, 14),
    ("Turnover", "3 Second Violation"): (5, 8),
    ("Missed Shot", "Turnaround Fadeaway Bank Jump Shot"): (2, 105),
    ("Instant Replay", "Coach Challenge Support Ruling"): (18, 4),
    ("Missed Shot", "Running Reverse Layup Shot"): (2, 74),
    ("Made Shot", "Driving Bank Hook Shot"): (1, 93),
    ("Missed Shot", "Finger Roll Layup Shot"): (2, 71),
    ("Free Throw", "Free Throw Flagrant 1 of 2"): (3, 18),
    ("Free Throw", "Free Throw Flagrant 2 of 2"): (3, 19),
    ("Missed Shot", "Running Dunk Shot"): (2, 50),
    ("Turnover", "Offensive Goaltending"): (5, 15),
    ("Missed Shot", "Driving Bank Hook Shot"): (2, 93),
    ("Missed Shot", "Cutting Finger Roll Layup Shot"): (2, 99),
    ("Missed Shot", "Tip Dunk Shot"): (2, 107),
    ("Made Shot", "Turnaround Bank Hook Shot"): (1, 96),
    ("Made Shot", "Running Alley Oop Layup Shot"): (1, 100),
    ("Foul", "Away From Play"): (6, 6),
    ("Turnover", "Palming Turnover"): (5, 21),
    ("Made Shot", "Reverse Dunk Shot"): (1, 51),
    ("Jump Ball", "Coach Challenge"): (10, 1),
    ("Turnover", "Double Dribble"): (5, 6),
    ("Made Shot", "Hook Bank Shot"): (1, 67),
    ("Ejection", "Other"): (11, 4),
    ("Foul", "Double Technical"): (6, 16),
    ("Foul", "Transition Take"): (6, 31),
    ("Turnover", "Discontinue Dribble"): (5, 7),
    ("Missed Shot", "Turnaround Bank Hook Shot"): (2, 96),
    ("Made Shot", "Turnaround Bank shot"): (1, 85),
    ("Violation", "Lane"): (7, 3),
    ("Missed Shot", "Hook Bank Shot"): (2, 67),
    ("Instant Replay", "Altercation Ruling"): (18, 2),
    ("Foul", "Clear Path"): (6, 9),
    ("Free Throw", "Free Throw Clear Path 1 of 2"): (3, 25),
    ("Free Throw", "Free Throw Clear Path 2 of 2"): (3, 26),
    ("Turnover", "5 Second Violation"): (5, 9),
    ("Missed Shot", "Putback Dunk Shot"): (2, 87),
    ("Foul", "Delay Technical"): (6, 18),
    ("Instant Replay", "Replay Center"): (18, 7),
    ("Missed Shot", "Turnaround Bank shot"): (2, 85),
    ("Made Shot", "Step Back Bank Jump Shot"): (1, 104),
    ("Missed Shot", "Step Back Bank Jump Shot"): (2, 104),
    ("Made Shot", "Fadeaway Bank shot"): (1, 83),
    ("Turnover", "8 Second Violation"): (5, 10),
    ("Missed Shot", "Running Alley Oop Layup Shot"): (2, 100),
    ("Turnover", ""): (5, 0),
    ("Made Shot", "Driving Reverse Dunk Shot"): (1, 109),
    ("Missed Shot", "Fadeaway Bank shot"): (2, 83),
    ("Free Throw", "Free Throw Flagrant 1 of 3"): (3, 27),
    ("Free Throw", "Free Throw Flagrant 2 of 3"): (3, 28),
    ("Free Throw", "Free Throw Flagrant 3 of 3"): (3, 29),
    ("Missed Shot", "Running Alley Oop Dunk Shot"): (2, 106),
    ("Turnover", "Kicked Ball Violation"): (5, 19),
    ("Turnover", "Inbound Turnover"): (5, 12),
    ("Made Shot", "Running Reverse Dunk Shot"): (1, 110),
    ("Free Throw", "Free Throw Flagrant 1 of 1"): (3, 20),
    ("Foul", "Double Personal"): (6, 10),
    ("Foul", "Flagrant Type 2"): (6, 15),
    ("Turnover", "Lane Violation"): (5, 17),
    ("Violation", "Jump Ball"): (7, 4),
    ("Turnover", "Illegal Assist Turnover"): (5, 20),
    ("Missed Shot", "Reverse Dunk Shot"): (2, 51),
    ("Violation", "Double Lane"): (7, 6),
    ("Missed Shot", "Driving Reverse Dunk Shot"): (2, 109),
    ("Foul", "Non-Unsportsmanlike Technical"): (6, 12),
    ("Turnover", "Jump Ball Violation"): (5, 18),
    ("Foul", "Hanging Technical"): (6, 13),
    ("Turnover", "Basket from Below Turnover"): (5, 35),
    ("Foul", "Excess Timeout Technical"): (6, 25),
    ("Turnover", "Excess Timeout Turnover"): (5, 42),
    ("Free Throw", "Free Throw Technical 1 of 2"): (3, 21),
    ("Free Throw", "Free Throw Technical 2 of 2"): (3, 22),
    ("Foul", "Too Many Players Technical"): (6, 30),
    ("Turnover", "Illegal Screen Turnover"): (5, 36),
    ("Missed Shot", "Running Reverse Dunk Shot"): (2, 110),
    ("Turnover", "Punched Ball Turnover"): (5, 33),
    ("Turnover", "Too Many Players Turnover"): (5, 44),
    ("Turnover", "Swinging Elbows Turnover"): (5, 34),
    ("Foul", "Punching"): (6, 8),
}
V3_FIELDS = (
    "actionNumber",
    "actionId",
    "clock",
    "period",
    "teamId",
    "personId",
    "description",
    "actionType",
    "subType",
    "scoreHome",
    "scoreAway",
    "videoAvailable",
    "playerName",
    "playerNameI",
)
LIVE_FIELDS = (
    "actionNumber",
    "clock",
    "period",
    "actionType",
    "subType",
    "personId",
    "teamId",
    "playerName",
    "playerNameI",
    "assistPersonId",
    "foulDrawnPersonId",
    "stealPersonId",
    "blockPersonId",
    "jumpBallWonPersonId",
    "jumpBallLostPersonId",
    "jumpBallRecoverdPersonId",
    "personIdsFilter",
)
CLOCK = re.compile(r"PT(\d+)M(\d+)(?:\.\d+)?S")
SUB_NAMES = re.compile(r"SUB: (.+) FOR (.+)")
MADE_FREE_THROW = 3
SHOT_TYPES = {"Made Shot": 1, "Missed Shot": 2}
HOME_VOTE_SHARE = 0.9
MIN_HOME_VOTES = 5
DOUBLE_FOULS = {(6, 10), (6, 16)}  # double personal, double technical
# Revision 2 (#133): V3 pairs absent from the 2020–23 table. A documented rule pair first,
# then a class-preserving fallback that quarantines whenever the class is unclear.
RULE_TYPES = {
    # NBA rule from 2023–24: in-game flopping is a non-unsportsmanlike technical foul.
    # The registered validation found V2 codes it as foul action 32, not a technical, so this
    # entry fails its class check (docs/research/v3-event-path-validation.md, ADR-0033). The
    # path is not adopted; the entry stays as registered and must not be tuned on 2023–25.
    ("Foul", "Flopping"): (6, 12),
}
TECHNICAL_FOUL = (6, 11)
PERSONAL_FOUL = (6, 1)
TURNOVER = (5, 1)
TECHNICAL_TEXT = re.compile(r"(?<![A-Z.])T\.FOUL", re.IGNORECASE)
PERSONAL_TEXT = re.compile(r"(?<![A-Z.])P\.FOUL", re.IGNORECASE)
UNSAFE_FOUL = re.compile(r"FLAGRANT|DOUBLE", re.IGNORECASE)
TECHNICAL_CODES = {11, 12, 13, 18, 19, 25, 30}  # pbpstats Foul.is_technical


def fallback_code(action_type: str, sub_type: str, text: str) -> tuple[int, int] | None:
    """A class-preserving code for an unknown foul or turnover subtype, or None.

    pbpstats reads a foul's class, and a turnover's code only as zero ("no turnover") or
    not. Fouls: none when a flagrant or double foul is named; technical when the subtype
    names a technical or the text carries the ``T.FOUL`` marker; personal only with the
    ``P.FOUL`` marker; otherwise none, because inbound, block, take and similar classes
    change free-throw and possession handling. Turnovers: any named subtype is a real one.
    """
    if action_type == "Foul":
        if UNSAFE_FOUL.search(sub_type) or UNSAFE_FOUL.search(text):
            return None
        if "technical" in sub_type.lower() or TECHNICAL_TEXT.search(text):
            return TECHNICAL_FOUL
        if PERSONAL_TEXT.search(text):
            return PERSONAL_FOUL
        return None
    if action_type == "Turnover" and sub_type:
        return TURNOVER
    return None


def event_class(event_type: int, action_type: int) -> str:
    """The class the parser distinguishes for a foul or turnover code (revision-2 limit L8)."""
    if event_type == 6:
        if action_type in TECHNICAL_CODES:
            return "technical"
        if action_type in {10, 16}:
            return "double"
        if action_type in {14, 15}:
            return "flagrant"
        return "personal" if action_type == 1 else f"foul_{action_type}"
    if event_type == 5:
        return "no_turnover" if action_type == 0 else "turnover"
    return f"type_{event_type}"


@dataclass(frozen=True)
class Action:
    line: int
    fields: dict[str, str]

    def number(self, name: str) -> int:
        value = self.fields.get(name, "")
        return int(float(value)) if value not in ("", "NA") else 0


def _games(path: Path, key: str, keep: Sequence[str]) -> dict[str, list[Action]]:
    games: dict[str, list[Action]] = defaultdict(list)
    for line, row in enumerate(archive_rows(path), 2):
        games[nba_game_id(row[key])].append(Action(line, {k: row.get(k, "") for k in keep}))
    return dict(games)


def v3_actions(path: Path) -> dict[str, list[Action]]:
    return _games(path, "gameId", V3_FIELDS)


def live_actions(path: Path) -> dict[str, list[Action]]:
    return _games(path, "gameId", LIVE_FIELDS)


FLAGRANT = {(6, 14), (6, 15)}


def flagrant_events(path: Path, games: Container[str]) -> set[tuple[str, str]]:
    """(game, event number) of the flagrant fouls in a V3 file, as the rebuilt rows code them."""
    found: set[tuple[str, str]] = set()
    for row in archive_rows(path):
        if ACTION_TYPES.get((row["actionType"], row["subType"])) not in FLAGRANT:
            continue
        game_id = nba_game_id(row["gameId"])
        if game_id in games:
            found.add((game_id, str(int(float(row["actionNumber"])))))
    return found


def v2_clock(value: str) -> str:
    """PT11M43.20S to the V2 form 11:43; V2 truncates tenths."""
    match = CLOCK.fullmatch(value)
    if match is None:
        raise GameIssue("v3_clock_format", f"Unreadable V3 clock {value!r}")
    return f"{int(match.group(1))}:{match.group(2)}"


def derive_home(actions: Sequence[Action], teams: tuple[int, int]) -> int | None:
    """The home team from V3 running scores: a team's points move ``scoreHome`` iff it is home.

    Each scoring change by one of the two teams is a vote. A team is home when at least
    ``HOME_VOTE_SHARE`` of its votes say so and the other team's votes say away by the same
    share; a few corrected or misattributed baskets therefore do not block the decision.
    """
    votes: dict[int, list[int]] = {team: [0, 0] for team in teams}  # [home, away]
    home = away = 0
    for action in sorted(actions, key=lambda a: a.number("actionId")):
        if action.fields["scoreHome"] in ("", "NA") or action.fields["scoreAway"] in ("", "NA"):
            continue
        h, a = action.number("scoreHome"), action.number("scoreAway")
        team = action.number("teamId")
        if team in votes and (h != home) != (a != away):
            votes[team][0 if h != home else 1] += 1
        home, away = h, a
    for candidate, other in (teams, teams[::-1]):
        as_home, as_away = votes[candidate], votes[other]
        if (
            sum(as_home) >= MIN_HOME_VOTES
            and sum(as_away) >= MIN_HOME_VOTES
            and as_home[0] >= HOME_VOTE_SHARE * sum(as_home)
            and as_away[1] >= HOME_VOTE_SHARE * sum(as_away)
        ):
            return candidate
    return None


def _side(action: Action, home: int, away: int) -> str:
    team = action.number("teamId") or action.number("personId")
    if team == home:
        return "HOMEDESCRIPTION"
    if team == away:
        return "VISITORDESCRIPTION"
    return "NEUTRALDESCRIPTION"


def _person_type(person: int, team: int | None, home: int, away: int) -> int:
    if person == 0:
        return 0
    if team is None:
        return 2 if person == home else 3 if person == away else 0
    return 4 if team == home else 5 if team == away else 0


def _surname(name: str) -> str:
    return name.split(". ", 1)[-1].strip().casefold()


class _Substitutions:
    """liveData ``substitution in`` rows, paired with V3 substitutions.

    liveData writes each stoppage's substitutions as one batch of consecutive rows: the
    ``out`` rows, which share the V3 action numbers, then the ``in`` rows. A V3 substitution
    takes an ``in`` row of the same team from the batch of its ``out`` row, preferring the
    one whose surname matches the incoming name in the V3 description. Without a matching
    ``out`` row it falls back to an ``in`` row of the same team, period and clock. A surname
    that names exactly one player of the team in the game's own V3 or liveData rows is used first.
    """

    def __init__(self, live: Sequence[Action], actions: Sequence[Action]) -> None:
        # Surname to person per team, from the game's own V3 and liveData rows.
        names: dict[tuple[int, str], set[int]] = defaultdict(set)
        for action in (*actions, *live):
            person, team = action.number("personId"), action.number("teamId")
            for field in ("playerName", "playerNameI"):
                name = action.fields[field].strip().casefold()
                if person and team and name:
                    names[(team, name)].add(person)
        self.names = {key: next(iter(v)) for key, v in names.items() if len(v) == 1}
        self.used: set[int] = set()  # liveData ``in`` rows already paired, by line
        self.batch_of: dict[int, int] = {}
        self.pending: dict[tuple[int, int], list[Action]] = defaultdict(list)
        self.by_clock: dict[tuple[str, str, int], list[Action]] = defaultdict(list)
        batch, previous = -1, False
        for action in sorted(live, key=lambda a: a.number("actionNumber")):
            is_sub = action.fields["actionType"] == "substitution"
            if is_sub and not previous:
                batch += 1
            previous = is_sub
            if not is_sub:
                continue
            if action.fields["subType"] == "out":
                self.batch_of[action.number("actionNumber")] = batch
            elif action.fields["subType"] == "in":
                self.pending[(batch, action.number("teamId"))].append(action)
                key = (action.fields["period"], action.fields["clock"], action.number("teamId"))
                self.by_clock[key].append(action)

    def incoming(self, sub: Action) -> int:
        team = sub.number("teamId")
        names = SUB_NAMES.fullmatch(sub.fields["description"].strip())
        wanted = names.group(1).strip().casefold() if names is not None else None
        batch = self.batch_of.get(sub.number("actionNumber"))
        if batch is not None and self.pending.get((batch, team)):
            candidates = self.pending[(batch, team)]
        else:
            candidates = self.by_clock.get((sub.fields["period"], sub.fields["clock"], team), [])
        candidates = [c for c in candidates if c.line not in self.used]
        if wanted is not None and (team, wanted) in self.names:
            person = self.names[(team, wanted)]
            # Retire this substitution's own liveData row so a fallback cannot take it.
            for candidate in candidates:
                if candidate.number("personId") == person:
                    self.used.add(candidate.line)
                    break
            return person
        if not candidates:
            raise GameIssue(
                "v3_substitution_unpaired",
                "No liveData substitution in for a V3 substitution",
                sub.number("actionNumber"),
            )
        chosen = candidates[0]
        if wanted is not None:
            named = [c for c in candidates if _surname(c.fields["playerName"]) == _surname(wanted)]
            if len(named) == 1:
                chosen = named[0]
        self.used.add(chosen.line)
        return chosen.number("personId")


def rebuild_game(
    game_id: str,
    actions: Sequence[Action],
    live: Sequence[Action],
    teams: tuple[int, int],
    home: int | None,
    roster: Mapping[int, int],
) -> list[RawEvent]:
    """V2-schema rows for one game, in V3 action order.

    teams are the two box teams and home the box home team, or None when the box
    leaves it unflagged. roster maps each box player to his team. Raises GameIssue.
    """
    derived = derive_home(actions, teams)
    if derived is None:
        raise GameIssue("v3_home_undetermined", "V3 running scores do not fix the home team")
    if home is not None and derived != home:
        raise GameIssue("v3_home_conflict", "V3 running scores contradict the box home flag")
    home = derived
    away = teams[1] if home == teams[0] else teams[0]
    groups: dict[int, list[Action]] = defaultdict(list)
    for action in actions:
        groups[action.number("actionNumber")].append(action)
    live_by_number: dict[int, Action] = {}
    for action in live:
        if action.fields["actionType"] != "substitution" or action.fields["subType"] != "in":
            live_by_number.setdefault(action.number("actionNumber"), action)
    subs = _Substitutions(live, actions)

    def position(item: tuple[int, list[Action]]) -> tuple[int, int, int]:
        # V3 action order, except that a period's start row leads its period: V3 sometimes
        # files a stoppage at 12:00 (a delay-of-game violation, say) before it.
        first = min(item[1], key=lambda a: a.number("actionId"))
        start = first.fields["actionType"] == "period" and first.fields["subType"] == "start"
        return first.number("period"), 0 if start else 1, first.number("actionId")

    ordered = sorted(groups.items(), key=position)
    events: list[RawEvent] = []
    for number, group in ordered:
        group.sort(key=lambda a: a.number("actionId"))
        typed = [a for a in group if a.fields["actionType"].strip()]
        if not typed:
            raise GameIssue("v3_action_without_type", "V3 event has no typed action", number)
        primary = typed[0]
        key = (primary.fields["actionType"].strip(), primary.fields["subType"].strip())
        if key in ACTION_TYPES:
            event_type, action_type = ACTION_TYPES[key]
        elif key in RULE_TYPES:
            event_type, action_type = RULE_TYPES[key]
        elif key[0] in SHOT_TYPES:
            # Shot action codes are read by neither pbpstats nor the build, so a new shot
            # subtype becomes a plain made or missed field goal. Any other unknown pair is not.
            event_type, action_type = SHOT_TYPES[key[0]], 0
        elif fallback := fallback_code(*key, primary.fields["description"]):
            event_type, action_type = fallback
        else:
            raise GameIssue("v3_unmapped_action", f"Unmapped V3 action {key}", number)
        row = dict.fromkeys(V2_HEADERS, "")
        descriptions: dict[str, list[str]] = defaultdict(list)
        for action in group:
            text = action.fields["description"].strip()
            if text:
                descriptions[_side(action, home, away)].append(text)
        if (event_type, action_type) in DOUBLE_FOULS:
            # V2 writes double fouls and double technicals as neutral events.
            descriptions = {
                "NEUTRALDESCRIPTION": [t for texts in descriptions.values() for t in texts]
            }
        for column, texts in descriptions.items():
            row[column] = " ".join(texts)
        person = primary.number("personId")
        team = primary.number("teamId") or None
        player2 = player3 = 0
        player3_team: int | None = None
        match = live_by_number.get(number)
        # liveData clocks are sometimes edited after the fact, so match on number and period.
        if match is not None and match.fields["period"] != primary.fields["period"]:
            match = None

        def live_id(name: str) -> int:
            return match.number(name) if match is not None else 0

        secondary = [a for a in group if a is not primary and not a.fields["actionType"].strip()]
        if event_type == 1:
            player2 = live_id("assistPersonId")
        elif event_type == 2:
            blocks = [a for a in secondary if "BLOCK" in a.fields["description"]]
            player3 = blocks[0].number("personId") if blocks else live_id("blockPersonId")
        elif event_type == 5:
            steals = [a for a in secondary if "STEAL" in a.fields["description"]]
            player2 = steals[0].number("personId") if steals else live_id("stealPersonId")
        elif event_type == 6 and (event_type, action_type) in DOUBLE_FOULS:
            ids = (
                [int(p) for p in re.findall(r"\d+", match.fields["personIdsFilter"])]
                if match
                else []
            )
            others = [p for p in ids if p != person]
            player2 = others[0] if others else 0
        elif event_type == 6:
            player2 = live_id("foulDrawnPersonId")
        elif event_type == 8:
            player2 = subs.incoming(primary)
        elif event_type == 10:
            jumpers = {live_id("jumpBallWonPersonId"), live_id("jumpBallLostPersonId")} - {0}
            others = sorted(jumpers - {person})
            player2 = others[0] if len(others) == 1 else 0
            player3 = live_id("jumpBallRecoverdPersonId")
            if player3:
                player3_team = roster.get(player3)
            elif match is not None and match.number("teamId"):
                player3 = match.number("teamId")
        player2_team = roster.get(player2) if player2 else None
        if event_type != 10 and player3:
            player3_team = roster.get(player3)
        row.update(
            GAME_ID=game_id,
            EVENTNUM=str(number),
            EVENTMSGTYPE=str(event_type),
            EVENTMSGACTIONTYPE=str(action_type),
            PERIOD=primary.fields["period"],
            PCTIMESTRING=v2_clock(primary.fields["clock"]),
            PERSON1TYPE=str(_person_type(person, team, home, away)),
            PLAYER1_ID=str(person),
            PLAYER1_TEAM_ID="" if team is None else str(team),
            PERSON2TYPE=str(_person_type(player2, player2_team, home, away)),
            PLAYER2_ID=str(player2),
            PLAYER2_TEAM_ID="" if player2_team is None else str(player2_team),
            PERSON3TYPE=str(_person_type(player3, player3_team, home, away)),
            PLAYER3_ID=str(player3),
            PLAYER3_TEAM_ID="" if player3_team is None else str(player3_team),
            VIDEO_AVAILABLE_FLAG=str(primary.number("videoAvailable")),
        )
        if event_type == 1 or (event_type == MADE_FREE_THROW and "MISS " not in row_text(row)):
            h, a = primary.fields["scoreHome"], primary.fields["scoreAway"]
            if h.isdigit() and a.isdigit():
                margin = int(h) - int(a)
                row["SCORE"] = f"{a} - {h}"
                row["SCOREMARGIN"] = "TIE" if margin == 0 else str(margin)
        events.append(RawEvent(row, [a.line for a in group]))
    return events


def row_text(row: Mapping[str, str]) -> str:
    return " ".join(
        row[c] for c in ("HOMEDESCRIPTION", "NEUTRALDESCRIPTION", "VISITORDESCRIPTION") if row[c]
    )


def rebuilt_games(
    v3_path: Path,
    live_path: Path,
    boxes: Mapping[str, tuple[tuple[int, int], int | None, Mapping[int, int]]],
) -> Iterator[tuple[str, list[RawEvent] | GameIssue]]:
    """Each box game's rebuilt V2 rows, or the GameIssue that stopped the rebuild."""
    actions = v3_actions(v3_path)
    live = live_actions(live_path)
    for game_id in sorted(actions):
        if game_id not in boxes:
            continue
        teams, home, roster = boxes[game_id]
        if game_id not in live:
            yield game_id, GameIssue("v3_livedata_missing", "The game has no liveData actions")
            continue
        try:
            yield (
                game_id,
                rebuild_game(game_id, actions[game_id], live[game_id], teams, home, roster),
            )
        except GameIssue as issue:
            yield game_id, issue
