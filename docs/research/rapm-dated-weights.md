# Dated RAPM eligibility clock and exponential weights

[Issue #64][issue] adds an as-of date and exponential decay to the [prior-centered solver](rapm-prior-centered.md). The evidence is synthetic and numerical. Nothing here selects a half-life, penalty or prior for historical fits, and no EPM output is used. Labels: the cutoff rule reuses the existing evaluation contract (**Documented**); the decay form and its interaction with penalties are **Original** modeling choices, not claims about EPM's unpublished weighting.

## Clock and weights

```python
from bil.models.rapm import fit_dated_prior_rapm

result = fit_dated_prior_rapm(
    possessions,  # Possession(..., played_date=date(...))
    as_of=date(2025, 1, 31),
    half_life_days=30.0,  # None disables decay
    offense_ridge=7.5,
    defense_ridge=62.5,
    offense_prior=...,
    defense_prior=...,
)
result.fit, result.included, result.excluded_same_or_later
```

- **Dates.** `Possession.played_date` and `as_of` are Eastern calendar dates, matching the rating-date convention in `bil.evaluation.eligibility`. Only values of exact type `date` are accepted, so a `datetime` cannot smuggle in a time or timezone.
- **Eligibility.** A row is eligible only if `played_date < as_of` (strictly earlier calendar day). The comparison is the shared `played_before` helper in `bil.evaluation.eligibility`, which the `same_or_later_played_date` rule there also uses, so there is one definition of the cutoff.
- **Age.** `age = (as_of - played_date).days`, an integer of at least 1 for every eligible row.
- **Decay.** `multiplier = 0.5 ** (age / half_life_days)`, with `half_life_days` in calendar days, positive and finite. `None` gives multiplier 1 for every row.
- **Composition.** The fit weight is `base_weight * multiplier`, where `base_weight` is the supplied `Possession.weight`.
- **Normalization.** None. Consistent with [ADR-0012/0014](../decisions/0014-prior-centered-rapm.md), weights keep their absolute scale against the penalties. Decay therefore lowers the total data weight and raises the effective penalty, pulling ratings toward the priors. Shorter half-lives need smaller penalties to give the same shrinkage. Penalties are never rescaled automatically, and penalty selection must be done jointly with the half-life.
- **Missing dates.** Fail closed. Any row, including a row that would be excluded, whose `played_date` is `None` or not a `date` raises `ValueError`. A decayed weight that underflows to zero or is not finite also raises, rather than silently dropping the row.
- **Empty fit.** If no row is eligible the call raises.

## Leakage controls

Rows failing the cutoff are removed before any weight is computed and before the design is built, so they affect neither the response, the weights nor the player universe (a player seen only on or after `as_of` has no output coefficient). The solver keeps no module-level state or cache; `fit_dated_prior_rapm` neither mutates its inputs nor remembers earlier calls, and the tests check that fits at two different `as_of` dates interleaved with a repeat fit return identical results. Any future cache of designs or fits must key on `as_of` and the eligible-row identity, not on the full row set.

## Numerical evidence

Run `uv run pytest -q -s tests/test_rapm_dated.py`. The fixture is 96 generated noisy possessions with base weights from 1/3 to 5/3, spread over 60 days around `as_of`, of which the later part is excluded. The oracle forms the dense weighted normal equations `(X'WX + P)b = X'Wy + Pm`, with an unpenalized intercept, its own date filter and its own `2 ** (-age / h)` weights, and solves with `numpy.linalg.pinv`. It shares no code with the sparse solver. Penalties are 7.5 (offense) and 62.5 (defense) with the nonzero priors of the #61 fixture. Tolerance: `1e-8` absolute on coefficients and on fitted rates, in points per 100 possessions.

| Half-life (days) | Max coefficient delta | Max fitted-rate delta | Augmented condition number |
| ---: | ---: | ---: | ---: |
| none | 6.5011e-11 | 9.4559e-11 | 11.4195 |
| 365 | 4.5220e-11 | 6.7402e-11 | not recorded |
| 30 | 5.5436e-11 | 9.1745e-11 | 9.9664 |
| 3 | 1.1292e-11 | 1.9043e-11 | 6.9939 |
| 0.5 | 6.7502e-14 | 2.2649e-13 | 14.6605 |

The condition number is for the weighted, intercept-included augmented matrix `[sqrt(W)X; sqrt(P)]` in original coordinates. Limit cases: `half_life_days=None` equals `fit_prior_rapm` on the pre-filtered rows exactly, a half-life of `1e9` agrees with no decay within `1e-5`, and a half-life of 1 day with age 1 equals an undated fit with halved weights. Rows with ages beyond roughly `1074 * half_life` underflow `0.5 ** x` and raise, so very short half-lives suit only short windows.

Not established: sensitivity of the dated solver to degenerate designs (the #61 conditioning cases still apply), behavior when the fitted universe changes between as-of dates, and any choice of half-life.

[issue]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/64
