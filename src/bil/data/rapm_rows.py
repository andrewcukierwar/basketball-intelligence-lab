"""Build the historical RAPM row set from a pinned pilot build.

Implements docs/research/rapm-historical-rows.md. The input is an exported pilot build whose
manifest digest the caller pins. The outputs are per-possession model rows, a disposition for every
canonical possession, a classification of every score allocation, one reconciliation row per
expected game and a content-addressed manifest. Nothing here fits a model.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections.abc import Callable
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from typing import cast

import duckdb

from bil.data.pilot_sources import ATTRIBUTION, NBA_TERMS, sha256_file, utc_now, write_json

CONTRACT_REVISION = "rapm-historical-rows-issue-82-v2"
PILOT_TABLES = (
    "game",
    "event",
    "game_stream",
    "game_review",
    "lineup",
    "stint",
    "possession",
    "score_allocation",
)
OUTPUT_TABLES = (
    "model_row",
    "possession_disposition",
    "score_reconciliation",
    "game_reconciliation",
)
REASONS = (
    "eligible",
    "multiple_lineups",
    "period_end_start",
    "no_action",
    "pilot_excluded",
    "unresolved_control",
)
# The canonical variant keeps every accepted stable-lineup possession, so its rows equal the
# pilot-eligible set: the pilot already excludes starts with under 3 s left (ADR-0019). The other
# two are sensitivity alternatives. ``period_end_start`` drops accepted possessions whose first
# event is ``period_end``, which are run-outs after a change of control. ``no_action`` drops
# accepted possessions with no shot, free throw, turnover, foul or violation event.
VARIANTS = ("canonical", "period_end_start", "no_action")
EXCLUSION = {
    "period_end_start": ("period_end_start", "coalesce(a.first_kind, '') = 'period_end'"),
    "no_action": ("no_action", "a.action_events = 0"),
    "canonical": ("none", "false"),
}
# Events that give a possession a player-attributable outcome. A possession with none of them
# inside its own half-open sequence interval is a no-action (run-out) possession.
ACTION_KINDS = "('shot', 'free_throw', 'turnover', 'foul', 'violation')"
DESTINATIONS = ("possession", "unassigned_dead_ball", "unresolved")

# Expected games: every reviewed game with its stream and the game revision the stream names.
GAMES = """
CREATE TEMP TABLE games AS
SELECT r.game_id, r.season_type, r.accepted, r.reason AS quarantine_reason, r.strata,
       s.revision AS stream_revision, s.official_game_revision AS game_revision,
       s.available_at AS stream_available_at, s.availability_basis AS stream_availability_basis,
       s.complete AS stream_complete, s.quality AS stream_quality,
       g.game_date, g.season_start_year, g.season_type AS game_season_type,
       g.home_team_id, g.away_team_id, g.home_final, g.away_final
FROM game_review r
JOIN game_stream s ON s.game_id = r.game_id
JOIN game g ON g.game_id = r.game_id AND g.revision = s.official_game_revision
"""

# One row per canonical possession. A half-open sequence interval [start_seq, end_seq) overlaps a
# same-period stint when the stint starts before the possession ends and ends after it starts.
DISPOSITION = """
CREATE TEMP TABLE possession_disposition AS
WITH overlap AS (
  SELECT p.game_id, p.stream_revision, p.possession_seq,
         count(s.stint_seq) AS stints,
         count(DISTINCT s.home_lineup_id || '|' || s.away_lineup_id) AS lineup_pairs,
         coalesce(sum(least(s.end_seq, p.end_seq) - greatest(s.start_seq, p.start_seq)), 0)
           AS covered_seqs,
         min(s.home_lineup_id) AS home_lineup_id, min(s.away_lineup_id) AS away_lineup_id
  FROM possession p
  LEFT JOIN stint s ON s.game_id = p.game_id AND s.stream_revision = p.stream_revision
    AND s.period = p.period AND s.start_seq < p.end_seq AND s.end_seq > p.start_seq
  GROUP BY ALL),
