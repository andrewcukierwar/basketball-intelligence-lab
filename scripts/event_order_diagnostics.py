"""Classify event-order quarantines of a built season by defect pattern, and compare feeds.

Read-only over a pinned snapshot and a finished build. For every game it compares V2 file order
(clock sorted), archived V3 action order and, where the archive has ``ord``, data.nba.com entry
order. For the build's order-class quarantines it replays the pipeline offline to find where
the pinned parser failed, and optionally replays them with the opt-in order repair
(``--simulate-repair``; ADR-0023, proposed) without writing any build tables.

Output is aggregate only. ``--games-csv`` writes one private row per game for local inspection.

    PYTHONPATH=src python scripts/event_order_diagnostics.py SNAPSHOT_DIR BUILD_DIR \
        --report report.json --simulate-repair
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb

import bil.data.pilot as pilot
from bil.data.pilot_inputs import (
    GAME_PREFIXES,
    GameIssue,
    RawEvent,
    archive_rows,
    deduplicate_events,
    event_games,
    nba_game_id,
    v3_games,
)
from bil.data.pilot_order import clock_seconds, displaced_events, ord_sequence, repair_order
from bil.data.pilot_sources import (
    datanba_has_order,
    has_datanba,
    load_snapshot,
)

# Quarantine reasons that mean the event stream could not be ordered or repaired.
ORDER_REASONS = ("parser_error", "unsupported_reorder", "unresolved_event_order")
EVENT_TYPES = {
    "1": "made_shot",
    "2": "missed_shot",
    "3": "free_throw",
    "4": "rebound",
    "5": "turnover",
    "6": "foul",
    "7": "violation",
    "8": "substitution",
    "9": "timeout",
    "10": "jump_ball",
    "11": "ejection",
    "12": "period_start",
    "13": "period_end",
    "18": "instant_replay",
    "20": "stoppage",
}
PREVIOUS_EVENT = re.compile(r"previous event: <Stats(\w+) ")
SUFFIXES = {"regular": "", "playoffs": "_po"}


def type_name(event: RawEvent) -> str:
    code = event.fields["EVENTMSGTYPE"]
    return EVENT_TYPES.get(code, f"type_{code}")


def read_build(build: Path) -> dict[str, dict[str, Any]]:
    """Per-game review rows joined to game dates, from a finished build."""
    with duckdb.connect() as connection:
        rows = connection.execute(
            f"""select r.game_id, r.season_type, r.accepted, r.reason, s.observed_date
                from read_parquet('{build / "game_review.parquet"}') r
                join read_parquet('{build / "game_stream.parquet"}') s using (game_id)
                order by r.game_id"""
        ).fetchall()
    return {
        game_id: {"season_type": kind, "accepted": accepted, "reason": reason, "date": played}
        for game_id, kind, accepted, reason, played in rows
    }


def datanba_order(path: Path | None) -> dict[str, dict[int, int]]:
    """data.nba.com ``ord`` by game and V2 event number. Empty without an archive or field."""
    order: dict[str, dict[int, int]] = defaultdict(dict)
    for row in archive_rows(path) if path is not None else ():
        if row.get("ord", "").isdigit() and row["evt"].isdigit():
            order[nba_game_id(row["GAME_ID"])][int(row["evt"])] = int(row["ord"])
    return order


def descents(values: list[int]) -> int:
    return sum(later < earlier for earlier, later in zip(values, values[1:], strict=False))


def game_features(
    raw: dict[int, RawEvent], v3_order: list[int] | None, ord_map: dict[int, int]
) -> dict[str, Any]:
    """Order evidence for one game from V2, V3 and data.nba, with no parser involved."""
    numbers = list(raw)
    ends = {
        event.fields["PERIOD"]: event_num
        for event_num, event in raw.items()
        if event.fields["EVENTMSGTYPE"] == "13"
    }
    features: dict[str, Any] = {
        "v2_events": len(numbers),
        "v2_eventnum_descents": descents(numbers),
        "v2_clock_descents": 0,
        "v3_same_as_v2": v3_order == numbers if v3_order is not None else None,
        "ord_complete": False,
        "displaced": [],
        "displaced_types": [],
        "displaced_after_period_end_number": 0,
        "displaced_boundary": False,
        "shift_seconds": [],
    }
    previous = None
    for event in raw.values():
        key = int(event.fields["PERIOD"]), -clock_seconds(event.fields["PCTIMESTRING"])
        if previous is not None and key < previous and event.fields["EVENTMSGTYPE"] != "12":
            features["v2_clock_descents"] += 1
        previous = key
    sequence = ord_sequence(raw, ord_map)
    if sequence is None:
        return features
    features["ord_complete"] = True
    features["ord_same_as_v2"] = sequence == numbers
    displaced = displaced_events(raw, sequence)
    features["displaced"] = displaced
    features["displaced_types"] = [type_name(raw[n]) for n in displaced]
    features["displaced_boundary"] = any(
        raw[n].fields["EVENTMSGTYPE"] in ("12", "13") for n in displaced
    )
    features["displaced_after_period_end_number"] = sum(
        n > ends.get(raw[n].fields["PERIOD"], n) for n in displaced
    )
    # Seconds between a displaced clock and the clock of its predecessor in entry order.
    position = {n: index for index, n in enumerate(sequence)}
    shifts = []
    for n in displaced:
        index = position[n]
        if index:
            before = raw[sequence[index - 1]].fields["PCTIMESTRING"]
            shifts.append(clock_seconds(raw[n].fields["PCTIMESTRING"]) - clock_seconds(before))
    features["shift_seconds"] = shifts
    return features


class Replay:
    """Run the pipeline for chosen games, recording where the pinned parser failed."""

    def __init__(self) -> None:
        self.signature: dict[str, str] = {}
        self._parse = pilot.parse_game
        self._normalize = pilot.normalize_game

    def __enter__(self) -> Replay:
        pilot.parse_game = self._record_parse  # type: ignore[assignment]
        pilot.normalize_game = self._record_normalize  # type: ignore[assignment]
        return self

    def __exit__(self, *_: object) -> None:
        pilot.parse_game = self._parse
        pilot.normalize_game = self._normalize

    def _record_parse(self, game: Any, raw: dict[int, RawEvent], *args: Any, **kwargs: Any) -> Any:
        try:
            return self._parse(game, raw, *args, **kwargs)
        except GameIssue as error:
            cause = error.__cause__
            if error.code == "parser_error" and type(cause).__name__ == "EventOrderError":
                found = PREVIOUS_EVENT.search(str(cause))
                name = found.group(1).lower() if found else "unknown"
                self.signature.setdefault(game.game_id, f"rebound_after_{name}")
            elif error.code == "unresolved_event_order" and error.event_num is not None:
                self.signature.setdefault(game.game_id, "rebound_order_unresolved")
            else:
                self.signature.setdefault(game.game_id, f"{error.code}:{type(cause).__name__}")
            raise

    def _record_normalize(
        self, game: Any, roster: Any, raw: dict[int, RawEvent], *args: Any
    ) -> Any:
        try:
            return self._normalize(game, roster, raw, *args)
        except GameIssue as error:
            if error.code == "unsupported_reorder":
                parsed = [event.event_num for event in args[0]]
                moved = sorted(
                    {
                        type_name(raw[n])
                        for n, original in zip(parsed, raw, strict=False)
                        if n != original
                    }
                )
                self.signature.setdefault(game.game_id, "parser_moved_" + "+".join(moved))
            raise


def replay(
    snapshot: Path, chosen: set[str], order_repair: bool
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Rebuild only ``chosen`` games in memory. Returns each game's review row and signature."""
    manifest = load_snapshot(snapshot)
    year = manifest["season_start_year"]
    sources = {row["name"]: row for row in manifest["artifacts"]}
    reviews: dict[str, dict[str, Any]] = {}
    if not chosen:
        return reviews, {}
    with (
        Replay() as recorder,
        tempfile.TemporaryDirectory() as temp,
        duckdb.connect() as connection,
    ):
        games = pilot._season_games(
            connection,
            snapshot,
            sources,
            chosen,
            Path(temp),
            "diagnostic",
            "diagnostic",
            year,
            order_repair=order_repair,
        )
        for rows in games:
            review = rows["game_review"][0]
            reviews[review["game_id"]] = review
    return reviews, recorder.signature


