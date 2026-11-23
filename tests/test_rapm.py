"""Mathematical checks for the synthetic offensive/defensive RAPM reference."""

from __future__ import annotations

from dataclasses import replace

import pytest

pytest.importorskip("numpy")
pytest.importorskip("scipy")

import numpy as np  # noqa: E402
from scipy.sparse import isspmatrix_csr  # noqa: E402

from bil.models.rapm import Possession, build_design, fit_rapm  # noqa: E402
from bil.models.rapm.synthetic import DEFENSE, INTERCEPT, OFFENSE, generate_possessions  # noqa: E402

ROW = Possession((5, 3, 1, 4, 2), (10, 8, 6, 9, 7), 1.27, 2)


def test_sparse_signs_units_and_roles() -> None:
    swap = Possession(ROW.defense, ROW.offense, 0)
    design = build_design([ROW, swap])
    assert isspmatrix_csr(design.matrix)
    assert design.matrix.nnz == 22
    assert design.player_ids == tuple(range(1, 11))
    np.testing.assert_array_equal(design.response, [127, 0])
    np.testing.assert_array_equal(design.weights, [2, 1])
    np.testing.assert_array_equal(
        design.matrix.toarray(),
        [
            [1] + [1] * 5 + [0] * 5 + [0] * 5 + [-1] * 5,
            [1] + [0] * 5 + [1] * 5 + [-1] * 5 + [0] * 5,
        ],
    )
    coefficients = np.zeros(21)
    coefficients[[0, 1, 11]] = [112, 7, 4]
    np.testing.assert_array_equal(design.matrix @ coefficients, [119, 108])


def test_recovers_known_effects_and_intercept() -> None:
    rows = generate_possessions(800, seed=6014)
    # A full rotation identifies all contrasts beyond the two block-level shifts.
    assert np.linalg.matrix_rank(build_design(rows).matrix.toarray()) == 23
    fit = fit_rapm(rows, ridge=1e-4)
    assert fit.intercept == pytest.approx(INTERCEPT, rel=0, abs=1e-6)
    assert fit.offense == pytest.approx(OFFENSE, rel=0, abs=2e-5)
    assert fit.defense == pytest.approx(DEFENSE, rel=0, abs=2e-5)
    assert sum(fit.offense.values()) == pytest.approx(0, abs=1e-12)
    assert sum(fit.defense.values()) == pytest.approx(0, abs=1e-12)


def test_matches_independent_dense_weighted_reference() -> None:
    rows = [
        replace(row, weight=(index % 5 + 1) / 3)
        for index, row in enumerate(generate_possessions(64, seed=721, noisy=True))
    ]
    fit = fit_rapm(rows, ridge=7.5)
    ids = sorted({player for row in rows for player in (*row.offense, *row.defense)})
    # Solve the small normal equations directly from indicator membership.
    indicators = np.array(
        [
            [1, *(p in row.offense for p in ids), *(-int(p in row.defense) for p in ids)]
            for row in rows
        ],
        dtype=float,
    )
    weights = np.array([row.weight for row in rows])
    response = np.array([100 * row.points for row in rows])
    penalty = np.diag([0.0] + [7.5] * (2 * len(ids)))
    expected = np.linalg.solve(
        indicators.T @ (weights[:, None] * indicators) + penalty,
        indicators.T @ (weights * response),
    )
    actual = np.array(
        [fit.intercept, *(fit.offense[p] for p in ids), *(fit.defense[p] for p in ids)]
    )
    np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-8)
    np.testing.assert_allclose(indicators @ actual, indicators @ expected, rtol=0, atol=1e-8)


@pytest.mark.parametrize("ridge", [1e4, 1e28])
def test_ridge_leaves_intercept_unpenalized(ridge: float) -> None:
    rows = [replace(ROW, points=0, weight=1), replace(ROW, points=2, weight=3)]
    fit = fit_rapm(rows, ridge=ridge)
    assert fit.intercept == pytest.approx(150, rel=0, abs=1e-8)
    np.testing.assert_allclose(
        list(fit.offense.values()) + list(fit.defense.values()), 0, atol=1e-8
    )


def test_rescaling_loss_and_penalty_preserves_the_fit() -> None:
    rows = generate_possessions(64, seed=721, noisy=True)
    fit = fit_rapm(rows, ridge=7.5)
    scaled = fit_rapm([replace(row, weight=1e-280) for row in rows], ridge=7.5e-280)
    assert scaled.intercept == pytest.approx(fit.intercept, rel=0, abs=1e-8)
    assert scaled.offense == pytest.approx(fit.offense, rel=0, abs=1e-8)
    assert scaled.defense == pytest.approx(fit.defense, rel=0, abs=1e-8)


def test_tiny_nonzero_response_preserves_relative_effects() -> None:
    rows = generate_possessions(100, seed=18)
    points_scale = 1e-190
    fit = fit_rapm(rows, ridge=0.01)
    scaled = fit_rapm([replace(row, points=row.points * points_scale) for row in rows], ridge=0.01)
    assert scaled.intercept / points_scale == pytest.approx(fit.intercept, rel=0, abs=1e-8)
    for player in fit.offense:
        assert scaled.offense[player] / points_scale == pytest.approx(
            fit.offense[player], rel=0, abs=1e-8
        )
        assert scaled.defense[player] / points_scale == pytest.approx(
            fit.defense[player], rel=0, abs=1e-8
        )


def test_aliased_players_share_each_ridge_coefficient() -> None:
    rows = generate_possessions(800, seed=6014, paired=True)
    fit = fit_rapm(rows, ridge=1e-4)
    assert OFFENSE[1] != OFFENSE[2] and DEFENSE[1] != DEFENSE[2]
    assert fit.offense[1] == pytest.approx(fit.offense[2], rel=0, abs=1e-10)
    assert fit.defense[1] == pytest.approx(fit.defense[2], rel=0, abs=1e-10)
    predictions = [
        fit.intercept
        + sum(fit.offense[p] for p in r.offense)
        - sum(fit.defense[p] for p in r.defense)
        for r in rows
    ]
    np.testing.assert_allclose(predictions, [100 * r.points for r in rows], atol=5e-5, rtol=0)


@pytest.mark.parametrize(
    "row",
    [
        replace(ROW, offense=(1, 1, 2, 3, 4)),
        replace(ROW, defense=(1, 7, 8, 9, 10)),
        replace(ROW, offense=(1, 2, 3, 4)),
        replace(ROW, defense=(0, 7, 8, 9, 10)),
        replace(ROW, points=-1),
        replace(ROW, points=float("nan")),
        replace(ROW, points=1e308),
        replace(ROW, weight=0),
        replace(ROW, weight=float("inf")),
    ],
)
def test_rejects_invalid_possessions(row: Possession) -> None:
    with pytest.raises(ValueError, match="possession 0"):
        build_design([row])


@pytest.mark.parametrize("ridge", [0, -1, float("inf"), float("nan")])
def test_requires_positive_finite_ridge(ridge: float) -> None:
    with pytest.raises(ValueError, match="ridge"):
        fit_rapm([ROW], ridge=ridge)


def test_requires_observations() -> None:
    with pytest.raises(ValueError, match="at least one"):
        fit_rapm([], ridge=1)
