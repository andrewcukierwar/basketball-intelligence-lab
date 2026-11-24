"""Verify possession and lineup attribution in games repaired by order-repair-v2 (ADR-0029).

Example:
    uv run python scripts/order_repair_verification.py BUILD_DIR EVIDENCE_DIR YEAR [--report FILE]

Compares the repaired games (stratum ``datanba_event_order_v2``) with the other accepted games on
three independent measures: lineup seconds against Bentes stints, counted possessions against
pbpstats.com, and possession offense against data.nba on live-ball events. The repaired games
cannot be compared with an unrepaired attempt, because that attempt failed a hard check and
produced no rows. All feeds derive from the same NBA event log, so agreement is consistency
evidence, not external truth. Read-only; the output is aggregate JSON.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb

from bil.data.pilot_evidence import lineup_agreement, possession_agreement, stage_build, stage_feeds

STRATUM = "datanba_event_order_v2"


def verify(build: Path, evidence: Path, year: int) -> dict[str, object]:
    with TemporaryDirectory() as temp, duckdb.connect() as connection:
        stage_feeds(connection, evidence, Path(temp), year)
        stage_build(connection, build)
        lineup_agreement(connection)  # builds lineup_overlap
        possession_agreement(connection)  # builds live_events
        group = f"case when list_contains(r.strata, '{STRATUM}') then 'repaired' else 'other' end"
        lineup = connection.execute(
            f"""select {group} as grp, count(distinct l.game_id),
                       sum(seconds) filter (where same) / sum(seconds),
                       sum(seconds) filter (where not same and seconds > 2)
                from lineup_overlap l join game_review r using (game_id) group by 1"""
        ).fetchall()
        per_game = connection.execute(
            f"""select {group} as grp, min(share) from (
                  select l.game_id, sum(seconds) filter (where same) / sum(seconds) as share
                  from lineup_overlap l group by 1) s join game_review r using (game_id) group by 1"""
        ).fetchall()
        counts = connection.execute(
            f"""
            with theirs as (
              select GAMEID as game_id, count(*) as n from (
                select distinct GAMEID, PERIOD, STARTTIME, ENDTIME, OPPONENT from pbpstats)
              group by 1),
            mine as (select game_id, count(*) filter (where status = 'accepted') as n
                     from possession group by 1)
            select {group} as grp, count(*), count(*) filter (where t.n = m.n),
                   count(*) filter (where abs(t.n - m.n) <= 2), sum(m.n - t.n)
            from mine m join theirs t using (game_id) join game_review r using (game_id)
            where r.accepted group by 1"""
        ).fetchall()
        offense = connection.execute(
            f"""
            with feed as (select distinct GAME_ID as game_id, cast(evt as int) as evt, oftid as team
                          from datanba where oftid not in ('', '0'))
            select {group} as grp, count(*), count(*) filter (where f.team = l.offense)
            from live_events l join feed f using (game_id, evt)
            join game_review r using (game_id) group by 1"""
        ).fetchall()
        unresolved = connection.execute(
            f"""select {group} as grp, count(*), count(*) filter (where p.status = 'unresolved')
                from possession p join game_review r using (game_id) where r.accepted group by 1"""
        ).fetchall()
    return {
        "lineup_vs_bentes": {
            g: {"games": n, "same_seconds_share": s, "disagreeing_seconds_over_2s_pieces": d}
            for g, n, s, d in lineup
        },
        "lowest_game_lineup_share": dict(per_game),
        "possession_count_vs_pbpstats": {
            g: {"games": n, "equal": e, "within_2": w, "net_difference": d}
            for g, n, e, w, d in counts
        },
        "possession_offense_vs_datanba_live_ball": {
            g: {"events": n, "agree": a, "share": a / n if n else None} for g, n, a in offense
        },
        "possessions": {g: {"possessions": n, "unresolved": u} for g, n, u in unresolved},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("build", type=Path)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("year", type=int)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    text = json.dumps(verify(args.build, args.evidence, args.year), indent=2, sort_keys=True)
    print(text)
    if args.report:
        args.report.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
