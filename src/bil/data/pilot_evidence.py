"""Cross-check an exported pilot build against separately archived, pinned evidence feeds.

The evidence snapshot holds archived NBA liveData (cdn.nba.com) and data.nba.com play-by-play,
pbpstats.com possessions, and Bentes lineup stints. None of these are build inputs. All of them
derive from the NBA's own event log, so agreement shows consistent archiving and parsing rather
than external truth: an error in the official log is shared by every feed. Each comparison reads
exported tables only and reports agreement and coverage, so the results can be reproduced.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb

from bil.data.pilot_inputs import archive_rows, v3_games
from bil.data.pilot_sources import (
    DATANBA,
    LIVEDATA,
    has_datanba,
    has_livedata,
    lineup_stat_names,
)

FEEDS = {
    "pbpstats": ("GAMEID", ("GAMEID", "PERIOD", "STARTTIME", "ENDTIME", "OPPONENT")),
    "datanba": (
        "GAME_ID",
        ("evt", "cl", "etype", "oftid", "ord", "hs", "vs", "PERIOD", "GAME_ID"),
    ),
    "cdnnba": (
        "gameId",
        (
            "actionNumber",
            "clock",
            "period",
            "actionType",
            "subType",
            "personId",
            "teamId",
            "possession",
            "scoreHome",
            "scoreAway",
            "orderNumber",
            "gameId",
        ),
    ),
}
LOWER_TRUST = (
    "livedata_starters",
    "v3_period_defect",
    "datanba_possession_labels",
    "inferred_starters",
    "immaterial_starters",
    "same_clock_box_credit",
    "v3_primary_order",
    "v3_event_order",
    "unresolved_possessions",
    "v2_home_designation",
    "no_livedata",
    "no_datanba",
    "datanba_event_order",
)
PERIOD_START = "case when {p} <= 4 then ({p} - 1) * 720000 else 2880000 + ({p} - 5) * 300000 end"


def _literal(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def stage_feeds(
    connection: duckdb.DuckDBPyConnection,
    evidence: Path,
    staging: Path,
    season_start_year: int = 2022,
) -> None:
    """Load the archived evidence CSVs into DuckDB tables keyed by ten-digit game IDs.

    A season without pinned liveData or data.nba gets an empty table for that feed, so every
    comparison with it reports nothing rather than a disagreement. The first data.nba archives
    lack ``ord``, which stays empty, so their period scores and event order are not compared.
    """
    for name, (game_key, columns) in FEEDS.items():
        path = staging / f"{name}.csv"
        absent = (name == LIVEDATA and not has_livedata(season_start_year)) or (
            name == DATANBA and not has_datanba(season_start_year)
        )
        with path.open("w", newline="", encoding="utf-8") as target:
            writer = csv.writer(target)
            writer.writerow(columns)
            for suffix in () if absent else ("", "_po"):
                for row in archive_rows(evidence / f"{name}{suffix}_{season_start_year}.tar.xz"):
                    writer.writerow([row.get(column, "") for column in columns])
        connection.execute(
            f"create or replace table {name} as select * replace (lpad({game_key}, 10, '0') as {game_key}) "
            f"from read_csv({_literal(path)}, all_varchar = true)"
        )
    files = ", ".join(_literal(evidence / name) for name in lineup_stat_names(season_start_year))
    connection.execute(
        f"""
        create or replace table bentes as
        select game_id, secs_game_start as t0, secs_game_end as t1,
               list_sort(list_transform(string_split(lineup_team, ', '),
                                        lambda x: split_part(x, ' ', 1))) as ids
        from read_parquet([{files}])
        """
    )


def stage_build(connection: duckdb.DuckDBPyConnection, build: Path) -> None:
    for name in ("event", "stint", "lineup", "possession", "game_review", "quality_issue"):
        connection.execute(
            f"create or replace view {name} as select * from read_parquet({_literal(build / name)}"
            " || '.parquet')"
        )
    connection.execute(
        """
        create or replace table ours as
        select s.game_id, s.stint_seq, s.period, l.team_id as team,
               s.start_elapsed_ms / 1000.0 as t0,
               s.end_elapsed_ms / 1000.0 as t1, s.start_elapsed_ms, s.end_elapsed_ms,
               list_sort(l.player_ids) as ids
        from stint s join lineup l
          on l.game_id = s.game_id and l.lineup_id in (s.home_lineup_id, s.away_lineup_id)
        """
    )


def lineup_agreement(connection: duckdb.DuckDBPyConnection) -> dict[str, object]:
    """Time-weighted agreement of each team's five players with Bentes stints."""
    connection.execute(
        """
        create or replace table bentes_team as
        select b.*, r.team from bentes b
        join (select distinct game_id, team, unnest(ids) as pid from ours) r
          on r.game_id = b.game_id and r.pid = b.ids[1]
        """
    )
    connection.execute(
        """
        create or replace table lineup_overlap as
        select o.game_id, o.team, greatest(o.t0, b.t0) as start_s,
               least(o.t1, b.t1) - greatest(o.t0, b.t0) as seconds, o.ids = b.ids as same,
               list_filter(o.ids, lambda x: not list_contains(b.ids, x)) as ours_only,
               list_filter(b.ids, lambda x: not list_contains(o.ids, x)) as bentes_only
        from ours o join bentes_team b
          on b.game_id = o.game_id and b.team = o.team and b.t0 < o.t1 and b.t1 > o.t0
        """
    )
    total = connection.execute(
        """select count(distinct game_id), sum(seconds) filter (where same) / sum(seconds)
           from lineup_overlap"""
    ).fetchone()
    by_game = """
        select l.game_id, sum(seconds) filter (where same) / sum(seconds) as share,
               any_value(r.strata) as strata
        from lineup_overlap l join game_review r using (game_id) group by l.game_id"""
    strata = {}
    for label in LOWER_TRUST:
        row = connection.execute(
            f"select count(*), min(share) from ({by_game}) where list_contains(strata, ?)",
            [label],
        ).fetchone()
        strata[label] = {"games": row[0] if row else 0, "min_share": row[1] if row else None}
    lowest = connection.execute(f"select min(share) from ({by_game})").fetchone()
    long_pieces = connection.execute(
        """select game_id, team, round(start_s, 1), round(seconds, 1), ours_only, bentes_only
           from lineup_overlap where not same and seconds > 2 order by game_id, start_s"""
    ).fetchall()
    covered = connection.execute(
        """select count(distinct game_id), (select count(distinct game_id) from ours)
           from lineup_overlap"""
    ).fetchone()
    return {
        "games": total[0] if total else 0,
        "build_games_covered": f"{covered[0]} of {covered[1]}" if covered else None,
        "time_share": total[1] if total else None,
        "lowest_game_share": lowest[0] if lowest else None,
        "lower_trust_strata": strata,
        "disagreements_over_2s": [list(map(str, row)) for row in long_pieces],
    }


