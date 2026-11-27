"""Refresh-cadence plans, gap criterion and game scoring (#129)."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from bil.models.refresh_cadence import (
    CONTRASTS,
    closes_gap,
    cutoffs,
    latest,
    score_games,
)
from bil.models.team_outcomes import Game

BLOCKS = [
    date(2023, 10, 1),
    date(2023, 12, 1),
    date(2024, 2, 1),
    date(2024, 4, 1),
    date(2024, 4, 20),
]
DAYS = [date(2023, 10, 24) + timedelta(days=i) for i in range(0, 220, 2)]


def test_cadence_plans() -> None:
    assert cutoffs("block", 2023, BLOCKS, DAYS) == BLOCKS
    weekly = cutoffs("weekly", 2023, BLOCKS, DAYS)
    assert weekly[0] == date(2023, 10, 1) and all(d.weekday() == 0 for d in weekly[1:])
    assert weekly[1] == date(2023, 10, 2) and max(weekly) <= max(DAYS)
    assert all(b - a == timedelta(days=7) for a, b in zip(weekly[1:], weekly[2:], strict=False))
    daily = cutoffs("daily", 2023, BLOCKS, DAYS)
    assert daily == [date(2023, 10, 1), *DAYS] == cutoffs("daily_box", 2023, BLOCKS, DAYS)
    with pytest.raises(ValueError, match="unknown"):
        cutoffs("hourly", 2023, BLOCKS, DAYS)


def test_latest_never_uses_a_later_refresh() -> None:
    assert latest(BLOCKS, date(2023, 12, 1)) == date(2023, 12, 1)
    assert latest(BLOCKS, date(2023, 11, 30)) == date(2023, 10, 1)
    with pytest.raises(ValueError, match="no refresh"):
        latest(BLOCKS, date(2023, 9, 30))


def test_gap_criterion() -> None:
    better = {"rmse": "ei_better", "log_loss": "inconclusive"}
    worse = {"rmse": "ei_worse", "log_loss": "ei_worse"}
    flat = {"rmse": "inconclusive", "log_loss": "inconclusive"}
    assert closes_gap({"daily_vs_block": better, "daily_vs_team_daily": flat}, "daily")
    assert not closes_gap({"daily_vs_block": better, "daily_vs_team_daily": worse}, "daily")
    assert not closes_gap({"daily_vs_block": flat, "daily_vs_team_daily": flat}, "daily")


def test_score_games_reports_every_contrast_and_verdict() -> None:
    rng = np.random.default_rng(1)
    games = [
        Game(
            f"g{i}",
            2023 + i % 2,
            date(2023, 11, 1) + timedelta(days=i),
            False,
            "1",
            "2",
            ("1", "2"),
            float(m),
        )
        for i, m in enumerate(rng.normal(2, 12, 200).round())
    ]
    margin = np.asarray([g.margin for g in games])
    names = {n for pair in CONTRASTS.values() for n in pair}
    preds = {}
    for k, name in enumerate(sorted(names)):
        guess = margin * 0.3 + rng.normal(0, 1 + k, margin.size)
        preds[name] = (guess, np.clip(0.5 + guess / 40, 0.01, 0.99))
    out = score_games(games, preds, (2023, 2024))
    assert set(out["verdicts"]) == set(CONTRASTS)
    assert set(out["regular"]["pooled"]["contrasts"]) == set(CONTRASTS)
    assert out["regular"]["pooled"]["ei_daily"]["games"] == 200
    assert "playoffs" in out and out["playoffs"] == {}