acts AS (
  SELECT p.game_id, p.stream_revision, p.possession_seq, count(e.seq) AS action_events,
         (SELECT f.kind FROM event f WHERE f.game_id = p.game_id
            AND f.stream_revision = p.stream_revision AND f.seq >= p.start_seq
            AND f.seq < p.end_seq ORDER BY f.seq LIMIT 1) AS first_kind
  FROM possession p
  LEFT JOIN event e ON e.game_id = p.game_id AND e.stream_revision = p.stream_revision
    AND e.seq >= p.start_seq AND e.seq < p.end_seq AND e.kind IN {action_kinds}
  GROUP BY ALL),
control AS (
  SELECT game_id, stream_revision, possession_seq, scoring_team_id,
         sum(points_delta) AS points, count(*) AS allocations
  FROM score_allocation WHERE possession_reason = 'control_possession'
  GROUP BY ALL)
SELECT p.game_id, p.stream_revision, p.possession_seq, g.season_type, p.period,
       p.start_seq, p.end_seq, p.offense_team_id, p.defense_team_id, p.status AS pilot_status,
       CASE p.status
         WHEN 'excluded' THEN 'pilot_excluded'
         WHEN 'unresolved' THEN 'unresolved_control'
         WHEN 'accepted' THEN CASE WHEN {excluded} THEN '{excluded_reason}'
                                   WHEN o.lineup_pairs > 1 THEN 'multiple_lineups'
                                   ELSE 'eligible' END
       END AS reason,
       CASE WHEN p.status = 'accepted' AND NOT ({excluded}) AND o.lineup_pairs = 1
            THEN 1 ELSE 0 END AS exposure,
       a.action_events, a.first_kind AS first_event_kind,
       o.lineup_pairs, o.covered_seqs, p.end_seq - p.start_seq AS possession_seqs,
       CASE WHEN p.status <> 'accepted' OR ({excluded}) OR o.lineup_pairs <> 1 THEN NULL
            WHEN p.offense_team_id = g.home_team_id THEN o.home_lineup_id
            ELSE o.away_lineup_id END AS offense_lineup_id,
       CASE WHEN p.status <> 'accepted' OR ({excluded}) OR o.lineup_pairs <> 1 THEN NULL
            WHEN p.offense_team_id = g.home_team_id THEN o.away_lineup_id
            ELSE o.home_lineup_id END AS defense_lineup_id,
       coalesce(c.points, 0) AS control_points
FROM possession p
JOIN games g ON g.game_id = p.game_id AND g.stream_revision = p.stream_revision
JOIN overlap o ON o.game_id = p.game_id AND o.stream_revision = p.stream_revision
  AND o.possession_seq = p.possession_seq
JOIN acts a ON a.game_id = p.game_id AND a.stream_revision = p.stream_revision
  AND a.possession_seq = p.possession_seq
LEFT JOIN control c ON c.game_id = p.game_id AND c.stream_revision = p.stream_revision
  AND c.possession_seq = p.possession_seq AND c.scoring_team_id = p.offense_team_id
"""

SORTED_IDS = """
CREATE TEMP MACRO sorted_ids(ids) AS
  list_transform(list_sort(list_transform(ids, lambda x: CAST(x AS BIGINT))), lambda x: CAST(x AS VARCHAR))
"""
MODEL_ROW = """
CREATE TEMP TABLE model_row AS
SELECT d.game_id, d.stream_revision, g.game_revision, g.game_date, g.season_start_year,
       d.season_type, d.possession_seq, d.period, d.start_seq, d.end_seq,
       d.offense_team_id, d.defense_team_id, d.offense_lineup_id, d.defense_lineup_id,
       sorted_ids(o.player_ids) AS offense_player_ids,
       sorted_ids(f.player_ids) AS defense_player_ids,
       d.control_points AS model_points, d.exposure, 1.0::DOUBLE AS weight,
       g.stream_available_at, g.stream_availability_basis
FROM possession_disposition d
JOIN games g ON g.game_id = d.game_id
JOIN lineup o ON o.game_id = d.game_id AND o.stream_revision = d.stream_revision
  AND o.lineup_id = d.offense_lineup_id
JOIN lineup f ON f.game_id = d.game_id AND f.stream_revision = d.stream_revision
  AND f.lineup_id = d.defense_lineup_id
WHERE d.exposure = 1
"""

SCORE = """
CREATE TEMP TABLE score_reconciliation AS
SELECT a.game_id, a.stream_revision, a.seq, a.scoring_team_id, a.points_delta,
       a.possession_reason AS destination_reason,
       CASE a.possession_reason WHEN 'control_possession' THEN 'possession'
            ELSE a.possession_reason END AS destination,
       a.possession_seq, d.reason AS disposition, coalesce(d.reason = 'eligible', false) AS modeled,
       a.credited_stint_seq