def possession_agreement(connection: duckdb.DuckDBPyConnection) -> dict[str, object]:
    """Compare possession offense with each feed's offense team on live-ball events."""
    connection.execute(
        """
        create or replace table live_events as
        select e.game_id, cast(e.source_event_id as int) as evt, p.possession_seq,
               p.offense_team_id as offense, p.status
        from event e join possession p
          on p.game_id = e.game_id and e.seq >= p.start_seq and e.seq < p.end_seq
        where e.kind in ('shot', 'free_throw', 'turnover')
          and e.game_id not in (
            select game_id from game_review
            where list_contains(strata, 'datanba_possession_labels'))
        """
    )
    feeds = {
        "datanba": "select distinct GAME_ID as game_id, cast(evt as int) as evt, oftid as team "
        "from datanba where oftid not in ('', '0')",
        "cdnnba": "select distinct gameId as game_id, cast(actionNumber as int) as evt, "
        "possession as team from cdnnba where possession not in ('', '0')",
    }
    result: dict[str, object] = {}
    for name, sql in feeds.items():
        rows = connection.execute(
            f"""select status, count(*), count(*) filter (where f.team = l.offense)
                from live_events l join ({sql}) f using (game_id, evt)
                group by status order by status"""
        ).fetchall()
        result[name] = {status: {"events": n, "agree": agree} for status, n, agree in rows}
    rows = connection.execute(
        """
        with feed as (
          select distinct GAME_ID as game_id, cast(evt as int) as evt, oftid as team
          from datanba where oftid not in ('', '0')),
        per as (
          select l.game_id, l.possession_seq, any_value(l.status) as status,
                 count(*) as n, count(*) filter (where f.team = l.offense) as agree
          from live_events l join feed f using (game_id, evt) group by all)
        select status, count(*), count(*) filter (where agree = n), count(*) filter (where agree = 0)
        from per group by status order by status
        """
    ).fetchall()
    excluded = connection.execute(
        """select count(*) from game_review
           where list_contains(strata, 'datanba_possession_labels')"""
    ).fetchone()
    result["games_excluded_relabeled_from_datanba"] = excluded[0] if excluded else 0
    result["note"] = (
        "Live-ball events mostly name the acting team, so this checks event attribution and "
        "joining more than possession boundaries; see possession_counts_vs_pbpstats. Games "
        "with possessions relabeled from data.nba are excluded because they agree by design."
    )
    counts = connection.execute(
        """
        with theirs as (
          select GAMEID as game_id, count(*) as possessions from (
            select distinct GAMEID, PERIOD, STARTTIME, ENDTIME, OPPONENT from pbpstats)
          group by 1),
        mine as (
          select game_id, count(*) filter (where status = 'accepted') as possessions
          from possession group by 1)
        select count(*), count(t.game_id), count(*) filter (where t.possessions = m.possessions),
               count(*) filter (where abs(t.possessions - m.possessions) <= 2),
               sum(m.possessions), sum(t.possessions)
        from mine m left join theirs t using (game_id)
        """
    ).fetchone()
    if counts:
        result["possession_counts_vs_pbpstats"] = {
            "build_games": counts[0],
            "games_in_pbpstats": counts[1],
            "equal": counts[2],
            "within_2": counts[3],
            "counted_possessions": counts[4],
            "pbpstats_possessions": counts[5],
        }
    result["possessions_vs_datanba"] = {
        status: {"possessions": n, "all_agree": full, "all_disagree": none}
        for status, n, full, none in rows
    }
    return result