def season_features(
    snapshot: Path,
) -> Iterator[tuple[str, dict[int, RawEvent], list[int] | None, dict[int, int]]]:
    manifest = load_snapshot(snapshot)
    year = manifest["season_start_year"]
    for kind, suffix in SUFFIXES.items():
        ord_map = datanba_order(
            snapshot / f"datanba{suffix}_{year}.tar.xz" if datanba_has_order(year) else None
        )
        v3 = v3_games(snapshot / f"nbastatsv3{suffix}_{year}.tar.xz")
        for game_id, events in event_games(snapshot / f"nbastats{suffix}_{year}.tar.xz"):
            if GAME_PREFIXES[game_id[:3]] == kind:
                reference = v3.get(game_id)
                yield (
                    game_id,
                    deduplicate_events(events),
                    reference.order if reference else None,
                    ord_map.get(game_id, {}),
                )


def repaired_games(build: Path) -> set[str]:
    """Accepted games that a ``--order-repair`` build marked with the ``datanba_event_order`` stratum."""
    with duckdb.connect() as connection:
        rows = connection.execute(
            f"""select game_id from read_parquet('{build / "game_review.parquet"}')
                where accepted and list_contains(strata, 'datanba_event_order')"""
        ).fetchall()
    return {game_id for (game_id,) in rows}


