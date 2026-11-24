"""Audit accepted possessions whose first event is ``period_end`` in a pilot build.

Usage: ``python scripts/audit_period_end_possessions.py <pilot_dir>``. Prints deterministic JSON.
Supports ADR-0019: such a possession is a period-end pseudo-possession with no live-ball
opportunity if it holds no action or jump-ball event, no score delta or allocation, no game-clock
duration beyond a small tolerance, stays inside one period, and is followed by ``period_start`` or
the end of the stream. Every exception is listed individually.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb

ACTIONS = "('shot', 'free_throw', 'turnover', 'foul', 'violation', 'jump_ball')"

SQL = f"""
WITH first_event AS (
  SELECT p.game_id, p.stream_revision, p.possession_seq, p.period, p.start_seq, p.end_seq,
         (SELECT e.kind FROM event e WHERE e.game_id = p.game_id
            AND e.stream_revision = p.stream_revision AND e.seq >= p.start_seq
            AND e.seq < p.end_seq ORDER BY e.seq LIMIT 1) AS first_kind
  FROM possession p WHERE p.status = 'accepted'),
target AS (SELECT * FROM first_event WHERE first_kind = 'period_end'),
stats AS (
  SELECT t.*,
    (SELECT count(*) FROM event e WHERE e.game_id = t.game_id AND e.stream_revision = t.stream_revision
       AND e.seq >= t.start_seq AND e.seq < t.end_seq) AS events,
    (SELECT count(*) FROM event e WHERE e.game_id = t.game_id AND e.stream_revision = t.stream_revision
       AND e.seq >= t.start_seq AND e.seq < t.end_seq AND e.kind IN {ACTIONS}) AS action_events,
    (SELECT count(*) FROM event e WHERE e.game_id = t.game_id AND e.stream_revision = t.stream_revision
       AND e.seq >= t.start_seq AND e.seq < t.end_seq
       AND (coalesce(e.home_delta, 0) <> 0 OR coalesce(e.away_delta, 0) <> 0)) AS score_events,
    (SELECT count(*) FROM score_allocation a WHERE a.game_id = t.game_id
       AND a.stream_revision = t.stream_revision AND a.seq >= t.start_seq AND a.seq < t.end_seq)
       AS allocations,
    (SELECT count(*) FROM score_allocation a WHERE a.game_id = t.game_id
       AND a.stream_revision = t.stream_revision AND a.possession_seq = t.possession_seq)
       AS linked_allocations,
    (SELECT coalesce(max(e.elapsed_ms) - min(e.elapsed_ms), 0) FROM event e
       WHERE e.game_id = t.game_id AND e.stream_revision = t.stream_revision
       AND e.seq >= t.start_seq AND e.seq < t.end_seq) AS duration_ms,
    (SELECT count(*) FROM event e WHERE e.game_id = t.game_id AND e.stream_revision = t.stream_revision
       AND e.seq >= t.start_seq AND e.seq < t.end_seq
       AND (e.period <> t.period OR e.kind = 'period_start')) AS boundary_events,
    (SELECT e.kind FROM event e WHERE e.game_id = t.game_id AND e.stream_revision = t.stream_revision
       AND e.seq >= t.end_seq ORDER BY e.seq LIMIT 1) AS next_kind
  FROM target t)
SELECT * FROM stats ORDER BY game_id, stream_revision, possession_seq
"""


def audit(pilot: Path, tolerance_ms: int = 1000) -> dict[str, object]:
    with duckdb.connect() as connection:
        for name in ("event", "possession", "score_allocation"):
            location = str(pilot / f"{name}.parquet").replace("'", "''")
            connection.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{location}')")
        columns = [c[0] for c in connection.execute(SQL).description]
        rows = [dict(zip(columns, r, strict=True)) for r in connection.execute(SQL).fetchall()]
        total_accepted = connection.execute(
            "SELECT count(*) FROM possession WHERE status = 'accepted'"
        ).fetchone()
    exceptions: list[dict[str, object]] = []
    for r in rows:
        reasons = [
            name
            for name, bad in (
                ("action_or_jump_ball_event", r["action_events"] > 0),
                ("score_delta", r["score_events"] > 0),
                ("score_allocation", r["allocations"] > 0 or r["linked_allocations"] > 0),
                ("duration_over_tolerance", (r["duration_ms"] or 0) > tolerance_ms),
                ("spans_period_boundary", r["boundary_events"] > 0),
                ("followed_by_live_play", r["next_kind"] not in (None, "period_start")),
            )
            if bad
        ]
        if reasons:
            exceptions.append(
                {
                    "game_id": r["game_id"],
                    "stream_revision": r["stream_revision"],
                    "possession_seq": r["possession_seq"],
                    "reasons": reasons,
                }
            )
    durations = sorted(int(r["duration_ms"] or 0) for r in rows)
    next_kinds: dict[str, int] = {}
    for r in rows:
        key = str(r["next_kind"])
        next_kinds[key] = next_kinds.get(key, 0) + 1
    return {
        "accepted_possessions": int(total_accepted[0]) if total_accepted else 0,
        "first_event_period_end": len(rows),
        "with_action_or_jump_ball_event": sum(r["action_events"] > 0 for r in rows),
        "with_score_delta": sum(r["score_events"] > 0 for r in rows),
        "with_score_allocation": sum(
            r["allocations"] > 0 or r["linked_allocations"] > 0 for r in rows
        ),
        "spanning_period_boundary": sum(r["boundary_events"] > 0 for r in rows),
        "events_per_possession_max": max((r["events"] for r in rows), default=0),
        "duration_ms": {
            "min": durations[0] if durations else None,
            "median": durations[len(durations) // 2] if durations else None,
            "p99": durations[int(0.99 * (len(durations) - 1))] if durations else None,
            "max": durations[-1] if durations else None,
            "over_tolerance": sum(d > tolerance_ms for d in durations),
            "tolerance_ms": tolerance_ms,
        },
        "next_event_kind": dict(sorted(next_kinds.items())),
        "exceptions": exceptions,
    }


if __name__ == "__main__":
    print(json.dumps(audit(Path(sys.argv[1])), indent=2, sort_keys=True))