def order_agreement(connection: duckdb.DuckDBPyConnection) -> dict[str, object]:
    """Count adjacent events whose data.nba order is reversed in the build, by stratum."""
    rows = connection.execute(
        """
        with ranked as (
          select e.game_id, e.seq, d.ord_value,
                 lag(d.ord_value) over (partition by e.game_id order by e.seq) as previous
          from event e
          join (select distinct GAME_ID, cast(evt as int) as evt, try_cast(ord as bigint) as ord_value
                from datanba where try_cast(ord as bigint) is not null) d
            on d.GAME_ID = e.game_id and d.evt = cast(e.source_event_id as int)),
        per_game as (
          select game_id, count(*) filter (where previous > ord_value) as descents
          from ranked group by game_id)
        select case when list_contains(r.strata, 'v3_primary_order') then 'v3_primary_order'
                    when list_contains(r.strata, 'v3_event_order') then 'v3_event_order'
                    else 'v2_file_order' end as basis,
               count(*), count(*) filter (where descents > 0), sum(descents)
        from per_game join game_review r using (game_id) group by 1 order by 1
        """
    ).fetchall()
    return {
        basis: {"games": games, "games_with_descents": with_descents, "descents": total}
        for basis, games, with_descents, total in rows
    }


def starter_agreement(
    connection: duckdb.DuckDBPyConnection, season_start_year: int = 2022
) -> dict[str, object]:
    """Check inferred starters against Bentes and liveData between-period substitutions.

    The liveData check starts from BIL's own lineup at the end of the previous period, so it
    confirms the inference given that state. Bentes' first stint is a separate reconstruction.
    Requires ``lineup_agreement`` to have built ``bentes_team``.
    """
    inferred = []
    for game_id, detail in connection.execute(
        "select game_id, detail from quality_issue where code = 'inferred_starters'"
    ).fetchall():
        for period, team, ids in re.findall(r"period (\d+) team (\d+): ([\d,]+)", detail):
            inferred.append((game_id, int(period), team, sorted(ids.split(","))))
    # Starters taken from liveData are checked against Bentes only; a liveData check would
    # repeat the input.
    recorded = []
    for game_id, detail in connection.execute(
        "select game_id, detail from quality_issue where code = 'livedata_starters'"
    ).fetchall():
        for period, team in re.findall(r"period (\d+) team (\d+)", detail):
            first = connection.execute(
                """select ids from ours where game_id = ? and team = ? and period = ?
                   order by stint_seq limit 1""",
                [game_id, team, int(period)],
            ).fetchall()
            if first:
                recorded.append((game_id, int(period), team, list(first[0][0])))
    recorded_agree = 0
    for game_id, period, team, ids in recorded:
        start_ms = (period - 1) * 720_000 if period <= 4 else 2_880_000 + (period - 5) * 300_000
        match = connection.execute(
            "select ids from bentes_team where game_id = ? and t0 = ? and team = ?",
            [game_id, start_ms // 1000, team],
        ).fetchall()
        recorded_agree += int(len(match) == 1 and match[0][0] == ids)
    bentes_agree = live_agree = live_checked = live_unavailable = 0
    disagreements: list[list[str]] = []
    for game_id, period, team, ids in inferred:
        start_ms = (period - 1) * 720_000 if period <= 4 else 2_880_000 + (period - 5) * 300_000
        first = connection.execute(
            """select ids from bentes_team where game_id = ? and t0 = ? and team = ?""",
            [game_id, start_ms // 1000, team],
        ).fetchall()
        if len(first) == 1 and first[0][0] == ids:
            bentes_agree += 1
        else:
            disagreements.append(["bentes", game_id, str(period), team, f"{len(first)} rows"])
        if period == 1:
            continue
        covered = connection.execute(
            "select count(*) from cdnnba where gameId = ?", [game_id]
        ).fetchone()
        if not covered or not covered[0]:
            if has_livedata(season_start_year):
                raise ValueError(f"liveData is pinned for {season_start_year} but lacks {game_id}")
            live_unavailable += 1
            continue
        previous = connection.execute(
            """select ids from ours where game_id = ? and team = ? and period = ?
               order by stint_seq desc limit 1""",
            [game_id, team, period - 1],
        ).fetchall()
        clock = "PT12M00.00S" if period <= 4 else "PT05M00.00S"
        subs = connection.execute(
            """select subType, personId from cdnnba where gameId = ? and actionType = 'substitution'
               and period = ? and clock = ? and teamId = ?""",
            [game_id, str(period), clock, team],
        ).fetchall()
        if not previous:
            disagreements.append(["previous lineup", game_id, str(period), team, "missing"])
            continue
        live_checked += 1
        state = set(previous[0][0]) - {pid for kind, pid in subs if kind == "out"}
        state |= {pid for kind, pid in subs if kind == "in"}
        if sorted(state) == ids:
            live_agree += 1
        else:
            disagreements.append(["liveData", game_id, str(period), team])
    return {
        "livedata_team_periods": len(recorded),
        "livedata_bentes_agree": recorded_agree,
        "inferred_team_periods": len(inferred),
        "livedata_not_applicable_period_1": sum(period == 1 for _, period, _, _ in inferred),
        "bentes_agree": bentes_agree,
        "livedata_checked": live_checked,
        "livedata_agree": live_agree,
        "livedata_unavailable": live_unavailable,
        "disagreements": disagreements,
    }


def period_score_agreement(
    connection: duckdb.DuckDBPyConnection, snapshot: Path, season_start_year: int = 2022
) -> dict[str, object]:
    """Compare archived V3 period-end scores with liveData and data.nba period-end scores."""
    v3 = {}
    for suffix in ("", "_po"):
        for game_id, game in v3_games(
            snapshot / f"nbastatsv3{suffix}_{season_start_year}.tar.xz"
        ).items():
            for period, score in game.periods.items():
                v3[(game_id, period)] = score

    def scores(sql: str) -> dict[tuple[str, int], tuple[int, int]]:
        return {
            (game_id, int(period)): (int(home), int(away))
            for game_id, period, home, away in connection.execute(sql).fetchall()
            if str(home).isdigit() and str(away).isdigit()
        }

    live = scores(
        """select gameId, period, last(scoreHome order by cast(orderNumber as bigint)),
                  last(scoreAway order by cast(orderNumber as bigint))
           from cdnnba where actionType = 'period' and subType = 'end' group by all"""
    )
    data_nba = scores(
        """select GAME_ID, PERIOD, last(hs order by try_cast(ord as bigint)),
                  last(vs order by try_cast(ord as bigint)) from datanba
           where try_cast(ord as bigint) is not null group by all"""
    )
    shared = sorted(v3.keys() & live.keys() & data_nba.keys())
    # Without liveData, V3 and data.nba remain the only two-feed period comparison.
    pairs = sorted(v3.keys() & data_nba.keys())
    v3_alone = sorted(
        {
            game
            for game, period in shared
            if v3[(game, period)] != live[(game, period)] == data_nba[(game, period)]
        }
    )
    data_nba_alone = sorted(
        {
            game
            for game, period in shared
            if data_nba[(game, period)] != live[(game, period)] == v3[(game, period)]
        }
    )
    return {
        "periods_compared": len(shared),
        "livedata_equals_datanba": sum(live[key] == data_nba[key] for key in shared),
        "v3_equals_livedata": sum(v3[key] == live[key] for key in shared),
        "games_where_v3_alone_differs": v3_alone,
        "games_where_datanba_alone_differs": data_nba_alone,
        "v3_datanba_periods_compared": len(pairs),
        "v3_equals_datanba": sum(v3[key] == data_nba[key] for key in pairs),
        "games_where_v3_differs_from_datanba": sorted(
            {game for game, period in pairs if v3[(game, period)] != data_nba[(game, period)]}
        ),
    }


def compare(
    build: Path, snapshot: Path, evidence: Path, season_start_year: int = 2022
) -> dict[str, object]:
    with TemporaryDirectory() as temp, duckdb.connect() as connection:
        stage_feeds(connection, evidence, Path(temp), season_start_year)
        stage_build(connection, build)
        return {
            "lineups_vs_bentes": lineup_agreement(connection),
            "possession_offense": possession_agreement(connection),
            "event_order_vs_datanba": order_agreement(connection),
            "inferred_starters": starter_agreement(connection, season_start_year),
            "period_scores": period_score_agreement(connection, snapshot, season_start_year),
        }
