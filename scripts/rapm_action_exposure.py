"""Audit #164 exposure shares without fitting or scoring prediction outcomes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import numpy as np
from rapm_lineup_exposure import (
    COHORT_AUDIT,
    LEDGER_AUDIT,
    ROW_SET_VERSION,
    SEASONS,
    check_season,
    count,
    fractional_rows,
    read_verified,
    verify_pilot,
    verify_row_set,
)

from bil.data.rapm_rows import DECISIVE_CONTROL

ACTION_EXPOSURE = f"""
CREATE TEMP TABLE action_pieces AS
WITH counted AS (
    SELECT c.row_id, x.stint_seq,
           count(e.seq) FILTER (e.team_id = c.offense_team_id) AS tokens,
           count(e.seq) FILTER (e.team_id <> c.offense_team_id) AS conflicts,
           count(e.seq) FILTER (e.team_id IS NULL) AS unknown
    FROM cohort c
    JOIN segments x USING (row_id)
    JOIN stint s ON s.game_id = c.game_id AND s.stream_revision = c.stream_revision
      AND s.stint_seq = x.stint_seq
    LEFT JOIN event e ON e.game_id = c.game_id AND e.stream_revision = c.stream_revision
      AND e.seq >= greatest(c.start_seq, s.start_seq)
      AND e.seq < least(c.end_seq, s.end_seq)
      AND {DECISIVE_CONTROL}
    GROUP BY 1, 2
), weights AS (
    SELECT x.*, c.multi, p.tokens, sum(p.tokens) OVER w AS all_tokens,
           sum(p.conflicts) OVER w AS conflicts, sum(p.unknown) OVER w AS unknown,
           sum(x.ms) OVER w AS total_ms, count(*) OVER w AS pieces
    FROM segments x
    JOIN cohort c USING (row_id)
    JOIN counted p USING (row_id, stint_seq)
    WINDOW w AS (PARTITION BY row_id)
)
SELECT *,
       CASE WHEN conflicts > 0 THEN 'control_conflict'
            WHEN unknown > 0 THEN 'control_unknown'
            WHEN NOT multi THEN 'stable'
            WHEN all_tokens > 0 THEN 'action'
            WHEN total_ms > 0 THEN 'clock'
            ELSE 'unsupported_zero_clock'
       END AS disposition,
       CASE WHEN conflicts > 0 OR unknown > 0 THEN 0.0
            WHEN NOT multi THEN 1.0 / pieces
            WHEN all_tokens > 0 THEN tokens::DOUBLE / all_tokens
            WHEN total_ms > 0 THEN ms::DOUBLE / total_ms
            ELSE 0.0
       END AS share
FROM weights;
"""


def audit(processed: Path, season: int) -> dict[str, object]:
    """Reuse the #110 archived ledger checks and verify the expanded sparse design mass."""
    pin = check_season(season, SEASONS)
    rows = processed / pin.label / ROW_SET_VERSION
    pilot = processed / pin.label / pin.pilot_build
    row_manifest = verify_row_set(rows, season, pin)
    verify_pilot(pilot, pin, row_manifest)
    manifest = json.loads((pilot / "manifest.json").read_text())
    with duckdb.connect(config={"threads": 2}) as con:
        read_verified(con, rows, row_manifest, ("model_row", "possession_disposition"))
        read_verified(
            con,
            pilot,
            manifest,
            ("event", "game", "game_stream", "lineup", "stint", "score_allocation"),
        )
        if count(con, LEDGER_AUDIT):
            raise ValueError(f"{pin.label} control ledger differs from the archived allocations")
        con.execute(Path(__file__).with_name("rapm_lineup_exposure.sql").read_text())
        if count(con, "SELECT count(*) FROM cohort") != count(
            con, "SELECT count(*) FROM possession_disposition WHERE pilot_status='accepted'"
        ) or count(con, COHORT_AUDIT):
            raise ValueError(f"{pin.label} opportunity identity or lineage disagrees")
        con.execute(ACTION_EXPOSURE)
        coverage = con.execute("""
            SELECT multi, disposition, count(DISTINCT row_id)
            FROM action_pieces GROUP BY ALL ORDER BY ALL
        """).fetchall()
        pieces = con.execute("""
            SELECT row_id, share, offense, defense FROM action_pieces WHERE share > 0
            ORDER BY row_id, stint_seq
        """).fetchall()
        accepted_rows = count(con, "SELECT count(DISTINCT row_id) FROM action_pieces")
        if accepted_rows != count(con, "SELECT count(*) FROM cohort"):
            raise ValueError(f"{pin.label} exposure lost an accepted opportunity")

    row_id, share, offense, defense = zip(*pieces, strict=True)
    eligible, row_index = np.unique(row_id, return_inverse=True)
    off = np.asarray(offense, dtype=np.int64)
    dfn = np.asarray(defense, dtype=np.int64)
    if off.shape[1] != 5 or dfn.shape[1] != 5:
        raise ValueError(f"{pin.label} requires five players per role")
    players_by_piece = np.sort(np.concatenate([off, dfn], axis=1), axis=1)
    if np.any(players_by_piece <= 0) or np.any(np.diff(players_by_piece, axis=1) == 0):
        raise ValueError(f"{pin.label} lineups must have ten distinct players")
    players = np.unique(np.concatenate([off.ravel(), dfn.ravel()]))
    fractional_rows(players, row_index, np.asarray(share), off, dfn, int(eligible.size))
    return {
        "candidate_rows": int(eligible.size),
        "archived_rows": accepted_rows,
        "dispositions": [
            {"multi": multi, "reason": reason, "rows": total} for multi, reason, total in coverage
        ],
        "row_manifest_sha256": pin.row_manifest_sha256,
        "pilot_manifest_sha256": pin.pilot_manifest_sha256,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("processed", type=Path)
    parser.add_argument("--season", action="append", type=int, choices=SEASONS)
    args = parser.parse_args()
    print(json.dumps({year: audit(args.processed, year) for year in args.season or SEASONS}))


if __name__ == "__main__":
    main()
