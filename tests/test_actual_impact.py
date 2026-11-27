"""Actual impact estimates exclude the entire scored game from the season fit."""

from dataclasses import replace

import numpy as np
from test_rapm_targets import synthetic

from bil.models.actual_impact import FOLDS, VERSION, heldout_predictions, scores
from bil.models.rapm.multiseason import build_matrix
from bil.models.rapm.targets import game_folds


def test_heldout_game_outcomes_do_not_change_their_own_predictions() -> None:
    rows, _, _ = synthetic((2023,), step=3, possessions=32)
    design = build_matrix(rows.offense, rows.defense)
    anchor = np.zeros(2 * design.size)
    selected = game_folds(rows.game_ids, FOLDS, VERSION)[rows.game] == 0
    index, original, audit = heldout_predictions(rows, design, 2023, anchor)
    outcome = rows.y.copy()
    outcome[selected] += 100.0
    changed, predictions, _ = heldout_predictions(replace(rows, y=outcome), design, 2023, anchor)
    assert len(audit) == FOLDS
    np.testing.assert_array_equal(changed, index)
    for name in original:
        np.testing.assert_array_equal(
            predictions[name][selected[index]], original[name][selected[index]]
        )
    np.testing.assert_array_equal(original["season_only"], original["uniform_anchor"])
    metrics = scores(rows, index, original)
    assert metrics["regular"]["possessions"] + metrics["playoffs"]["possessions"] == index.size
