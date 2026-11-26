"""Compare a V3-event build of a season with its V2-event build (#133).

Both inputs are canonical RAPM row sets (``bil.data.rapm_rows``) built from pilot builds of
the same source snapshot. The comparison reads only model rows and game reconciliation:
accepted-game agreement, and in games both accept, possession-row identity on the fields the
models use (period, offense team, both lineups and points).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import duckdb

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
                   (SELECT sum(model_points) FROM a), (SELECT sum(model_points) FROM b)
            """
        ).fetchone()
        assert per_game is not None
        common, differing, rows_a, rows_b, only_a, only_b, points_a, points_b = per_game
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
        "aligned_rows": int(aligned[0]),
        "aligned_rows_identical": int(aligned[1]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("v2_rows", type=Path)
    parser.add_argument("v3_rows", type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(args.v2_rows, args.v3_rows), indent=2))


if __name__ == "__main__":
    main()