FROM score_allocation a
LEFT JOIN possession_disposition d ON d.game_id = a.game_id
  AND d.stream_revision = a.stream_revision AND d.possession_seq = a.possession_seq
"""

GAME_RECONCILIATION = """
CREATE TEMP TABLE game_reconciliation AS
WITH d AS (
  SELECT game_id,
         count(*) AS possessions,
         count(*) FILTER (reason = 'eligible') AS eligible,
         count(*) FILTER (reason = 'multiple_lineups') AS multiple_lineups,
         count(*) FILTER (reason = 'no_action') AS no_action,
         count(*) FILTER (reason = 'period_end_start') AS period_end_start,
         count(*) FILTER (reason = 'pilot_excluded') AS pilot_excluded,
         count(*) FILTER (reason = 'unresolved_control') AS unresolved_control,
         count(*) FILTER (reason = 'eligible' AND offense_team_id = home_team_id)
           AS home_model_offense_exposure,
         count(*) FILTER (reason = 'eligible' AND offense_team_id = away_team_id)
           AS away_model_offense_exposure
  FROM possession_disposition JOIN games USING (game_id) GROUP BY game_id),
s AS (
  SELECT x.game_id,
    {score_fields}
    count(*) AS allocations
  FROM score_reconciliation x JOIN games g USING (game_id) GROUP BY x.game_id)
SELECT g.game_id, g.season_type, g.strata, g.accepted, g.quarantine_reason, g.stream_revision,
       g.game_revision, g.game_date, g.home_team_id, g.away_team_id,
       coalesce(d.possessions, 0) AS possessions, coalesce(d.eligible, 0) AS eligible,
       coalesce(d.multiple_lineups, 0) AS multiple_lineups,
       coalesce(d.no_action, 0) AS no_action,
       coalesce(d.period_end_start, 0) AS period_end_start,
       coalesce(d.pilot_excluded, 0) AS pilot_excluded,
       coalesce(d.unresolved_control, 0) AS unresolved_control,
       coalesce(d.home_model_offense_exposure, 0) AS home_model_offense_exposure,
       coalesce(d.away_model_offense_exposure, 0) AS away_model_offense_exposure,
       coalesce(s.allocations, 0) AS allocations,
       {final_fields}
       g.home_final, g.away_final
