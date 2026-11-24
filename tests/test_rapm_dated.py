"""Eligibility, decay and dense-oracle checks for dated prior-centered RAPM."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta

import pytest

pytest.importorskip("numpy")
pytest.importorskip("scipy")

import numpy as np  # noqa: E402

from bil.models.rapm import Possession, fit_dated_prior_rapm, fit_prior_rapm  # noqa: E402
from bil.models.rapm.synthetic import generate_possessions  # noqa: E402

AS_OF = date(2025, 1, 31)
OFFENSE_PRIOR = {1: 15, 2: -12, 3: 4, 4: 8}
DEFENSE_PRIOR = {1: -7, 2: 13, 4: -2, 6: 6}
OFFENSE_RIDGE, DEFENSE_RIDGE = 7.5, 62.5
TOLERANCE = 1e-8
OFFENSE, DEFENSE = (1, 2, 3, 4, 5), (6, 7, 8, 9, 10)


def dated_rows(count=96, *, span=60):
    """Rows spread over `span` days centred on AS_OF, so some are same-day or later."""
    rows = generate_possessions(count, seed=909, noisy=True)
    start = AS_OF - timedelta(days=span // 2)
    return [
        replace(row, weight=(i % 5 + 1) / 3, played_date=start + timedelta(days=i * span // count))
        for i, row in enumerate(rows)
    ]


def fit(rows, *, half_life=30.0, as_of=AS_OF):
    return fit_dated_prior_rapm(
        rows,
        as_of=as_of,
        half_life_days=half_life,
        offense_ridge=OFFENSE_RIDGE,
        defense_ridge=DEFENSE_RIDGE,
        offense_prior=OFFENSE_PRIOR,
        defense_prior=DEFENSE_PRIOR,
    )


def undated_fit(rows):
    return fit_prior_rapm(
        rows,
        offense_ridge=OFFENSE_RIDGE,
        defense_ridge=DEFENSE_RIDGE,
        offense_prior=OFFENSE_PRIOR,
        defense_prior=DEFENSE_PRIOR,
    )


def flat(fit_result, ids):
    f = getattr(fit_result, "fit", fit_result)
    return np.array([f.intercept, *(f.offense[p] for p in ids), *(f.defense[p] for p in ids)])


def oracle(rows, half_life):
    """Dense weighted ridge from normal equations; shares no code with the solver."""
    kept = [r for r in rows if r.played_date < AS_OF]
    ids = sorted({p for r in kept for p in (*r.offense, *r.defense)})
    x = np.array(
        [[1, *(p in r.offense for p in ids), *(-int(p in r.defense) for p in ids)] for r in kept],
        dtype=float,
    )
    age = np.array([(AS_OF - r.played_date).days for r in kept], dtype=float)
    decay = np.ones(len(kept)) if half_life is None else 2.0 ** (-age / half_life)
    w = np.array([r.weight for r in kept]) * decay
    y = np.array([100 * r.points for r in kept])
    m = np.array(
        [0, *(OFFENSE_PRIOR.get(p, 0) for p in ids), *(DEFENSE_PRIOR.get(p, 0) for p in ids)],
        dtype=float,
    )
    pen = np.diag([0.0, *([OFFENSE_RIDGE] * len(ids)), *([DEFENSE_RIDGE] * len(ids))])
    lhs = x.T @ (w[:, None] * x) + pen
    beta = np.linalg.pinv(lhs, rcond=1e-12) @ (x.T @ (w * y) + pen @ m)
    augmented = np.vstack([np.sqrt(w)[:, None] * x, np.sqrt(pen)])
    return ids, x, beta, np.linalg.cond(augmented)


@pytest.mark.parametrize("half_life", [None, 365.0, 30.0, 3.0, 0.5])
def test_matches_dense_oracle(half_life):
    rows = dated_rows()
    ids, x, expected, _ = oracle(rows, half_life)
    actual = flat(fit(rows, half_life=half_life), ids)
    np.testing.assert_allclose(actual, expected, rtol=0, atol=TOLERANCE)
    np.testing.assert_allclose(x @ actual, x @ expected, rtol=0, atol=TOLERANCE)
    print(
        f"half_life={half_life} max coefficient delta {np.max(np.abs(actual - expected)):.4e}"
        f" max rate delta {np.max(np.abs(x @ actual - x @ expected)):.4e}"
    )


@pytest.mark.parametrize("half_life", [None, 30.0, 3.0, 0.5])
def test_representative_conditioning(half_life):
    _, _, _, condition = oracle(dated_rows(), half_life)
    print(f"half_life={half_life} augmented condition number {condition:.4f}")
    assert 1 < condition < 1e6


def test_no_decay_equals_undated_fit_on_eligible_rows():
    rows = dated_rows()
    eligible = [r for r in rows if r.played_date < AS_OF]
    result = fit(rows, half_life=None)
    assert result.fit == undated_fit(eligible)
    assert (result.included, result.excluded_same_or_later) == (
        len(eligible),
        len(rows) - len(eligible),
    )
    assert 0 < result.included < len(rows)


def test_very_long_half_life_approaches_no_decay():
    rows = dated_rows()
    ids, *_ = oracle(rows, None)
    np.testing.assert_allclose(
        flat(fit(rows, half_life=1e9), ids), flat(fit(rows, half_life=None), ids), atol=1e-5
    )


def test_decay_composes_multiplicatively_with_base_weights():
    day = date(2025, 1, 29)
    heavy = Possession(OFFENSE, DEFENSE, 1.0, weight=4.0, played_date=day)
    light = Possession(OFFENSE, DEFENSE, 0.0, weight=2.0, played_date=day)
    # Age 1 at half-life 1 halves each base weight.
    dated = fit([heavy, light], half_life=1.0, as_of=date(2025, 1, 30))
    manual = undated_fit([replace(heavy, weight=2.0), replace(light, weight=1.0)])
    assert dated.fit.intercept == pytest.approx(manual.intercept, abs=1e-9)
    for role in ("offense", "defense"):
        np.testing.assert_allclose(
            list(getattr(dated.fit, role).values()), list(getattr(manual, role).values()), atol=1e-9
        )


def test_decay_is_not_renormalized_so_it_raises_relative_penalty():
    rows = dated_rows()
    ids, *_ = oracle(rows, None)
    prior = np.array([OFFENSE_PRIOR.get(p, 0) for p in ids])
    slow = flat(fit(rows, half_life=1e6), ids)[1 : len(ids) + 1]
    fast = flat(fit(rows, half_life=1.0), ids)[1 : len(ids) + 1]
    assert np.linalg.norm(fast - prior) < np.linalg.norm(slow - prior)


def test_same_day_and_later_rows_cannot_change_the_fit_or_universe():
    rows = dated_rows()
    clean = [r for r in rows if r.played_date < AS_OF]
    poison = [
        Possession((101, 102, 103, 104, 105), (106, 107, 108, 109, 110), 4.0, 50.0, played_date=day)
        for day in (AS_OF, AS_OF + timedelta(days=1), AS_OF + timedelta(days=400))
    ]
    mixed = fit(poison + rows + poison)
    assert mixed.fit == fit(clean).fit
    assert mixed.excluded_same_or_later == len(rows) - len(clean) + 6
    assert not set(range(101, 111)) & (set(mixed.fit.offense) | set(mixed.fit.defense))


def test_eligibility_boundary_is_strict_by_calendar_day():
    one = Possession(OFFENSE, DEFENSE, 1.0, played_date=AS_OF - timedelta(days=1))
    same = replace(one, played_date=AS_OF)
    assert fit([one, same], half_life=2.0).included == 1
    with pytest.raises(ValueError, match="before as_of"):
        fit([same])
    with pytest.raises(ValueError, match="before as_of"):
        fit([replace(one, played_date=AS_OF + timedelta(days=1))])


def test_repeated_calls_hold_no_state_and_do_not_mutate_inputs():
    rows = dated_rows()
    snapshot = [(r.weight, r.played_date) for r in rows]
    first = fit(rows)
    fit(rows, as_of=AS_OF - timedelta(days=10))
    assert fit(rows) == first
    assert snapshot == [(r.weight, r.played_date) for r in rows]


@pytest.mark.parametrize("bad", [None, datetime(2025, 1, 1, 12), "2025-01-01"])
def test_missing_or_non_date_values_fail_closed_even_on_excluded_rows(bad):
    rows = dated_rows()
    late = replace(rows[0], played_date=bad)
    with pytest.raises(ValueError, match="played_date"):
        fit([*rows, late])


@pytest.mark.parametrize(
    ("as_of", "half_life", "message"),
    [
        (datetime(2025, 1, 31), 30.0, "as_of"),
        (AS_OF, 0.0, "half_life"),
        (AS_OF, -1.0, "half_life"),
        (AS_OF, float("nan"), "half_life"),
        (AS_OF, float("inf"), "half_life"),
    ],
)
def test_rejects_invalid_clock_parameters(as_of, half_life, message):
    with pytest.raises(ValueError, match=message):
        fit(dated_rows(), half_life=half_life, as_of=as_of)


def test_decay_underflow_fails_closed():
    row = Possession(OFFENSE, DEFENSE, 1.0, played_date=AS_OF - timedelta(days=5))
    with pytest.raises(ValueError, match="decayed weight"):
        fit([row], half_life=1e-3)
