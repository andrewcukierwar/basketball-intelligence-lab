"""Audit possessions whose first event is ``period_end`` in a pilot build.

Usage: ``python scripts/audit_period_end_possessions.py <pilot_dir>``. Prints deterministic JSON.
For each pilot status it reports what such possessions contain, what the clock showed when the
possession began (``remaining_ms`` of the last event before its first event, in the same period),
the kind of that preceding event and how many start with less than 3 s left. A possession that
begins after a change of control with time on the clock is a run-out, not a pseudo-possession,
even if it holds no further action (ADR-0019). The pilot's own rule already marks starts with
under 3 s left as ``excluded``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb

ACTIONS = "('shot', 'free_throw', 'turnover', 'foul', 'violation', 'jump_ball')"
LOW_MS = 3000

SQL = f"""
WITH first_event AS (
  SELECT p.*, (SELECT e.kind FROM event e WHERE e.game_id = p.game_id
            AND e.stream_revision = p.stream_revision AND e.seq >= p.start_seq
            AND e.seq < p.end_seq ORDER BY e.seq LIMIT 1) AS first_kind
  FROM possession p),
target AS (SELECT * FROM first_event WHERE first_kind = 'period_end')
SELECT t.status, t.game_id, t.stream_revision, t.possession_seq, t.period,
  (SELECT count(*) FROM event e WHERE e.game_id = t.game_id AND e.stream_revision = t.stream_revision
     AND e.seq >= t.start_seq AND e.seq < t.end_seq AND e.kind IN {ACTIONS}) AS action_events,
  (SELECT count(*) FROM score_allocation a WHERE a.game_id = t.game_id
     AND a.stream_revision = t.stream_revision AND a.seq >= t.start_seq AND a.seq < t.end_seq)
     AS allocations,
  (SELECT count(*) FROM event e WHERE e.game_id = t.game_id AND e.stream_revision = t.stream_revision
     AND e.seq >= t.start_seq AND e.seq < t.end_seq AND e.kind = 'period_start') AS boundary_events,
  (SELECT p.remaining_ms FROM event p WHERE p.game_id = t.game_id
     AND p.stream_revision = t.stream_revision AND p.seq < t.start_seq AND p.period = t.period
     ORDER BY p.seq DESC LIMIT 1) AS prior_remaining_ms,
  (SELECT p.kind FROM event p WHERE p.game_id = t.game_id
     AND p.stream_revision = t.stream_revision AND p.seq < t.start_seq AND p.period = t.period
     ORDER BY p.seq DESC LIMIT 1) AS prior_kind,
  (SELECT p.remaining_ms FROM event p WHERE p.game_id = t.game_id
     AND p.stream_revision = t.stream_revision AND p.seq = t.start_seq) AS start_remaining_ms,
  (SELECT p.kind FROM event p WHERE p.game_id = t.game_id
     AND p.stream_revision = t.stream_revision AND p.seq >= t.end_seq ORDER BY p.seq LIMIT 1)
     AS next_kind
FROM target t ORDER BY t.game_id, t.stream_revision, t.possession_seq
"""


def _quantiles(values: list[int]) -> dict[str, int | None]:
    values = sorted(values)
    if not values:
        return dict.fromkeys(("min", "p25", "median", "p75", "max"))
    last = len(values) - 1
    return {
        "min": values[0],
        "p25": values[last // 4],
        "median": values[last // 2],
        "p75": values[(3 * last) // 4],
        "max": values[-1],
    }


def audit(pilot: Path) -> dict[str, object]:
    with duckdb.connect() as connection:
        for name in ("event", "possession", "score_allocation"):
            location = str(pilot / f"{name}.parquet").replace("'", "''")
            connection.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{location}')")
        cursor = connection.execute(SQL)
        columns = [c[0] for c in cursor.description]
        rows = [dict(zip(columns, r, strict=True)) for r in cursor.fetchall()]
    by_status: dict[str, object] = {}
    for status in sorted({r["status"] for r in rows}):
        group = [r for r in rows if r["status"] == status]
        clocks = [
            int(r["prior_remaining_ms"]) for r in group if r["prior_remaining_ms"] is not None
        ]
        kinds: dict[str, int] = {}
        for r in group:
            kinds[str(r["prior_kind"])] = kinds.get(str(r["prior_kind"]), 0) + 1
        nexts: dict[str, int] = {}
        for r in group:
            nexts[str(r["next_kind"])] = nexts.get(str(r["next_kind"]), 0) + 1
        by_status[status] = {
            "possessions": len(group),
            "with_action_or_jump_ball_event": sum(r["action_events"] > 0 for r in group),
            "with_score_allocation": sum(r["allocations"] > 0 for r in group),
            "spanning_period_boundary": sum(r["boundary_events"] > 0 for r in group),
            "no_prior_event_in_period": sum(r["prior_remaining_ms"] is None for r in group),
            "clock_at_start_ms": _quantiles(clocks),
            "under_3s_at_start": sum(c < LOW_MS for c in clocks),
            "3s_or_more_at_start": sum(c >= LOW_MS for c in clocks),
            "final_period_or_overtime_3s_or_more": sum(
                (r["prior_remaining_ms"] or 0) >= LOW_MS and r["period"] >= 4 for r in group
            ),
            "preceding_event_kind": dict(sorted(kinds.items())),
            "next_event_kind": dict(sorted(nexts.items())),
        }
    return {
        "first_event_period_end_by_pilot_status": by_status,
        "accepted_examples_3s_or_more": [
            {k: r[k] for k in ("game_id", "stream_revision", "possession_seq", "period")}
            | {"clock_ms": r["prior_remaining_ms"], "prior_kind": r["prior_kind"]}
            for r in rows
            if r["status"] == "accepted" and (r["prior_remaining_ms"] or 0) >= LOW_MS
        ][:5],
    }


if __name__ == "__main__":
    print(json.dumps(audit(Path(sys.argv[1])), indent=2, sort_keys=True))
