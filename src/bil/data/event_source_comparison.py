"""Compare a V3-event build of a season with its V2-event build (#133).

Both inputs are canonical RAPM row sets (``bil.data.rapm_rows``) built from pilot builds of
the same source snapshot. The comparison reads only model rows and game reconciliation:
accepted-game agreement, and in games both accept, possession-row identity on the fields the
models use (period, offense team, both lineups and points). ``fields`` compares the rebuilt
event rows themselves with the archived V2 rows of the same snapshot.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import duckdb

from bil.data.pilot_inputs import GameIssue, _v2_field, archive_rows, box_scores, event_games
from bil.data.pilot_v3_events import ACTION_TYPES, SHOT_TYPES, fallback_code, rebuilt_games

ROW_KEY = (
    "period, offense_team_id, list_sort(offense_player_ids) AS offense, "
    "list_sort(defense_player_ids) AS defense, model_points"
)


def _quoted(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def compare(v2_rows: Path, v3_rows: Path) -> dict[str, Any]:
    with duckdb.connect() as c:
        for name, path in (("a", v2_rows), ("b", v3_rows)):
            games_path = _quoted(path / "game_reconciliation.parquet")
            rows_path = _quoted(path / "model_row.parquet")
            c.execute(f"CREATE TEMP TABLE {name}_game AS SELECT * FROM read_parquet({games_path})")
            c.execute(
                f"CREATE TEMP TABLE {name}_row AS SELECT game_id, possession_seq, season_type, "
                f"{ROW_KEY} FROM read_parquet({rows_path})"
            )
        games = {}
        for kind in ("regular", "playoffs"):
            row = c.execute(
                "SELECT count(*) FILTER (a.accepted AND b.accepted), "
                "count(*) FILTER (a.accepted AND NOT b.accepted), "
                "count(*) FILTER (NOT a.accepted AND b.accepted), "
                "count(*) FILTER (NOT a.accepted AND NOT b.accepted), "
                "count(*) FILTER (a.accepted), count(*) FILTER (b.accepted), count(*) "
                "FROM a_game a JOIN b_game b USING (game_id) WHERE a.season_type = ?",
                [kind],
            ).fetchone()
            assert row is not None
            games[kind] = dict(
                zip(
                    ("both", "v2_only", "v3_only", "neither", "v2", "v3", "games"),
                    map(int, row),
                    strict=True,
                )
            )
        c.execute(
            "CREATE TEMP TABLE common AS SELECT game_id FROM a_game a JOIN b_game b "
            "USING (game_id) WHERE a.accepted AND b.accepted"
        )
        per_game = c.execute(
            """
            WITH a AS (SELECT * FROM a_row WHERE game_id IN (SELECT game_id FROM common)),
                 b AS (SELECT * FROM b_row WHERE game_id IN (SELECT game_id FROM common)),
                 only_a AS (SELECT * EXCLUDE (possession_seq) FROM a
                            EXCEPT ALL SELECT * EXCLUDE (possession_seq) FROM b),
                 only_b AS (SELECT * EXCLUDE (possession_seq) FROM b
                            EXCEPT ALL SELECT * EXCLUDE (possession_seq) FROM a),
                 diff AS (SELECT game_id, count(*) AS n FROM
                          (SELECT game_id FROM only_a UNION ALL SELECT game_id FROM only_b)
                          GROUP BY 1)
            SELECT (SELECT count(*) FROM common),
                   (SELECT count(*) FROM diff),
                   (SELECT count(*) FROM a), (SELECT count(*) FROM b),
                   (SELECT count(*) FROM only_a), (SELECT count(*) FROM only_b),
                   (SELECT sum(model_points) FROM a), (SELECT sum(model_points) FROM b),
                   (SELECT sum(abs(coalesce(pa, 0) - coalesce(pb, 0))) FROM
                      (SELECT game_id, sum(model_points) AS pa FROM a GROUP BY 1) FULL JOIN
                      (SELECT game_id, sum(model_points) AS pb FROM b GROUP BY 1) USING (game_id))
            """
        ).fetchone()
        assert per_game is not None
        common, differing, rows_a, rows_b, only_a, only_b, points_a, points_b, gap = per_game
        aligned = c.execute(
            """
            SELECT count(*), count(*) FILTER (a.offense = b.offense AND a.defense = b.defense
                                              AND a.model_points = b.model_points
                                              AND a.offense_team_id = b.offense_team_id)
            FROM a_row a JOIN b_row b USING (game_id, possession_seq)
            WHERE game_id IN (SELECT game_id FROM common)
            """
        ).fetchone()
        assert aligned is not None
    return {
        "games": games,
        "common_games": int(common),
        "common_games_identical_rows": int(common) - int(differing),
        "identical_game_share": (int(common) - int(differing)) / int(common) if common else None,
        "rows_v2": int(rows_a),
        "rows_v3": int(rows_b),
        "rows_only_v2": int(only_a),
        "rows_only_v3": int(only_b),
        "row_mismatch_share": (int(only_a) + int(only_b)) / (int(rows_a) + int(rows_b)),
        "points_v2": float(points_a or 0),
        "points_v3": float(points_b or 0),
        "points_abs_game_gap": float(gap or 0),
        "points_abs_game_gap_share": float(gap or 0) / float(points_a) if points_a else None,
        "aligned_rows": int(aligned[0]),
        "aligned_rows_identical": int(aligned[1]),
    }


FIELDS = (
    "EVENTMSGTYPE",
    "EVENTMSGACTIONTYPE",
    "PERIOD",
    "PCTIMESTRING",
    "HOMEDESCRIPTION",
    "VISITORDESCRIPTION",
    "NEUTRALDESCRIPTION",
    "PLAYER1_ID",
    "PLAYER1_TEAM_ID",
    "PLAYER2_ID",
    "PLAYER2_TEAM_ID",
    "PLAYER3_ID",
    "PLAYER3_TEAM_ID",
)

PLAYER_SLOTS = ("PLAYER1_ID", "PLAYER2_ID", "PLAYER3_ID")


def _normal(column: str, value: str) -> object:
    parsed = _v2_field(column, value)
    if isinstance(parsed, str):
        parsed = parsed.strip()
    return None if parsed in (None, 0, "") else parsed


def fallback_events(v3_path: Path) -> dict[str, int]:
    """V3 rows whose (actionType, subType) the table lacks, by pair and fallback code."""
    found: Counter[str] = Counter()
    for row in archive_rows(v3_path):
        key = (row["actionType"].strip(), row["subType"].strip())
        if key[0] and key not in ACTION_TYPES and key[0] not in SHOT_TYPES:
            found[f"{key} -> {fallback_code(*key, row['description'])}"] += 1
    return dict(sorted(found.items()))


def field_agreement(snapshot: Path, season: int) -> dict[str, Any]:
    """Event-level agreement of rebuilt rows with archived V2 rows of the same snapshot."""
    with duckdb.connect() as connection:
        games, players = box_scores(connection, snapshot)
    boxes = {
        g: (
            (b.home_id, b.away_id),
            b.home_id if b.home_designated else None,
            {p: box.team_id for p, box in players[g].items()},
        )
        for g, b in games.items()
    }
    issues: Counter[str] = Counter()
    events = Counter[str]()
    mismatches: Counter[str] = Counter()
    # Player slots by V2 event type, over events where either side names a player.
    slot_events: Counter[tuple[str, str]] = Counter()
    slot_mismatches: Counter[tuple[str, str]] = Counter()
    fallbacks: dict[str, dict[str, int]] = {}
    for suffix in ("", "_po"):
        fallbacks[suffix or "_regular"] = fallback_events(
            snapshot / f"nbastatsv3{suffix}_{season}.tar.xz"
        )
        real = dict(event_games(snapshot / f"nbastats{suffix}_{season}.tar.xz"))
        rebuilt = rebuilt_games(
            snapshot / f"nbastatsv3{suffix}_{season}.tar.xz",
            snapshot / f"cdnnba{suffix}_{season}.tar.xz",
            boxes,
        )
        for game_id, out in rebuilt:
            if game_id not in real:
                continue
            events["games"] += 1
            if isinstance(out, GameIssue):
                issues[out.code] += 1
                continue
            v2: dict[int, dict[str, str]] = {}
            for event in real[game_id]:
                v2.setdefault(int(event.fields["EVENTNUM"]), event.fields)
            v3 = {int(e.fields["EVENTNUM"]): e.fields for e in out}
            events["v2_only"] += len(v2.keys() - v3.keys())
            events["v3_only"] += len(v3.keys() - v2.keys())
            events["v2"] += len(v2)
            events["v3"] += len(v3)
            for number in v2.keys() & v3.keys():
                events["matched"] += 1
                kind = v2[number]["EVENTMSGTYPE"]
                for column in FIELDS:
                    left = _normal(column, v2[number][column])
                    right = _normal(column, v3[number][column])
                    if column in PLAYER_SLOTS and (left is not None or right is not None):
                        slot_events[kind, column] += 1
                        slot_mismatches[kind, column] += left != right
                    if left != right:
                        mismatches[column] += 1
    matched = events["matched"]
    by_type: dict[str, dict[str, dict[str, float | int]]] = {}
    for (kind, column), count in sorted(slot_events.items()):
        by_type.setdefault(kind, {})[column] = {
            "events": count,
            "agreement": 1 - slot_mismatches[kind, column] / count,
        }
    return {
        "games": events["games"],
        "rebuild_issues": dict(issues),
        "events_matched": matched,
        "events_v2_only": events["v2_only"],
        "events_v3_only": events["v3_only"],
        "events_v2": events["v2"],
        "events_v3": events["v3"],
        "events_v2_only_share": events["v2_only"] / events["v2"] if events["v2"] else None,
        "events_v3_only_share": events["v3_only"] / events["v3"] if events["v3"] else None,
        "field_agreement": {c: 1 - mismatches[c] / matched if matched else None for c in FIELDS},
        "player_agreement_by_type": by_type,
        "fallback_events": fallbacks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    rows = commands.add_parser("rows", help="compare two canonical row sets")
    rows.add_argument("v2_rows", type=Path)
    rows.add_argument("v3_rows", type=Path)
    fields = commands.add_parser("fields", help="compare rebuilt events with archived V2")
    fields.add_argument("snapshot", type=Path)
    fields.add_argument("--season", type=int, required=True)
    args = parser.parse_args()
    if args.action == "rows":
        result = compare(args.v2_rows, args.v3_rows)
    else:
        result = field_agreement(args.snapshot, args.season)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
