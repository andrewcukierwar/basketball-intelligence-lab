"""Synthetic weighted-oracle checks for prior-centered RAPM."""

from __future__ import annotations

from dataclasses import replace

import pytest

pytest.importorskip("numpy")
pytest.importorskip("scipy")

import numpy as np  # noqa: E402

from bil.models.rapm import Possession, fit_prior_rapm, fit_rapm  # noqa: E402
from bil.models.rapm.synthetic import generate_possessions  # noqa: E402

OFFENSE_PRIOR = {1: 15, 2: -12, 3: 4, 4: 8}
DEFENSE_PRIOR = {1: -7, 2: 13, 4: -2, 6: 6}


def weighted_rows(*, paired=False):
    return [
        replace(row, weight=(index % 5 + 1) / 3)
        for index, row in enumerate(generate_possessions(64, seed=721, noisy=True, paired=paired))
    ]


def dense_system(rows):
    ids = sorted({player for row in rows for player in (*row.offense, *row.defense)})
    matrix = np.array(
        [[1, *(p in r.offense for p in ids), *(-int(p in r.defense) for p in ids)] for r in rows],
        dtype=float,
    )
    root_weights = np.sqrt([row.weight for row in rows])
    response = np.array([100 * row.points for row in rows])
    return ids, matrix, root_weights, response


def coefficients(fit, ids):
    return np.array([fit.intercept, *(fit.offense[p] for p in ids), *(fit.defense[p] for p in ids)])


def priors_and_penalties(ids, offense_ridge, defense_ridge):
    prior = np.array(
        [0, *(OFFENSE_PRIOR.get(p, 0) for p in ids), *(DEFENSE_PRIOR.get(p, 0) for p in ids)]
    )
    penalty_rows = np.diag(np.sqrt(np.repeat([offense_ridge, defense_ridge], len(ids))))
    return prior, penalty_rows


def assert_dense_agreement(rows, offense_ridge, defense_ridge):
    ids, matrix, root_weights, response = dense_system(rows)
    prior, penalty = priors_and_penalties(ids, offense_ridge, defense_ridge)
    # Independent augmented dense least squares, with the intercept column left in
    # the observation block and omitted from the role penalties.
    augmented = np.vstack([root_weights[:, None] * matrix, np.pad(penalty, ((0, 0), (1, 0)))])
    target = np.concatenate([root_weights * response, penalty @ prior[1:]])
    expected = np.linalg.lstsq(augmented, target, rcond=None)[0]
    actual = coefficients(
        fit_prior_rapm(
            rows,
            offense_ridge=offense_ridge,
            defense_ridge=defense_ridge,
            offense_prior=OFFENSE_PRIOR,
            defense_prior=DEFENSE_PRIOR,
        ),
        ids,
    )
    np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-8)
    np.testing.assert_allclose(matrix @ actual, matrix @ expected, rtol=0, atol=1e-8)
    np.testing.assert_allclose(
        [(actual - prior)[1 : len(ids) + 1].sum(), (actual - prior)[len(ids) + 1 :].sum()],
        0,
        rtol=0,
        atol=1e-12,
    )
    return np.max(np.abs(actual - expected)), np.max(np.abs(matrix @ actual - matrix @ expected))


def test_nonzero_role_priors_match_weighted_dense_oracle():
    coefficients_delta, rates_delta = assert_dense_agreement(
        weighted_rows(), offense_ridge=7.5, defense_ridge=62.5
    )
    print(f"max absolute coefficient delta {coefficients_delta:.4e}")
    print(f"max absolute fitted rate delta {rates_delta:.4e}")


@pytest.mark.parametrize("prior", [None, {1: 0.0, 3: -0.0, 99: 10.0}])
def test_exact_zero_priors_match_existing_shared_penalty_fit(prior):
    rows = weighted_rows()
    assert fit_prior_rapm(
        rows, offense_ridge=7.5, defense_ridge=7.5, offense_prior=prior, defense_prior=prior
    ) == fit_rapm(rows, ridge=7.5)


