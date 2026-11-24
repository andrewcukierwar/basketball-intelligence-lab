"""Read the pinned 2022–23 event, shot-chart and box-score inputs."""

from __future__ import annotations

import csv
import re
import tarfile
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from io import TextIOWrapper
from itertools import groupby
from pathlib import Path

import duckdb

GAME_PREFIXES = {"002": "regular", "004": "playoffs"}
SHOT_FIELDS = ("GAME_EVENT_ID", "LOC_X", "LOC_Y", "SHOT_DISTANCE")
INTEGER_FIELDS = re.compile(
    r"EVENTNUM|EVENTMSGTYPE|EVENTMSGACTIONTYPE|PERIOD|PERSON[123]TYPE|"
    r"PLAYER[123]_(ID|TEAM_ID)|VIDEO_AVAILABLE_FLAG"
)


class GameIssue(ValueError):
    """Data evidence is insufficient to accept this game."""

    def __init__(self, code: str, detail: str, event_num: int | None = None) -> None:
        super().__init__(detail)
        self.code = code
        self.event_num = event_num


@dataclass(frozen=True)
class GameBox:
    game_id: str
    played_date: date
    home_id: int
    away_id: int
    home_points: int
    away_points: int
    # False when the box log leaves the home flag null for both teams, as it does for some
    # 2024–25 neutral-site games. The home/away order is then provisional until V2 designates it.
    home_designated: bool = True


def designate_home(game: GameBox, events: list[RawEvent]) -> GameBox | None:
    """Take the home side from V2, where each team's actions appear in one description column.

    Counts events whose PLAYER1 team is set and that carry exactly one of the home and visitor
    descriptions. Both box teams must appear, each always on one side and on opposite sides.
    """
    sides: dict[str, set[str]] = defaultdict(set)
    for raw in events:
        row = raw.fields
        team = row.get("PLAYER1_TEAM_ID", "")
        home = row.get("HOMEDESCRIPTION", "") not in ("", "NA")
        visitor = row.get("VISITORDESCRIPTION", "") not in ("", "NA")
        if team not in ("", "NA") and home != visitor:
            sides[team].add("home" if home else "away")
    teams = {str(game.home_id), str(game.away_id)}
    if sides.keys() != teams or any(len(side) != 1 for side in sides.values()):
        return None
    if {side for values in sides.values() for side in values} != {"home", "away"}:
        return None
    if sides[str(game.home_id)] == {"home"}:
        return GameBox(
            game.game_id,
            game.played_date,
            game.home_id,
            game.away_id,
            game.home_points,
            game.away_points,
        )
    return GameBox(
        game.game_id,
        game.played_date,
        game.away_id,
        game.home_id,
        game.away_points,
        game.home_points,
    )


@dataclass(frozen=True)
class PlayerBox:
    team_id: int
    minutes_ms: int
    plus_minus: int


@dataclass
class RawEvent:
    fields: dict[str, str]
    row_numbers: list[int]


@dataclass
class V3Game:
    periods: dict[int, tuple[int, int]]
    substitutions: Counter[tuple[str, str, str]]
    # Event numbers in archived V3 action order. V3 actionNumber is the V2 EVENTNUM.
    order: list[int] = field(default_factory=list)


def nba_game_id(value: str) -> str:
    if not value.isascii() or not value.isdecimal() or len(value) > 10:
        raise ValueError("Malformed NBA game ID")
    return value.zfill(10)


def archive_rows(path: Path) -> Iterator[dict[str, str]]:
    with tarfile.open(path, "r:xz") as archive:
        members = [member for member in archive if member.isfile() and member.name.endswith(".csv")]
        if len(members) != 1:
            raise ValueError(f"Expected one CSV in {path.name}")
        raw = archive.extractfile(members[0])
        if raw is None:
            raise ValueError(f"Missing CSV stream in {path.name}")
        with TextIOWrapper(raw, encoding="utf-8-sig", newline="") as stream:
            yield from csv.DictReader(stream)


def event_games(path: Path) -> Iterator[tuple[str, list[RawEvent]]]:
    seen: set[str] = set()
    rows = enumerate(archive_rows(path), 2)
    for game_id, group in groupby(rows, key=lambda pair: nba_game_id(pair[1]["GAME_ID"])):
        if game_id in seen:
            raise ValueError(f"Interleaved NBA game in {path.name}: {game_id}")
        seen.add(game_id)
        yield game_id, [RawEvent(row, [line]) for line, row in group]


def deduplicate_events(rows: list[RawEvent]) -> dict[int, RawEvent]:
    unique: dict[int, RawEvent] = {}
    for row in rows:
        event_num = int(row.fields["EVENTNUM"])
        picked = unique.get(event_num)
        if picked is None:
            unique[event_num] = RawEvent(row.fields, list(row.row_numbers))
        elif picked.fields == row.fields:
            picked.row_numbers.extend(row.row_numbers)
        else:
            raise GameIssue("conflicting_event_id", "Source event has distinct rows", event_num)
    return unique


