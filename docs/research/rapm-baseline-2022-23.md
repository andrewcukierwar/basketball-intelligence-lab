# Zero-prior RAPM baseline on the 2022–23 row set

[Issue #23](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/23) fits and evaluates the first historical zero-prior RAPM baseline. The [scoring protocol](rapm-baseline-protocol.md) was committed (`26cb127`) and the runner committed (`82b3452`) before the run. The run used a clean working tree at `82b3452` and protocol SHA-256 `69aa571a…01b5e56`. Source data are attributed to NBA.com and stay private under the [pilot terms](../data-pilot.md). Player-level estimates are in the private output directory only. This report contains aggregates.

**Evidence tier: `retrospective_capture_bound`.** The 224,039 rows come from a capture with no verified historical publication times ([#59](rapm-historical-rows.md), build `bc7b0174…b45`). The run is a chronological replay on stable-lineup possessions with realized lineups, not a strict rolling-origin backtest and not a pregame forecast. Only 2022–23 was read. No 2023–24, 2024–25 or 2025–26 data and no EPM value were read or used.

| Claim | Label |
| --- | --- |
| Zero-prior ridge with unpenalized intercept, sparse LSQR | **Documented** (verified against dense and OpenRAPM-matched fits in [#6](rapm-synthetic.md) and [#65](rapm-open-benchmark.md)) |
| Fold design, scoring and exclusion protocol | **Original** |
| Every number below | **Experimental**, retrospective |

## Result in one paragraph

Fitting on earlier games improves held-out possession scoring over the league-average model by a very small amount: 0.10% of the mean squared error pooled over four regular-season folds (−14.1 on a base of 14,109 squared points per 100 possessions, 95% game-clustered interval −18.3 to −9.8). Most of the gain is offensive. A defense-only prediction does not beat the league average. On the playoff check fold the delta is −8.0 with an interval that includes zero (−24.0 to +7.5). The model is a measurable but weak predictor of single-possession points, which is expected for a response whose noise dominates. Individual estimates are noisy: split-half correlation of total estimates is 0.38. Dropping games with non-routine adjudication strata moves estimates modestly and does not change held-out scores beyond noise.

## Setup

One shared ridge on all player coefficients, unit weights, response in points per 100 possessions, positive defense preventing points. The league baseline (B0) predicts the fit-window mean (109.6 in the final fit's intercept; each fold uses its own fit window). Held-out players absent from the fit take zero effect. 9,002 of 136,730 pooled regular-season scored possessions (6.6%) and 132 of 14,097 playoff possessions involve one. Folds fit on games strictly before the cutoff and score whole later games.

| Fold | Fit rows | Scored games | Scored possessions |
| --- | ---: | ---: | ---: |
| R1 (fit < 2022-12-15) | 73,212 | 220 | 38,230 |
| R2 (fit < 2023-01-15) | 111,442 | 219 | 37,818 |
| R3 (fit < 2023-02-15) | 149,260 | 160 | 27,905 |
| R4 (fit < 2023-03-15) | 177,165 | 187 | 32,777 |
| P1 (fit < 2023-04-15, playoffs) | 209,942 | 84 | 14,097 |

## Held-out scores at the chosen penalty ($\lambda^\*$ = 4,000)

Delta = MSE(model) − MSE(league), in (points per 100 possessions)². Negative is better. Intervals are 95% percentile game-clustered bootstrap (2,000 resamples, seed 2023) and ignore dependence across folds.

| Fold | League MSE | Model MSE | Delta | 95% interval |
| --- | ---: | ---: | ---: | --- |
| R1 | 14,153.2 | 14,146.2 | −7.0 | −14.0 to −0.03 |
| R2 | 14,067.5 | 14,054.0 | −13.5 | −20.6 to −6.4 |
| R3 | 14,168.5 | 14,150.5 | −18.0 | −27.8 to −8.4 |
| R4 | 14,056.6 | 14,036.8 | −19.8 | −30.3 to −9.8 |
| Pooled R1–R4 (selection folds) | 14,109.5 | 14,095.4 | −14.1 | −18.3 to −9.8 |
| P1 playoffs (not used in selection) | 14,022.1 | 14,014.2 | −8.0 | −24.0 to +7.5 |

The gain grows across R1 to R4. Fit size is confounded with time of season, so attributing this to fit size is **Inferred**. RMSE is 118.72 against 118.78 for the league model. Pooled ablations: offense-only −9.2, defense-only +1.1 (defense alone is not better than the league average). The pooled team-game aggregate RMSE (summed predicted against actual points for a team in a game) is 10.45 for the model, 10.69 for the league model, 10.58 offense-only and 10.78 defense-only. On the playoff fold the model's team-game RMSE is 10.42 against 10.32 for the league model, so the possession-level gain there does not carry to game totals. Regular season and playoffs are never pooled.

## Regularization sensitivity

Pooled R1–R4 held-out MSE by penalty. The league MSE is 14,109.5.

| $\lambda$ | Model MSE | Delta vs league | 95% interval | Offense-only delta | Defense-only delta |
| ---: | ---: | ---: | --- | ---: | ---: |
| 250 | 14,134.7 | +25.2 | 14.4 to 35.9 | +0.9 | +50.9 |
| 500 | 14,115.3 | +5.8 | −2.8 to 14.9 | −5.9 | +31.2 |
| 1,000 | 14,102.4 | −7.1 | −14.1 to 0.4 | −9.6 | +16.2 |
| 2,000 | 14,096.3 | −13.2 | −18.6 to −7.4 | −10.4 | +6.4 |
| **4,000** | **14,095.4** | **−14.1** | −18.3 to −9.8 | −9.2 | +1.1 |
| 8,000 | 14,097.4 | −12.1 | −15.1 to −9.1 | −7.3 | −1.2 |
| 16,000 | 14,100.5 | −8.9 | −11.0 to −7.0 | −5.1 | −1.7 |
| 32,000 | 14,103.6 | −5.8 | −7.1 to −4.6 | −3.3 | −1.4 |

The minimum is interior, so the grid was not extended. The curve is flat within about 1 MSE unit over 2,000 to 4,000 and within about 2 units to 8,000. Weak penalties (250 and 500) lose to the league average with the defense-only ablation worst, which suggests overfit defensive effects (**Inferred**). $\lambda^\*$ was chosen on R1–R4 only, so those scores are optimistic, although the pooled delta is negative at every $\lambda \ge 1{,}000$. P1 was scored after the choice. The grid choice used no EPM output.

## Final-fit exposure and estimates (in-sample, descriptive)

One fit on all 224,039 rows (1,292 games, 541 players) at $\lambda^\*$.

| Quantity | Value |
| --- | --- |
| Offensive possessions per player: median, p05, p95 | 1,786, 54, 4,812 |
| Defensive possessions per player: median, p05, p95 | 1,785, 55, 4,818 |
| Games per player: median, p05, p95 | 55, 4, 86 |
| Players below 250, 500, 1,000 offensive possessions | 85 (15.7%), 128 (23.7%), 186 (34.4%) |
| Share of player-possessions below 250, 500, 1,000 | 0.8%, 2.1%, 6.0% |
| Offense estimate: sd, p05 to p95 (points per 100) | 0.95, −1.48 to 1.71 |
| Defense estimate: sd, p05 to p95 | 0.81, −1.40 to 1.39 |
| Total estimate: sd, p05 to p95, min to max | 1.29, −2.02 to 2.30, −4.18 to 4.59 |
| Offense versus defense correlation | 0.06 |
| Total-estimate sd by on-court possessions: under 500, 500–1,500, 1,500–3,000, over 3,000 | 0.35, 0.77, 1.11, 1.51 |
| Split-half correlation of totals (alternating games, 398 players with at least 250 possessions per role in each half): total, offense, defense | 0.38, 0.35, 0.27 |

Estimates are shrunk hard (a total spread of about 1.3 points per 100) and the spread rises with exposure, which is the ridge pulling low-exposure players to zero. The split-half correlations show the estimates carry real but limited signal at this sample size. Offense and defense are close to uncorrelated.

## Effect of excluding adjudication strata

The routine strata (`same_clock_free_throw_substitution`, `technical_free_throw`, `overtime`) cover nearly every game and are not exclusions. Dropping every game with any other stratum removes 170 of 1,292 games (13.2%). The penalty stayed at 4,000.

Held-out scores, pooled R1–R4 (the same scored possessions for the full and exclusion fits):

| Scored set | League MSE | Full-fit model MSE | Exclusion-fit model MSE |
| --- | ---: | ---: | ---: |
| All held-out possessions (136,730) | 14,109.5 | 14,095.4 | 14,094.6 |
| Held-out possessions of non-flagged games (119,484) | 14,113.3 | 14,097.8 | 14,096.8 |
| Playoffs, all (14,097) | 14,022.1 | 14,014.2 | 14,014.3 |
| Playoffs, non-flagged (12,737) | 13,996.1 | 13,985.2 | 13,985.5 |

(The exclusion fit's own league mean also changes slightly, so the league column is the full-fit window mean.) Differences are around 1 MSE unit, below the 5 to 10 unit width of the paired intervals, so excluding the strata neither helps nor hurts held-out scoring measurably. A significance test of the exclusion contrast itself was not run.

Shift in final-fit estimates when dropping all flagged games (539 players present in both): offense RMS 0.26 and max 1.24, defense RMS 0.27 and max 1.02, total RMS 0.37 and max 1.67 points per 100, total correlation 0.958. Two players drop out entirely. Dropping one stratum at a time (RMS shift in totals, correlation, games, possessions):

| Stratum | Games | Possessions | Total RMS shift | Total correlation |
| --- | ---: | ---: | ---: | ---: |
| `v3_event_order` | 80 | 13,933 | 0.268 | 0.978 |
| `unresolved_possessions` | 30 | 5,237 | 0.161 | 0.992 |
| `livedata_starters` | 29 | 5,254 | 0.137 | 0.994 |
| `same_clock_box_credit` | 18 | 3,145 | 0.112 | 0.996 |
| `source_repeat` | 14 | 2,415 | 0.093 | 0.997 |
| `v3_primary_order` | 7 | 1,211 | 0.073 | 0.998 |
| `inferred_starters` | 2 | 356 | 0.041 | 0.9995 |
| `datanba_possession_labels` | 2 | 333 | 0.029 | 0.9998 |
| `v3_period_defect` | 2 | 350 | 0.029 | 0.9998 |

The shifts scale roughly with the possessions removed. Without a size-matched random-game exclusion control, the data cannot say whether any stratum shifts estimates more than removing the same number of ordinary games would. Strata overlap, so the rows are not additive.

## Optimizer, runtime and memory

All 53 logged fits stopped with LSQR code 2 (least-squares solution within tolerance, atol and btol 1e-12), with 8 to 82 iterations (median 26). The final 224,039-row fit took 0.41 s, 28 iterations, scaled residual norm 1.77 and a condition estimate of 34.4. The largest condition estimate was 170.9. All 53 fits took 14.5 s in total and the whole run, including loading, scoring, bootstraps and the exclusion, stability and per-stratum fits, took 19.1 s on one machine (Python 3.14.3, NumPy 2.5.5, SciPy 1.18.1, DuckDB 2.0.1). Peak resident memory was 898 MiB. Wall times are from one run, not repeated. Two further split-half stability fits are not logged. They converged, because the solver raises an error otherwise. Deviation from the protocol: results.json stores aggregate solver diagnostics plus the final fit, not per-fit records (per-fit records, split penalties and the random-exclusion control were added in [#77](rapm-baseline-controls-2022-23.md)).

## Limitations

- Retrospective, capture-bound data and realized lineups. The result supports a statement about stable-lineup possessions in a replay, not pregame prediction. Multiple-lineup possessions (12.6% of accepted possessions, with higher scoring) are not in the rows or the targets.
- Selection and reporting share R1–R4. The pooled R1–R4 score is optimistic for $\lambda^\*$. Only P1 is independent of the choice, and its interval includes zero.
- Bootstrap intervals cluster by game but ignore time dependence across folds, and four folds are few.
- A role-symmetric penalty only was searched. Separate offense and defense penalties may suit the weaker defensive signal. No context terms (home, rest, score state) or priors are included, so it is a baseline only.
- The OpenRAPM comparison is by the #65 synthetic benchmark of the same objective. It was not rerun on these rows. No league-and-context possession model beyond the league mean was run (the contract's "context-only" comparator remains open).
- Held-out squared error is dominated by possession noise (RMSE about 119 against a 14,109 variance). Small relative gains are what this response permits and do not imply useful player ratings.
- 2022–23 is a development season. Nothing here is confirmatory.

## Reproduce

```sh
uv sync --locked --extra dev --extra pilot --extra rapm
uv run python -m bil.models.rapm.baseline \
  data/processed/2022-23/issue-59-v1 data/processed/2022-23/issue-23-v1
```

The runner verifies the pinned digests of `manifest.json`, `model_row.parquet` and `game_reconciliation.parquet` and refuses a different row set or output directory that exists. It writes `results.json`, `manifest.json` and the private `player_estimates.csv` (offense, defense, total and exposure per player).
