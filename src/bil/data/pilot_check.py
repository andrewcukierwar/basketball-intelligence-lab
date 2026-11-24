"""Check an exported pilot build against its documented invariants.

The checks read only the exported tables, the manifest and the pinned box and event inputs.
They do not import the reconstruction code, so they are an independent check of the output.
Each check counts violating rows, and zero means the check passed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb

from bil.data.pilot_inputs import archive_rows, nba_game_id
from bil.data.pilot_sources import pinned_season

TABLES = (
    "game",
    "game_stream",
    "game_review",
    "event",
    "event_actor",
    "lineup",
    "stint",
    "possession",
    "score_allocation",
)
QUARANTINE_FREE = ("event", "event_actor", "lineup", "stint", "possession", "score_allocation")
# The same tolerance the pilot documents: 2,000 ms per player, plus 1,000 ms for each of the
# player's substitutions at a truncated clock inside a period's final minute.
MINUTES_BASE_MS = 2_000
TRUNCATED_CLOCK_MS = 60_000
TRUNCATION_MS = 1_000

PERIOD_START = (
    "case when period <= 4 then (period - 1) * 720000 else 2880000 + (period - 5) * 300000 end"
)
PERIOD_END = "case when period <= 4 then period * 720000 else 2880000 + (period - 4) * 300000 end"

SIDES = """
    select s.game_id, s.stint_seq, s.start_seq, s.end_seq,
           s.end_elapsed_ms - s.start_elapsed_ms as duration,
           h.team_id as home_team, h.player_ids as home_ids,
           a.team_id as away_team, a.player_ids as away_ids
    from stint s
    join lineup h on h.game_id = s.game_id and h.lineup_id = s.home_lineup_id
    join lineup a on a.game_id = s.game_id and a.lineup_id = s.away_lineup_id