FROM games g LEFT JOIN d USING (game_id) LEFT JOIN s USING (game_id)
"""
POINT_FIELDS = (
    "home_modeled_points",
    "away_modeled_points",
    "home_other_control_points",
    "away_other_control_points",
    "home_unassigned_dead_ball_points",
    "away_unassigned_dead_ball_points",
    "home_unresolved_points",
    "away_unresolved_points",
)

METRICS = (
    "games_expected",
    "games_accepted",
    "games_quarantined",
    "final_points",
    *(
        f"{reason}_{name}"
        for reason in REASONS
        for name in ("possessions", "control_points", "exposure")
    ),
    *(f"score_{name}_points" for name in (*DESTINATIONS, "modeled", "not_modeled")),
)

# Each check counts violations against the pilot ledgers and the written outputs.
CHECKS = {
    "one_game_per_review": """
        select (select count(*) from game_review) - (select count(*) from games)
             + (select count(*) - count(distinct game_id) from games)""",
    "stream_status_matches_review": """
        select count(*) from games
        where accepted <> (stream_complete and stream_quality = 'accepted')
           or season_type <> game_season_type or season_start_year <> 2022""",
    "pilot_rows_only_in_accepted_game_streams": """
        select
          (select count(*) from possession p left join games g
             on g.game_id = p.game_id and g.stream_revision = p.stream_revision and g.accepted
           where g.game_id is null)
        + (select count(*) from score_allocation p left join games g
             on g.game_id = p.game_id and g.stream_revision = p.stream_revision and g.accepted
           where g.game_id is null)
        + (select count(*) from stint p left join games g
             on g.game_id = p.game_id and g.stream_revision = p.stream_revision and g.accepted
           where g.game_id is null)
        + (select count(*) from lineup p left join games g
             on g.game_id = p.game_id and g.stream_revision = p.stream_revision and g.accepted
           where g.game_id is null)""",
    "lineups_have_five_distinct_positive_ids": """
        select count(*) from lineup
        where len(player_ids) <> 5 or len(list_distinct(player_ids)) <> 5
           or len(list_filter(player_ids, lambda x: regexp_matches(x, '^[1-9][0-9]*$'))) <> 5""",
    "disposition_keys_match_possession_ledger": """
        select (select count(*) from possession) - (select count(*) from possession_disposition)
             + (select count(*) - count(distinct (game_id, stream_revision, possession_seq))
                from possession_disposition)
             + (select count(*) from possession_disposition where reason is null)
             + (select count(*) from possession p join possession_disposition d
                  using (game_id, stream_revision, possession_seq)
                where p.status <> d.pilot_status or p.offense_team_id <> d.offense_team_id)""",
    "accepted_possessions_covered_once_by_actual_stints": """
        select count(*) from possession_disposition
        where pilot_status = 'accepted'
          and (covered_seqs <> possession_seqs or lineup_pairs < 1)""",
    "accepted_possession_sides_match_game": """
        select count(*) from possession_disposition d join games g using (game_id)
        where d.pilot_status = 'accepted'
          and not ((d.offense_team_id = g.home_team_id and d.defense_team_id = g.away_team_id)
                or (d.offense_team_id = g.away_team_id and d.defense_team_id = g.home_team_id))""",
    "eligible_exposure_is_one_and_exclusions_zero": """
        select count(*) from possession_disposition d
        left join model_row m using (game_id, stream_revision, possession_seq)
        where (d.reason = 'eligible') <> (m.possession_seq is not null)
           or d.exposure <> (d.reason = 'eligible')::int
           or (d.exposure = 0) <> (d.offense_lineup_id is null and d.defense_lineup_id is null)
           or (d.exposure = 1) <> (d.offense_lineup_id is not null and d.defense_lineup_id is not null)""",
    "stints_contiguous_within_period": """
        select count(*) from (
          select start_seq, end_seq,
                 lag(end_seq) over (partition by game_id, stream_revision, period
                                    order by start_seq, stint_seq) as previous_end
          from stint)
        where end_seq <= start_seq or (previous_end is not null and start_seq <> previous_end)""",
    "model_rows_unique_unit_weight_and_valid_points": """
        select (select count(*) - count(distinct (game_id, stream_revision, possession_seq))
                from model_row)
             + (select count(*) from model_row
                where exposure <> 1 or weight <> 1.0 or model_points < 0
                   or len(offense_player_ids) <> 5 or len(defense_player_ids) <> 5
                   or list_has_any(offense_player_ids, defense_player_ids)
                   or offense_lineup_id = defense_lineup_id)
             + (select count(*) from model_row m join lineup o
                  on o.game_id = m.game_id and o.stream_revision = m.stream_revision
                 and o.lineup_id = m.offense_lineup_id
                join lineup f on f.game_id = m.game_id and f.stream_revision = m.stream_revision
                 and f.lineup_id = m.defense_lineup_id
                where o.team_id <> m.offense_team_id or f.team_id <> m.defense_team_id)""",
    "score_allocations_classified_once": """
        select (select count(*) from score_allocation) - (select count(*) from score_reconciliation)
             + (select count(*) - count(distinct (game_id, stream_revision, seq, scoring_team_id))
                from score_reconciliation)
             + (select count(*) from score_reconciliation
                where destination not in ('possession', 'unassigned_dead_ball', 'unresolved')
                   or (destination = 'possession') <> (possession_seq is not null)
                   or (destination = 'possession') <> (disposition is not null))""",
    "control_points_scored_by_offense": """
        select count(*) from score_reconciliation s
        join possession_disposition d using (game_id, stream_revision, possession_seq)
        where s.scoring_team_id <> d.offense_team_id or s.points_delta < 0""",
    "pilot_possession_status_counts_reconcile_by_game": """
        select count(*) from game_reconciliation r
        left join (select game_id, count(*) n,
                     count(*) filter (status = 'accepted') a,
                     count(*) filter (status = 'excluded') e,
                     count(*) filter (status = 'unresolved') u
                   from possession group by game_id) p using (game_id)
        where r.possessions <> r.eligible + r.multiple_lineups + r.no_action + r.period_end_start
                               + r.pilot_excluded
                               + r.unresolved_control
           or r.possessions <> coalesce(p.n, 0)
           or r.eligible + r.multiple_lineups + r.no_action + r.period_end_start
              <> coalesce(p.a, 0)
           or r.pilot_excluded <> coalesce(p.e, 0) or r.unresolved_control <> coalesce(p.u, 0)
           or (not r.accepted and r.possessions + r.allocations <> 0)""",
    "modeled_points_equal_eligible_control_points_by_team": """
        select count(*) from game_reconciliation r
        left join (select game_id,
                     coalesce(sum(control_points) filter (offense_team_id = home_team_id), 0) h,
                     coalesce(sum(control_points) filter (offense_team_id = away_team_id), 0) a
                   from possession_disposition join games using (game_id)
                   where reason = 'eligible' group by game_id) e using (game_id)
        left join (select game_id,
                     coalesce(sum(model_points) filter (offense_team_id = home_team_id), 0) h,
                     coalesce(sum(model_points) filter (offense_team_id = away_team_id), 0) a
                   from model_row join games using (game_id) group by game_id) m using (game_id)
        where r.home_modeled_points <> coalesce(e.h, 0) or r.away_modeled_points <> coalesce(e.a, 0)
           or coalesce(m.h, 0) <> coalesce(e.h, 0) or coalesce(m.a, 0) <> coalesce(e.a, 0)""",
    "allocations_reconcile_to_final_score_by_side": """
        select count(*) from game_reconciliation r
        left join (select a.game_id,
                     sum(points_delta) filter (scoring_team_id = home_team_id) h,
                     sum(points_delta) filter (scoring_team_id = away_team_id) a,
                     count(*) filter (scoring_team_id not in (home_team_id, away_team_id)) other
                   from score_allocation a join games using (game_id) group by a.game_id) p
          using (game_id)
        where r.accepted and (
              r.home_modeled_points + r.home_other_control_points
                + r.home_unassigned_dead_ball_points + r.home_unresolved_points
                <> r.home_final
           or r.away_modeled_points + r.away_other_control_points
                + r.away_unassigned_dead_ball_points + r.away_unresolved_points <> r.away_final
           or coalesce(p.h, 0) <> r.home_final or coalesce(p.a, 0) <> r.away_final
           or coalesce(p.other, 0) <> 0)""",
    "model_exposure_matches_eligible_count_by_team_and_role": """
        select count(*) from game_reconciliation r
        left join (select game_id, count(*) n, sum(len(offense_player_ids)) o,
                     sum(len(defense_player_ids)) f from model_row group by game_id) m
          using (game_id)
        where r.home_model_offense_exposure + r.away_model_offense_exposure <> r.eligible
           or coalesce(m.n, 0) <> r.eligible
           or coalesce(m.o, 0) <> 5 * r.eligible or coalesce(m.f, 0) <> 5 * r.eligible""",
}

# Checks that apply to one exclusion variant only.
VARIANT_CHECKS = {
    "no_action": {
        "no_action_possessions_have_no_events_and_score_zero": """
        select count(*) from possession_disposition
        where (reason = 'no_action') <> (pilot_status = 'accepted' and action_events = 0)
           or (reason = 'no_action' and control_points <> 0)"""
    },
    "period_end_start": {
        "period_end_start_possessions_start_on_period_end_and_score_zero": """
        select count(*) from possession_disposition
        where (reason = 'period_end_start')
              <> (pilot_status = 'accepted' and first_event_kind = 'period_end')
           or (reason = 'period_end_start' and (control_points <> 0 or action_events <> 0))"""
    },
    "canonical": {},
}


def _points(side: str, destination: str, modeled: bool) -> str:
    team = f"g.{side}_team_id"
    flag = "x.modeled" if modeled else "NOT x.modeled"
    if destination == "possession":
        scope = f"x.destination = 'possession' AND {flag}"
    else:
        scope = f"x.destination = '{destination}'"
    return f"coalesce(sum(x.points_delta) FILTER (x.scoring_team_id = {team} AND {scope}), 0)"


def _pilot_inputs(pilot: Path, pin: str) -> dict[str, object]:
    manifest_path = pilot / "manifest.json"
    if sha256_file(manifest_path) != pin:
        raise ValueError("The pilot manifest differs from the pinned digest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    listed = {row["filename"]: row for row in manifest["output_artifacts"]}
    for name in PILOT_TABLES:
        row = listed[f"{name}.parquet"]
        if sha256_file(pilot / row["filename"]) != row["sha256"]:
            raise ValueError(f"Pilot table {name} differs from its manifest digest")
    return cast(dict[str, object], manifest)


def _tally(connection: duckdb.DuckDBPyConnection) -> dict[str, dict[str, int]]:
    """Counts, points and exposure by season type and adjudication stratum.

    Strata overlap, so a game appears under each of its strata and stratum cells do not sum.
    """
    result: dict[str, dict[str, int]] = {}
    strata = "unnest(list_concat(['all'], g.strata)) AS stratum"
    queries: tuple[tuple[str, Callable[..., dict[str, int]]], ...] = (
        (
            f"SELECT g.season_type, {strata}, g.accepted, coalesce(g.home_final + g.away_final, 0), 1 "
            "FROM games g",
            lambda accepted, final, n: {
                "games_expected": n,
                "games_accepted": n * int(accepted),
                "games_quarantined": n * int(not accepted),
                "final_points": final * int(accepted),
            },
        ),
        (
            f"SELECT g.season_type, {strata}, d.reason, d.control_points, 1 "
            "FROM possession_disposition d JOIN games g USING (game_id)",
            lambda reason, points, n: {
                f"{reason}_possessions": n,
                f"{reason}_control_points": points,
                f"{reason}_exposure": n * int(reason == "eligible"),
            },
        ),
        (
            f"SELECT g.season_type, {strata}, s.destination, s.points_delta, s.modeled "
            "FROM score_reconciliation s JOIN games g USING (game_id)",
            lambda destination, points, modeled: {
                f"score_{destination}_points": points,
                f"score_{'modeled' if modeled else 'not_modeled'}_points": points,
            },
        ),
    )
    for sql, metrics in queries:
        for season, stratum, first, second, third in connection.execute(sql).fetchall():
            for scope in (season, "all"):
                cell = result.setdefault(f"{scope}|{stratum}", dict.fromkeys(METRICS, 0))
                for name, value in metrics(first, second, third).items():
                    cell[name] = cell.get(name, 0) + int(value)
    return {key: dict(sorted(result[key].items())) for key in sorted(result)}


def _violations(connection: duckdb.DuckDBPyConnection, variant: str) -> dict[str, int]:
    return {
        name: int(cast(tuple[int], connection.execute(sql).fetchone())[0])
        for name, sql in {**CHECKS, **VARIANT_CHECKS[variant]}.items()
    }


def build_rows(
    pilot_dir: Path,
    output: Path,
    code_commit: str,
    pilot_manifest_sha256: str,
    variant: str = "canonical",
) -> dict[str, object]:
    if variant not in VARIANTS:
        raise ValueError(f"Unknown exclusion variant {variant}")
    excluded_reason, excluded = EXCLUSION[variant]
    if re.fullmatch(r"[0-9a-f]{40}", code_commit) is None:
        raise ValueError("Record a full Git commit for the row build")
    pilot = _pilot_inputs(pilot_dir, pilot_manifest_sha256)
    when = utc_now()
    output.mkdir(mode=0o700, parents=True)
    try:
        staging = output / ".staging"
        staging.mkdir(mode=0o700)
        with duckdb.connect() as connection:
            connection.execute("SET TimeZone = 'UTC'")
            connection.execute("SET temp_directory = ?", [str(staging / "duckdb-spill")])
            for name in PILOT_TABLES:
                location = str(pilot_dir / f"{name}.parquet").replace("'", "''")
                connection.execute(
                    f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{location}')"
                )
            for sql in (
                SORTED_IDS,
                GAMES,
                DISPOSITION.replace("{action_kinds}", ACTION_KINDS)
                .replace("{excluded_reason}", excluded_reason)
                .replace("{excluded}", excluded),
                MODEL_ROW,
                SCORE,
                _game_reconciliation_sql(),
            ):
                connection.execute(sql)
            counts = _violations(connection, variant)
            failed = {name: count for name, count in counts.items() if count}
            if failed:
                raise ValueError(f"Row-set identities failed against the pilot ledgers: {failed}")
            summary = _tally(connection)
            order = {
                "model_row": "game_id, stream_revision, possession_seq",
                "possession_disposition": "game_id, stream_revision, possession_seq",
                "score_reconciliation": "game_id, stream_revision, seq, scoring_team_id",
                "game_reconciliation": "game_id",
            }
            artifacts: list[dict[str, object]] = []
            for name in OUTPUT_TABLES:
                path = output / f"{name}.parquet"
                connection.execute(
                    f"COPY (SELECT * FROM {name} ORDER BY {order[name]}) TO ? "
                    "(FORMAT PARQUET, COMPRESSION ZSTD)",
                    [str(path)],
                )
                artifacts.append(
                    {
                        "filename": path.name,
                        "sha256": sha256_file(path),
                        "size_bytes": path.stat().st_size,
                        "row_count": int(
                            cast(
                                tuple[int],
                                connection.execute(f"SELECT count(*) FROM {name}").fetchone(),
                            )[0]
                        ),
                    }
                )
        shutil.rmtree(staging, ignore_errors=True)
        pilot_artifacts = {
            row["filename"]: row["sha256"]
            for row in cast(list[dict[str, str]], pilot["output_artifacts"])
            if row["filename"] in {f"{name}.parquet" for name in PILOT_TABLES}
        }
        identity: dict[str, object] = {
            "contract_revision": CONTRACT_REVISION,
            "variant": variant,
            "pilot_manifest_sha256": pilot_manifest_sha256,
            "pilot_source_snapshot_sha256": pilot["source_snapshot_sha256"],
            "pilot_input_tables": pilot_artifacts,
            "output_artifacts": [
                {k: row[k] for k in ("filename", "sha256", "row_count")} for row in artifacts
            ],
        }
        build_id = sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        manifest: dict[str, object] = {
            "schema_version": 1,
            "build_id": build_id,
            "contract_revision": CONTRACT_REVISION,
            "variant": variant,
            "code_commit": code_commit,
            "generated_at": when,
            "duckdb_version": version("duckdb"),
            "pilot_manifest_sha256": pilot_manifest_sha256,
            "pilot_code_commit": pilot["code_commit"],
            "pilot_parser": pilot["parser"],
            "pilot_source_snapshot_sha256": pilot["source_snapshot_sha256"],
            "pilot_input_tables": pilot_artifacts,
            "output_artifacts": artifacts,
            "unit_exposure": "one_full_opportunity_per_eligible_possession",
            "evidence_tier": pilot["availability"],
            "availability_note": (
                "Retrospective capture-bound availability. Strict rolling-origin availability at "
                "historical game dates is unavailable for this snapshot."
            ),
            "identity_violations": counts,
            "reconciliation": summary,
            "attribution": ATTRIBUTION,
            "terms": NBA_TERMS,
        }
        write_json(output / "manifest.json", manifest)
    except BaseException:
        shutil.rmtree(output, ignore_errors=True)
        raise
    return manifest


def _game_reconciliation_sql() -> str:
    score = ",\n    ".join(
        f"{_points(side, destination, modeled)} AS {side}_{name}_points"
        for side in ("home", "away")
        for name, destination, modeled in (
            ("modeled", "possession", True),
            ("other_control", "possession", False),
            ("unassigned_dead_ball", "unassigned_dead_ball", False),
            ("unresolved", "unresolved", False),
        )
    )
    final = "".join(f"coalesce(s.{name}, 0) AS {name}, " for name in POINT_FIELDS)
    return GAME_RECONCILIATION.replace("{score_fields}", score + ",").replace(
        "{final_fields}", final
    )


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("pilot_dir", type=Path, help="exported pilot build")
    cli.add_argument("output_dir", type=Path, help="new directory for the row set")
    cli.add_argument("--pilot-manifest-sha256", required=True)
    cli.add_argument("--code-commit", required=True)
    cli.add_argument(
        "--variant",
        choices=VARIANTS,
        default="canonical",
        help="canonical keeps all accepted stable-lineup possessions; period_end_start and "
        "no_action are sensitivity exclusions",
    )
    args = cli.parse_args()
    manifest = build_rows(
        args.pilot_dir, args.output_dir, args.code_commit, args.pilot_manifest_sha256, args.variant
    )
    print(json.dumps({"build_id": manifest["build_id"], "outputs": manifest["output_artifacts"]}))


if __name__ == "__main__":
    main()
