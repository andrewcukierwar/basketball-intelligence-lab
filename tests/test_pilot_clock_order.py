"""Synthetic edge cases for the same-clock rebound rule (ADR-0028)."""

from __future__ import annotations

from bil.data.pilot_clock_order import ClockOrder, Declined, reorder_same_clock
from bil.data.pilot_inputs import RawEvent

A, B = "100", "200"


def ev(num: int, kind: int, clock: str, team: str = A, text: str = "", period: int = 1) -> RawEvent:
    fields = {
        "EVENTNUM": str(num),
        "EVENTMSGTYPE": str(kind),
        "PERIOD": str(period),
        "PCTIMESTRING": clock,
        "HOMEDESCRIPTION": text,
        "VISITORDESCRIPTION": "",
        "NEUTRALDESCRIPTION": "",
        "PLAYER1_ID": f"{num}9",
        "PLAYER1_TEAM_ID": team,
    }
    return RawEvent(fields, [num])


def stream(*events: RawEvent) -> dict[int, RawEvent]:
    return {int(e.fields["EVENTNUM"]): e for e in events}


def order(result: object) -> list[int]:
    assert isinstance(result, ClockOrder)
    return list(result.events)


def test_tip_in_attempt_entered_late_is_placed_before_the_second_rebound() -> None:
    raw = stream(
        ev(1, 2, "5:00", A, "MISS shot"),
        ev(2, 4, "4:58", A, "REBOUND"),
        ev(3, 4, "4:58", A, "REBOUND"),
        ev(9, 2, "4:58", A, "MISS tip"),
        ev(4, 1, "4:58", A, "tip made"),
    )
    result = reorder_same_clock(raw)
    assert order(result) == [1, 2, 9, 3, 4]
    assert isinstance(result, ClockOrder)
    assert result.moves == (("1", "4:58", 9, 3),)


def test_ordered_stream_and_and_one_need_no_change() -> None:
    raw = stream(
        ev(1, 1, "5:00", A, "made"),
        ev(2, 6, "5:00", B, "foul"),
        ev(3, 3, "5:00", A, "Free Throw 1 of 1"),
        ev(4, 2, "4:50", A, "MISS shot"),
        ev(5, 8, "4:50", A, "SUB"),
        ev(6, 4, "4:50", B, "REBOUND"),
    )
    assert reorder_same_clock(raw) is None


def test_missed_free_throw_is_a_valid_predecessor() -> None:
    raw = stream(ev(1, 3, "5:00", A, "MISS Free Throw 2 of 2"), ev(2, 4, "5:00", B, "REBOUND"))
    assert reorder_same_clock(raw) is None


def test_team_rebound_is_matched_by_its_team_identifier() -> None:
    team_rebound = ev(3, 4, "4:58", "", "Rebound")
    team_rebound.fields["PLAYER1_ID"] = A
    raw = stream(
        ev(1, 2, "5:00", A, "MISS shot"),
        ev(2, 4, "4:58", A, "REBOUND"),
        team_rebound,
        ev(9, 2, "4:58", A, "MISS tip"),
    )
    assert order(reorder_same_clock(raw)) == [1, 2, 9, 3]


def test_blocked_shot_counts_as_a_missed_field_goal() -> None:
    raw = stream(
        ev(1, 2, "5:00", A, "MISS shot BLOCK"),
        ev(2, 4, "4:58", B, "REBOUND"),
        ev(3, 4, "4:58", B, "REBOUND"),
        ev(9, 2, "4:58", B, "MISS putback BLOCK"),
    )
    assert order(reorder_same_clock(raw)) == [1, 2, 9, 3]


def test_shot_by_the_other_team_is_not_a_candidate_after_a_rebound() -> None:
    raw = stream(
        ev(1, 2, "5:00", A, "MISS"),
        ev(2, 4, "4:58", A, "REBOUND"),
        ev(3, 4, "4:58", A, "REBOUND"),
        ev(8, 2, "4:58", B, "MISS other team"),
        ev(9, 2, "4:58", A, "MISS tip"),
    )
    assert order(reorder_same_clock(raw)) == [1, 2, 9, 3, 8]


def test_candidates_of_two_teams_without_a_preceding_rebound_are_ambiguous() -> None:
    raw = stream(
        ev(1, 1, "5:00", A, "made"),
        ev(2, 4, "4:58", A, "REBOUND"),
        ev(8, 2, "4:58", B, "MISS"),
        ev(9, 2, "4:58", A, "MISS"),
    )
    result = reorder_same_clock(raw)
    assert result == Declined("ambiguous_team", "1", "4:58", 2)