"""

CHECKS = {
    "review_matches_stream": """
        select count(*) from game_review r join game_stream s using (game_id)
        where r.accepted <> (s.quality = 'accepted')""",
    "lineup_five_distinct_players": """
        select count(*) from lineup
        where len(player_ids) <> 5 or len(list_distinct(player_ids)) <> 5""",
    "lineup_sides_match_game": """
        select count(*) from sides x join game g using (game_id)
        where x.home_team <> g.home_team_id or x.away_team <> g.away_team_id""",
    "stints_tile_each_period": f"""
        with s as (
          select *, lag(end_elapsed_ms) over w as previous_end,
                 row_number() over w as position,
                 count(*) over (partition by game_id, period) as total,
                 {PERIOD_START} as period_start, {PERIOD_END} as period_end
          from stint window w as (partition by game_id, period order by stint_seq))
        select count(*) from s
        where start_elapsed_ms > end_elapsed_ms
           or (position = 1 and start_elapsed_ms <> period_start)
           or (position > 1 and start_elapsed_ms <> previous_end)
           or (position = total and end_elapsed_ms <> period_end)""",
    "stint_sequences_chain": """
        with s as (select *, lag(end_seq) over (partition by game_id order by stint_seq) as prev
                   from stint)
        select count(*) from s where start_seq >= end_seq or (prev is not null and start_seq <> prev)""",
    "possessions_ordered_and_disjoint": """
        with p as (select *, lag(end_seq) over (partition by game_id order by possession_seq) as prev
                   from possession)
        select count(*) from p where start_seq >= end_seq or (prev is not null and start_seq < prev)""",
    "possession_within_one_period": """
        select count(*) from possession p
        join event s on s.game_id = p.game_id and s.seq = p.start_seq
        join event e on e.game_id = p.game_id and e.seq = p.end_seq - 1
        where s.period <> p.period or e.period <> p.period""",
    "possession_teams_known": """
        select count(*) from possession p join game g using (game_id)
        where p.offense_team_id = p.defense_team_id
           or p.offense_team_id not in (g.home_team_id, g.away_team_id)
           or p.defense_team_id not in (g.home_team_id, g.away_team_id)
           or p.status not in ('accepted', 'excluded', 'unresolved')""",
    "event_scores_equal_finals": """
        select count(*) from game g join (
          select game_id, sum(home_delta) as home, sum(away_delta) as away from event group by 1
        ) e using (game_id) where e.home <> g.home_final or e.away <> g.away_final""",
    "allocations_equal_event_deltas": """
        with deltas as (
          select e.game_id, e.seq, g.home_team_id as team, e.home_delta as points
          from event e join game g using (game_id) where e.home_delta <> 0
          union all
          select e.game_id, e.seq, g.away_team_id, e.away_delta
          from event e join game g using (game_id) where e.away_delta <> 0),
        ledger as (
          select game_id, seq, scoring_team_id as team, sum(points_delta) as points,
                 count(*) as rows_per_side
          from score_allocation group by all)
        select count(*) from deltas d full join ledger l using (game_id, seq, team)
        where d.points is distinct from l.points or l.rows_per_side <> 1""",
    "allocation_possession_rules": """
        select count(*) from score_allocation a
        left join possession p on p.game_id = a.game_id and p.possession_seq = a.possession_seq
        where (a.possession_reason = 'control_possession'
               and (p.possession_seq is null or p.offense_team_id <> a.scoring_team_id
                    or a.seq < p.start_seq or a.seq >= p.end_seq))
           or (a.possession_reason in ('unassigned_dead_ball', 'unresolved')
               and a.possession_seq is not null)
           or a.possession_reason not in ('control_possession', 'unassigned_dead_ball', 'unresolved')""",
    "unresolved_points_inside_unresolved_possessions": """
        select count(*) from score_allocation a
        where a.possession_reason = 'unresolved' and not exists (
          select 1 from possession p where p.game_id = a.game_id and p.status = 'unresolved'
            and a.seq >= p.start_seq and a.seq < p.end_seq)""",
    "credited_stint_at_scoring_clock": """
        select count(*) from score_allocation a
        join event e on e.game_id = a.game_id and e.seq = a.seq
        join stint s on s.game_id = a.game_id and s.stint_seq = a.credited_stint_seq
        where e.elapsed_ms < s.start_elapsed_ms or e.elapsed_ms > s.end_elapsed_ms
           or e.period <> s.period""",
    "credited_lineup_contains_shooter": """
        select count(*) from score_allocation a
        join event_actor x on x.game_id = a.game_id and x.seq = a.seq and x.role = 'shooter'
        join sides s on s.game_id = a.game_id and s.stint_seq = a.credited_stint_seq
        where not ((a.scoring_team_id = s.home_team and list_contains(s.home_ids, x.player_id))
                or (a.scoring_team_id = s.away_team and list_contains(s.away_ids, x.player_id)))""",
    "shooters_on_court": """
        select count(*) from event_actor x where x.role = 'shooter' and not exists (
          select 1 from sides s where s.game_id = x.game_id
            and x.seq >= s.start_seq and x.seq < s.end_seq
            and ((x.team_id = s.home_team and list_contains(s.home_ids, x.player_id))
              or (x.team_id = s.away_team and list_contains(s.away_ids, x.player_id))))""",
    "lineup_players_in_box": """
        select count(*) from (select distinct game_id, player_id from on_court) o
        where not exists (select 1 from reconciled r
                          where r.game_id = o.game_id and r.player_id = o.player_id)""",
    "player_minutes_within_tolerance": f"""
        select count(*) from reconciled
        where abs(minutes_ms - box_ms) > {MINUTES_BASE_MS} + {TRUNCATION_MS} * truncated""",
    "player_plus_minus_exact": "select count(*) from reconciled where plus_minus <> box_plus_minus",
}


def _literal(path: Path) -> str:
    """Quote a path as a SQL string literal; view definitions cannot take parameters."""
    return "'" + str(path).replace("'", "''") + "'"


def _prepare(connection: duckdb.DuckDBPyConnection, output: Path, snapshot: Path) -> None:
    for name in TABLES:
        connection.execute(
            f"create view {name} as select * from read_parquet({_literal(output / name)}"
            " || '.parquet')"
        )
    connection.execute(
        "create view player_box as select * from read_parquet("
        f"{_literal(snapshot / 'player_game_logs.parquet')})"
    )
    connection.execute(f"create view sides as {SIDES}")
    connection.execute(
        """
        create temp table on_court as
        select game_id, stint_seq, duration, unnest(home_ids) as player_id, home_team as team_id
        from sides
        union all
        select game_id, stint_seq, duration, unnest(away_ids), away_team from sides
        """
    )
    connection.execute(
        f"""
        create temp table reconciled as
        with minutes as (
          select game_id, player_id, sum(duration) as minutes_ms from on_court group by all),
        plus_minus as (
          select o.game_id, o.player_id,
                 sum(case when a.scoring_team_id = o.team_id then a.points_delta
                          else -a.points_delta end) as plus_minus
          from score_allocation a join on_court o
            on o.game_id = a.game_id and o.stint_seq = a.credited_stint_seq
          group by all),
        truncated as (
          select x.game_id, x.player_id, count(*) as truncated
          from event_actor x join event e on e.game_id = x.game_id and e.seq = x.seq
          where x.role in ('sub_in', 'sub_out')
            and e.remaining_ms > 0 and e.remaining_ms < {TRUNCATED_CLOCK_MS}
          group by all),
        box as (
          select lpad(cast(game_id as varchar), 10, '0') as game_id,
                 cast(player_id as varchar) as player_id,
                 round(min * 60000) as box_ms, plus_minus as box_plus_minus
          from player_box)
        select b.game_id, b.player_id, b.box_ms, b.box_plus_minus,
               coalesce(m.minutes_ms, 0) as minutes_ms, coalesce(p.plus_minus, 0) as plus_minus,
               coalesce(t.truncated, 0) as truncated
        from box b
        left join minutes m using (game_id, player_id)
        left join plus_minus p using (game_id, player_id)
        left join truncated t using (game_id, player_id)
        where b.game_id in (select game_id from game_stream where quality = 'accepted')
        """
    )


def _same_offense_violations(
    connection: duckdb.DuckDBPyConnection, snapshot: Path, season_start_year: int = 2022
) -> int:
    """Check within-period pairs against unresolved status and original V2 foul codes."""
    pairs = connection.execute(
        """
        with neighbors as (
            select *, lag(offense_team_id) over w as earlier_offense,
                   lag(status) over w as earlier_status,
                   lag(start_seq) over w as earlier_start, lag(end_seq) over w as earlier_end,
                   lag(start_seq, 2) over w as preceding_start,
                   lag(end_seq, 2) over w as preceding_end
            from possession
            window w as (partition by game_id, stream_revision, period order by possession_seq)
        )
        select p.game_id, array(
            select e.source_event_id from event e
            where e.game_id = p.game_id and e.stream_revision = p.stream_revision
              and ((e.seq >= p.earlier_start and e.seq < p.earlier_end)
                   or (e.seq >= p.preceding_start and e.seq < p.preceding_end))
              and e.kind = 'foul'
        ) as possible_exemptions
        from neighbors p
        where offense_team_id = earlier_offense
          and (status is distinct from 'unresolved' or earlier_status is distinct from 'unresolved')
        """
    ).fetchall()
    candidate_games = {game_id for game_id, events in pairs if events}
    flagrant_fouls: set[tuple[str, str]] = set()
    year = season_start_year
    for prefix, filename in (("002", f"nbastats_{year}"), ("004", f"nbastats_po_{year}")):
        if not any(game_id.startswith(prefix) for game_id in candidate_games):
            continue
        for row in archive_rows(snapshot / f"{filename}.tar.xz"):
            if row["EVENTMSGTYPE"] != "6" or row["EVENTMSGACTIONTYPE"] not in {"14", "15"}:
                continue
            game_id = nba_game_id(row["GAME_ID"])
            if game_id in candidate_games:
                flagrant_fouls.add((game_id, row["EVENTNUM"]))
    return sum(
        not any((game_id, event_id) in flagrant_fouls for event_id in events)
        for game_id, events in pairs
    )


def check_build(output: Path, snapshot: Path) -> dict[str, int]:
    """Return the number of violations for each check. Every value is zero for a valid build."""
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    year = manifest["season_start_year"]
    if type(year) is not int:
        raise ValueError("Manifest does not record an integer season start year")
    pinned_season(year)  # refuses the confirmatory holdout and unpinned seasons
    results: dict[str, int] = {}
    with duckdb.connect() as connection:
        mismatched = 0
        for artifact in manifest["output_artifacts"]:
            path = output / artifact["filename"]
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            row = connection.execute("select count(*) from read_parquet(?)", [str(path)]).fetchone()
            mismatched += int(
                digest != artifact["sha256"] or row is None or row[0] != artifact["row_count"]
            )
        results["manifest_digests_and_counts"] = mismatched
        _prepare(connection, output, snapshot)
        for table in QUARANTINE_FREE:
            row = connection.execute(
                f"""select count(*) from {table} where game_id not in
                    (select game_id from game_stream where quality = 'accepted')"""
            ).fetchone()
            results[f"no_quarantined_rows_in_{table}"] = row[0] if row else -1
        results["consecutive_offenses_accounted_for"] = _same_offense_violations(
            connection, snapshot, year
        )
        for name, sql in CHECKS.items():
            row = connection.execute(sql).fetchone()
            results[name] = row[0] if row else -1
    return results


CROSS_SEASON_CHECKS = {
    "game_ids_unique_across_seasons": "select count(*) - count(distinct game_id) from games",
    "game_id_encodes_season_and_type": """
        select count(*) from games
        where substr(game_id, 4, 2) <> lpad(cast(season_start_year % 100 as varchar), 2, '0')
           or season_start_year <> manifest_year
           or (left(game_id, 3) = '002') <> (season_type = 'regular')
           or left(game_id, 3) not in ('002', '004')""",
    "seasons_in_date_order": """
        with spans as (
          select season_start_year as year, min(game_date) as first, max(game_date) as last
          from games group by 1)
        select count(*) from spans a join spans b on b.year > a.year and b.first <= a.last""",
    "playoffs_after_each_team_regular_season": """
        with sides as (
          select season_start_year, season_type, game_date, home_team_id as team from games
          where home_team_id is not null
          union all
          select season_start_year, season_type, game_date, away_team_id from games
          where away_team_id is not null)
        select count(*) from (
          select season_start_year, team,
                 max(game_date) filter (where season_type = 'regular') as last_regular,
                 min(game_date) filter (where season_type = 'playoffs') as first_playoff
          from sides group by all)
        where first_playoff <= last_regular""",
    "lineup_team_matches_player_box": """
        select count(*) from (select distinct game_id, team_id, player_id from on_court) o
        left join box b using (game_id, player_id)
        where b.team_id is distinct from o.team_id""",
}


def check_seasons(builds: list[tuple[Path, Path]]) -> tuple[dict[str, int], dict[str, int]]:
    """Check identity and chronology across several season builds and their snapshots.

    Returns violation counts, each zero for a valid set, and aggregate roster counts. Lineup
    players are matched to that game's box team, so traded players are checked per game.
    """
    with duckdb.connect() as connection:
        for index, (output, snapshot) in enumerate(builds):
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            year = manifest["season_start_year"]
            if type(year) is not int:
                raise ValueError("Manifest does not record an integer season start year")
            pinned_season(year)
            recorded = manifest["source_snapshot_sha256"]
            digest = hashlib.sha256((snapshot / "snapshot.json").read_bytes()).hexdigest()
            if recorded != digest:
                raise ValueError(f"The {year} build was not made from the snapshot at {snapshot}")
            game = _literal(output / "game.parquet")
            lineup = _literal(output / "lineup.parquet")
            box = _literal(snapshot / "player_game_logs.parquet")
            verb = "create table {} as" if index == 0 else "insert into {}"
            connection.execute(
                f"""{verb.format("games")}
                select game_id, season_start_year, {year} as manifest_year, season_type,
                       cast(game_date as date) as game_date, home_team_id, away_team_id
                from read_parquet({game})"""
            )
            connection.execute(
                f"""{verb.format("on_court")}
                select game_id, team_id, unnest(player_ids) as player_id, {year} as year
                from read_parquet({lineup})"""
            )
            connection.execute(
                f"""{verb.format("box")}
                select lpad(cast(game_id as varchar), 10, '0') as game_id,
                       cast(player_id as varchar) as player_id,
                       cast(team_id as varchar) as team_id, {year} as year
                from read_parquet({box})
                where left(lpad(cast(game_id as varchar), 10, '0'), 3) in ('002', '004')"""
            )
        results: dict[str, int] = {}
        for name, sql in CROSS_SEASON_CHECKS.items():
            row = connection.execute(sql).fetchone()
            results[name] = row[0] if row else -1
        summary = connection.execute(
            """
            with teams as (
              select year, player_id, count(distinct team_id) as n from box group by all),
            lineup_teams as (
              select year, player_id, count(distinct team_id) as n from on_court group by all)
            select (select count(*) from games),
                   (select count(distinct player_id) from box),
                   (select count(*) from teams where n > 1),
                   (select count(*) from lineup_teams where n > 1),
                   (select count(*) from (select player_id from box group by 1
                                          having count(distinct year) > 1))
            """
        ).fetchone()
    keys = (
        "games",
        "box_players",
        "player_seasons_with_several_box_teams",
        "player_seasons_on_court_for_several_teams",
        "players_in_several_seasons",
    )
    return results, dict(zip(keys, summary or (), strict=True))
