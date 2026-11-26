"""Apply the registered #133 limits to the saved validation outputs (#133).

The limits are those of docs/research/v3-event-path-protocol.md §4. Every input is a file the
validation runs already wrote. Nothing is rebuilt or refitted, and the verdict follows from the
files alone.

    python scripts/v3_event_verdict.py QUALITY_DIR MODEL_CHECK.json OUT.json \
        --season 2023-24 COMPARE.json FIELDS.json --season 2024-25 COMPARE.json FIELDS.json
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

# Registered limits (protocol §4).
MIN_GAMES = {"regular": 15, "playoffs": 3}  # L3: V3 accepted games at least V2 minus this,
# and at most this many games accepted by V2 alone
MAX_ROW_MISMATCH = 0.005  # L4
MAX_POINTS_GAP = 0.005  # L5: summed absolute per-game points gap over V2 points
CORE_FIELDS = ("EVENTMSGTYPE", "EVENTMSGACTIONTYPE", "PERIOD", "PCTIMESTRING", "PLAYER1_TEAM_ID")
MIN_CORE_AGREEMENT = 0.995  # L6a
MIN_SLOT_EVENTS = 200  # L6b: player slots by V2 type with at least this many events
MIN_SLOT_AGREEMENT = 0.99  # L6b
MAX_UNMATCHED_EVENTS = 0.001  # L6c: V2-only and V3-only event shares
MAX_DELTA_CHANGE = 0.5  # L7, (points per 100)^2
PRIMARY = "rapm_context"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def season_limits(
    season: str, quality: list[dict[str, str]], compare: Any, fields: Any
) -> dict[str, dict[str, Any]]:
    [row] = [r for r in quality if r["season"] == season]
    if row["invariants_failed"] == "":
        raise SystemExit("season_quality ran without --run-checks; L1 cannot be read")
    results: dict[str, dict[str, Any]] = {
        "L1": {"invariants_failed": int(row["invariants_failed"])},
        "L2": {"hard_failures": row["hard_failures"]},
    }
    results["L1"]["pass"] = results["L1"]["invariants_failed"] == 0
    results["L2"]["pass"] = row["hard_failures"] == ""
    games = compare["games"]
    results["L3"] = {
        kind: {key: games[kind][key] for key in ("v2", "v3", "v2_only")} for kind in MIN_GAMES
    }
    results["L3"]["pass"] = all(
        games[kind]["v3"] >= games[kind]["v2"] - allowed and games[kind]["v2_only"] <= allowed
        for kind, allowed in MIN_GAMES.items()
    )
    share = compare["row_mismatch_share"]
    results["L4"] = {"row_mismatch_share": share, "pass": share <= MAX_ROW_MISMATCH}
    gap = compare["points_abs_game_gap_share"]
    results["L5"] = {"points_abs_game_gap_share": gap, "pass": gap <= MAX_POINTS_GAP}
    core = {c: fields["field_agreement"][c] for c in CORE_FIELDS}
    slots = {
        f"{kind}/{slot}": value
        for kind, by_slot in fields["player_agreement_by_type"].items()
        for slot, value in by_slot.items()
        if value["events"] >= MIN_SLOT_EVENTS
    }
    unmatched = {
        "v2_only": fields["events_v2_only_share"],
        "v3_only": fields["events_v3_only_share"],
    }
    results["L6"] = {
        "core": core,
        "slots": slots,
        "unmatched": unmatched,
        "pass": all(v >= MIN_CORE_AGREEMENT for v in core.values())
        and all(v["agreement"] >= MIN_SLOT_AGREEMENT for v in slots.values())
        and all(v <= MAX_UNMATCHED_EVENTS for v in unmatched.values()),
    }
    return results


def model_limit(check: Any) -> dict[str, Any]:
    primary = check["comparators"][PRIMARY]
    change = primary["delta_change"]
    intervals = [primary["v3"]["ci95_game"], primary["v3"]["ci95_week"]]
    excludes = all(low > 0 or high < 0 for low, high in intervals)
    same = check["verdicts_v3"] == check["verdicts_issue_36_v1"]
    return {
        "delta_change": change,
        "intervals": intervals,
        "intervals_exclude_zero": excludes,
        "verdicts_unchanged": same,
        "pass": abs(change) <= MAX_DELTA_CHANGE and excludes and same,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("quality", type=Path, help="season_quality output directory")
    parser.add_argument("model_check", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--season", nargs=3, action="append", required=True, metavar=("LABEL", "ROWS", "FIELDS")
    )
    args = parser.parse_args()
    quality = _rows(args.quality / "m1_classification.csv")
    verdict: dict[str, Any] = {
        "seasons": {
            label: season_limits(label, quality, _load(Path(rows)), _load(Path(fields)))
            for label, rows, fields in args.season
        },
        "L7": model_limit(_load(args.model_check)),
    }
    verdict["pass"] = verdict["L7"]["pass"] and all(
        limit["pass"] for season in verdict["seasons"].values() for limit in season.values()
    )
    args.output.write_text(json.dumps(verdict, indent=2, sort_keys=True))
    for label, season in verdict["seasons"].items():
        print(
            label, " ".join(f"{key}={'pass' if v['pass'] else 'FAIL'}" for key, v in season.items())
        )
    print(f"L7={'pass' if verdict['L7']['pass'] else 'FAIL'}")
    print("ALL PASS" if verdict["pass"] else "FAIL")


if __name__ == "__main__":
    main()
