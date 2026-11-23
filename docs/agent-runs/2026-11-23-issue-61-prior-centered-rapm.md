# Agent run — Prior-centered sparse RAPM

- **Date:** 2026-11-23
- **Status:** Implementation and local verification complete. Independent review and publication pending.
- **Issues:** [#61](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/61), parent [#34](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/34)
- **Branch and implementation:** `codex/issue-61-prior-centered-rapm`, base `d3d01f3`, implementation `da96a58`.

## Scope and decisions

Added `fit_prior_rapm` using the existing sparse possession design and the same solver as `fit_rapm`. The new call accepts separate positive role penalties and prior maps in points per 100 possessions, with positive defensive values lowering opponent scoring. Missing entries use zero. A player absent from all fit rows has no output coefficient. A player unobserved in one role retains that role's aligned prior. The free intercept and role-centered deviations give the minimum penalty solution within the set of prediction-equivalent effects. The implementation keeps extreme penalties in one role from dominating the numerical scale of the other role. [Estimator contract and evidence](../research/rapm-prior-centered.md) · [ADR-0013](../DECISIONS.md#adr-0013--center-rapm-deviations-on-the-supplied-role-priors)

## Verification

| Check | Observed result |
| --- | --- |
| `PYTHONPATH=src python -m pytest -q` with the existing project environment | 64 passed. Includes the 22 existing RAPM cases and 21 new prior cases. |
| `PYTHONPATH=src python -m pytest -q -s tests/test_rapm_prior.py` | 21 passed. The weighted dense comparison had maximum coefficient and rate deltas of `8.9894e-11` and `1.4127e-10` points per 100 possessions against an absolute tolerance of `1e-8`. |
| Paired-player conditioning probe in the same test | Condition numbers 89.2882, 2.1151 and 2.0262 with penalty pairs (0.01, 0.08), (30, 70) and (1,600, 400). Each fit agreed with the dense oracle. |
| Numerical controls in the same test | Verified exact zero-prior compatibility, stronger role shrinkage, common response and prior scaling across `1e-190` to `1e190`, and a defense penalty of `1e280`. Cases with huge unobserved or exactly canceling common priors retained their small response scale. |
| `ruff check`, `ruff format --check`, `mypy src`, `git diff --check` | Passed. The first type check caught ambiguous NumPy index types in the active-role lookup. Explicit integer indexing resolved it. |

## Next action

Review the exact changes and evidence before closing #61. The synthetic fit does not select a historical penalty, construct dated priors or enforce chronological eligibility. The dated weight and cutoff work belongs to [#64](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/64).