def test_missing_priors_are_zero_and_empty_role_columns_retain_their_priors():
    row = Possession((1, 2, 3, 4, 5), (6, 7, 8, 9, 10), points=2)
    fit = fit_prior_rapm(
        [row],
        offense_ridge=1.5,
        defense_ridge=8.0,
        offense_prior={1: 9, 6: 1.23456789, 11: 7},
        defense_prior={6: -3, 1: -9.8765432109, 11: 99},
    )
    assert fit.offense == pytest.approx(
        {1: 9, 6: 1.23456789, **dict.fromkeys([2, 3, 4, 5, 7, 8, 9, 10], 0)}
    )
    assert fit.defense == pytest.approx(
        {1: -9.8765432109, 6: -3, **dict.fromkeys([2, 3, 4, 5, 7, 8, 9, 10], 0)}
    )
    assert fit.offense[6] == 1.23456789
    assert fit.defense[1] == -9.8765432109
    # With constant lineups the free intercept fits every point and the role
    # penalties alone determine the coefficients.
    assert fit.intercept == pytest.approx(200 - 9 - 3)


@pytest.mark.parametrize("role", ["offense", "defense"])
def test_stronger_penalty_pulls_its_role_toward_the_supplied_prior(role):
    rows = weighted_rows()
    weak = fit_prior_rapm(
        rows,
        offense_ridge=7.5,
        defense_ridge=7.5,
        offense_prior=OFFENSE_PRIOR,
        defense_prior=DEFENSE_PRIOR,
    )
    stronger_penalties = {"offense_ridge": 7.5, "defense_ridge": 7.5, f"{role}_ridge": 1000.0}
    strong = fit_prior_rapm(
        rows, **stronger_penalties, offense_prior=OFFENSE_PRIOR, defense_prior=DEFENSE_PRIOR
    )
    prior = OFFENSE_PRIOR if role == "offense" else DEFENSE_PRIOR
    weak_deviation = [estimate - prior.get(p, 0) for p, estimate in getattr(weak, role).items()]
    strong_deviation = [estimate - prior.get(p, 0) for p, estimate in getattr(strong, role).items()]
    assert np.linalg.norm(strong_deviation) < np.linalg.norm(weak_deviation)


@pytest.mark.parametrize("scale", [1e-190, 3.0, 1e190])
def test_scaling_points_and_priors_scales_the_fit(scale):
    rows = weighted_rows()
    fit = fit_prior_rapm(
        rows,
        offense_ridge=7.5,
        defense_ridge=62.5,
        offense_prior=OFFENSE_PRIOR,
        defense_prior=DEFENSE_PRIOR,
    )
    scaled = fit_prior_rapm(
        [replace(row, points=scale * row.points) for row in rows],
        offense_ridge=7.5,
        defense_ridge=62.5,
        offense_prior={p: value * scale for p, value in OFFENSE_PRIOR.items()},
        defense_prior={p: value * scale for p, value in DEFENSE_PRIOR.items()},
    )
    ids = sorted(fit.offense)
    np.testing.assert_allclose(
        coefficients(scaled, ids) / scale, coefficients(fit, ids), rtol=0, atol=1e-8
    )


def test_extreme_penalty_in_one_role_does_not_mask_the_fitted_role():
    rows = weighted_rows()
    ids, matrix, root_weights, response = dense_system(rows)
    prior, _ = priors_and_penalties(ids, 7.5, 1e280)
    # The extreme defense penalty fixes that block to its prior at float64 precision.
    off_design = matrix[:, : len(ids) + 1]
    adjusted_response = response - matrix[:, len(ids) + 1 :] @ prior[len(ids) + 1 :]
    off_penalty = np.pad(np.sqrt(7.5) * np.eye(len(ids)), ((0, 0), (1, 0)))
    expected = np.linalg.lstsq(
        np.vstack([root_weights[:, None] * off_design, off_penalty]),
        np.concatenate([root_weights * adjusted_response, off_penalty @ prior[: len(ids) + 1]]),
        rcond=None,
    )[0]
    fit = fit_prior_rapm(
        rows,
        offense_ridge=7.5,
        defense_ridge=1e280,
        offense_prior=OFFENSE_PRIOR,
        defense_prior=DEFENSE_PRIOR,
    )
    np.testing.assert_allclose(coefficients(fit, ids)[: len(ids) + 1], expected, rtol=0, atol=1e-8)
    assert fit.defense == pytest.approx({p: DEFENSE_PRIOR.get(p, 0) for p in ids}, abs=1e-12)


