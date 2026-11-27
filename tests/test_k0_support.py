"""Development K0 comparisons keep games disjoint and require common lineup support."""

from pathlib import Path

import numpy as np
from test_rapm_targets import synthetic

from bil.data.pilot_sources import sha256_file
from bil.models.k0_support import (
    fit_season,
    lineup_slots,
    outcome_slices,
    schedule_blocks,
    supported_contrasts,
)
from bil.models.rapm.multiseason import build_matrix


def test_schedule_and_frozen_outcomes_use_disjoint_games(tmp_path: Path) -> None:
    rows, teams, _ = synthetic((2021,), possessions=48)
    partitions = schedule_blocks(rows, 2021)
    groups = [set(rows.game[index]) for index in partitions.values()]
    assert sum(map(len, groups)) == len(set.union(*groups))
    assert sum(len(i) for i in partitions.values()) == int((~rows.playoff).sum())
    assert rows.day[partitions["candidate"]].max() < rows.day[partitions["repeat"]].min()
    assert rows.day[partitions["proxy"]].max() < rows.day[partitions["repeat"]].min()
    assert rows.day[partitions["repeat"]].max() < rows.day[partitions["outcome"]].min()

    design = build_matrix(rows.offense, rows.defense)
    report, index, predictions, _, minimum = fit_season(rows, design, teams, 2021, tmp_path)
    assert set(report["roles"]) == {"offense", "defense"}
    assert minimum.shape == index.shape
    assert np.array_equal(index, partitions["outcome"])
    prediction_path = tmp_path / "predictions_2021.npz"
    assert report["predictions_sha256"] == sha256_file(prediction_path)
    slices = outcome_slices(rows, index, teams, predictions, minimum)
    assert slices["all"]["possessions"] == index.size
    assert (
        slices["all_ten_250"]["possessions"] + slices["any_below_250"]["possessions"] == index.size
    )
    with np.load(prediction_path) as frozen:
        assert np.array_equal(frozen["possession_seq"], rows.possession_seq[index])
        assert np.array_equal(frozen["points_per_100"], np.column_stack(list(predictions.values())))


def test_matched_contrast_requires_same_nine_and_two_games_in_each_block() -> None:
    lineups = np.repeat([[1, 3, 4, 5, 6], [2, 3, 4, 5, 6]], 15, axis=0)
    opposition = np.tile([11, 12, 13, 14, 15], (30, 1))
    games = np.tile(np.repeat([1, 2], [7, 8]), 2)
    earlier = lineup_slots(lineups, opposition, games)
    later = lineup_slots(lineups[:, ::-1], opposition[:, ::-1], games + 2)
    assert [(p, q) for p, q, _, _ in supported_contrasts(earlier, later)] == [(1, 2)]

    single_game = lineup_slots(lineups, opposition, np.ones(30, dtype=np.int64))
    assert supported_contrasts(earlier, single_game) == []
    opposition[:, -1] = 16
    changed_opponent = lineup_slots(lineups, opposition, games + 2)
    assert supported_contrasts(earlier, changed_opponent) == []