def _v2_field(column: str, value: str) -> str | int | None:
    if column == "GAME_ID":
        return nba_game_id(value)
    if value in ("", "NA"):
        return None
    if INTEGER_FIELDS.fullmatch(column):
        return int(value)
    return value


def event_payload(rows: dict[int, RawEvent]) -> object:
    headers = list(next(iter(rows.values())).fields)
    return {
        "resultSets": [
            {
                "name": "PlayByPlay",
                "headers": headers,
                "rowSet": [
                    [_v2_field(key, row.fields[key]) for key in headers] for row in rows.values()
                ],
            }
        ]
    }


def shot_rows(path: Path) -> dict[str, dict[int, list[tuple[int, ...]]]]:
    games: dict[str, dict[int, list[tuple[int, ...]]]] = {}
    for row in archive_rows(path):
        teams = games.setdefault(nba_game_id(row["GAME_ID"]), {})
        teams.setdefault(int(row["TEAM_ID"]), []).append(
            tuple(int(row[key]) for key in SHOT_FIELDS)
        )
    return games


def shot_payload(rows: list[tuple[int, ...]]) -> object:
    return {"resultSets": [{"name": "Shot_Chart_Detail", "headers": SHOT_FIELDS, "rowSet": rows}]}


def v3_games(path: Path) -> dict[str, V3Game]:
    final: dict[tuple[str, int], tuple[int, tuple[int, int]]] = {}
    games: dict[str, V3Game] = {}
    actions: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for row in archive_rows(path):
        game_id = nba_game_id(row["gameId"])
        game = games.setdefault(game_id, V3Game({}, Counter()))
        actions[game_id].append((int(row["actionId"]), int(row["actionNumber"])))
        if row["actionType"].casefold() == "substitution":
            game.substitutions[(row["period"], row["teamId"], row["personId"])] += 1
        if row["actionType"] != "period" or row["subType"] != "end":
            continue
        if not row["scoreHome"].isdigit() or not row["scoreAway"].isdigit():
            continue
        key = game_id, int(row["period"])
        order = int(row["actionNumber"])
        points = int(row["scoreHome"]), int(row["scoreAway"])
        if key not in final or order > final[key][0]:
            final[key] = order, points
        elif order == final[key][0] and points != final[key][1]:
            raise ValueError(f"Conflicting V3 final score for {game_id}")
    for (game_id, period), (_, points) in final.items():
        games[game_id].periods[period] = points
    for game_id, pairs in actions.items():
        if len({action_id for action_id, _ in pairs}) != len(pairs):
            raise ValueError(f"Repeated V3 action ID for {game_id}")
        sequence = games[game_id].order
        seen: set[int] = set()
        for _, event_num in sorted(pairs):
            if event_num not in seen:
                seen.add(event_num)
                sequence.append(event_num)
    return games


def v2_substitutions(raw: dict[int, RawEvent]) -> Counter[tuple[str, str, str]]:
    return Counter(
        (row.fields["PERIOD"], row.fields["PLAYER1_TEAM_ID"], row.fields["PLAYER1_ID"])
        for row in raw.values()
        if row.fields["EVENTMSGTYPE"] == "8"
    )


def box_scores(
    connection: duckdb.DuckDBPyConnection,
    directory: Path,
) -> tuple[dict[str, GameBox], dict[str, dict[int, PlayerBox]]]:
    team_rows = connection.execute(
        """
        SELECT game_id, game_date, team_id, opp_team_id, home, pts
        FROM read_parquet(?)
        WHERE left(game_id, 3) IN ('002', '004')
        ORDER BY game_id, home DESC
        """,
        [str(directory / "team_game_logs.parquet")],
    ).fetchall()
    games: dict[str, GameBox] = {}
    for game_id, rows in groupby(team_rows, key=lambda row: row[0]):
        sides = list(rows)
        if len(sides) != 2:
            raise ValueError(f"Expected two box-score teams for {game_id}")
        home, away = sides
        # Both flags null: keep a provisional, deterministic order for V2 to designate later.
        undesignated = home[4] is None and away[4] is None
        if undesignated and int(home[2]) > int(away[2]):
            home, away = away, home
        if not (
            (undesignated or (home[4] is True and away[4] is False))
            and home[1] == away[1]
            and home[2] == away[3]
            and away[2] == home[3]
            and home[2] != away[2]
        ):
            raise ValueError(f"Conflicting box-score team rows for {game_id}")
        games[game_id] = GameBox(
            game_id, home[1], int(home[2]), int(away[2]), home[5], away[5], not undesignated
        )
    players: dict[str, dict[int, PlayerBox]] = defaultdict(dict)
    for game_id, player_id, team_id, minutes, plus_minus in connection.execute(
        """
        SELECT game_id, player_id, team_id, min, plus_minus
        FROM read_parquet(?)
        WHERE left(game_id, 3) IN ('002', '004')
        """,
        [str(directory / "player_game_logs.parquet")],
    ).fetchall():
        person = int(player_id)
        if person <= 0 or person in players[game_id]:
            raise ValueError(f"Invalid player box-score keys for {game_id}")
        player = PlayerBox(int(team_id), round(minutes * 60_000), plus_minus)
        game = games.get(game_id)
        if game is None or player.team_id not in (game.home_id, game.away_id):
            raise ValueError(f"Invalid player box-score team for {game_id}")
        players[game_id][person] = player
    if games.keys() != players.keys():
        raise ValueError("Player and team box-score game sets differ")
    return games, dict(players)