def test_paired_rotation_conditioning():
    rows = weighted_rows(paired=True)
    ids, matrix, root_weights, _ = dense_system(rows)
    players = matrix[:, 1:]
    centered = players - np.average(players, axis=0, weights=root_weights**2)

    conditions = []
    for offense, defense in ((0.01, 0.08), (30.0, 70.0), (1600.0, 400.0)):
        _, penalty = priors_and_penalties(ids, offense, defense)
        condition = float(np.linalg.cond(np.vstack([root_weights[:, None] * centered, penalty])))
        conditions.append(condition)
        assert_dense_agreement(rows, offense, defense)
        print(f"offense ridge {offense:g} | defense ridge {defense:g} | condition {condition:.4f}")
    assert conditions[0] > conditions[1] > conditions[2]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"offense_ridge": 0.0}, "offense_ridge"),
        ({"defense_ridge": -3.0}, "defense_ridge"),
        ({"offense_ridge": float("nan")}, "offense_ridge"),
        ({"defense_ridge": float("inf")}, "defense_ridge"),
        ({"offense_prior": {0: 2}}, "positive integers"),
        ({"defense_prior": {99: float("inf")}}, "must be finite"),
        ({"defense_prior": {2: float("nan")}}, "must be finite"),
    ],
)
def test_rejects_invalid_priors_and_role_penalties(overrides, message):
    options = {"offense_ridge": 7.5, "defense_ridge": 62.5, **overrides}
    with pytest.raises(ValueError, match=message):
        fit_prior_rapm(weighted_rows(), **options)


def test_unrepresentable_intercept_raises():
    row = Possession((1, 2, 3, 4, 5), (6, 7, 8, 9, 10), points=2)
    with pytest.raises(RuntimeError, match="not representable"):
        fit_prior_rapm(
            [row],
            offense_ridge=7.5,
            defense_ridge=62.5,
            offense_prior=dict.fromkeys(range(1, 6), 8e307),
        )


def test_priors_for_unobserved_roles_do_not_set_the_response_scale():
    rows = [
        Possession((1, 2, 3, 4, 5), (7, 8, 9, 10, 11), points=1e-190),
        Possession((1, 2, 3, 4, 6), (7, 8, 9, 10, 11), points=3e-190),
    ]
    baseline = fit_prior_rapm(rows, offense_ridge=1.5, defense_ridge=3)
    fit = fit_prior_rapm(
        rows,
        offense_ridge=1.5,
        defense_ridge=3,
        offense_prior={11: 8e307},
        defense_prior={1: -7e307},
    )
    assert fit.intercept == baseline.intercept
    assert tuple(fit.offense[p] for p in range(1, 7)) == tuple(
        baseline.offense[p] for p in range(1, 7)
    )
    assert fit.offense[11] == 8e307
    assert fit.defense[1] == -7e307


def test_equal_role_level_does_not_erase_small_responses():
    rows = [replace(row, points=row.points * 1e-190) for row in weighted_rows()]
    baseline = fit_prior_rapm(rows, offense_ridge=7.5, defense_ridge=62.5)
    common_prior = dict.fromkeys(baseline.offense, 8e307)
    fit = fit_prior_rapm(
        rows,
        offense_ridge=7.5,
        defense_ridge=62.5,
        offense_prior=common_prior,
        defense_prior=common_prior,
    )
    assert fit.intercept == baseline.intercept
    assert fit.offense == fit.defense == common_prior
