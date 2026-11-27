"""R1 v2 holdout plumbing (#42): guard, blocks, cold rating and strict verdict."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from bil.models import r1_holdout
from bil.models.r1_holdout import (
    COLD_RATING,
    LOG_LABEL,
    HoldoutLocked,
    _snapshot_dir,
    access_logged,
    box_logs,
    capture_holdout_logs,
    cuts,
    guard,
    strict_verdict,
    with_cold,
)
from bil.models.team_outcomes import Game, Snapshot, ridge_team_ratings


def game(day: date, playoff: bool = False, season: int = 2025) -> Game:
    return Game(
        "0042500101" if playoff else "0022500001", season, day, playoff, "1", "2", ("1", "2"), 3.0
    )


def test_guard_refuses_until_frozen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(r1_holdout, "R1_PROTOCOL_SHA256", None)
    with pytest.raises(HoldoutLocked):
        guard()
    with pytest.raises(HoldoutLocked):
        capture_holdout_logs(tmp_path)
    with pytest.raises(HoldoutLocked):
        box_logs(tmp_path, 2025, {"snapshot": "r1-v1", "sha256": "0" * 64})
    with pytest.raises(ValueError):
        box_logs(tmp_path, 2026, {"snapshot": "x", "sha256": "0" * 64})
    assert not any(tmp_path.iterdir())


def test_guard_rejects_a_wrong_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(r1_holdout, "R1_PROTOCOL_SHA256", "0" * 64)
    with pytest.raises(HoldoutLocked):
        guard()


def test_blocks_use_fixed_dates_and_the_first_playoff_day() -> None:
    games = [game(date(2025, 10, 21)), game(date(2026, 4, 25), True), game(date(2026, 4, 19), True)]
    blocks = cuts(2025, games)
    assert [(b.label, b.cutoff) for b in blocks] == [
        ("2025-R1", date(2025, 10, 1)),
        ("2025-R2", date(2025, 12, 1)),
        ("2025-R3", date(2026, 2, 1)),
        ("2025-R4", date(2026, 4, 1)),
        ("2025-P", date(2026, 4, 19)),
    ]
    assert len(cuts(2025, games[:1])) == 4


HEADER = "as_of,player_id,rating_total,window_possessions,box_history\n"


def test_cold_rating_is_fixed_and_checked(tmp_path: Path) -> None:
    snaps = [
        Snapshot(date(2025, 10, 1), {1: 2.0}, 0.0, "a"),
        Snapshot(date(2025, 12, 1), {}, -0.3757, "b"),
    ]
    path = tmp_path / "ratings.csv"
    path.write_text(HEADER + "2025-10-01,1,2.000000,500,True\n2025-12-01,9,-0.375704,0,False\n")
    assert [s.cold for s in with_cold(snaps, path)] == [COLD_RATING, COLD_RATING]
    path.write_text(HEADER + "2025-12-01,9,-0.400000,0,False\n")
    with pytest.raises(ValueError):
        with_cold(snaps, path)


def test_strict_verdict_needs_both_intervals() -> None:
    entry = {"rmse_delta": -0.2, "rmse_ci95_game": [-0.3, -0.1], "rmse_ci95_week": [-0.4, -0.05]}
    assert strict_verdict(entry, "rmse")["verdict"] == "ei_better"
    entry["rmse_ci95_week"] = [-0.4, 0.02]
    result = strict_verdict(entry, "rmse")
    assert result["verdict"] == "inconclusive" and result["interval_including_zero"] == ["week"]
    worse = {"rmse_delta": 0.2, "rmse_ci95_game": [0.1, 0.3], "rmse_ci95_week": [0.05, 0.4]}
    assert strict_verdict(worse, "rmse")["verdict"] == "ei_worse"


def test_snapshot_names_cannot_escape_their_season(tmp_path: Path) -> None:
    for name in ("../../2025-26/r1-v1", "a/b", ".hidden", ""):
        with pytest.raises(ValueError):
            _snapshot_dir(tmp_path, 2024, name)
    assert _snapshot_dir(tmp_path, 2024, "issue-52-v1") == tmp_path / "2024-25" / "issue-52-v1"


def test_access_log_needs_the_labelled_digest_line() -> None:
    digest = "ab" * 32
    assert access_logged(f"| x | {LOG_LABEL}{digest}\n", digest)
    assert not access_logged(f"some text mentioning {digest} in passing\n", digest)


def test_team_rating_ignores_same_day_and_later_margins() -> None:
    day = date(2026, 1, 10)
    history = [
        Game(f"00225000{i:02d}", 2025, date(2026, 1, i), False, "1", "2", ("1", "2"), m)
        for i, m in enumerate([5.0, -3.0, 8.0], start=7)
    ]
    later = [
        Game("0022500099", 2025, day, False, "1", "2", ("1", "2"), 40.0),
        Game("0022500098", 2025, date(2026, 1, 12), False, "2", "1", ("1", "2"), -25.0),
    ]
    base = ridge_team_ratings(history, day, ["1", "2"], 60.0, 4.0)
    assert ridge_team_ratings(history + later, day, ["1", "2"], 60.0, 4.0) == base
