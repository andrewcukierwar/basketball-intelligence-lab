"""Count local historical NBA source rows and report availability of pilot evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import duckdb

from bil.data.pilot_inputs import archive_rows, nba_game_id

SEASON_PREFIX = {"regular": "002", "playoffs": "004"}
ID_COLUMNS = {
    "nbastats": "GAME_ID",
    "nbastatsv3": "gameId",
    "cdnnba": "gameId",
    "datanba": "GAME_ID",
    "shotdetail": "GAME_ID",
    "pbpstats": "GAMEID",
}
LIVE_BALL_TYPES = {"1", "2", "3", "5"}
PERIOD_END_COLUMNS = {"actionType", "subType", "scoreHome", "scoreAway", "period"}
RULE_COLUMNS = {
    "nbastats": {"PERIOD", "EVENTNUM", "EVENTMSGTYPE"},
    "nbastatsv3": PERIOD_END_COLUMNS | {"actionId", "actionNumber"},
    "cdnnba": PERIOD_END_COLUMNS | {"orderNumber", "clock", "teamId", "personId"},
    "datanba": {"ord", "hs", "vs", "PERIOD", "oftid", "evt"},
}


Entry = dict[str, Any]


def digest(path: Path, algorithm: str, *, git_blob: bool = False) -> str:
    hashed = hashlib.new(algorithm)
    if git_blob:
        hashed.update(f"blob {path.stat().st_size}\0".encode())
    with path.open("rb") as source:
        while chunk := source.read(2**20):
            hashed.update(chunk)
    return hashed.hexdigest()


def verify_pin(path: Path, entry: Entry) -> str:
    """Match publisher pins when supplied and return the hash of the counted bytes."""
    if entry.get("size") is not None and path.stat().st_size != entry["size"]:
        raise ValueError(f"Source byte count differs for {path.name}")
    sha256 = digest(path, "sha256")
    if entry["provider"] == "Shufinskiy":
        if digest(path, "sha1", git_blob=True) != entry["revision"].split(":")[-1]:
            raise ValueError(f"Git blob differs for {path.name}")
    elif entry["provider"] == "Bentes" and sha256 != entry["revision"].split(":")[-1]:
        raise ValueError(f"Release digest differs for {path.name}")
    if entry.get("sha256") and entry["sha256"] != sha256:
        raise ValueError(f"Audit digest differs for {path.name}")
    return sha256


def parquet_counts(path: Path, prefix: str) -> tuple[int, int, set[str]]:
    with duckdb.connect(config={"threads": 1}) as connection:
        counts = connection.execute(
            """
            select lpad(cast(game_id as varchar), 10, '0'), count(*)
            from read_parquet(?) group by 1
            """,
            [str(path)],
        ).fetchall()
    games = {game for game, _ in counts if game and game.startswith(prefix)}
    scoped_rows = sum(count for game, count in counts if game in games)
    return sum(count for _, count in counts), scoped_rows, games


class Shape:
    """Summarize source fields used by pilot adjudication, by source game."""

    def __init__(self) -> None:
        self.game_ids: set[str] = set()
        self.periods: dict[str, set[str]] = defaultdict(set)
        self.event_ids: dict[str, set[str]] = defaultdict(set)
        self.action_ids: dict[str, set[str]] = defaultdict(set)
        self.invalid_v3: set[str] = set()
        self.ball_events: dict[str, set[str]] = defaultdict(set)
        self.start_clock_sub_games: set[str] = set()
        self.missing_columns: set[str] = set()

    def add(self, feed: str, game_id: str, row: dict[str, str]) -> None:
        self.game_ids.add(game_id)
        if feed == "nbastats":
            if period := row.get("PERIOD"):
                self.periods[game_id].add(period)
            if event_num := row.get("EVENTNUM"):
                self.event_ids[game_id].add(event_num)
                if row.get("EVENTMSGTYPE") in LIVE_BALL_TYPES:
                    self.ball_events[game_id].add(event_num)
        elif feed == "nbastatsv3":
            action_id = row.get("actionId", "")
            action_num = row.get("actionNumber", "")
            if not action_id.isdigit() or not action_num.isdigit():
                self.invalid_v3.add(game_id)
            if action_id in self.action_ids[game_id]:
                self.invalid_v3.add(game_id)
            self.action_ids[game_id].add(action_id)
            self.event_ids[game_id].add(action_num)
            if is_period_end(row):
                self.periods[game_id].add(row["period"])
        elif feed == "cdnnba":
            period = row.get("period", "")
            if is_period_end(row) and row.get("orderNumber", "").isdigit():
                self.periods[game_id].add(period)
            if (
                row.get("actionType", "") == "substitution"
                and period.isdigit()
                and int(period) > 1
                and row.get("clock", "") == ("PT12M00.00S" if int(period) <= 4 else "PT05M00.00S")
                and row.get("teamId", "").isdigit()
                and row.get("personId", "").isdigit()
                and row.get("subType", "") in {"in", "out"}
            ):
                self.start_clock_sub_games.add(game_id)
        elif feed == "datanba":
            if (
                row.get("ord", "").isdigit()
                and row.get("hs", "").isdigit()
                and row.get("vs", "").isdigit()
            ):
                self.periods[game_id].add(row.get("PERIOD", ""))
            if (
                row.get("oftid", "").isdigit()
                and int(row.get("oftid", ""))
                and row.get("evt", "").isdigit()
            ):
                self.ball_events[game_id].add(row.get("evt", ""))


def is_period_end(row: dict[str, str]) -> bool:
    return (
        row.get("actionType", "") == "period"
        and row.get("subType", "") == "end"
        and row.get("period", "").isdigit()
        and row.get("scoreHome", "").isdigit()
        and row.get("scoreAway", "").isdigit()
    )


def archive_counts(path: Path, feed: str, prefix: str) -> tuple[int, int, Shape]:
    shape = Shape()
    total_rows = scoped_rows = 0
    for row in archive_rows(path):
        if not total_rows:
            shape.missing_columns = RULE_COLUMNS.get(feed, set()) - row.keys()
        total_rows += 1
        game_id = nba_game_id(row[ID_COLUMNS[feed]])
        if game_id.startswith(prefix):
            scoped_rows += 1
            shape.add(feed, game_id, row)
    return total_rows, scoped_rows, shape


def csv_row(entry: Entry, kind: str, **values: object) -> Entry:
    return {
        "start_year": entry["year"],
        "season_type": kind,
        "feed": entry["feed"],
        "provider": entry["provider"],
        "availability": entry["state"],
        "file": entry["name"],
        "source_url": entry.get("uri"),
        "publisher_revision": entry.get("revision"),
        "artifact_bytes": entry.get("size"),
        **values,
    }


def audit_partition(
    inputs: Path, year: int, kind: str, entries: list[Entry]
) -> tuple[list[Entry], Entry | None]:
    prefix = SEASON_PREFIX[kind]
    rows: list[Entry] = []
    shapes: dict[str, Shape] = {}
    game_sets: dict[str, set[str]] = {}
    for entry in entries:
        if entry["state"] == "absent":
            rows.append(csv_row(entry, kind))
            continue
        if year >= 2025:
            rows.append(csv_row(entry, kind, availability="inventory_only"))
            continue

        feed = entry["feed"]
        path = inputs / entry["name"]
        if not path.is_file():
            rows.append(csv_row(entry, kind, availability="listed_payload_unavailable"))
            continue
        sha256 = verify_pin(path, entry)
        if feed in ID_COLUMNS:
            total_rows, scoped_rows, shape = archive_counts(path, feed, prefix)
            games = shape.game_ids
            shapes[feed] = shape
            missing_columns = ",".join(sorted(shape.missing_columns))
        else:
            total_rows, scoped_rows, games = parquet_counts(path, prefix)
            missing_columns = ""
        game_sets[feed] = games
        rows.append(
            csv_row(
                entry,
                kind,
                availability="measured",
                artifact_bytes=path.stat().st_size,
                sha256=sha256,
                artifact_rows=total_rows,
                season_type_rows=scoped_rows,
                season_type_games=len(games),
                missing_adjudication_columns=missing_columns,
            )
        )

    if year >= 2025:
        return rows, None
    base = game_sets.get("team_game_logs")
    for row in rows:
        feed_games = game_sets.get(row["feed"])
        if base is not None and feed_games is not None:
            row["missing_vs_team_box"] = len(base - feed_games)
            row["extra_vs_team_box"] = len(feed_games - base)
    return rows, rule_coverage(year, kind, shapes, game_sets)


def rule_coverage(
    year: int, kind: str, shapes: dict[str, Shape], game_sets: dict[str, set[str]]
) -> Entry:
    v2, v3, live, data = (
        shapes.get(name, Shape()) for name in ("nbastats", "nbastatsv3", "cdnnba", "datanba")
    )
    v2_games = v2.game_ids
    both = v2_games & v3.game_ids
    return {
        "start_year": year,
        "season_type": kind,
        "v2_games": len(v2_games),
        "v3_v2_overlap": len(both),
        "v3_exact_v2_event_set_with_valid_order_ids": sum(
            bool(v2.event_ids[game])
            and game not in v3.invalid_v3
            and v2.event_ids[game] == v3.event_ids[game]
            for game in both
        ),
        "v3_covers_v2_periods": sum(
            bool(v2.periods[g]) and v2.periods[g] <= v3.periods[g] for g in both
        ),
        "live_v2_overlap": len(v2_games & live.game_ids),
        "live_start_clock_sub_games_after_period_1": len(v2_games & live.start_clock_sub_games),
        "datanba_v2_overlap": len(v2_games & data.game_ids),
        "both_live_and_datanba_cover_v2_periods": sum(
            bool(v2.periods[g])
            and v2.periods[g] <= live.periods[g]
            and v2.periods[g] <= data.periods[g]
            for g in v2_games
        ),
        "datanba_covers_all_v2_live_ball_event_keys": sum(
            bool(v2.ball_events[g]) and v2.ball_events[g] <= data.ball_events[g] for g in v2_games
        ),
        "pbpstats_v2_overlap": len(v2_games & game_sets.get("pbpstats", set())),
        "bentes_stints_v2_overlap": len(v2_games & game_sets.get("lineup_stats", set())),
    }


ASSET_COLUMNS = (
    "start_year",
    "season_type",
    "feed",
    "provider",
    "availability",
    "file",
    "source_url",
    "publisher_revision",
    "artifact_bytes",
    "sha256",
    "artifact_rows",
    "season_type_rows",
    "season_type_games",
    "missing_vs_team_box",
    "extra_vs_team_box",
    "missing_adjudication_columns",
)


def write_rows(path: Path, columns: tuple[str, ...], rows: list[Entry]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_pins(directory: Path) -> list[Entry]:
    entries = []
    for provider in ("shufinskiy", "bentes", "box"):
        path = directory / f"nba-feed-coverage-{provider}.csv"
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                entries.append(
                    {
                        "year": int(row["start_year"]),
                        "kind": row["season_type"],
                        "feed": row["feed"],
                        "provider": row["provider"],
                        "name": row["file"],
                        "state": "absent" if row["availability"] == "absent" else "listed",
                        "uri": row["source_url"],
                        "revision": row["publisher_revision"],
                        "size": int(row["artifact_bytes"]) if row["artifact_bytes"] else None,
                        "sha256": row["sha256"],
                    }
                )
    return entries


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("input_dir", type=Path)
    cli.add_argument("output_dir", type=Path)
    cli.add_argument("--jobs", type=int, default=2)
    cli.add_argument("--pins", type=Path, help="directory with recorded audit asset CSVs")
    cli.add_argument("--first-year", type=int, default=2001)
    cli.add_argument("--last-year", type=int, default=2026)
    args = cli.parse_args()
    if not 2001 <= args.first_year <= args.last_year <= 2026:
        cli.error("Select starting years from 2001 through 2026")
    entries = (
        read_pins(args.pins)
        if args.pins
        else json.loads((args.input_dir / "inventory.json").read_bytes())
    )
    for row in entries:
        if row["year"] not in range(2001, 2027):
            raise ValueError("Coverage audit inventory must cover 2001–02 through 2026–27 only")
        if Path(row["name"]).name != row["name"]:
            raise ValueError("Coverage audit filenames must be local basenames")
    partitions = [
        (year, kind, [e for e in entries if e["year"] == year and e["kind"] in (kind, "combined")])
        for year in range(args.first_year, args.last_year + 1)
        for kind in SEASON_PREFIX
    ]
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        jobs = [
            pool.submit(audit_partition, args.input_dir, year, kind, entries)
            for year, kind, entries in partitions
        ]
        asset_rows, rule_rows = [], []
        for job in jobs:
            assets, rules = job.result()
            asset_rows.extend(assets)
            if rules is not None:
                rule_rows.append(rules)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for provider, basename in (
        ("Shufinskiy", "shufinskiy"),
        ("Bentes", "bentes"),
        ("Bill Mill", "box"),
    ):
        write_rows(
            args.output_dir / f"nba-feed-coverage-{basename}.csv",
            ASSET_COLUMNS,
            [row for row in asset_rows if row["provider"] == provider],
        )
    if rule_rows:
        write_rows(args.output_dir / "nba-feed-coverage-rules.csv", tuple(rule_rows[0]), rule_rows)
    print(dict(Counter(row["availability"] for row in asset_rows)))


if __name__ == "__main__":
    main()
