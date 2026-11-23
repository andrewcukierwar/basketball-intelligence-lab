"""Audit frozen 2017–18 through 2022–23 NBA defensive tracking feeds locally."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import duckdb

Report = dict[str, Any]
START_YEARS = range(2017, 2023)
TYPES = {"regular": "002", "playoffs": "004"}
PAIR_METRICS = (
    "partial_possessions",
    "matchup_field_goals_made",
    "matchup_field_goals_attempted",
    "matchup_turnovers",
)
HUSTLE_METRICS = ("contested_shots", "deflections", "charges_drawn", "def_boxouts")


def verify_pins(path: Path, tracking: Path, boxes: Path) -> None:
    expected = {
        *(("Bill Mill", f"player_game_logs_{year + 1}.parquet") for year in START_YEARS),
        *(
            ("Shufinskiy", f"matchups{suffix}_{year}.tar.xz")
            for year in START_YEARS
            for suffix in ("", "_po")
        ),
        *(
            ("SportsDataverse", f"{feed}_{year + 1}.parquet")
            for year in START_YEARS
            for feed in (
                "game_matchups",
                "player_tracking_defense",
                "leaguehustlestatsplayer_playoffs_totals",
                "leaguehustlestatsplayer_regular-season_totals",
            )
        ),
    }
    with path.open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            key = (row["provider"], row["file"])
            if key not in expected:
                raise ValueError(f"Unexpected or duplicate tracking audit asset {key}")
            expected.remove(key)
            if int(row["start_year"]) not in START_YEARS:
                raise ValueError("Tracking audit is restricted to the six historical seasons")
            filename = row["file"]
            if Path(filename).name != filename:
                raise ValueError("Expected a source basename")
            directory = boxes if row["provider"] == "Bill Mill" else tracking
            payload = directory / filename
            with payload.open("rb") as handle:
                sha256 = hashlib.file_digest(handle, "sha256").hexdigest()
            if payload.stat().st_size != int(row["bytes"]) or sha256 != row["sha256"]:
                raise ValueError(f"Source bytes differ for {filename}")
            if row["provider"] == "Shufinskiy":
                sha1 = hashlib.sha1(f"blob {row['bytes']}\0".encode())
                with payload.open("rb") as handle:
                    while chunk := handle.read(2**20):
                        sha1.update(chunk)
                if sha1.hexdigest() != row["revision"].rsplit(":", 1)[-1]:
                    raise ValueError(f"Source Git blob differs for {filename}")
    if expected:
        raise ValueError(f"Missing tracking audit pins: {sorted(expected)}")


def query(db: duckdb.DuckDBPyConnection, sql: str, params: list[Any] | None = None) -> Report:
    result = db.execute(sql, params or [])
    values = result.fetchone()
    if values is None:
        raise ValueError("Expected one aggregate row")
    return {column[0]: value for column, value in zip(result.description, values, strict=True)}


def load_shufinskiy(db: duckdb.DuckDBPyConnection, archive: Path) -> None:
    with TemporaryDirectory() as directory, tarfile.open(archive, "r:xz") as source:
        files = [m for m in source.getmembers() if m.isfile() and m.name.endswith(".csv")]
        if len(files) != 1:
            raise ValueError(f"Expected one CSV in {archive.name}")
        content = source.extractfile(files[0])
        if content is None:
            raise ValueError(f"Missing CSV in {archive.name}")
        target = Path(directory) / "matchups.csv"
        with content, target.open("wb") as output:
            shutil.copyfileobj(content, output)
        db.execute(
            f"""
            create temp table shuf as
            select lpad(game_id, 10, '0') as game_id,
                   cast(person_id as bigint) as off_id,
                   cast(matchups_person_id as bigint) as def_id,
                   cast(team_id as bigint) as off_team,
                   case when team_id = home_team_id then
                       cast(away_team_id as bigint) else cast(home_team_id as bigint)
                   end as def_team,
                   {", ".join("cast(" + col + " as double) as " + col for col in PAIR_METRICS)}
            from read_csv(?, all_varchar=true)
            """,
            [str(target)],
        )


def profile_pairs(db: duckdb.DuckDBPyConnection, label: str) -> Report:
    return query(
        db,
        f"""
        with pairs as (
          select m.*, coalesce(o.team_id = m.off_team and d.team_id = m.def_team
                 and o.team_id <> d.team_id, false) as linked,
                 isfinite(partial_possessions)
                 and partial_possessions >= 0
                 and isfinite(matchup_field_goals_made) and matchup_field_goals_made >= 0
                 and isfinite(matchup_field_goals_attempted)
                 and matchup_field_goals_attempted >= matchup_field_goals_made
                 and isfinite(matchup_turnovers) and matchup_turnovers >= 0 as valid
          from {label} m
          left join box o on o.game_id = m.game_id and o.player_id = m.off_id
          left join box d on d.game_id = m.game_id and d.player_id = m.def_id
        ), defenders as (
          select game_id, def_id, bool_and(linked and coalesce(valid, false)) as usable,
                 sum(partial_possessions) as exposure,
                 sum(matchup_field_goals_attempted) as fga
          from pairs group by 1, 2
        ), shooters as (
          select game_id, off_id, sum(matchup_field_goals_attempted) as fga
          from pairs group by 1, 2
        )
        select count(*) as pair_rows, count(distinct game_id) as tracking_games,
               count(*) - count(distinct (game_id, off_id, def_id)) as duplicate_keys,
               count(*) filter (where linked) as linked_opposing_positive_minutes_rows,
               count(*) filter (where valid) as valid_opportunity_rows,
               count(*) filter (where partial_possessions = 0) as zero_partial_possession_rows,
               count(*) filter (where matchup_field_goals_attempted = 0) as zero_matchup_fga_rows,
               (select count(*) from defenders) as defender_appearances,
               (select count(*) from defenders where usable and exposure > 0)
                   as linked_defender_appearances_with_positive_exposure,
               (select count(*) from defenders where usable and exposure > 0 and fga > 0)
                   as linked_defender_appearances_with_positive_exposure_and_fga,
               (select count(*) from box b join shooters s
                    on b.game_id = s.game_id and b.player_id = s.off_id
                    where b.fga > 0 and s.fga = b.fga) as shooter_games_with_exact_box_fga,
               (select count(*) from box b join shooters s
                    on b.game_id = s.game_id and b.player_id = s.off_id
                    where b.fga > 0) as matched_shooter_games_with_positive_box_fga,
               (select count(*) from (select distinct game_id from {label}) t
                    where not exists (select 1 from box b where b.game_id = t.game_id))
                   as games_outside_box_universe
        from pairs
        """,
    )


def profile_partition(tracking: Path, boxes: Path, year: int, kind: str, prefix: str) -> Report:
    with duckdb.connect(config={"threads": 2}) as db:
        db.execute(
            """
            create temp table box as
            select lpad(cast(game_id as varchar), 10, '0') as game_id,
                   cast(player_id as bigint) as player_id, cast(team_id as bigint) as team_id,
                   fga
            from read_parquet(?)
            where starts_with(lpad(cast(game_id as varchar), 10, '0'), ?) and min > 0
            """,
            [str(boxes / f"player_game_logs_{year + 1}.parquet"), prefix],
        )
        counts = query(
            db,
            """select count(distinct game_id) as games, count(*) as player_games,
                      count(distinct player_id) as players,
                      count(*) - count(distinct (game_id, player_id)) as duplicate_keys
               from box""",
        )
        if counts["duplicate_keys"]:
            raise ValueError("Ambiguous player-game appearances in box comparison")

        suffix = "_po" if kind == "playoffs" else ""
        load_shufinskiy(db, tracking / f"matchups{suffix}_{year}.tar.xz")
        db.execute(
            f"""
            create temp table sdv as
            select lpad(game_id, 10, '0') as game_id, off_person_id as off_id,
                   def_person_id as def_id, off_team_id as off_team, def_team_id as def_team,
                   {", ".join(PAIR_METRICS)}
            from read_parquet(?)
            where starts_with(lpad(game_id, 10, '0'), ?)
            """,
            [str(tracking / f"game_matchups_{year + 1}.parquet"), prefix],
        )
        shuf, sdv = profile_pairs(db, "shuf"), profile_pairs(db, "sdv")
        if shuf["duplicate_keys"] or sdv["duplicate_keys"]:
            raise ValueError("Ambiguous directed matchup keys in archive comparison")
        mirror = query(
            db,
            f"""
            with g as (select distinct game_id from shuf),
                 s as (select distinct game_id from sdv)
            select count(*) as same_directed_pair_rows,
                   count(*) filter (where
                   {" and ".join(f"a.{col} = b.{col}" for col in (*PAIR_METRICS, "off_team", "def_team"))}
                   ) as same_values_on_compared_fields,
                   (select count(*) from g join s using (game_id)) as same_games,
                   (select count(*) from s anti join g using (game_id)) as sdv_only_games,
                   (select count(*) from g anti join s using (game_id)) as shuf_only_games
            from shuf a join sdv b using (game_id, off_id, def_id)
            """,
        )

        dashboard_kind = "Playoffs" if kind == "playoffs" else "Regular Season"
        rim = query(
            db,
            """
            with r as (select * from read_parquet(?) where season_type = ?)
            select count(*) as rows, count(distinct player_id) as players,
                   count(distinct player_id) filter (where player_id in (select player_id from box))
                     as linked_box_players,
                   count(*) filter (where def_rim_fga > 0 and def_rim_fgm between 0 and def_rim_fga)
                     as positive_rim_attempt_rows,
                   count(*) filter (where def_rim_fga = 0) as zero_rim_attempt_rows,
                   count(*) filter (where def_rim_fga is null or def_rim_fgm is null)
                     as missing_rim_count_rows,
                   min(per_mode) as min_per_mode, max(per_mode) as max_per_mode
             from r
            """,
            [str(tracking / f"player_tracking_defense_{year + 1}.parquet"), dashboard_kind],
        )
        hustle_kind = "playoffs" if kind == "playoffs" else "regular-season"
        hustle = query(
            db,
            f"""
            select count(*) as rows, count(distinct player_id) as players,
                   count(distinct player_id) filter (where player_id in (select player_id from box))
                     as linked_box_players,
                   count(*) filter (where {" or ".join(f"{col} is null" for col in HUSTLE_METRICS)})
                     as missing_candidate_count_rows,
                   count(*) filter (where contested_shots = 0) as zero_contest_rows,
                   count(*) filter (where deflections = 0) as zero_deflection_rows,
                   count(*) filter (where min > 0) as positive_minutes_rows,
                   min(per_mode) as min_per_mode, max(per_mode) as max_per_mode
            from read_parquet(?)
            """,
            [str(tracking / f"leaguehustlestatsplayer_{hustle_kind}_totals_{year + 1}.parquet")],
        )
        return {
            "start_year": year,
            "season_type": kind,
            "box": counts,
            "shufinskiy": shuf,
            "sportsdataverse": sdv,
            "mirror_overlap": mirror,
            "hustle": hustle,
            "rim_tracking": rim,
        }


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("tracking_inputs", type=Path)
    cli.add_argument("box_inputs", type=Path)
    cli.add_argument("pins", type=Path)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    verify_pins(args.pins, args.tracking_inputs, args.box_inputs)
    rows = [
        profile_partition(args.tracking_inputs, args.box_inputs, year, kind, prefix)
        for year in START_YEARS
        for kind, prefix in TYPES.items()
    ]
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(rows, handle, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
