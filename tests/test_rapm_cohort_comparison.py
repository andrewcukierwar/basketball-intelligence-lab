"""Synthetic checks for the row-set variant comparison on a common held-out cohort."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from bil.models.rapm.baseline import Observation, Scored
from bil.models.rapm.cohort_comparison import check_aligned, check_nested, compare
from bil.models.rapm.reference import Possession

DATES = [
    date(2022, 12, 1),
    date(2023, 1, 1),
    date(2023, 2, 1),
    date(2023, 3, 1),
    date(2023, 4, 1),
]


def _rows() -> tuple[list[Observation], dict[int, tuple[str, int, int]]]:
    rng = np.random.default_rng(7)
    observations: list[Observation] = []
    keys: dict[int, tuple[str, int, int]] = {}
    for game, played in enumerate(DATES * 2):
        for seq in range(12):
            players = rng.permutation(10) + 1
            obs = Observation(
                f"g{game}",
                "T1",
                "regular",
                Possession(
                    tuple(int(p) for p in players[:5]),
                    tuple(int(p) for p in players[5:]),
                    float(rng.integers(0, 4)),
                    1.0,
                    played,
                ),
            )
            observations.append(obs)
            keys[id(obs)] = (f"g{game}", 1, seq)
    return observations, keys


def _subset(
    loaded: tuple[list[Observation], dict[int, tuple[str, int, int]]], drop: set[int]
) -> tuple[list[Observation], dict[int, tuple[str, int, int]]]:
    observations, keys = loaded
    kept = [o for o in observations if keys[id(o)][2] not in drop]
    return kept, {id(o): keys[id(o)] for o in kept}


def test_variants_are_scored_on_identical_common_rows() -> None:
    full = _rows()
    loaded = {
        "canonical": full,
        "period_end_start": _subset(full, {0}),
        "no_action": _subset(full, {0, 1}),
    }
    results = compare(loaded)
    primary = results["primary_common_canonical_cohort"]
    assert len(set(primary["possessions"].values())) == 1
    assert primary["possessions"]["canonical"] == 8 * 12
    secondary = results["secondary_common_no_action_cohort"]
    assert secondary["possessions"]["canonical"] == 8 * 10
    own = results["tertiary_own_cohort"]["possessions"]
    assert own["canonical"] > own["period_end_start"] > own["no_action"]
    for name in ("period_end_start", "no_action"):
        assert f"model_{name}_minus_canonical" in primary
    # The canonical fit scored on the canonical cohort is the zero-context baseline itself.
    assert primary["canonical"]["mse_model"] == pytest.approx(
        results["tertiary_own_cohort"]["canonical"]["mse_model"]
    )


def test_nesting_guard_rejects_a_variant_with_extra_rows() -> None:
    cohorts = {
        "canonical": {("g", 1, 1), ("g", 1, 2)},
        "period_end_start": {("g", 1, 1), ("g", 1, 3)},
        "no_action": {("g", 1, 1)},
    }
    with pytest.raises(ValueError, match="nested"):
        check_nested(cohorts)


def test_alignment_guard_rejects_different_rows() -> None:
    def scored(y: list[float], game: list[int]) -> Scored:
        arr = np.array(y)
        index = np.array(game, dtype=np.int64)
        flag = np.zeros(arr.size, dtype=bool)
        return Scored(arr, arr, arr, arr, arr, index, index, flag)

    check_aligned(scored([1.0, 2.0], [0, 1]), scored([1.0, 2.0], [0, 1]))
    with pytest.raises(ValueError, match="aligned"):
        check_aligned(scored([1.0, 2.0], [0, 1]), scored([1.0, 3.0], [0, 1]))