@dataclass
class CrossFeed:
    """Evidence from the archived NBA liveData and data.nba.com feeds for one game."""

    live_periods: dict[int, tuple[int, int]] = field(default_factory=dict)
    datanba_periods: dict[int, tuple[int, int]] = field(default_factory=dict)
    # Substitutions logged at a period's starting clock, keyed by (period, team ID), as
    # (outgoing players, incoming players). Present only for games with liveData actions.
    between_periods: dict[tuple[int, int], tuple[frozenset[int], frozenset[int]]] = field(
        default_factory=dict
    )
    has_livedata: bool = False
    # data.nba.com offense team for each V2 event number that names one.
    offense: dict[int, int] = field(default_factory=dict)
    # data.nba.com ``ord`` for each V2 event number: the feed's own event sequence. It is
    # evidence only, and it is used solely by the opt-in order repair (ADR-0023, proposed).
    order: dict[int, int] = field(default_factory=dict)


def _period_start_clock(period: int) -> str:
    return "PT12M00.00S" if period <= 4 else "PT05M00.00S"


def cross_feeds(livedata: Path | None, datanba: Path | None) -> dict[str, CrossFeed]:
    """Read both cross-feeds. An absent archive leaves its evidence empty for every game.

    The first two data.nba seasons lack the ``ord`` field, so they carry offense keys but no
    period scores or event order.
    """
    games: dict[str, CrossFeed] = defaultdict(CrossFeed)
    live_ends: dict[tuple[str, int], tuple[int, tuple[int, int]]] = {}
    moves: dict[tuple[str, int, int], tuple[set[int], set[int]]] = defaultdict(
        lambda: (set(), set())
    )
    for row in archive_rows(livedata) if livedata is not None else ():
        game_id = nba_game_id(row["gameId"])
        games[game_id].has_livedata = True
        if not row["period"].isdigit() or not row["orderNumber"].isdigit():
            continue
        period = int(row["period"])
        order = int(row["orderNumber"])
        if row["actionType"] == "period" and row["subType"] == "end":
            if row["scoreHome"].isdigit() and row["scoreAway"].isdigit():
                score = int(row["scoreHome"]), int(row["scoreAway"])
                key = game_id, period
                if key not in live_ends or order > live_ends[key][0]:
                    live_ends[key] = order, score
        elif (
            row["actionType"] == "substitution"
            and row["clock"] == _period_start_clock(period)
            and row["teamId"].isdigit()
            and row["personId"].isdigit()
        ):
            side = 0 if row["subType"] == "out" else 1 if row["subType"] == "in" else None
            if side is None:
                raise ValueError(f"Unknown liveData substitution type in {game_id}")
            moves[(game_id, period, int(row["teamId"]))][side].add(int(row["personId"]))
    for (game_id, period), (_, score) in live_ends.items():
        games[game_id].live_periods[period] = score
    for (game_id, period, team), (outgoing, incoming) in moves.items():
        games[game_id].between_periods[(period, team)] = (frozenset(outgoing), frozenset(incoming))

    nba_ends: dict[tuple[str, int], tuple[int, tuple[int, int]]] = {}
    for row in archive_rows(datanba) if datanba is not None else ():
        game_id = nba_game_id(row["GAME_ID"])
        feed = games[game_id]
        if row["oftid"].isdigit() and int(row["oftid"]) and row["evt"].isdigit():
            feed.offense[int(row["evt"])] = int(row["oftid"])
        if row.get("ord", "").isdigit() and row["evt"].isdigit():
            feed.order[int(row["evt"])] = int(row["ord"])
        if (
            row["hs"].isdigit()
            and row["vs"].isdigit()
            and row.get("ord", "").isdigit()
            and row["PERIOD"].isdigit()
        ):
            key = game_id, int(row["PERIOD"])
            order = int(row["ord"])
            if key not in nba_ends or order > nba_ends[key][0]:
                nba_ends[key] = order, (int(row["hs"]), int(row["vs"]))
    for (game_id, period), (_, score) in nba_ends.items():
        games[game_id].datanba_periods[period] = score
    return dict(games)
