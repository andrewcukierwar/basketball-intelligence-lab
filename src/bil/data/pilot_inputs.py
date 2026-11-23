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
        if not (
            home[4] is True
            and away[4] is False
            and home[1] == away[1]
            and home[2] == away[3]
            and away[2] == home[3]
            and home[2] != away[2]
        ):
            raise ValueError(f"Conflicting box-score team rows for {game_id}")
        games[game_id] = GameBox(game_id, home[1], int(home[2]), int(away[2]), home[5], away[5])
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
