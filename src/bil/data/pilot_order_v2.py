"""Safeguarded data.nba event-order repair ``order-repair-v2`` (ADR-0029, proposed).

Version 1 (``pilot_order``) gave every displaced event its predecessor's clock without a bound.
Version 2 implements the maintainer conditions of 2026-11-24 recorded in ADR-0023. It never
mutates a raw record, and the build keeps the original clock of every modified event in the
modification log.

Rules, applied per period to a failed game's V2 events and the archived data.nba ``ord`` order:

1. Instant replays (type 18) and timeouts (type 9) are non-substantive metadata. They are left out
   of the order solve, never re-clocked and never anchor another event. They are merged back by
   their own original clock after the substantive events are placed.
2. The substantive events (everything else, including period boundaries) are placed in ``ord``
   order. The longest non-increasing run of clocks, earliest entered on ties, keeps its clocks.
   Every other event is re-clocked to the valid clock nearest its original clock that lies between
   its kept neighbours (and not later in the stream than the event before it). A displaced period
   boundary event declines the repair.
3. A substantive event may move at most 24 s. A larger correction rejects the repair, the game
   keeps its original quarantine, and the proposed corrections are logged. Nothing is truncated.
   The ceiling bounds the damage a wrong correction can do. It does not validate a correction.
4. Every moved shot, free throw, turnover, rebound and substitution needs corroboration. Either
   archived V3 action order agrees with ``ord`` on where the event sits between its nearest
   unmoved neighbours present in V3, or (rebounds only) the event follows a missed shot or free
   throw in ``ord`` order, skipping substitutions, timeouts and replays. Without it the repair
   is declined.
5. Every moved event is logged: original and corrected clock, signed shift, justification and
   evidence source. Declined games log what they would have changed.

Because the corrected clocks are monotone by construction, ``unsupported_reorder`` and
``unresolved_clock_reset`` cannot fire on moved events. Every hard reconciliation still runs on the
repaired stream.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from bil.data.pilot_inputs import RawEvent
from bil.data.pilot_order import _kept_positions, clock_seconds, ord_sequence
from bil.data.pilot_sources import sha256_file

VERSION = "order-repair-v2"
CEILING_SECONDS = 24.0
PERIOD_START, PERIOD_END = "12", "13"
SHOT, MISS, FREE_THROW, REBOUND, TURNOVER, SUBSTITUTION = "1", "2", "3", "4", "5", "8"
TIMEOUT, REPLAY = "9", "18"
# Left out of the order solve: they have no lineup, score or possession effect.
NON_SUBSTANTIVE = frozenset({TIMEOUT, REPLAY})
# Moves of these types can change possession attribution or lineup exposure.
CORROBORATED_TYPES = frozenset({SHOT, MISS, FREE_THROW, REBOUND, TURNOVER, SUBSTITUTION})
_SKIPPED_BETWEEN_MISS_AND_REBOUND = frozenset({SUBSTITUTION, TIMEOUT, REPLAY})

EVIDENCE_V3 = "data.nba ord + V3 action order"
EVIDENCE_REBOUND = "data.nba ord + rebound follows a missed shot"
EVIDENCE_ORD = "data.nba ord only (type needs no corroboration)"


@dataclass(frozen=True)
class Modification:
    event_num: int
    event_type: str
    period: int
    original_clock: str
    corrected_clock: str
    # Seconds of game time the event moved later (positive) or earlier (negative).
    shift_seconds: float
    justification: str
    evidence: str


@dataclass(frozen=True)
class RepairedV2:
    events: dict[int, RawEvent]
    modifications: list[Modification]
    # Replays and timeouts left out of the solve, with their clocks unchanged.
    metadata_events: int


@dataclass(frozen=True)
class DeclinedV2:
    reason: str
    detail: str
    period: int | None = None
    event_num: int | None = None
    # What the repair would have changed, logged even though it was rejected.
    proposed: list[Modification] = field(default_factory=list)


def _stable_positions(v2_index: list[int], numbers: list[int]) -> set[int]:
    """Positions of the longest ``ord`` subsequence whose V2 order is unchanged.

    Ties prefer the earliest-entered events (lowest event numbers), as in ``_kept_positions``.
    """
    count = len(v2_index)
    best: list[tuple[int, int]] = []
    previous = [-1] * count
    for position in range(count):
        best.append((1, -numbers[position]))
        for before in range(position):
            if v2_index[before] < v2_index[position]:
                length, weight = best[before]
                candidate = (length + 1, weight - numbers[position])
                if candidate > best[position]:
                    best[position] = candidate
                    previous[position] = before
    if not count:
        return set()
    end = max(range(count), key=lambda position: (best[position], -position))
    stable: set[int] = set()
    while end != -1:
        stable.add(end)
        end = previous[end]
    return stable


def _is_miss(event: RawEvent) -> bool:
    kind = event.fields["EVENTMSGTYPE"]
    if kind == MISS:
        return True
    text = event.fields.get("HOMEDESCRIPTION", "") + event.fields.get("VISITORDESCRIPTION", "")
    return kind == FREE_THROW and "MISS " in text


def _follows_miss(raw: dict[int, RawEvent], ordered: list[int], position: int) -> bool:
    for before in reversed(ordered[:position]):
        kind = raw[before].fields["EVENTMSGTYPE"]
        if kind in _SKIPPED_BETWEEN_MISS_AND_REBOUND:
            continue
        return _is_miss(raw[before])
    return False


def _v3_agrees(
    event_num: int, ordered: list[int], position: int, moved: set[int], v3: dict[int, int]
) -> bool:
    """V3 order puts the event between its nearest unmoved ``ord`` neighbours that V3 lists."""
    if event_num not in v3:
        return False
    anchors_before = [n for n in reversed(ordered[:position]) if n not in moved and n in v3]
    anchors_after = [n for n in ordered[position + 1 :] if n not in moved and n in v3]
    if not anchors_before and not anchors_after:
        return False
    if anchors_before and v3[anchors_before[0]] > v3[event_num]:
        return False
    return not (anchors_after and v3[anchors_after[0]] < v3[event_num])


def repair_order_v2(
    raw: dict[int, RawEvent], order: dict[int, int], v3_order: list[int] | None
) -> RepairedV2 | DeclinedV2 | None:
    """Reorder and re-clock a failed game's events under the v2 safeguards.

    Returns None when ``ord`` agrees with the V2 stream and nothing needs repair, and a
    ``DeclinedV2`` when a safeguard refuses the repair.
    """
    sequence = ord_sequence(raw, order)
    if sequence is None:
        return DeclinedV2("incomplete_entry_order", "ord is missing, tied or not period-monotone")
    v3 = {event_num: index for index, event_num in enumerate(v3_order or [])}
    v2_index = {event_num: index for index, event_num in enumerate(raw)}
    by_period: dict[int, list[int]] = {}
    for event_num in sequence:
        by_period.setdefault(int(raw[event_num].fields["PERIOD"]), []).append(event_num)

    placed: dict[int, RawEvent] = {}
    modifications: list[Modification] = []
    metadata = 0
    problems: list[DeclinedV2] = []
    for period, numbers in by_period.items():
        meta = [n for n in numbers if raw[n].fields["EVENTMSGTYPE"] in NON_SUBSTANTIVE]
        ordered = [n for n in numbers if n not in meta]
        metadata += len(meta)
        clocks = [clock_seconds(raw[n].fields["PCTIMESTRING"]) for n in ordered]
        kept = _kept_positions(clocks, ordered)
        stable = _stable_positions([v2_index[n] for n in ordered], ordered)
        # Events whose relative order changed, or whose clock breaks the kept run.
        moved_positions = {p for p in range(len(ordered)) if p not in kept or p not in stable}
        moved = {ordered[p] for p in moved_positions}
        assigned: list[float] = []
        texts: list[str] = []
        for position, event_num in enumerate(ordered):
            source = raw[event_num]
            if position in kept:
                assigned.append(clocks[position])
                texts.append(source.fields["PCTIMESTRING"])
                continue
            kind = source.fields["EVENTMSGTYPE"]
            if position == 0 or kind in (PERIOD_START, PERIOD_END):
                problems.append(
                    DeclinedV2(
                        "boundary_event_displaced",
                        f"period {period} event {event_num} (type {kind}) would be re-clocked",
                        period,
                        event_num,
                    )
                )
                assigned.append(clocks[position])
                texts.append(source.fields["PCTIMESTRING"])
                continue
            later = [p for p in range(position + 1, len(ordered)) if p in kept]
            floor = clocks[later[0]] if later else 0.0
            candidates = [
                (clocks[position], source.fields["PCTIMESTRING"]),
                (floor, raw[ordered[later[0]]].fields["PCTIMESTRING"] if later else "0:00"),
            ]
            value, text = max(candidates, key=lambda pair: pair[0])
            if value > assigned[-1]:
                value, text = assigned[-1], texts[-1]
            assigned.append(value)
            texts.append(text)
        for position in sorted(moved_positions):
            event_num = ordered[position]
            source = raw[event_num]
            kind = source.fields["EVENTMSGTYPE"]
            original = source.fields["PCTIMESTRING"]
            corrected = texts[position]
            shift = clocks[position] - assigned[position]
            if kind not in CORROBORATED_TYPES:
                evidence = EVIDENCE_ORD
            elif _v3_agrees(event_num, ordered, position, moved, v3):
                evidence = EVIDENCE_V3
            elif kind == REBOUND and _follows_miss(raw, ordered, position):
                evidence = EVIDENCE_REBOUND
            else:
                evidence = ""
            reason = (
                "clock breaks the kept non-increasing run; placed at the nearest valid "
                "neighbouring clock"
                if position not in kept and shift
                else "entered in a different order than the V2 clock sort"
            )
            modification = Modification(
                event_num, kind, period, original, corrected, shift, reason, evidence or "none"
            )
            modifications.append(modification)
            if abs(shift) > CEILING_SECONDS:
                problems.append(
                    DeclinedV2(
                        "shift_over_ceiling",
                        f"period {period} event {event_num} (type {kind}) would move {shift:+g} s",
                        period,
                        event_num,
                    )
                )
            if not evidence:
                problems.append(
                    DeclinedV2(
                        "uncorroborated",
                        f"period {period} event {event_num} (type {kind}) has no V3 or "
                        "semantic corroboration",
                        period,
                        event_num,
                    )
                )
        final = _merge_metadata(raw, ordered, assigned, texts, meta, v2_index)
        for event_num, clock in final:
            source = raw[event_num]
            if clock == source.fields["PCTIMESTRING"]:
                placed[event_num] = source
            else:
                fields = dict(source.fields)
                fields["PCTIMESTRING"] = clock
                placed[event_num] = RawEvent(fields, list(source.row_numbers))
    if not modifications and list(placed) == list(raw):
        return None
    if problems:
        first = problems[0]
        reasons = sorted({p.reason for p in problems})
        return DeclinedV2(
            first.reason,
            f"{len(problems)} problems ({', '.join(reasons)}); first: {first.detail}",
            first.period,
            first.event_num,
            modifications,
        )
    return RepairedV2(placed, modifications, metadata)


def _merge_metadata(
    raw: dict[int, RawEvent],
    ordered: list[int],
    assigned: list[float],
    texts: list[str],
    meta: list[int],
    v2_index: dict[int, int],
) -> list[tuple[int, str]]:
    """Return (event number, clock text) for one period with replays and timeouts merged back."""
    final = list(zip(ordered, texts, strict=True))
    seconds = list(assigned)
    for event_num in sorted(meta, key=v2_index.__getitem__):
        clock = clock_seconds(raw[event_num].fields["PCTIMESTRING"])
        index = len(final)
        for candidate, (other, _) in enumerate(final):
            if seconds[candidate] < clock or (
                seconds[candidate] == clock and v2_index[other] > v2_index[event_num]
            ):
                index = candidate
                break
        final.insert(index, (event_num, raw[event_num].fields["PCTIMESTRING"]))
        seconds.insert(index, clock)
    return final


LOG_COLUMNS = (
    "game_id",
    "outcome",
    "reason",
    "event_num",
    "event_type",
    "period",
    "original_clock",
    "corrected_clock",
    "shift_s",
    "justification",
    "evidence",
)
_MOD_KEYS = LOG_COLUMNS[3:]
LOG_FILENAME = "order_repair_v2_log.csv"


def write_order_repair_log(
    connection: duckdb.DuckDBPyConnection, output: Path
) -> dict[str, object]:
    """Write every modification (applied, declined or rejected) to a CSV and summarize it."""
    cursor = connection.execute(
        "SELECT game_id, detail FROM read_parquet(?) "
        "WHERE code IN ('order_repair_v2_applied', 'order_repair_v2_declined', "
        "'order_repair_v2_rejected') ORDER BY game_id, issue_seq",
        [str(output / "quality_issue.parquet")],
    )
    games: dict[str, tuple[str, str]] = {}
    rows: list[list[object]] = []
    for game_id, detail in cursor.fetchall():
        record = json.loads(detail)
        games[game_id] = (record["outcome"], record["reason"])
        for mod in record["modifications"] or [None]:
            tail: list[object] = [""] * len(_MOD_KEYS)
            if mod is not None:
                tail = [mod[key] for key in _MOD_KEYS]
            rows.append([game_id, record["outcome"], record["reason"], *tail])
    path = output / LOG_FILENAME
    with path.open("x", newline="", encoding="utf-8") as target:
        writer = csv.writer(target)
        writer.writerow(LOG_COLUMNS)
        writer.writerows(rows)
    applied = [row for row in rows if row[1] == "applied"]
    shifts = sorted(abs(float(str(row[8]))) for row in applied)
    return {
        "version": VERSION,
        "ceiling_seconds": CEILING_SECONDS,
        "log": {"filename": LOG_FILENAME, "sha256": sha256_file(path), "rows": len(rows)},
        "games": dict(Counter(outcome for outcome, _ in games.values())),
        "decline_reasons": dict(
            Counter(reason.split(":")[0] for _, reason in games.values() if reason)
        ),
        "applied_modifications": len(applied),
        "applied_by_type": dict(Counter(str(row[4]) for row in applied)),
        "applied_largest_abs_shift_s": shifts[-1] if shifts else None,
        "applied_median_abs_shift_s": shifts[len(shifts) // 2] if shifts else None,
    }
