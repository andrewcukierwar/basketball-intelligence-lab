# Zero-prior RAPM baseline: scoring protocol (2022–23)

**Status:** Frozen before the first evaluation run of [issue #23](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/23). **Classification:** Original BIL design, applying the [validation contract](../validation-strategy.md). The results are in [the baseline report](rapm-baseline-2022-23.md), which is written after the run. A change to anything below after the run starts is a deviation and is listed in that report.

## Frozen inputs

| Item | Value |
| --- | --- |
| Row set | [#59](rapm-historical-rows.md) build `issue-59-v1`, 224,039 model rows from 1,292 accepted games |
| `build_id` | `bc7b0174a2277146aba4eedef5bae7dbfd90462e03b6db14f46f63bc3af45b68` |
| `manifest.json` SHA-256 | `0accaa154bc3c85077551a9337c422c56cf8fdfa8dd6a21b00840eca80527a22` |
| `model_row.parquet` SHA-256 | `ebadd15122df870cdfd40e43b04d381bbb6f7058e014c4c26802d8c93b58ad90` |
| `game_reconciliation.parquet` SHA-256 | `c0c4fee3398d28691023f2fbc937d424bc7095abda2117f1ec56909ab80eb0e2` |
| Evidence tier | `retrospective_capture_bound` (no verified historical publication times) |
| Scope | 2022–23 only (regular season and playoffs). No 2023–24, 2024–25 or 2025–26 data are read. No EPM output is read, used or compared. |

The runner verifies the three SHA-256 values and `build_id` before reading any row and refuses to run on a mismatch.

## Estimator and response

The verified zero-prior sparse ridge from [#6](rapm-synthetic.md): unit weights, one row per eligible possession, response is model points × 100, an unpenalized intercept, and one shared penalty $\lambda$ on every offensive and defensive player coefficient. Positive defensive effects prevent points. Total = offense + defense, in points per 100 possessions. Player IDs are converted from decimal strings to integers at the estimator boundary.

## Chronological, game-grouped development folds

A fold has a fit cutoff date $C$ and a scored block $[C, C')$. Fit rows are those with Eastern game date strictly before $C$ (the same `played_before` rule as [dated RAPM](rapm-dated-weights.md)). Scored rows are all model rows from games dated in the block. Games are never split, and a game appears in at most one block.

| Fold | Fit rows | Scored block | Role |
| --- | --- | --- | --- |
| R1 | before 2022-12-15 | `[2022-12-15, 2023-01-15)` | Penalty selection |
| R2 | before 2023-01-15 | `[2023-01-15, 2023-02-15)` | Penalty selection |
| R3 | before 2023-02-15 | `[2023-02-15, 2023-03-15)` | Penalty selection |
| R4 | before 2023-03-15 | `[2023-03-15, 2023-04-11)` | Penalty selection |
| P1 | before 2023-04-15 (all regular season) | playoffs | Check on the chosen penalty. Not used to choose it. |

A held-out player absent from the fit rows has zero offense and defense effect (the zero prior). The count of such possessions is reported. Held-out scoring conditions on realized lineups, which is a retrospective diagnostic, not a pregame forecast.

## Models scored

- **B0 league average.** Prediction is the fit-window mean points per 100 possessions (the zero-effects model with the same intercept definition: the fit intercept at infinite penalty).
- **RAPM($\lambda$).** Prediction is intercept + sum of the five offensive effects − sum of the five defensive effects.
- **Ablations.** Offense-only (defensive effects zeroed) and defense-only (offensive effects zeroed) predictions from the same fit, to report offense and defense slices.
- **OpenRAPM reference.** Not rerun. The #6 estimator was benchmarked against OpenRAPM at commit `8cfb3df` in [#65](rapm-open-benchmark.md) on synthetic fixtures with the same objective. EPM is never used.

## Metrics

Unit is points per 100 possessions on one possession, squared. Primary metric is **pooled held-out possession mean squared error (MSE)** over R1–R4, with the RMSE alongside. The paired delta is `MSE(RAPM) − MSE(B0)` on the identical possessions, so negative is better. Secondary metrics are the same quantities for each fold and for P1; a team-game aggregate RMSE (team's modeled points in a game: sum of predicted points per possession against actual, in points); and the offense-only and defense-only ablation deltas. Regular season and playoffs are reported separately and never pooled.

Uncertainty for the pooled delta uses a game-clustered bootstrap: 2,000 resamples of games with replacement, fixed seed 2023, 95% percentile interval. Possessions within a game are not independent replications. These intervals are descriptive, with the temporal dependence between folds not modeled.

## Penalty selection

The grid for $\lambda$ is {250, 500, 1000, 2000, 4000, 8000, 16000, 32000}, in squared points-per-100 units with unit weights. It is a role-symmetric grid. The selected $\lambda^\*$ is the grid value with the lowest pooled R1–R4 MSE. If the minimum lies at a grid edge, the grid is extended by successive factors of two on that side until the minimum is interior, and this is recorded as a deviation. No EPM value or player-level quantity informs the choice. $\lambda^\*$ is frozen before P1 is scored. Because $\lambda^\*$ is chosen on R1–R4, those scores are development evidence and optimistic for that fold set. P1 is the only score not touched by selection.

## Final fit and reporting rules

The reported player estimates come from one fit on all 2022–23 model rows at $\lambda^\*$ (descriptive, in-sample, not a prediction claim). Player-level estimates stay in the private output directory. The committed report contains aggregate diagnostics only: exposure and estimate distributions, correlations, metrics and runtime.

- **Exposure report.** Per-player offensive and defensive possessions and games: quantiles, the count and exposure share below 250, 500 and 1,000 possessions, and the estimate spread by exposure band.
- **Stability.** Correlation of total estimates from two disjoint game halves (alternating by chronological game order), for players with at least 250 possessions in each role in both halves, at $\lambda^\*$.
- **Optimizer diagnostics.** LSQR stop code, iterations, residual norm and condition estimate per fit, wall time per fit, and peak resident memory of the whole run.
- **Adjudication strata.** The routine strata are `same_clock_free_throw_substitution`, `technical_free_throw` and `overtime`. They cover nearly every game and are not exclusions. The non-routine strata are all others in the game reconciliation. (a) Exclude every game carrying any non-routine stratum from the fit rows of every fold and the final fit, keep $\lambda^\*$, and score on the same held-out possessions as the full fit and on the held-out possessions of non-flagged games only. (b) For each non-routine stratum, drop its games from the final fit and report the root-mean-square and maximum shift in offense, defense and total estimates and their correlation with the full fit, restricted to players present in both fits. Exclusion never changes the held-out target set for the paired comparison in (a).
- **Evidence tier.** Every output carries `retrospective_capture_bound`. The model is not a pregame claim, and nothing here is a strict rolling-origin backtest.

## Run manifest

The runner writes to a new directory and records: the pinned inputs and verified digests, this document's SHA-256, the protocol and grid, code commit and whether the working tree was clean, library versions, per-fit solver diagnostics, runtime, peak memory, output SHA-256 values and the evidence tier.
