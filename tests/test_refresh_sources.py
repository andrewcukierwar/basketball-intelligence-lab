"""Per-origin source-revision resolution (#143)."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from test_expected_impact import CUTOFF
from test_refresh import inputs as refresh_inputs

from bil.refresh import MANIFEST, SOURCES, RefreshError, refresh_origin
from bil.refresh_sources import (
    Capture,
    GameRecord,
    SourceError,
    box_capture,
    possession_captures,
    resolve,
)

A, B = "a" * 64, "b" * 64


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def capture(cid: str, when: datetime | None, **games: GameRecord) -> Capture:
    return Capture("box_logs/2023", cid, when, games)


def test_a_correction_available_after_the_origin_enters_only_later_origins() -> None:
    played = date(2024, 1, 3)
    first = capture("c1", at("2024-01-05T12:00:00"), g=GameRecord(played, A))
    fixed = capture("c2", at("2024-01-10T12:00:00"), g=GameRecord(played, B))
    before = resolve([first, fixed], date(2024, 1, 8), "strict_rolling")
    assert before.games == {"box_logs/2023:g": (1, A, "c1")}
    after = resolve([first, fixed], date(2024, 1, 11), "strict_rolling")
    assert after.games == {"box_logs/2023:g": (2, B, "c2")}
    assert after.summary()["games_on_a_later_revision"] == 1
    early = resolve([first, fixed], date(2024, 1, 5), "strict_rolling")
    assert early.games == {} and early.exclusions == {"available_at_or_after_cutoff": 1}
    # An unchanged later capture is not a new revision.
    same = capture("c3", at("2024-01-12T12:00:00"), g=GameRecord(played, B))
    assert resolve([first, fixed, same], date(2024, 1, 20), "strict_rolling").games == {
        "box_logs/2023:g": (2, B, "c2")
    }


def test_availability_must_be_strictly_before_the_eastern_midnight_cutoff() -> None:
    # Midnight Eastern at the start of 2024-01-05 is 05:00 UTC.
    on = capture("c1", at("2024-01-05T05:00:00"), g=GameRecord(date(2024, 1, 3), A))
    assert resolve([on], date(2024, 1, 5), "strict_rolling").games == {}
    assert resolve([on], date(2024, 1, 6), "strict_rolling").games != {}


def test_a_game_finishing_after_eastern_midnight_keeps_its_official_date() -> None:
    # Official date 3 January; it finished at 00:30 Eastern on 4 January and was captured at
    # 01:00 Eastern.
    late = GameRecord(date(2024, 1, 3), A, finalized_at=at("2024-01-04T05:30:00"))
    seen = capture("c1", at("2024-01-04T06:00:00"), g=late)
    next_day = resolve([seen], date(2024, 1, 4), "strict_rolling")
    assert next_day.games == {} and next_day.exclusions == {"available_at_or_after_cutoff": 1}
    # Origin 5 January: available, and dated by its official date, not its finish day.
    assert resolve([seen], date(2024, 1, 5), "strict_rolling").games == {
        "box_logs/2023:g": (1, A, "c1")
    }
    # With no recorded finish time, the capture instant bounds it, and the result is the same.
    bare = capture("c1", at("2024-01-04T06:00:00"), g=GameRecord(date(2024, 1, 3), A))
    assert resolve([bare], date(2024, 1, 4), "strict_rolling").games == {}
    # Same-day games never enter, whatever their availability.
    today = capture("c1", at("2024-01-03T06:00:00"), g=GameRecord(date(2024, 1, 4), A))
    assert resolve([today], date(2024, 1, 4), "strict_rolling").exclusions == {
        "same_or_later_played_date": 1
    }


def test_missing_or_ambiguous_times_refuse_the_game() -> None:
    played = date(2024, 1, 3)
    known = capture("c1", at("2024-01-04T12:00:00"), g=GameRecord(played, A))
    unknown = capture("c2", None, g=GameRecord(played, B))
    origin = date(2024, 1, 20)
    # A later capture with no time refuses the game, rather than falling back to revision 1.
    assert resolve([known, unknown], origin, "strict_rolling").exclusions == {
        "availability_unknown": 1
    }
    naive = capture("c1", datetime(2024, 1, 4, 12), g=GameRecord(played, A))
    assert resolve([naive], origin, "strict_rolling").exclusions == {"time_ambiguous": 1}
    after_capture = GameRecord(played, A, finalized_at=at("2024-01-05T00:00:00"))
    assert resolve(
        [capture("c1", at("2024-01-04T12:00:00"), g=after_capture)], origin, "strict_rolling"
    ).exclusions == {"time_ambiguous": 1}
    undated = capture("c1", at("2024-01-04T12:00:00"), g=GameRecord(None, A))
    assert resolve([undated], origin, "strict_rolling").exclusions == {"played_date_unknown": 1}
    moved = capture("c2", at("2024-01-06T12:00:00"), g=GameRecord(date(2024, 1, 2), B))
    assert resolve([known, moved], origin, "strict_rolling").exclusions == {
        "played_date_ambiguous": 1
    }


def test_captures_must_be_in_retrieval_order_and_modes_are_checked() -> None:
    first = capture("c1", at("2024-01-05T12:00:00"), g=GameRecord(date(2024, 1, 3), A))
    second = capture("c2", at("2024-01-04T12:00:00"), g=GameRecord(date(2024, 1, 3), B))
    with pytest.raises(SourceError, match="retrieval order"):
        resolve([first, second], date(2024, 1, 20), "strict_rolling")
    with pytest.raises(SourceError, match="exactly one pinned capture"):
        resolve([second, first], date(2024, 1, 20), "retrospective")
    with pytest.raises(SourceError, match="unknown"):
        resolve([first], date(2024, 1, 20), "hourly")  # type: ignore[arg-type]


def test_retrospective_resolution_uses_the_official_date_rule() -> None:
    pinned = capture(
        "pin",
        at("2024-07-01T00:00:00"),
        g1=GameRecord(date(2024, 1, 3), A),
        g2=GameRecord(date(2024, 1, 4), B),
        g3=GameRecord(None, B),
    )
    found = resolve([pinned], date(2024, 1, 4), "retrospective")
    assert found.games == {"box_logs/2023:g1": (1, A, "pin")}
    assert found.exclusions == {"same_or_later_played_date": 1, "played_date_unknown": 1}
    # Strict resolution of the same post-season pin selects nothing.
    assert resolve([pinned], date(2024, 1, 4), "strict_rolling").games == {}


def test_record_and_digest_depend_only_on_selected_revisions() -> None:
    played = date(2024, 1, 3)
    base = capture("c1", at("2024-01-04T12:00:00"), g=GameRecord(played, A))
    more = capture(
        "c1", at("2024-01-04T12:00:00"), g=GameRecord(played, A), h=GameRecord(date(2024, 2, 1), B)
    )
    one = resolve([base], date(2024, 1, 10), "strict_rolling")
    two = resolve([more], date(2024, 1, 10), "strict_rolling")
    assert one.digest() == two.digest() and one.exclusions != two.exclusions


def test_source_adapters_hash_each_game() -> None:
    base = refresh_inputs()
    box = base.logs[2021]
    [season] = possession_captures(base.analysis.rows, {"2021-22": "r" * 64})
    assert season.source == "possessions/2021-22" and season.capture_id == "r" * 64
    assert all(record.game_date is not None for record in season.games.values())
    plain = box_capture("box_logs/2021", "x", None, box)
    changed = box_capture(
        "box_logs/2021", "x", None, [replace(box[0], fga=box[0].fga + 1), *box[1:]]
    )
    diffs = [g for g in plain.games if plain.games[g] != changed.games[g]]
    assert diffs == [box[0].game_id]


def test_the_refresh_records_its_resolution_and_refuses_strict_mode(tmp_path: Path) -> None:
    done = refresh_origin(tmp_path, CUTOFF, refresh_inputs())
    manifest = json.loads((done.path / MANIFEST).read_text(encoding="utf-8"))
    sources = json.loads((done.path / SOURCES).read_text(encoding="utf-8"))
    summary = manifest["source_resolution"]
    assert summary["mode"] == "retrospective" and summary["games"] == len(sources["games"]) > 0
    assert manifest["inputs"]["source_resolution"] == summary["digest"]
    assert all(
        key.split(":")[0] in ("box_logs/2021", "possessions/2021-22") for key in sources["games"]
    )
    assert summary["exclusions"]["same_or_later_played_date"] > 0
    with pytest.raises(RefreshError, match="strict resolution"):
        refresh_origin(tmp_path, CUTOFF, replace(refresh_inputs(), mode="strict_rolling"))
