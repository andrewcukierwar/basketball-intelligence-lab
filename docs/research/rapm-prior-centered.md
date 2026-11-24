# Prior-centered offensive and defensive RAPM

[Issue #61][issue] extends BIL's [synthetic RAPM reference](rapm-synthetic.md) with supplied player priors and separate role penalties. The same five-on-five possession design predicts the scoring side's points per 100 possessions from a free intercept, the five offensive coefficients and the negatives of the five defensive coefficients.

## Objective and inputs

Let `y` be scoring in points per 100 possessions, `X` the sparse signed player matrix, `b` the intercept, `o` and `d` the offensive and defensive coefficients, and `m_O` and `m_D` the aligned priors. The fit minimizes

$$
\sum_i w_i \left(y_i-b-X_i[o,d]\right)^2
+ \lambda_O\|o-m_O\|_2^2 + \lambda_D\|d-m_D\|_2^2.
$$

Both penalties are positive and finite. Observation weights retain their supplied scale. Both prior maps use positive integer player IDs and finite effects **in points per 100 possessions**. Larger positive offense raises scoring and larger positive defense lowers the opposing offense's scoring. Omitted player-role entries use zero. Players with no lineup appearance have no output coefficients. A player seen in only one role keeps the supplied or default prior coefficient for the other role.

```python
from bil.models.rapm import fit_prior_rapm

fit = fit_prior_rapm(
    possessions,
    offense_ridge=7.5,
    defense_ridge=62.5,
    offense_prior={11: 2.0, 18: -1.0},
    defense_prior={11: -0.5, 18: 1.5},
)
```

A fixed lineup size allows a uniform shift in each role to be absorbed by the intercept. Within either set of prediction-equivalent coefficients, the penalty selects the solution whose unweighted mean deviation from the supplied prior is zero in each role. The intercept remains the weighted mean of the observed rate after subtracting the fitted player effect. An equal penalty and zero priors use the same solver as `fit_rapm(possessions, ridge=...)`.

The solver shifts the response by the signed lineup priors and fits the residual coefficients with sparse LSQR. Within-role prior differences set the response scale alongside the observed rates. The constant part of each role prior is restored through the free intercept after the solve. The solver projects out that intercept and scales the role columns separately when one penalty is much larger. Right scaling changes the solver coordinates, with the original penalty and input units restored in the result. It returns the supplied prior plus the fitted deviation. Finite results must fit in float64.

## Synthetic evidence

Run the existing checks and reproduce the prior and conditioning cases with the locked optional dependencies.

```sh
uv run --locked --extra dev --extra rapm pytest -q tests/test_rapm.py
uv run --locked --extra dev --extra rapm pytest -q -s tests/test_rapm_prior.py
```

The independent dense oracle constructs the signed indicator matrix directly from lineup membership. It solves the augmented weighted least-squares problem with the free intercept in the observation rows and priors in the player penalty rows. In the 64-row unequal-weight fixture with penalties of 7.5 and 62.5, the maximum coefficient and fitted-rate deltas were `8.9894e-11` and `1.4127e-10` points per 100 possessions, below the `1e-8` absolute tolerance. The tests also check joint scaling of scoring rates and priors by `1e-190`, 3, and `1e190`. A constant offense prior of `8e306` preserved the defense effects and defense prior differences on a fixture whose scoring rates ranged from `1e-188` to `3e-188`. The tests also exercise a representable intercept after cancellation of an intermediate role shift above the float64 range. A defense penalty of `1e280` keeps the defense at its prior at float64 precision while the offensive fit still agrees with a dense fit conditional on that defense.

Increasing one role's penalty from 7.5 to 1,000 while keeping the other penalty at 7.5 reduced the L2 distance from the offense prior from 45.049 to 0.748, and from the defense prior from 34.269 to 0.631, in separate runs.

The paired-player fixture forces two players to share the same role or sit together. The condition numbers below come from the singular values of the weighted, intercept-profiled augmented matrix in the original coefficient coordinates, before the sparse solver's numerical right scaling. Sparse and dense results agreed within `1e-8` for every listed pair.

| Offense penalty | Defense penalty | Condition number |
| ---: | ---: | ---: |
| 0.01 | 0.08 | 89.2882 |
| 30 | 70 | 2.1151 |
| 1,600 | 400 | 2.0262 |

These are synthetic checks of one objective. Choosing prior inputs, penalties, cutoff rules and decay for historical fits requires separate evidence. [ADR-0014](../decisions/0014-prior-centered-rapm.md) · [Parent #34][parent]

[issue]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/61
[parent]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/34
