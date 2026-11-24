# M2 report: independent RAPM baseline and gate assessment

[Issue #27](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/27) consolidates the M2 evidence for BIL's independent offensive/defensive RAPM baseline. This is a synthesis of existing reports. It fits and scores nothing new, and every number below is copied from the linked source report, ADR or experiment-log entry. Source data are attributed to NBA.com and stay private under the [pilot terms](../data-pilot.md). This document is aggregate only, with no player estimates or rankings.

**The M2 gate is not closed by this document.** Section 7 is a recommendation that waits for maintainer sign-off.

**Evidence tier.** Every empirical result is `retrospective_capture_bound`: a chronological replay on stable-lineup possessions with realized lineups, not a pregame forecast and not a strict rolling-origin backtest ([validation strategy](../validation-strategy.md)). No EPM value was read or used anywhere in M2. 2025–26 was not read.

| Claim type | Label |
| --- | --- |
| Zero-prior ridge with a free intercept, sparse LSQR solver, dated clock and decay arithmetic | **Documented** in this repository (verified against dense oracles and OpenRAPM) |
| Possession row set, target scaling, exposure, windows, penalties, comparators and verdict rules | **Original** |
| Every held-out metric | **Experimental**, retrospective |
| Explanations marked "Inferred" | **Inferred** |

## 1. Result in one paragraph

The estimator is numerically correct on controlled cases and agrees with OpenRAPM's solver to 6.790e-10 on shared fixtures. On real data, a two-season zero-prior RAPM (`W2`, $\lambda_o$ = 4,000, $\lambda_d$ = 8,000) beats the league-mean possession model on held-out possessions in both outer seasons, by −23.39 (−26.48 to −20.33) in regular-season MSE units. It does **not** beat a no-player context-only model that uses home, score and time terms: it is worse by +8.82 (+4.09 to +13.68). Most of that comparator's advantage comes from end-of-period run-out possessions that score zero, which the canonical rows keep under ADR-0019. Offense carries the whole player signal. Defense-only predictions are worse than the league mean. The playoffs are inconclusive. Individual estimates are noisy: split-half correlations of totals are 0.38 in the single-season baseline and 0.46 for the selected multi-season configuration. The estimator, row contract and evaluation harness are the reusable M2 deliverables. The ratings themselves are weak predictors of single-possession points, as the response noise (RMSE about 119) implies.

## 2. Frozen reproducible fit

### 2.1 Pins and commands

All inputs are hash-pinned. Runners verify the digests, refuse an existing output directory and write a manifest. Private outputs live under `data/processed/` and are never committed.

| Stage | Pin and command | Source |
| --- | --- | --- |
| Pilot build `issue-19-v6` (2022–23) | Manifest SHA-256 `89cb2e82af4d0fc4b7a95cf0f94b99b2b088361ffa893ce192de2b519d711570`. Snapshot `issue-5-v2`. See the [pilot guide](../data-pilot.md) | [PR #57](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/57) |
| Row contract and 2022–23 rows | `issue-59-v1`, rebuilt as `issue-82-canonical-v1` (manifest SHA-256 `bd25cd0a…56488`, 224,039 rows, byte-identical model rows). `python -m bil.data.rapm_rows` | [row contract](rapm-historical-rows.md), [PR #75](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/75), [PR #91](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/91) |
| Multi-season rows | `issue-93-v1` for 2018–19 through 2024–25, each pinned by manifest SHA-256, 0 identity violations across 16 checks | [data-pilot.md](../data-pilot.md#multi-season-row-sets-issue-93), [PR #94](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/94) |
| Single-season baseline (#23) | Protocol commit `26cb127`, runner `82b3452`, clean tree. `python -m bil.models.rapm.baseline` | [report](rapm-baseline-2022-23.md), [PR #78](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/78) |
| Context ablations (#24) | Protocol `1d6a885`, runner `9ad75e2`. `python -m bil.models.rapm.context_ablation` | [report](rapm-context-ablations-2022-23.md), [PR #83](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/83) |
| Row-set variants (#82) | Protocol v3 `abf011b`, rows at `0c6d111`. `python -m bil.models.rapm.cohort_comparison` | [report](rapm-no-action-2022-23.md), EXP-0011, ADR-0019 |
| Baseline controls (#77) | Protocol `e2168f3` (SHA-256 `7fb3ce72…8531b2`), runner `b032969`. `python -m bil.models.rapm.baseline_controls` | [report](rapm-baseline-controls-2022-23.md), EXP-0014, [PR #100](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/100) |
| Multi-season development (#26) | Protocol `86790ae` (SHA-256 `8787a112…4c99`), runner `ec4f127`, results `bd86289`. Output `issue-26-dev-v1`, manifest `8cbb4e5e…536a`. `python -m bil.models.rapm.multiseason dev` | [report](rapm-multiseason.md), EXP-0015 |
| Frozen outer addendum | Commit `57fe88e`, SHA-256 `23a9d3b7…420b`. Output `issue-26-outer-v1`. `python -m bil.models.rapm.multiseason outer --addendum … --addendum-sha256 … --dev-manifest …` | [addendum](rapm-multiseason-outer-addendum.md), [PR #104](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/104) |

The outer runner refuses to start unless the addendum matches its SHA-256, is committed and unmodified, the tree is clean, and the development manifest and protocol digests match. The development and outer runs each ran once.

### 2.2 The frozen configuration

Zero-prior two-penalty ridge, `W2`: rows played 1 to 730 days before each cutoff, unit weight, $\lambda_o$ = 4,000 and $\lambda_d$ = 8,000 in squared points-per-100 units, refit on a fixed calendar schedule (1 October, 1 December, 1 February, 1 April and the first playoff date). [ADR-0025](../DECISIONS.md) records it. It was **chosen on development folds only** (2021–22 and 2022–23) among eight candidates and then scored once on 2023–24 and 2024–25. It is a near-tie: `W2`, `W3`, `H365` and `H730` are within 0.3 MSE units, and the choice is unchanged in all four sensitivity scenarios. ADR-0025 is **Proposed** and awaits maintainer acceptance.

The single-season #23 baseline is the simpler reference: one shared ridge $\lambda$ = 4,000, unit weights, 2022–23. The split penalty from #77 is not adopted there (section 3.3).

### 2.3 Numerical verification (synthetic and benchmark)

| Check | Result | Source |
| --- | --- | --- |
| Noiseless synthetic recovery (EXP-0005) | All 24 effects within 2e-5 points per 100 possessions, effect RMSE 5.501e-6, intercept within 1e-6 | [rapm-synthetic.md](rapm-synthetic.md) |
| Sparse LSQR against an independent dense normal-equation oracle | Agree within 1e-8 on every coefficient and fitted rate | [rapm-synthetic.md](rapm-synthetic.md) |
| Prior-centered solver against a dense oracle (64 rows, penalties 7.5 and 62.5) | Maximum coefficient and fitted-rate deltas 8.9894e-11 and 1.4127e-10 | [rapm-prior-centered.md](rapm-prior-centered.md), ADR-0014 |
| Dated clock and decay against a dense oracle, half-lives 0.5 to 365 days and none | Maximum coefficient delta 6.5011e-11 | [rapm-dated-weights.md](rapm-dated-weights.md), ADR-0015 |
| OpenRAPM at commit `8cfb3df…` (EXP-0006), four fixtures | Maximum coefficient delta 3.429e-10, intercept 1.695e-10, fitted rates 6.790e-10 (limit 1e-8) | [rapm-open-benchmark.md](rapm-open-benchmark.md) |
| Multi-season design reuse against the dated reference on a real fold | 4e-15 | [rapm-multiseason.md](rapm-multiseason.md) |
| Timing audit, seven seasons | 0 leaks, 0 ledger disagreements | [rapm-multiseason.md](rapm-multiseason.md) |

The OpenRAPM comparison covers the shared two-role objective on synthetic fixtures. It does not compare published ratings, stint data, context terms or learned box-score priors. It was not rerun on the NBA rows.

### 2.4 Runtime and memory

All fits across all runs converged (LSQR stop code 2). Wall times come from single runs on one machine (Python 3.14.3, NumPy 2.5.5, SciPy 1.18.1, DuckDB 2.0.1). CI runs Python 3.12.

| Run | Fits | Time | Peak memory | Notes |
| --- | ---: | --- | --- | --- |
| #23 baseline | 53 logged | 19.1 s whole run, 14.5 s fitting | 898 MiB | Final 224,039-row fit: 0.41 s, 28 iterations, condition estimate 34.4 |
| #24 ablations | 83 | 33.8 s wall, 24.7 s fitting | 1,050 MiB | Iterations 18 to 28, maximum condition 34.5 |
| #77 controls | 3,806 | 975.8 s | 836 MiB | Iterations 8 to 60, maximum condition 106.0 |
| #26 development | 3,970 | 1,156 s | 3.10 GB | Largest fit 1,066,152 rows took 0.67 s, maximum condition 178 |
| #26 outer | 20 | 11.7 s | 2.93 GB | Fits of 434,000 to 447,000 rows, 0.21 s median |

A representative multi-season fit takes under one second. Memory is dominated by loading and the context SQL, not the solver.

## 3. Benchmark, results and uncertainty

### 3.1 Comparators (Documented in the [evaluation contract](../validation-strategy.md))

League-mean possession model (B0), context-only possession model (home, score, time, no players, `home_score_time` columns from #24), zero-prior RAPM, and a secondary `rapm_context` (RAPM fitted on the response minus the context offset). Metric: per-possession squared error in (points per 100 possessions)², with game-clustered percentile bootstrap intervals (2,000 resamples, seed 2023). Negative deltas favour the model. Regular season and playoffs are never pooled.

### 3.2 Held-out results by stage

| Stage (season, set) | Model against league mean | Model against context-only | Source |
| --- | --- | --- | --- |
| #23, 2022–23 regular, pooled R1–R4 (selection folds, optimistic) | −14.1 (−18.3 to −9.8), 0.10% of MSE | not yet available | [#23](rapm-baseline-2022-23.md) |
| #23, 2022–23 playoff fold P1 (after selection) | −8.0 (−24.0 to +7.5) | not yet available | [#23](rapm-baseline-2022-23.md) |
| #26 development, `W2`, 2021–22 and 2022–23 regular | −16.24 (−19.25 to −13.20) | +12.28 (+7.61 to +16.71) | [#26](rapm-multiseason.md) |
| #26 development, `W2`, playoffs | −11.26 (−21.04 to −2.02) | +35.21 (+19.58 to +51.39) | [#26](rapm-multiseason.md) |
| **#26 outer, regular, 2023–24 and 2024–25 (418,479 possessions, 2,423 games)** | **−23.39 (−26.48 to −20.33)** | **+8.82 (+4.09 to +13.68)** | [#26](rapm-multiseason.md) |
| #26 outer, playoffs (26,725 possessions, 165 games) | −14.03 (−30.24 to +1.39) | +15.56 (−6.03 to +36.32) | [#26](rapm-multiseason.md) |

Outer per season, regular: 2023–24 −21.30 (−25.51 to −17.09) against league and +12.74 (+6.55 to +19.11) against context. 2024–25 −25.50 (−29.84 to −21.25) and +4.85 (−2.61 to +11.55). The RAPM delta against the league mean is negative in all eight regular-season outer blocks. An independent reviewer reproduced the 2023–24 regular-season delta of −21.30.

Secondary, regular season, outer: the context-only model beats the league mean by −32.21 (−36.01 to −28.46). RAPM with a context offset beats context-only by −24.73 (−27.88 to −21.50) and the league mean by −56.94 (−61.72 to −52.18). It was frozen as secondary and not selected on. Team-game RMSE in points, regular season: `rapm` 10.61, league 11.08, context 11.51, `rapm_context` 11.02.

### 3.3 Negative and failed results

These are recorded honestly and none changed a frozen choice.

1. **RAPM alone does not beat the context-only comparator out of time.** Development +12.28, outer +8.82 (worse in 2023–24, inconclusive in 2024–25). In the single season, a context-only model with home, score and time beats zero-context player RAPM by −30.50 against the league mean, against RAPM's −14.09. Player RAPM adds a further −15.8 on top of context in 2022–23 ([#24](rapm-context-ablations-2022-23.md)) and −24.73 in the outer seasons. The honest comparator for any informed RAPM is therefore the context offset model, not the league mean (ADR-0025 consequence, proposed).
2. **The context comparator's advantage is largely structural.** About 80% of the time gain in 2022–23 comes from 996 run-out or no-action possessions that score exactly 0, 962 of them starting on `period_end`. On the row sets that drop run-outs, the `T_fit` gain falls from −25.69 to about −5 and the context-only `HST` advantage over zero context disappears (+4.21 and +4.66, intervals including 0) ([#82](rapm-no-action-2022-23.md)). This is a caveat on reading the canonical time effect, and not a reason to exclude the rows (ADR-0019).
3. **Defense-only predictions are worse than the league mean.** +1.1 at $\lambda$ = 4,000 in #23, +4.78 at the split penalty, +9.54 for `W2` in development and +4.19 (+1.31 to +6.98) in the outer regular season, despite doubling the defense penalty. Offense-only is −17.66 (−20.38 to −15.00) in the outer regular season. Defensive effects are poorly identified (Inferred).
4. **The split penalty is not distinguishable from the single penalty.** #77 selected ($\lambda_{off}$, $\lambda_{def}$) = (2,000, 8,000). The pooled R1–R4 delta against the single penalty is −1.57 (−3.11 to −0.06) and optimistic (49-cell search on the same folds). On the playoff fold, scored after selection, it is **+3.57 (−1.61 to +8.75)**, the wrong sign. By the frozen rule it is "not shown to improve held-out scoring" ([EXP-0014](../experiment-log.md)). The #26 `W2` configuration uses split penalties anyway, because every candidate selected $\lambda_d = 2\lambda_o$, which is a development choice and not confirmed by #77's outer-fold evidence.
5. **Literal ADR-0019 option (b) failed verification.** The maintainer's option (b) excluded the 962 `period_end`-start possessions, conditional on verification. All 962 begin after a change of control with 3 to 24 s on the clock (median 9 s), 729 in the final period, so the condition failed. The canonical set keeps them (section 4.1). A first audit that measured duration over the possession's own events was invalid, and protocol v2 was superseded.
6. **Weak penalties lose to the league mean.** At $\lambda$ = 250 and 500 the pooled delta is +25.2 and +5.8 in #23, with defense-only worst. In the synthetic fixture, a 48-row fit at $\lambda$ = 0.01 has expected-rate RMSE 76.031 against 9.366 for the intercept-only model.
7. **Home court is inconclusive** as a separate control (−0.39, −1.94 to +1.15) and hurt on fold R4. Late-blowout down-weighting (+0.00) and exclusion (+0.17) were rejected. Fitted control and the eligible offset are indistinguishable on held-out data. Score terms worsen team-game RMSE even as they improve per-possession scoring.
8. **Playoffs are inconclusive for player RAPM** against both baselines in the outer seasons, and the development playoff interval that excluded zero (−11.26) now includes it (−14.03). Every model over-predicts playoff scoring by 2 to 4 points per 100.
9. **Stability is modest.** Split-half correlation of totals 0.38 (#23) and 0.46 for `W2` (0.12 for players under 2,000 on-court possessions, 0.43 at 10,000 or more). Year-over-year r of 0.76 for `W2` is mostly mechanical overlap, and `W1`'s 0.36 is the only disjoint-data figure. Stability does not predict accuracy: `W5` and `H730` are the most stable and score slightly worse.
10. **Calibration.** The `rapm` calibration slope in the outer regular season is 1.12 (1.04 to 1.20), so predictions are under-dispersed, and the intercept runs 0.65 points per 100 low (Inferred: shrinkage slightly too hard, and the two-season window lags a rise in league scoring).
11. **Dropping stratum games is not special.** Removing the 170 games with non-routine adjudication strata moves estimates like removing 170 random ordinary games (total RMS shift 0.369 against 0.361, sd 0.015). A descriptive held-out effect (−0.79, lower than 2% of random draws) is Inferred and uncorrected.

### 3.4 Exclusions and sensitivity

- **Row exclusions.** Only stable-lineup possessions are modeled. Multiple-lineup possessions (32,417 of 256,456 accepted in 2022–23, 12.64%) score 138.20 control points per 100 against 111.18 for retained rows, so results describe stable-lineup scoring (ADR-0013). Pilot-excluded possessions and unresolved possessions carry zero exposure. Quarantined games contribute no rows.
- **Season and window sensitivity** ([#26](rapm-multiseason.md)). The selection is unchanged when excluding 2018–19, 2021–22, overtime, or the `no_livedata` seasons. Excluding the `no_livedata` stratum makes the 2021–22 `W2` folds 1.40 (+0.68 to +2.13) worse, so the weaker-verification season adds value. Excluding 2021–22 shifts the final fit most (RMS 0.85, r = 0.81).
- **Row-set variants** ([#82](rapm-no-action-2022-23.md)). RAPM against league is −14.09 (canonical), −13.16 (`period_end_start`) and −13.17 (`no_action`) on each variant's own cohort. On canonical held-out rows, fits on the variant rows score 1.74 and 1.86 MSE units better, which describes the sample and does not select the rule.

### 3.5 Uncertainty reported

Game-clustered 95% percentile bootstrap intervals throughout, calendar-week-clustered intervals for #26 (nearly the same), per-block and per-fold deltas, split-half and refit stability, random-draw controls (300 draws, two matching variants) and calibration slopes. No model produces a predictive interval, so interval coverage is not reported. Intervals ignore dependence between refit blocks. The week-clustered intervals of the R4 blocks are degenerate and the pooled sets are unaffected.

## 4. Accepted target definitions

### 4.1 Canonical row set (ADR-0019, accepted by the maintainer on 2026-11-23)

- **Rows.** One unit-weight row per pilot-accepted possession with a single actual offense/defense lineup pair (`eligible`). The canonical rows equal `issue-59-v1` and add no exclusion beyond the pilot's. The pilot already excludes genuine pseudo-possessions, the period-ending intervals with under 3 s left (1,567 in 2022–23). Run-outs, held balls and other outcome-free endings stay. Eligibility never depends on later actions or realized outcomes.
- **Sensitivity variants** selectable with `--variant`: `period_end_start` and `no_action`, never the default.
- **Departure from literal option (b).** The maintainer chose option (b) conditional on verification. Verification failed (section 3.3 item 5), and the principle was applied instead. **The maintainer may override this.** See section 7.
- **Cohort size.** 224,039 eligible possessions in 2022–23 (209,942 regular, 14,097 playoff) from 256,456 accepted. Row counts for 2018–19 through 2024–25 are in the [pilot guide](../data-pilot.md#multi-season-row-sets-issue-93).

### 4.2 Response, signs and exposure ([ADR-0012](../DECISIONS.md), [ADR-0014](../decisions/0014-prior-centered-rapm.md), [ADR-0015](../decisions/0015-dated-rapm-clock-and-decay.md))

- **Response.** $y_i$ is 100 times the points scored by the offense on possession $i$, from the canonical `control_possession` score allocations. Dead-ball (`unassigned_dead_ball`) and unresolved points carry zero modeling points and zero exposure. This is a possession-level target, not a stint margin.
- **Offense and defense.** The prediction is $\widehat y_i = b + \sum_{p \in O_i} o_p - \sum_{p \in D_i} d_p$ in points per 100 possessions. Positive offense raises scoring. Positive defense lowers the opponent's scoring. Total impact is $o_p + d_p$ on the same scale.
- **Centering.** The intercept is free. Each player block is centered on the unweighted mean over the fitted player universe (zero priors), which minimizes the ridge penalty within the prediction-equivalent class. Ratings depend on the fitted player universe and on the weight-to-penalty scale.
- **Exposure and weights.** One possession is one opportunity with unit weight. Exposure per player is the count of eligible possessions on court in each role, so player-role exposure sums to five times the eligible possession count in each role. Weights are never renormalized, so a decay or window changes the effective penalty. Players absent from the fit take zero effect (an unseen player).
- **Clock.** Dated fits keep rows with `played_date` strictly before the cutoff in Eastern calendar dates. The evidence has played dates but no verified historical publication times.
- **2022–23 exposure profile** (#23): median 1,786 offensive possessions per player (p05 54, p95 4,812), 541 players, 34.4% of players under 1,000 offensive possessions.

Status of the formal records: ADR-0012, ADR-0014, ADR-0015 and ADR-0019 are Accepted. **ADR-0013**, which limits the baseline to stable-lineup possessions, is still marked Proposed in `DECISIONS.md`, although every M2 result rests on it. ADR-0025 is Proposed.

## 5. Remaining EPM uncertainties

The register [epm-uncertainties.md](epm-uncertainties.md) now carries an "M2 status" note on each M2-relevant entry. Agreement with EPM resolves none of them.

| ID | M2 status | What M2 settled | What stays open |
| --- | --- | --- | --- |
| EPM-U01 target and exclusions | Partially resolved (Original) | Row, response and exposure definitions, ledger reconciliation with 16 identity checks, ADR-0019 exclusion rule, garbage-time down-weighting and exclusion rejected | Multiple-lineup possessions (12.64%) are excluded and not modeled. EPM's actual target and garbage-time rule are unpublished. ADR-0013 is Proposed |
| EPM-U08 home and score state | Open (Experimental) | One-season and outer-season context evidence: time and score help held-out scoring, home is inconclusive, fitted and offset treatments are indistinguishable | The multi-season baseline carries no context terms. Neutral court is untestable (flags null). Time gain depends on run-out eligibility. No registered outer context test |
| EPM-U09 prior strength | Open (M5) | A zero prior recovers baseline RAPM exactly on synthetic data, and prior penalties pull toward priors in the numerical tests | Penalty strength with real SPM priors, rookies and missing priors |
| EPM-U10 signs and centering | Resolved for the estimator contract (Original) | Sign, unit, role-block centering and total-impact convention in ADR-0012 and ADR-0014, with oracle checks | Daily league centering of team ratings is not implemented. Reporting rules for components |
| EPM-U12 snapshots and cutoffs | Partially addressed | All M2 results are labeled `retrospective_capture_bound`, with played-date clocks | No contemporaneous publication evidence exists. No live-equivalence claim |
| EPM-U13 feeds and parser | Partially resolved (Original) | 26 `check` invariants pass for every build, time-weighted Bentes lineup agreement of 99.97% or better in the 2016–17, 2017–18 and 2019–20 builds (older-era probes 99.996% to 100%), discrepancies tracked by season and reason (EXP-0007, EXP-0009, EXP-0012, EXP-0013) | EPM's exact feed is unknown. Weaker-verification strata remain (section 6). 2017–18 fails the hard limits |
| EPM-U14 recency weighting | Partially resolved (Experimental) | Strict clock and unnormalized exponential decay (ADR-0015). Windows of 1, 2, 3 and 5 seasons and decays with 90- to 730-day half-lives compared. The result is a near-tie | Interaction with prior strength (M5). Whether any default survives the 2025–26 holdout. EPM's clock and factors |

U02 to U07 and U11 belong to M3 and later and have no M2 evidence.

## 6. Coverage limits for downstream SPM (#28 and #30)

These limits describe what the RAPM baseline can supply as a target. The box-score SPM reference window is 2003–04 through 2022–23 ([validation strategy](../validation-strategy.md)).

### 6.1 Eligible seasons

Eligibility follows [ADR-0022](../DECISIONS.md) and the [matrix](../data-pilot.md#season-eligibility-matrix-adr-0022). Revised class on `main` at `7f9b85e`:

| Seasons | Status | RAPM fitted? |
| --- | --- | --- |
| 2018–19, 2019–20, 2020–21, 2021–22, 2022–23 | Primary training (2018–19 and 2021–22 conditional on the missingness analysis) | Yes, development folds |
| 2023–24, 2024–25 | Outer validation (2024–25 playoffs carry a 0.135% unresolved share, a documented warning) | Yes, outer scoring only |
| 2025–26 and later | Confirmatory holdout, never read | No |
| 2015–16, 2016–17, 2005–06, 2006–07, 2007–08 | Eligible history with warnings, row sets built, weaker verification | **No** |
| 2004–05, 2012–13, 2013–14, 2014–15 | Unavailable: miss a 97% coverage floor by 1 to 6 games | No |
| 2017–18 | Excluded: fails coverage (85.5%) and unresolved limit (0.391%) | No |
| 2008–09 through 2011–12 | Not built. A same-clock rebound rule is needed. 2010–11 probe: 96.5% regular-season coverage | No |
| 2001–02 through 2003–04 | Not probed | No |

No RAPM has been fit on any season before 2018–19, so #28's full 2003–04 through 2022–23 target does not yet exist. Where hard limits are missed, seasons are recorded unavailable and no threshold was loosened.

### 6.2 Weaker-verification strata

- `no_livedata` (ADR-0020): all of 2018–19 and 2019–20, and every season before 2020–21. Starters fall back to the box-guided search, and V3 period-score defects cannot be adjudicated. Dropping this stratum removes about 39% of the 2018–19 to 2022–23 cohort. Its sensitivity in #26 is small and in the direction of adding value.
- `no_datanba`: seasons before 2016–17 have no data.nba relabels or period scores. 2016–17 has data.nba without `ord`.
- `v2_home_designation` (ADR-0017): five 2024–25 games.
- Weaker starter verification in older eras: Bentes agrees with 9 of 9, 11 of 13, 10 of 13 and 13 of 14 inferred team-periods in the 2016–17, 2014–15, 2010–11 and 2005–06 probes ([backfill feasibility](backfill-feasibility.md)).
- Missingness flags in the conditional seasons: 2018–19 quarantines concentrate in overtime games (9 of 67 overtime games against 15 of 1,163 regulation games) and in November 2018 ([season quality](season-quality-2017-2025.md)).

### 6.3 Unseen players

Any prior or window excludes players absent from the training window. In the outer seasons, 14.6% (2023–24) and 14.8% (2024–25) of regular-season scored possessions involve an unseen player, about 51% in the first block R1 and 3 to 4% afterwards (Inferred: players new to the league or absent from the two-season window). In 2022–23, 6.6% of pooled regular-season scored possessions had one. Low exposure is the least reliable and the most shrunk: split-half r is 0.12 under 2,000 on-court possessions. SPM targets for low-exposure players are therefore mostly shrinkage.

### 6.4 Playoffs

Playoffs are scored separately and never pooled. RAPM is inconclusive in the playoffs against both baselines (section 3.3 item 8). The playoff fit includes the whole regular season, so no playoff possession has an unseen player. Playoff samples are small (165 outer games). Models over-predict playoff scoring by 2 to 4 points per 100. EPM documents playoffs for box-score SPM but the tracking-window inclusion is unspecified (EPM-U03). Playoff unresolved shares are higher than regular-season shares in several seasons (for example 0.404% in 2016–17 and 0.135% in 2024–25).

### 6.5 Other limits for a RAPM target

- Realized lineups and stable-lineup possessions only. The multiple-lineup group scores differently (138.20 against 111.18 per 100).
- Defense is poorly identified. A defense-only RAPM target should carry its uncertainty or be pooled with offense. #30 should treat defense targets as weak.
- Neutral-site flags are null everywhere, so every game is coded by its nominal home team.
- Estimates are shrunk hard (total spread about 1.3 points per 100 in 2022–23). Out-of-time label construction for SPM must respect the evaluation contract, because the 2022–23 pilot season overlaps the published SPM training windows.
- ADR-0025 proposes that informed-RAPM work compare against the context offset model. #30 should adopt a comparator only after maintainer sign-off.

## 7. M2 gate assessment (proposal, awaiting maintainer sign-off)

[PROJECT_PLAN §M2](../PROJECT_PLAN.md) lists four work items and one exit gate: "Numerical correctness demonstrated on controlled cases; multi-season impact ratings and holdout reports reproducible." Ratings below are a proposal. They do not close the gate.

| # | M2 item | Assessment | Evidence |
| --- | --- | --- | --- |
| 1 | Sparse design matrices and ridge estimators, benchmarked against independent reference implementations | **Met** | Dense-oracle agreement within 1e-8 (largest observed 6.5e-11 to 8.99e-11), OpenRAPM agreement to 6.790e-10 (EXP-0006, PR #65). Only one external implementation, on shared synthetic fixtures |
| 2 | Synthetic known-coefficient simulations, sensitivity checks, solver equivalence | **Met** | EXP-0005: recovery within 2e-5, penalty and sample sensitivity, paired-player aliasing, weight-and-penalty rescaling invariance (PR #18, #71, #73) |
| 3 | Home, score-state, temporal and regularization choices introduced separately | **Met as experiments, with open verdicts** | #24 (home, score, time, offset versus fitted, weighting), #77 (split penalty), #26 (window and decay). Home and fitted-versus-offset are undecided, no context enters the multi-season baseline, and the time effect depends on run-outs |
| 4 | Multi-season RAPM with coefficient stability by sample and window | **Met, with weak stability** | Seven seasons, 1,066,152 development rows, eight candidates, split-half, year-over-year and refit stability, four sensitivity scenarios. Split-half r 0.46 for `W2`, near-tied selection |
| 5 | Exit gate, part 1: numerical correctness on controlled cases | **Met** | Items 1 and 2 |
| 6 | Exit gate, part 2: multi-season impact ratings reproducible | **Partially met** | Pinned inputs, frozen protocol and addendum, a runner that enforces them, 3,970 and 20 converged fits, and one independent reproduction of a headline delta. Not yet independently re-run end to end from raw data. Each run executed once. The selection (ADR-0025) is not accepted and is a near-tie. Ratings are noisy and RAPM does not beat context-only |
| 7 | Exit gate, part 3: holdout reports reproducible | **Partially met** | Outer-validation reports for 2023–24 and 2024–25 follow a pre-frozen addendum and report negative results. They are development evidence for later registration. The confirmatory 2025–26 holdout has not been run, and the playoff outer result is inconclusive. Whether M2 requires the confirmatory run is a maintainer decision |

**Recommendation.** Numerical correctness (items 1, 2 and 5) is established. The empirical items (3, 4, 6 and 7) are met or partly met as development evidence and carry no confirmatory claim. The proposed overall assessment is **partially met, with the numerical gate met**, and a recommendation that the maintainer consider closing the gate with the listed caveats recorded after deciding the open items below. The gate stays open until the maintainer says otherwise.

### Open for the maintainer

1. **ADR-0025 acceptance.** Proposed and independently reviewed (approved). Accept, modify (for example `W3`, `H365` or `H730`, which are equally supported) or reject `W2` with split penalties. The outer seasons were not used to check the choice.
2. **ADR-0019 departure from literal option (b).** Confirm the canonical row set that keeps the 962 `period_end` run-outs, or override and adopt `period_end_start` (the sensitivity variant). The row set affects the size of the context comparator's advantage. Repository documents record the independent re-review of the canonical decision as pending (EXP-0011, #74 and #82 handoff). This report found no later record of it.
3. **ADR-0013.** Still marked Proposed. Accept the stable-lineup restriction (12.64% of accepted possessions excluded), or ask for a multiple-lineup treatment.
4. **ADR-0023.** Proposed, opt-in, off by default (event-order repair from data.nba entry order). It is not used by any M2 result. Even with it, 2017–18 stays 5 games short of coverage (96.6%) and 0.283% unresolved against the 0.1% limit. The safeguard options (i) to (iv) are undecided. Issue #99 (2017–18) is blocked on it.
5. **#53 backfill status.** Batches 1 to 3 are merged ([#96](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/96), [#97](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/97), [#98](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/98); PRs #101, #102, #103). #53 itself is open. Still open: 2008–09 through 2011–12 (needs a same-clock rebound rule), 2001–02 through 2003–04 (probe), 2017–18 (#99). Four seasons are unavailable (2004–05, 2012–13, 2013–14, 2014–15). The M2 multi-season fit does not need this history. #28 does.
6. **Comparator for informed RAPM.** Whether #30 and later judge RAPM against the context offset model and on which cohort (canonical or `no_action`).
7. **Split penalty and context in a later reference.** #77 does not distinguish the split from a single penalty, yet `W2` uses it. Whether context terms (EPM-U08) enter a reference specification requires a registered outer-fold protocol that does not yet exist.
8. **Confirmatory 2025–26 holdout.** Whether and when to register it. It was never read.
9. **Experiment log.** #23 and #24 have no EXP entries in `experiment-log.md`. The reports stand in for them. Propose adding entries, a documentation follow-up outside this task's scope.

## 8. Reproduce and verify this report

Every figure above comes from the linked reports, ADRs and EXP-0005, EXP-0006, EXP-0011, EXP-0012, EXP-0013, EXP-0014 and EXP-0015. To reproduce the fits, use the commands in each report's Reproduce section, with the pins in section 2.1 and the locked environment:

```sh
uv sync --locked --extra dev --extra pilot --extra rapm
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

The private data directories required by the fit commands are not in the repository.