def test_orphan_without_a_same_clock_miss_is_declined() -> None:
    raw = stream(ev(1, 1, "5:00", A, "made"), ev(2, 4, "4:58", A, "REBOUND"))
    assert reorder_same_clock(raw) == Declined("no_candidate", "1", "4:58", 2)


def test_period_end_shot_is_never_taken_from_beyond_the_period_boundary() -> None:
    raw = stream(
        ev(1, 2, "0:01", A, "MISS"),
        ev(2, 4, "0:00", A, "REBOUND"),
        ev(3, 4, "0:00", A, "REBOUND"),
        ev(4, 13, "0:00", A, "End of 1st Period"),
        ev(9, 2, "0:00", A, "MISS tip"),
    )
    assert reorder_same_clock(raw) == Declined("no_candidate", "1", "0:00", 3)


def test_period_end_tip_before_the_boundary_is_placed() -> None:
    raw = stream(
        ev(1, 2, "0:01", A, "MISS"),
        ev(2, 4, "0:00", A, "REBOUND"),
        ev(3, 4, "0:00", A, "REBOUND"),
        ev(9, 2, "0:00", A, "MISS tip"),
        ev(4, 13, "0:00", A, "End of 1st Period"),
    )
    assert order(reorder_same_clock(raw)) == [1, 2, 9, 3, 4]


def test_only_same_clock_events_move_and_the_result_is_deterministic() -> None:
    raw = stream(
        ev(0, 12, "12:00", A, "start"),
        ev(1, 2, "5:00", A, "MISS"),
        ev(2, 4, "4:58", A, "REBOUND"),
        ev(3, 4, "4:58", A, "REBOUND"),
        ev(9, 2, "4:58", A, "MISS tip"),
        ev(4, 2, "4:50", A, "MISS later"),
        ev(5, 4, "4:50", B, "REBOUND"),
    )
    first, second = reorder_same_clock(raw), reorder_same_clock(raw)
    assert first == second
    assert order(first) == [0, 1, 2, 9, 3, 4, 5]
    assert isinstance(first, ClockOrder)
    # Rows are the original objects: nothing is edited.
    assert all(first.events[num] is raw[num] for num in raw)


def test_substitution_between_miss_and_rebound_is_not_an_orphan() -> None:
    raw = stream(
        ev(1, 2, "5:00", A, "MISS"),
        ev(2, 8, "5:00", A, "SUB"),
        ev(3, 4, "5:00", B, "REBOUND"),
    )
    assert reorder_same_clock(raw) is None


def test_two_same_team_candidates_are_ambiguous_and_the_game_is_declined() -> None:
    raw = stream(
        ev(1, 2, "5:00", A, "MISS"),
        ev(2, 4, "4:58", A, "REBOUND"),
        ev(3, 4, "4:58", A, "REBOUND"),
        ev(9, 2, "4:58", A, "MISS tip late"),
        ev(7, 2, "4:58", A, "MISS tip early"),
    )
    assert reorder_same_clock(raw) == Declined("ambiguous_candidates", "1", "4:58", 3)


def test_rebound_after_a_jump_ball_that_follows_a_miss_is_not_an_orphan() -> None:
    raw = stream(
        ev(1, 2, "5:00", A, "MISS shot BLOCK"),
        ev(2, 10, "5:00", A, "Jump Ball"),
        ev(3, 4, "5:00", A, "REBOUND"),
    )
    assert reorder_same_clock(raw) is None


def test_rebound_after_a_jump_ball_without_a_miss_is_still_an_orphan() -> None:
    raw = stream(
        ev(1, 1, "5:00", A, "made"),
        ev(2, 10, "5:00", A, "Jump Ball"),
        ev(3, 4, "5:00", A, "REBOUND"),
    )
    assert reorder_same_clock(raw) == Declined("no_candidate", "1", "5:00", 3)


def test_a_miss_that_needs_its_own_rebound_is_not_reused() -> None:
    raw = stream(
        ev(1, 2, "5:00", A, "MISS"),
        ev(2, 4, "4:58", A, "REBOUND"),
        ev(3, 4, "4:58", A, "REBOUND"),
        ev(4, 4, "4:58", A, "REBOUND"),
        ev(9, 2, "4:58", A, "MISS tip"),
    )
    assert reorder_same_clock(raw) == Declined("no_candidate", "1", "4:58", 4)


def test_a_candidate_without_a_team_is_ambiguous_with_a_teamed_candidate() -> None:
    blank = ev(8, 2, "4:58", "", "MISS")
    blank.fields["PLAYER1_ID"] = ""
    raw = stream(
        ev(1, 1, "5:00", A, "made"),
        ev(2, 4, "4:58", A, "REBOUND"),
        blank,
        ev(9, 2, "4:58", A, "MISS"),
    )
    assert reorder_same_clock(raw) == Declined("ambiguous_team", "1", "4:58", 2)