def shift_report(snapshot: Path, build: Path) -> dict[str, Any]:
    """Signed clock shifts the order repair gave late-entered events, from raw inputs alone.

    A positive shift moves the event later in game time. Shifts are recomputed by replaying
    ``repair_order`` on each repaired game's V2 events and data.nba order, which is deterministic.
    The repaired streams have monotone clocks, so the ``unsupported_reorder`` and
    ``unresolved_clock_reset`` checks cannot fire on the re-clocked events.
    """
    wanted = repaired_games(build)
    by_type: dict[str, list[float]] = defaultdict(list)
    actors: dict[str, int] = Counter()
    game_peaks: list[float] = []
    missing = 0
    for game_id, raw, _, ord_map in season_features(snapshot):
        if game_id not in wanted:
            continue
        repaired = repair_order(raw, ord_map)
        if repaired is None:
            missing += 1
            continue
        peak = 0.0
        for event_num, (_, _, shift) in repaired.clamped.items():
            by_type[type_name(raw[event_num])].append(shift)
            if raw[event_num].fields.get("PLAYER1_ID", "") not in ("", "0"):
                actors["events_with_actor"] += 1
                actors["actor_events_over_24s"] += abs(shift) > 24
            peak = max(peak, abs(shift))
        game_peaks.append(peak)
    every = sorted(shift for values in by_type.values() for shift in values)

    def median(values: list[float]) -> float:
        ordered = sorted(values)
        return ordered[len(ordered) // 2]

    return {
        "repaired_games": len(wanted),
        "not_reproduced": missing,
        "reclocked_events": len(every),
        "earlier_in_game_time": sum(shift < 0 for shift in every),
        "later_in_game_time": sum(shift > 0 for shift in every),
        "median_abs_shift_s": median([abs(shift) for shift in every]) if every else None,
        "largest_later_s": max(every, default=None),
        "largest_earlier_s": min(every, default=None),
        "events_over_24s": sum(abs(shift) > 24 for shift in every),
        "events_over_60s": sum(abs(shift) > 60 for shift in every),
        "games_with_a_shift_over_24s": sum(peak > 24 for peak in game_peaks),
        "games_with_a_shift_over_60s": sum(peak > 60 for peak in game_peaks),
        "largest_abs_shift_s": max(game_peaks, default=None),
        **dict(sorted(actors.items())),
        "by_event_type": {
            kind: {
                "events": len(values),
                "earlier": sum(shift < 0 for shift in values),
                "median_signed_s": median(values),
                "min_s": min(values),
                "max_s": max(values),
                "over_24s": sum(abs(shift) > 24 for shift in values),
            }
            for kind, values in sorted(by_type.items())
        },
    }


def share(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def week(day: Any) -> str:
    iso = day.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("snapshot", type=Path, help="pinned season snapshot directory")
    cli.add_argument("build", type=Path, help="finished build directory of that snapshot")
    cli.add_argument("--report", type=Path, help="write the aggregate JSON report here")
    cli.add_argument("--games-csv", type=Path, help="write per-game features (private) here")
    cli.add_argument(
        "--simulate-repair",
        action="store_true",
        help="replay the order-class quarantines with the opt-in data.nba order repair",
    )
    cli.add_argument(
        "--shifts",
        action="store_true",
        help="only report signed clock shifts for the games a --order-repair build repaired",
    )
    args = cli.parse_args()
    if args.shifts:
        text = json.dumps(shift_report(args.snapshot, args.build), indent=2, sort_keys=True)
        print(text)
        if args.report:
            args.report.write_text(text + "\n", encoding="utf-8")
        return

    manifest = load_snapshot(args.snapshot)
    year = manifest["season_start_year"]
    review = read_build(args.build)
    features: dict[str, dict[str, Any]] = {}
    for game_id, raw, v3_order, ord_map in season_features(args.snapshot):
        if game_id in review:
            features[game_id] = game_features(raw, v3_order, ord_map)

    order_class = {
        game_id
        for game_id, row in review.items()
        if not row["accepted"] and row["reason"] in ORDER_REASONS
    }
    original, signatures = replay(args.snapshot, order_class, order_repair=False)
    if any(original[g]["accepted"] for g in original):
        raise SystemExit("A quarantined game was accepted on replay; the build is not this code")
    repaired: dict[str, dict[str, Any]] = {}
    if args.simulate_repair:
        repaired, _ = replay(args.snapshot, order_class, order_repair=True)

    report: dict[str, Any] = {
        "season_start_year": year,
        "data_nba_pinned": has_datanba(year),
        "data_nba_has_ord": datanba_has_order(year),
    }
    by_type: dict[str, dict[str, Any]] = {}
    for kind in SUFFIXES:
        ids = [g for g, row in review.items() if row["season_type"] == kind]
        quarantined = [g for g in ids if not review[g]["accepted"]]
        by_type[kind] = {
            "games": len(ids),
            "quarantined": len(quarantined),
            "quarantine_reasons": dict(
                sorted(Counter(review[g]["reason"] for g in quarantined).items())
            ),
            "order_class_quarantines": sum(g in order_class for g in ids),
        }
    report["season_types"] = by_type

    patterns: dict[str, dict[str, Any]] = {}
    for game_id in sorted(order_class):
        row = review[game_id]
        key = f"{row['reason']} / {signatures.get(game_id, 'unknown')}"
        pattern = patterns.setdefault(
            key,
            {
                "games": 0,
                "v3_same_as_v2": 0,
                "ord_complete": 0,
                "with_displaced": 0,
                "recovered": 0,
            },
        )
        feature = features[game_id]
        pattern["games"] += 1
        pattern["v3_same_as_v2"] += bool(feature["v3_same_as_v2"])
        pattern["ord_complete"] += feature["ord_complete"]
        pattern["with_displaced"] += bool(feature["displaced"])
        pattern["recovered"] += bool(repaired.get(game_id, {}).get("accepted"))
    report["order_defect_patterns"] = dict(sorted(patterns.items()))

    def profile(ids: list[str]) -> dict[str, Any]:
        kinds: Counter[str] = Counter()
        shifts: list[float] = []
        for g in ids:
            kinds.update(features[g]["displaced_types"])
            shifts += [abs(s) for s in features[g]["shift_seconds"]]
        late = sum(features[g]["displaced_after_period_end_number"] for g in ids)
        displaced = sum(len(features[g]["displaced"]) for g in ids)
        return {
            "games": len(ids),
            "v2_clock_descents": sum(features[g]["v2_clock_descents"] for g in ids),
            "v2_eventnum_descents_per_game": round(
                sum(features[g]["v2_eventnum_descents"] for g in ids) / max(len(ids), 1), 2
            ),
            "v3_same_as_v2": sum(bool(features[g]["v3_same_as_v2"]) for g in ids),
            "ord_complete": sum(features[g]["ord_complete"] for g in ids),
            "games_with_displaced": sum(bool(features[g]["displaced"]) for g in ids),
            "displaced_events": displaced,
            "displaced_with_eventnum_after_period_end": late,
            "displaced_by_type": dict(sorted(kinds.items())),
            "displaced_boundary_games": sum(features[g]["displaced_boundary"] for g in ids),
            "median_abs_shift_s": sorted(shifts)[len(shifts) // 2] if shifts else None,
            "max_abs_shift_s": max(shifts, default=None),
        }

    regular = [g for g, row in review.items() if row["season_type"] == "regular"]
    report["feed_comparison"] = {
        "order_class_quarantines": profile(sorted(order_class)),
        "other_quarantines": profile(
            [g for g in regular if not review[g]["accepted"] and g not in order_class]
        ),
        "accepted_regular": profile([g for g in regular if review[g]["accepted"]]),
    }
    weeks: dict[str, Counter[str]] = defaultdict(Counter)
    for game_id in regular:
        bucket = weeks[week(review[game_id]["date"])]
        bucket["games"] += 1
        bucket["quarantined"] += not review[game_id]["accepted"]
        bucket["order_class_quarantines"] += game_id in order_class
        bucket["games_with_displaced"] += bool(features[game_id]["displaced"])
        bucket["displaced_events"] += len(features[game_id]["displaced"])
    report["regular_by_week"] = {name: dict(weeks[name]) for name in sorted(weeks)}
    if args.simulate_repair:
        outcomes = Counter(
            "recovered" if repaired[g]["accepted"] else f"still:{repaired[g]['reason']}"
            for g in sorted(order_class)
        )
        report["order_repair_simulation"] = {
            "replayed": len(order_class),
            "outcomes": dict(sorted(outcomes.items())),
        }

    text = json.dumps(report, indent=2, sort_keys=True, default=str)
    print(text)
    if args.report:
        args.report.write_text(text + "\n", encoding="utf-8")
    if args.games_csv:
        with args.games_csv.open("w", newline="", encoding="utf-8") as target:
            writer = csv.writer(target)
            writer.writerow(
                ["game_id", "season_type", "accepted", "reason", "signature", "displaced"]
            )
            for game_id, row in review.items():
                writer.writerow(
                    [
                        game_id,
                        row["season_type"],
                        row["accepted"],
                        row["reason"],
                        signatures.get(game_id, ""),
                        len(features[game_id]["displaced"]),
                    ]
                )


if __name__ == "__main__":
    main()
