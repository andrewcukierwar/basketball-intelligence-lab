"""R1 v2 quality gate on the pinned 2025–26 box logs (#42 protocol §4.3, option A).

The gate's "box-feature build" is the unchanged #29 contract validation,
``load_appearances(season_start_year=2025)``, reached through the guarded ``box_logs``. It
refuses duplicate keys, unreciprocated team rows, disagreeing dates or home flags, and
count-identity violations. The #62 view builder is hard-wired to 2022–23 and is not run (see the
access log's pre-parse clarification). Coverage needs at least 97% of the 1,230 scheduled
regular-season games, each with two reciprocal team rows and player rows for both sides.
Warnings are reported only. No margin, score or rating is printed.

    python scripts/r1_gate.py data/raw data/processed/r1/holdout-gate
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

import duckdb

from bil.features.box_build import TEAM_LOG
from bil.models.r1_holdout import (
    HOLDOUT_SEASON,
    R1_PROTOCOL_SHA256,
    box_logs,
    guard,
    season_pins,
)
from bil.models.team_outcomes import team_games

SCHEDULED_REGULAR = 1230
MIN_COVERAGE = 0.97
MINUTES_TOLERANCE = 1.0


def gate(raw: Path, season: int = HOLDOUT_SEASON) -> dict[str, Any]:
    """The holdout gate; an earlier season only checks this script on non-holdout logs."""
    pin = season_pins(season)[season]
    if season == HOLDOUT_SEASON:
        guard()  # a locked guard is a refusal, not a gate result
    try:
        rows, profile, directory = box_logs(raw, season, pin)  # contract checks
    except (ValueError, KeyError, OSError, duckdb.Error) as exc:
        return {"box_feature_build": "failed", "error": repr(exc), "pass": False}
    games, counts = team_games(directory, season)  # warnings and playoff count only
    with duckdb.connect() as connection:
        team_rows = connection.execute(
            "SELECT game_id, team_id, opp_team_id, game_date, min FROM read_parquet(?) "
            "WHERE left(game_id, 3) IN ('002', '004')",
            [str(directory / TEAM_LOG)],
        ).fetchall()
    by_game: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    for row in team_rows:
        by_game[str(row[0])].append(row)
    sides: dict[str, set[str]] = defaultdict(set)
    minutes: dict[tuple[str, str], float] = defaultdict(float)
    for r in rows:
        sides[r.game_id].add(r.team_id)
        minutes[(r.game_id, r.team_id)] += r.minutes_ms / 60000

    covered, off_minutes = 0, 0
    # Coverage reads only team ids, opponents, dates and player sides: no score column.
    for game_id, pair in by_game.items():
        if not game_id.startswith("002") or len(pair) != 2:
            continue
        a, b = pair
        teams = {str(a[1]), str(b[1])}
        reciprocal = (
            len(teams) == 2 and str(a[2]) == str(b[1]) and str(b[2]) == str(a[1]) and a[3] == b[3]
        )
        if reciprocal and sides[game_id] == teams:
            covered += 1
    for game_id, pair in by_game.items():
        for _, team_id, _, _, game_minutes in pair:
            if game_minutes is None:
                continue
            overtimes = max(0, round((float(game_minutes) - 48.0) / 5.0))
            expected = 240.0 + 25.0 * overtimes
            if abs(minutes.get((game_id, str(team_id)), 0.0) - expected) > MINUTES_TOLERANCE:
                off_minutes += 1

    share = covered / SCHEDULED_REGULAR
    return {
        "protocol_sha256": R1_PROTOCOL_SHA256,
        "snapshot": pin,
        "box_feature_build": "completes (load_appearances contract validation)",
        "contract_profile": profile,
        "appearances": len(rows),
        "regular_games_covered": covered,
        "scheduled_regular_games": SCHEDULED_REGULAR,
        "regular_coverage": share,
        "min_regular_coverage": MIN_COVERAGE,
        "playoff_games": sum(g.playoff for g in games),
        "team_log_counts": counts,
        "warnings": {
            "minutes_off_by_more_than_1": off_minutes,
            "excluded_no_single_home_team": counts["unflagged_home"],
        },
        "pass": share >= MIN_COVERAGE,
    }


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("raw", type=Path)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite a gate run: {args.output}")
    result = gate(args.raw.resolve())
    args.output.mkdir(mode=0o700, parents=True)
    result["code_commit"] = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    path = args.output / "gate.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
