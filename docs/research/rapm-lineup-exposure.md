# RAPM with multiple-lineup training possessions

**Recommendation.** Keep the stable-lineup restriction for the current RAPM reference. Adding multiple-lineup possessions raised pooled regular-season MSE by 1.16 with entry lineups and by 0.90 with clock-fractional lineups. Both intervals included zero. Both candidates improved 2022–23 and worsened 2021–22, and both clearly worsened the playoff check. Neither met the [frozen advancement rule](rapm-lineup-exposure-protocol.md#decision-rule). The result concerns prediction on stable-lineup possessions. The excluded possessions remain a distinct, largely untested scoring cohort. [Issue #110](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/110)

## Which opportunities the canonical rule leaves out

These are pilot-accepted possessions. The exclusion share is relative to all accepted possessions in the corresponding slice. Rate is assigned control points per 100 opportunities. Within each season, the game-state, period and clock cuts combine regular season and playoffs.

| Season | Type | Stable | Multiple-lineup | Excluded share | Stable rate | Multiple-lineup rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2021–22 | Regular | 208,789 | 30,712 | 12.82% | 108.85 | 132.96 |
| 2021–22 | Playoffs | 14,254 | 2,262 | 13.70% | 108.13 | 131.96 |
| 2022–23 | Regular | 209,942 | 30,338 | 12.63% | 111.27 | 138.32 |
| 2022–23 | Playoffs | 14,097 | 2,079 | 12.85% | 109.95 | 136.51 |

| Possession state | 2021–22 excluded | 2022–23 excluded |
| --- | ---: | ---: |
| Offense down 10+ | 7,124 / 49,557 (14.38%) | 6,587 / 46,489 (14.17%) |
| Offense down 3–9 | 7,726 / 56,176 (13.75%) | 7,804 / 58,920 (13.25%) |
| Score within two | 6,234 / 55,868 (11.16%) | 6,409 / 57,687 (11.11%) |
| Offense up 3–9 | 6,603 / 51,006 (12.95%) | 6,728 / 53,333 (12.62%) |
| Offense up 10+ | 5,287 / 43,410 (12.18%) | 4,889 / 40,027 (12.21%) |
| Q1 | 6,915 / 64,778 (10.67%) | 6,781 / 65,062 (10.42%) |
| Q2 | 9,581 / 64,310 (14.90%) | 9,401 / 64,366 (14.61%) |
| Q3 | 7,528 / 63,551 (11.85%) | 7,352 / 63,416 (11.59%) |
| Q4 | 8,811 / 62,152 (14.18%) | 8,677 / 61,815 (14.04%) |
| Overtime | 139 / 1,226 (11.34%) | 206 / 1,797 (11.46%) |
| 0–24 s left in period | 1,314 / 7,330 (17.93%) | 1,377 / 7,405 (18.60%) |
| >24–120 s | 4,419 / 36,777 (12.02%) | 4,352 / 36,685 (11.86%) |
| >120–360 s | 14,602 / 84,356 (17.31%) | 14,405 / 84,403 (17.07%) |
| >360 s | 12,639 / 127,554 (9.91%) | 12,283 / 127,963 (9.60%) |

Both seasons show higher exclusion when the offense trails by at least ten than when the score is within two, and in Q2 and Q4 versus Q1. The last 24 s of a period have the largest clock-band exclusion. Within that band, stable versus multiple-lineup scoring rates were 78.52 versus 108.14 in 2021–22 and 80.21 versus 117.28 in 2022–23. These are descriptive differences. Substitution timing and scoring are both associated with game state.

| Pattern among multiple-lineup possessions | 2021–22, of 32,974 | 2022–23, of 32,417 |
| --- | ---: | ---: |
| Offense lineup changes only | 10,935 (33.16%) | 10,629 (32.79%) |
| Defense lineup changes only | 12,093 (36.67%) | 11,914 (36.75%) |
| Both lineups change | 9,946 (30.16%) | 9,874 (30.46%) |
| Two distinct pairs | 17,035 (51.66%) | 16,880 (52.07%) |
| At least three distinct pairs | 15,939 (48.34%) | 15,537 (47.93%) |
| One or more zero-clock pieces | 25,951 (78.70%) | 26,092 (80.49%) |
| Entire possession has zero clock elapsed | 395 (1.20%) | 335 (1.03%) |

Team exposure is the omitted share of each team's accepted offense or defense opportunities. Player exposure is the omitted share of each player's accepted clock-fractional opportunities by role, among players with at least 200 in that role. Values are the 10th percentile, median and 90th percentile within the group.

| Scope and role | 2021–22 cells | 2021–22 omitted exposure | 2022–23 cells | 2022–23 omitted exposure |
| --- | ---: | --- | ---: | --- |
| Team offense | 30 | 12.18%, 12.90%, 13.59% | 30 | 11.93%, 12.60%, 13.49% |
| Team defense | 30 | 12.00%, 12.79%, 13.80% | 30 | 11.82%, 12.61%, 13.55% |
| Player offense | 496 | 11.10%, 12.85%, 15.05% | 473 | 10.82%, 12.73%, 14.69% |
| Player defense | 496 | 11.00%, 12.99%, 15.34% | 473 | 10.86%, 12.81%, 15.16% |

## Common-cohort outcomes

Each candidate uses W2, unit weights, a zero prior and offense/defense penalties 4,000/8,000. Entry uses the first actual lineup pair for the full possession. Clock-fractional uses elapsed stint proportions, with the frozen equal-piece fallback when the whole possession has zero time. Both fit the full signed control point sum on one observation per opportunity. All fits score only the same stable possessions. No fit used an outer season or the confirmatory holdout. [Frozen protocol](rapm-lineup-exposure-protocol.md)

Δ is MSE(candidate) minus MSE(stable), in squared points-per-100 units. Intervals are game-clustered, with 2,000 draws. Team-game RMSE is in summed control points on the scored stable possessions.

| Scored cohort | Games / possessions | Stable MSE | Entry Δ (95%) | Fractional Δ (95%) | Team-game RMSE stable / entry / fractional |
| --- | ---: | ---: | --- | --- | --- |
| Regular, pooled | 2,427 / 418,731 | 14,109.76 | +1.16 (−1.18, +3.59) | +0.90 (−1.46, +3.32) | 10.447 / 10.482 / 10.475 |
| 2021–22 regular | 1,219 / 208,789 | 14,148.74 | +5.78 (+2.25, +9.28) | +5.44 (+2.02, +8.94) | 10.600 / 10.781 / 10.770 |
| 2022–23 regular | 1,208 / 209,942 | 14,070.99 | −3.44 (−6.77, −0.08) | −3.63 (−7.00, −0.18) | 10.290 / 10.171 / 10.168 |
| Playoffs, pooled | 171 / 28,351 | 14,161.97 | +20.68 (+11.26, +29.81) | +21.15 (+11.55, +30.38) | 10.609 / 11.261 / 11.285 |

| Refit block | Stable training opportunities | Expanded training opportunities | Stable test opportunities | Entry Δ | Fractional Δ |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2021–22 R1 | 395,384 | 454,417 | 53,652 | +35.11 | +33.59 |
| 2021–22 R2 | 398,974 | 458,189 | 74,160 | +3.77 | +3.46 |
| 2021–22 R3 | 397,488 | 456,395 | 66,936 | −10.23 | −9.74 |
| 2021–22 R4 | 423,911 | 486,271 | 14,041 | −19.25 | −19.27 |
| 2021–22 P | 437,952 | 502,139 | 14,254 | +19.15 | +19.92 |
| 2022–23 R1 | 424,103 | 486,141 | 55,880 | +10.60 | +10.30 |
| 2022–23 R2 | 479,179 | 549,595 | 75,869 | −8.55 | −8.69 |
| 2022–23 R3 | 505,424 | 579,539 | 65,859 | −8.38 | −8.71 |
| 2022–23 R4 | 499,726 | 572,915 | 12,334 | −9.26 | −8.48 |
| 2022–23 P | 491,905 | 563,737 | 14,097 | +22.22 | +22.39 |

The alternatives add 14.60% to 14.93% training opportunities per fold. With the penalties held fixed, that also changes regularization relative to exposure. The comparison does not isolate this effect from the changed mix of states, targets and lineups. Fractional exposure uses a reconciled game clock. A zero-clock piece can still contain an important shot, free throw or substitution. Neither representation establishes a causal player effect within a possession.

## Reproduce

The runner verifies the four pinned row sets and their source manifests, checks each control allocation and accepted possession against the canonical disposition, validates clock and sequence coverage, and verifies five opportunities per role per fit row. It reproduces the reference's pooled MSE and team-game RMSE within `1e-6` and exactly reproduces score coverage before returning candidate aggregates. The run converged on all 30 fits, with 33–38 LSQR iterations and condition estimates of 42.24–51.64. It used 17.9 seconds and 1,494 MiB peak memory with Python 3.14.3, DuckDB 2.0.1, NumPy 2.5.5 and SciPy 1.18.1.

```sh
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 OMP_NUM_THREADS=1 \
  uv run --locked --extra rapm --extra pilot python scripts/rapm_lineup_exposure.py \
  --processed data/processed --output /tmp/bil-lineup-exposure.json
```

The output contains aggregate comparisons, per-fit diagnostics, provenance and exposure summaries. NBA source data are attributed to NBA.com. [Source constraints](../data-pilot.md) · [Canonical row contract](rapm-historical-rows.md)
