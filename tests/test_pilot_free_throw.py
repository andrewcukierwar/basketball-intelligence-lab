"""Checks for the pinned V2 missed-free-throw evidence rule."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

pytest.importorskip("duckdb")
pytest.importorskip("pbpstats")

from bil.data.pilot import build_pilot  # noqa: E402
from bil.data.pilot_check import check_build  # noqa: E402
from bil.data.pilot_free_throw import infer_missing_misses  # noqa: E402
from bil.data.pilot_inputs import GameBox, PlayerBox, RawEvent  # noqa: E402

GAME = GameBox("0022209999", date(2022, 10, 20), 100, 200, 50, 45)


def event(
    number: int, kind: str, action: str, person: str, team: str, description: str, score: str = ""
) -> RawEvent:
    return RawEvent(
        {
            "EVENTMSGTYPE": kind,
            "EVENTMSGACTIONTYPE": action,
            "PLAYER1_ID": person,
            "PLAYER1_TEAM_ID": team,
            "HOMEDESCRIPTION": description,
            "VISITORDESCRIPTION": "",
            "NEUTRALDESCRIPTION": "",
            "SCORE": score,
            "PERIOD": "3",
            "PCTIMESTRING": "4:19",
        },
        [number + 1],
    )


def final_attempt() -> dict[int, RawEvent]:
    return {
        0: event(0, "1", "1", "12", "100", "Made shot", "34 - 40"),
        1: event(1, "3", "11", "11", "100", "Player Free Throw 1 of 2 (5 PTS)", "34 - 41"),
        2: event(2, "3", "12", "11", "100", "Free Throw 2 of 2"),
        3: event(3, "4", "1", "200", "", ""),
    }


def test_missing_marker_uses_box_totals_and_preserves_raw_bytes() -> None:
    raw = final_attempt()
    result = infer_missing_misses(raw, GAME, {11: PlayerBox(100, 1000, 1, 1, 2)})
    assert result is not None
    assert [(miss.shot, miss.rebound) for miss in result.misses] == [(2, 3)]
    assert result.box_totals == ((11, 1, 2),)
    parser_rows = result.parser_events(raw)
    assert list(parser_rows) == list(raw)
    assert parser_rows[2].fields["HOMEDESCRIPTION"] == "MISS Free Throw 2 of 2"
    assert parser_rows[2].row_numbers == raw[2].row_numbers
    assert raw[2].fields["HOMEDESCRIPTION"] == "Free Throw 2 of 2"


@pytest.mark.parametrize(
    ("number", "field", "value"),
    [
        (2, "SCORE", "34 - 42"),
        (2, "HOMEDESCRIPTION", "Player Free Throw 2 of 2"),
        (2, "VISITORDESCRIPTION", "Opposing description"),
        (3, "PLAYER1_ID", "22"),
        (3, "PLAYER1_TEAM_ID", "100"),
        (3, "PCTIMESTRING", "4:18"),
        (3, "PERIOD", "4"),
        (3, "EVENTMSGACTIONTYPE", "17"),
        (3, "SCORE", "34 - 42"),
    ],
)
def test_conflicting_local_evidence_does_not_change_the_feed(
    number: int, field: str, value: str
) -> None:
    raw = final_attempt()
    raw[number].fields[field] = value
    assert infer_missing_misses(raw, GAME, {11: PlayerBox(100, 1000, 1, 1, 2)}) is None


@pytest.mark.parametrize(
    "box", [PlayerBox(100, 1000, 1), PlayerBox(100, 1000, 1, 2, 2), PlayerBox(100, 1000, 1, 1, 3)]
)
def test_unknown_or_inconsistent_box_counts_are_declined(box: PlayerBox) -> None:
    assert infer_missing_misses(final_attempt(), GAME, {11: box}) is None


@pytest.mark.parametrize("score", ["34 - 40", "35 - 40", "34 - 42", "bad"])
def test_shooters_other_make_needs_exactly_one_point_on_its_side(score: str) -> None:
    raw = final_attempt()
    raw[1].fields["SCORE"] = score
    assert infer_missing_misses(raw, GAME, {11: PlayerBox(100, 1000, 1, 1, 2)}) is None


def test_competing_same_clock_field_goal_miss_is_declined() -> None:
    raw = final_attempt()
    raw[4] = event(4, "2", "1", "12", "100", "MISS Shot")
    assert infer_missing_misses(raw, GAME, {11: PlayerBox(100, 1000, 1, 1, 2)}) is None


def test_intermediate_attempt_needs_same_team_and_continuing_trip() -> None:
    raw = {
        0: event(0, "1", "1", "12", "100", "Made shot", "34 - 40"),
        1: event(1, "3", "11", "11", "100", "Free Throw 1 of 2"),
        2: event(2, "4", "1", "100", "", ""),
        3: event(3, "3", "12", "11", "100", "Player Free Throw 2 of 2 (5 PTS)", "34 - 41"),
    }
    roster = {11: PlayerBox(100, 1000, 1, 1, 2)}
    assert infer_missing_misses(raw, GAME, roster) is not None
    raw[2].fields["PLAYER1_ID"] = "200"
    assert infer_missing_misses(raw, GAME, roster) is None
    raw[2].fields["PLAYER1_ID"] = "100"
    raw[3].fields["PCTIMESTRING"] = "4:18"
    assert infer_missing_misses(raw, GAME, roster) is None


def test_archived_retry_keeps_scores_and_links_the_missing_marker(tmp_path: Path) -> None:
    value = os.environ.get("BIL_PILOT_FT_SNAPSHOT")
    if value is None:
        pytest.skip("Set BIL_PILOT_FT_SNAPSHOT to the private 2010–11 issue-90-v1 snapshot")
    snapshot = Path(value)
    game = {"0021000044"}
    before = build_pilot(snapshot, tmp_path / "before", "0" * 40, game, same_clock_rule=True)
    target = tmp_path / "after"
    after = build_pilot(
        snapshot, target, "0" * 40, game, same_clock_rule=True, free_throw_miss_rule=True
    )
    assert before["coverage"]["regular"]["accepted"] == 0
    assert after["coverage"]["regular"]["accepted"] == 1
    assert after["free_throw_miss_rule"]["games"][0]["code"] == "free_throw_miss"
    assert "FT 356 -> team rebound 357" in after["free_throw_miss_rule"]["games"][0]["detail"]
    assert not any(check_build(target, snapshot).values())
