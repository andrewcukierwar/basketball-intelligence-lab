# RAPM baseline controls on the 2022–23 row set

The remaining items of [issue #77](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/77) run on the canonical row set under the [frozen addendum](rapm-baseline-controls-protocol.md): separate offense and defense penalties, a size-matched random-game exclusion control and per-fit solver diagnostics. The context-only comparator was delivered by [#24](rapm-context-ablations-2022-23.md). The protocol was committed (`e2168f3`, SHA-256 `7fb3ce72…8531b2`) and the runner committed (`b032969`) before the one registered run. The run used a clean working tree at `b032969`. Source data are attributed to NBA.com and stay private under the [pilot terms](../data-pilot.md). This report contains aggregates only.

**Evidence tier: `retrospective_capture_bound`.** Row set `issue-82-canonical-v1` (224,039 rows, 1,292 games, [ADR-0019](../DECISIONS.md), `manifest.json` SHA-256 `bd25cd0a…56488`), which holds the same model rows as `issue-59-v1`. Only 2022–23 was read. No later-season data and no EPM value were read or used. Everything here is a retrospective replay on stable-lineup possessions with realized lineups, not a pregame forecast.

| Claim | Label |
| --- | --- |
| Split-penalty ridge is the verified #61 solver with a dense-oracle test | **Documented** (estimator), **Original** (use) |
| Grid, selection rule, exclusion control and reading rules | **Original** |
| Every number below | **Experimental**, retrospective, one season |

## Result in one paragraph

Separate penalties select $(\lambda_{off}, \lambda_{def})$ = (2,000, 8,000): a lighter penalty on offense and a heavier one on defense. Pooled over the four selection folds this beats the single penalty of 4,000 by 1.57 MSE units (95% −3.11 to −0.06), about a tenth of the model's gain over the league mean, and that figure is optimistic because the cell was chosen among 49 on those folds. On the playoff fold, scored after selection, the delta is **+3.57 (−1.61 to +8.75)**. By the frozen reading rule the split penalty is therefore **not distinguishable** from the single penalty, and the point estimate on P1 is the wrong sign. The random-game control shows that dropping the 170 adjudication-stratum games shifts player estimates by what dropping 170 ordinary games does. Its held-out effect differs from the random draws in direction (below), which is suggestive and not tested by the frozen rule. All 3,806 fits converged.

## Item 1: separate offense and defense penalties

Selection folds R1–R4 and the penalty grid follow the protocol: 7 × 7 cells from 500 to 32,000 on each axis, 196 fold fits. The selected cell is interior, so the grid was not extended. The best equal-penalty cell is (4,000, 4,000), the #23 choice, so the comparator is also the diagonal optimum.

Pooled R1–R4 held-out MSE (league mean 14,109.45). Rows are $\lambda_{off}$, columns are $\lambda_{def}$.

| $\lambda_{off}$ \ $\lambda_{def}$ | 500 | 1,000 | 2,000 | 4,000 | 8,000 | 16,000 | 32,000 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 500 | 14,115.3 | 14,106.7 | 14,101.8 | 14,099.7 | 14,099.4 | 14,099.9 | 14,100.8 |
| 1,000 | 14,110.9 | 14,102.4 | 14,097.4 | 14,095.3 | 14,095.0 | 14,095.5 | 14,096.4 |
| **2,000** | 14,109.9 | 14,101.3 | 14,096.3 | 14,094.2 | **14,093.8** | 14,094.4 | 14,095.2 |
| 4,000 | 14,111.2 | 14,102.6 | 14,097.5 | **14,095.4** | 14,095.0 | 14,095.6 | 14,096.5 |
| 8,000 | 14,113.4 | 14,104.8 | 14,099.8 | 14,097.7 | 14,097.4 | 14,098.0 | 14,098.9 |
| 16,000 | 14,115.7 | 14,107.1 | 14,102.1 | 14,100.1 | 14,099.8 | 14,100.5 | 14,101.5 |
| 32,000 | 14,117.5 | 14,109.0 | 14,104.1 | 14,102.0 | 14,101.9 | 14,102.6 | 14,103.6 |

The surface is flat. The 12 cells with $\lambda_{off}$ in 1,000 to 4,000 and $\lambda_{def}$ in 2,000 to 16,000 lie within 4 units of the minimum, and the single-penalty cell is 1.6 above it. Along the defense axis the surface is almost level from 4,000 to 16,000, so the data say defense wants no less than about 2,000 more than they pin 8,000. That a heavier defense penalty helps is consistent with the weak defensive signal in #23 (**Inferred**).

Held-out comparison at the selected cell (delta = MSE(split) − MSE(comparator) on identical possessions; negative favors the split penalty; 95% game-clustered percentile intervals, 2,000 resamples, seed 2023, temporal dependence between folds ignored):

| Block | Split MSE | Single MSE | Delta vs single | 95% interval | Delta vs league |
| --- | ---: | ---: | ---: | --- | ---: |
| R1 | 14,144.8 | 14,146.2 | −1.44 | −4.30 to +1.26 | −8.4 |
| R2 | 14,051.3 | 14,054.0 | −2.72 | −5.37 to −0.14 | −16.2 |
| R3 | 14,147.9 | 14,150.5 | −2.59 | −5.90 to +0.61 | −20.6 |
| R4 | 14,037.3 | 14,036.8 | +0.49 | −3.17 to +4.07 | −19.3 |
| Pooled R1–R4 (selection folds, optimistic) | 14,093.8 | 14,095.4 | −1.57 | −3.11 to −0.06 | −15.65 (−20.36 to −10.72) |
| **P1 playoffs (after selection)** | 14,017.7 | 14,014.2 | **+3.57** | −1.61 to +8.75 | −4.41 (−23.44 to +13.65) |

The single-penalty column reproduces #23 (pooled 14,095.4, P1 14,014.2). Ablations at the selected cell, pooled R1–R4 against the league mean: offense-only −11.65 (against −9.2 in #23) and defense-only +4.78 (against +1.1). The defense-only slice is now worse than the league mean because a defense penalty of 8,000 shrinks defensive effects further while the offense-only slice improves. In P1 the offense-only slice is +3.91 and the defense-only slice −0.79.

**Reading.** The pooled gain is small against its interval (the upper bound is −0.06) and it comes from a 49-cell search on the same folds. R4 and P1, the two later blocks, have positive point deltas. Under the frozen rule the split penalty is **not shown to improve held-out scoring**. P1 is one 84-game block (14,097 possessions), so this null is weak evidence against a real but small gain. The single penalty stays the baseline, and a split penalty is a candidate for later seasons only.

Final fit on all rows at (2,000, 8,000), in-sample and descriptive: offense estimate sd 1.41 (p05 to p95 −2.26 to 2.45), defense sd 0.52 (−0.91 to 0.87), total sd 1.54 (−2.49 to 2.86), offense–defense correlation 0.08, intercept 109.11. Against the single-penalty final fit (541 players in both): total RMS shift 0.58, maximum 1.96, correlation 0.931. The split penalty widens offense (sd 0.95 in #23) and narrows defense (0.81), as the penalties dictate. These are shrinkage settings, not findings about players. The split-half stability at the split penalty was out of scope.

## Item 2: size-matched random-game exclusion control

The observed set is the #23 stratum exclusion: 170 games (162 regular season, 8 playoff, 29,768 possessions) carrying any non-routine stratum, dropped from every fit at the single penalty. The run reproduces #23: the exclusion fit's pooled R1–R4 MSE is 0.79 below the full fit's (14,095.4 full), and the final-fit shift is total RMS 0.369, correlation 0.958. Random sets of 170 games (162 regular, 8 playoff) come from the 1,122 ordinary games. Variant A matches size and season type. Variant B also matches the date block (observed games per block: 63, 30, 23, 22, 24, 8). 300 draws each, seeds `[77, variant, draw]`. All draws had exactly 170 games.

| Statistic | Observed | Variant A draws: mean (sd), 95% range | Empirical p (frozen rule) | Variant B draws: mean (sd) | Empirical p |
| --- | ---: | --- | ---: | --- | ---: |
| Total estimate RMS shift | 0.369 | 0.361 (0.015), 0.333 to 0.392 | 0.28 | 0.362 (0.014) | 0.34 |
| Offense RMS shift | 0.257 | 0.258 (0.011), 0.239 to 0.280 | 0.51 | 0.258 (0.009) | 0.53 |
| Defense RMS shift | 0.269 | 0.255 (0.010), 0.236 to 0.277 | 0.09 | 0.255 (0.010) | 0.06 |
| 1 − correlation of totals | 0.042 | 0.040 (0.004), 0.034 to 0.047 | 0.29 | 0.040 (0.003) | 0.35 |
| Players dropped | 2 | 1.06 (1.06), 0 to 4 | 0.30 | 1.13 (1.05) | 0.32 |
| Possessions removed | 29,768 | 29,451 (120), 29,235 to 29,707 | 0.007 | 29,457 (126) | 0.013 |
| Held-out MSE delta, R1–R4 (exclusion minus full) | −0.79 | +1.28 (0.96), −0.71 to +3.07 | 0.75 (two-sided) | +1.23 (0.98) | 0.67 (two-sided) |
| Held-out MSE delta, P1 | +0.15 | +0.47 (1.98), −3.15 to +4.49 | 0.94 (two-sided) | +0.61 (2.00) | 0.93 (two-sided) |

**Estimate shifts.** Dropping the stratum games moves estimates by what dropping any 170 ordinary games moves them. No shift statistic is outside the random 95% range. The only close one is the defense RMS shift (p 0.06 to 0.09). The flagged games are slightly longer (about 1% more possessions than a random 170), so a linear adjustment of the shift for possessions removed (unplanned, within the draws) leaves the total shift at a residual z of 0.0 (A) and 0.5 (B) and the defense shift at 1.0 and 1.3. This agrees with the #23 note that shifts scale with the possessions removed and answers its open question: no stratum-level shift beyond chance is visible in aggregate. Per-stratum controls were not run.

**Held-out score.** The frozen two-sided $|\Delta|$ statistic has no power here, because the draws' effect is positive and the observed effect is negative with smaller magnitude. Looking at direction (an unplanned, descriptive tail count): dropping a random 13% of games raises held-out MSE by about 1.3 on average (fewer fit rows), and only 9% of draws are negative. The observed −0.79 is lower than 6 of 300 draws in A (lower-tail 0.023) and 4 of 300 in B (0.017). So removing the flagged games helped held-out scoring relative to removing the same number of ordinary games, by about 2 MSE units, while the same exclusion on the playoff fold is indistinguishable from chance. This is **Inferred**, descriptive and not corrected for the number of statistics looked at. It does not show that the strata are bad data, because the effect is two MSE units out of 14,000 and the paired interval for the exclusion contrast itself was not computed.

The ±10% possession-matched subset required by the protocol contains all 300 draws in both variants (draws stay within 2% of the observed possessions), so it adds nothing.

## Item 3: per-fit solver diagnostics

`results.json` stores a record for each of the 3,806 fits (stage, fold, penalties, rows, LSQR stop code, iterations, scaled residual norm, condition estimate, wall seconds). This closes the #23 deviation (aggregate diagnostics only).

| Quantity | Value |
| --- | --- |
| Fits and stop codes | 3,806, all LSQR code 2 (least-squares solution within tolerance, atol and btol 1e-12) |
| Iterations: min, median, max | 8, 23, 60 |
| Largest condition estimate | 106.0 (unequal-penalty selection fits: at most 101.9, at most 60 iterations) |
| Final 224,039-row fits | split 0.47 s, 36 iterations, condition 49.5. Single 0.41 s, 28 iterations, condition 34.4 (the same as #23) |
| Fit time: total, mean | 930.7 s, 0.245 s |
| Run time, peak resident memory | 975.8 s, 836 MiB (one machine, Python 3.14.3, NumPy 2.5.5, SciPy 1.18.1, DuckDB 2.0.1) |
| Fits by stage | selection 196, playoff 2, final 2, observed control 6, control A 1,800, control B 1,800 |

Split penalties do not hurt conditioning in this range. Wall times are from one run.

## Deviations and limitations

- **No deviation from the protocol** in the registered run: no grid extension was needed, the run used a clean tree at the recorded commit and the protocol file matched its recorded hash.
- Before the registered run, a 2-draw smoke run on the real rows wrote to a scratch directory. It ran at 07:53Z, after the protocol was frozen in e2168f3. It used the same code that was then committed unchanged as b032969. Its stderr lines that report outcomes (`selected` and `observed`) were filtered out before reading. Only structural facts were read from it (170 flagged games, 8 of them playoff, all fits converged, equal set sizes). No score or shift was read. The scratch output was deleted.
- The pre-declared two-sided statistic for held-out MSE delta is uninformative here, and the lower-tail counts above are a post hoc addition, labelled as such. The possession-linear adjustment is also post hoc.
- Selection ran on the same four folds that report the pooled delta, so only P1 is independent, and P1 is a single short block with a wide interval. Bootstrap intervals cluster by game and ignore dependence across folds.
- The random control draws from ordinary games and matches only size, season type and (in B) date block. It does not match team, lineup or possession counts beyond the near-equal totals. It was run at the single penalty only.
- 2022–23 is a development season. Nothing here is confirmatory, and neither result changes the baseline penalty.

## Reproduce

```sh
uv sync --locked --extra dev --extra pilot --extra rapm
uv run python -m bil.models.rapm.baseline_controls \
  data/processed/2022-23/issue-82-canonical-v1 data/processed/2022-23/issue-77-v1 \
  --pin-manifest-sha256 bd25cd0a8fe3702f5ae9021a435571224a3022c036d529f80b6e8ce108b56488
```

The runner verifies the manifest digest, the listed artifact digests, the `build_id` and the evidence tier, then refuses an existing output directory. It writes `results.json` (aggregates and every fit's diagnostics) and `manifest.json` (protocol SHA-256, code commit, clean-tree flag, versions, runtime, memory and output digest, `results.json` SHA-256 `dd3b16f9…3811f`). It takes about 16 minutes.
