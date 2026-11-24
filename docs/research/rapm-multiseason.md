# Multi-season RAPM: development selection, stability, sensitivity and outer validation

[Issue #26](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/26) fits ordinary offensive/defensive RAPM on several seasons, selects a temporal weighting and separate offense and defense penalties in chronological development folds inside 2018–19 through 2022–23, and then scores the frozen choice on the outer-validation seasons 2023–24 and 2024–25. Source data are attributed to NBA.com and stay private under the [pilot terms](../data-pilot.md). Player-level estimates stay in the private output directories. This report contains aggregates only, with no named players or rankings.

**Provenance.**
- The [development protocol](rapm-multiseason-protocol.md) was committed (`86790ae`) before any real-data fit.
- The runner and tests followed (`ec4f127`). That commit also added a pre-run clarification to the protocol for candidates with an empty fit window, which a synthetic test exposed (see Deviations).
- The development run happened once, from a clean tree at `ec4f127`, to `data/processed/multiseason/issue-26-dev-v1`. Its protocol SHA-256 was `8787a112…4c99`.
- No 2023–24, 2024–25, 2025–26 or 2026–27 row was read by Phase 1. No EPM value was read or used.

**Evidence tier: `retrospective_capture_bound`.** Every result is a chronological replay on stable-lineup possessions with realized lineups. None is a strict rolling-origin backtest or a pregame forecast.

| Claim | Label |
| --- | --- |
| The sparse ridge solver and dated clock | **Documented** in this repository ([#6](rapm-synthetic.md), [#64](rapm-dated-weights.md)). Design reuse matched the dated reference to 4e-15 on a real fold. |
| Candidates, folds, search, baselines, stability and sensitivity design | **Original** |
| Every metric below | **Experimental**, retrospective |
| Explanations marked "Inferred" | **Inferred** |

## Development results (Phase 1)

### Data and folds

- **Rows.** 1,066,152 canonical rows from 6,164 accepted games and 970 players: 223,686 (2018–19), 195,128 (2019–20), 200,256 (2020–21), 223,043 (2021–22) and 224,039 (2022–23).
- **Timing audit.** Every season's pre-possession covariate audit passed.
- **Scoring.** The ten scored blocks are R1–R4 and P of 2021–22 and 2022–23. Selection used the eight regular-season blocks: 418,731 possessions from 2,427 games. The playoff check has 28,351 possessions from 171 games.

### Selection

The selected configuration is **`W2`: two seasons (730 days) of unit-weight history, $\lambda_o$ = 4,000, $\lambda_d$ = 8,000**. Its pooled development MSE is 14,109.76 (points per 100)². Both baselines selected `W1`: one season, league-mean MSE 14,126.00 and context-only MSE 14,097.47.

Each candidate below is shown at its own selected penalties. Δ = MSE(model) − MSE(baseline) on identical possessions, so negative favours the model. Intervals are 95% game-clustered bootstrap (2,000 resamples, seed 2023). League and context are the selected `W1` baselines. "Same-window league" is the mean under the candidate's own weights.

| Candidate | $\lambda_o$ / $\lambda_d$ | Pooled MSE | Δ vs league | Δ vs context | Δ vs same-window league | Offense-only Δ vs league | Defense-only Δ vs league | Playoffs Δ vs league | Playoffs Δ vs context |
| --- | --- | ---: | --- | --- | --- | ---: | ---: | --- | --- |
| `W1` | 4,000 / 8,000 | 14,111.96 | −14.04 (−16.78 to −11.38) | +14.49 (+9.94 to +18.61) | −14.04 | −10.82 | +2.86 | −7.32 (−17.23 to +2.61) | +39.16 (+23.87 to +55.22) |
| **`W2`** | **4,000 / 8,000** | **14,109.76** | **−16.24 (−19.25 to −13.20)** | **+12.28 (+7.61 to +16.71)** | −16.86 | −12.43 | +9.54 | −11.26 (−21.04 to −2.02) | +35.21 (+19.58 to +51.39) |
| `W3` | 4,000 / 8,000 | 14,109.92 | −16.08 (−19.17 to −12.94) | +12.45 (+7.56 to +17.00) | −17.57 | −12.04 | +14.64 | −15.27 (−24.93 to −5.98) | +31.20 (+15.93 to +47.16) |
| `W5` | 4,000 / 8,000 | 14,110.65 | −15.35 (−18.58 to −12.09) | +13.18 (+8.27 to +17.88) | −19.07 | −11.15 | +21.26 | −16.80 (−26.69 to −7.03) | +29.68 (+13.75 to +46.34) |
| `H90` | 2,000 / 4,000 | 14,114.05 | −11.95 (−14.57 to −9.40) | +16.58 (+12.10 to +20.82) | −13.86 | −8.61 | +3.85 | −2.45 (−12.90 to +8.33) | +44.02 (+28.13 to +59.71) |
| `H180` | 2,000 / 4,000 | 14,111.29 | −14.71 (−17.70 to −11.78) | +13.82 (+9.05 to +18.26) | −16.04 | −10.94 | +7.27 | −7.99 (−18.73 to +2.56) | +38.48 (+22.73 to +55.25) |
| `H365` | 2,000 / 4,000 | 14,109.98 | −16.02 (−19.23 to −12.73) | +12.51 (+7.46 to +17.19) | −17.70 | −11.94 | +14.88 | −12.27 (−22.93 to −1.83) | +34.20 (+18.04 to +50.65) |
| `H730` | 4,000 / 8,000 | 14,110.03 | −15.97 (−18.82 to −13.03) | +12.56 (+7.87 to +16.96) | −18.38 | −11.55 | +13.16 | −14.66 (−23.91 to −5.62) | +31.82 (+16.81 to +47.42) |

How to read the table:
- **The temporal choice matters little.** Every candidate except `H90` is within 1.3 MSE units of the best. The top four (`W2`, `W3`, `H365`, `H730`) are within 0.3 units, well inside the intervals. The selection is a near-tie, and the scores are optimistic for the chosen configuration.
- **The defense penalty is always twice the offense penalty.** Every candidate selected $\lambda_d = 2\lambda_o$. Defense-only predictions are worse than the league mean for every candidate, and more so with longer history (+2.9 for `W1`, +21.3 for `W5`). Offense carries the whole gain, as in #23 (Inferred: defensive effects are poorly identified and drift).
- **Player RAPM beats the league mean in every candidate. It loses to the context-only baseline by 12 to 17 points in every candidate**, in the regular season and in the playoffs. This is the #24 single-season finding, repeated over two scored seasons. Most of the context gain comes from end-of-period possessions, which are kept under [ADR-0019](../DECISIONS.md) (see [#82](rapm-no-action-2022-23.md)).
- **Penalty search for `W2`.** The shared grid chose 4,000. With $\lambda_o$ held at 4,000, $\lambda_d$ = 8,000 (14,109.76) beat 4,000 (14,110.33) and 16,000 (14,110.17). With $\lambda_d$ held at 8,000, $\lambda_o$ = 4,000 beat 2,000 and 8,000. The penalty surface is flat to about 0.6 MSE units from 2,000 to 16,000.

### Selected configuration in detail (`W2`, development)

| Set | Possessions (games) | League MSE | `rapm` Δ vs league | `rapm` Δ vs context | `context` Δ vs league | `rapm_context` Δ vs context |
| --- | --- | ---: | --- | --- | --- | --- |
| Regular season, pooled R1–R4 | 418,731 (2,427) | 14,126.00 | −16.24 (−19.25 to −13.20) | +12.28 (+7.61 to +16.71) | −28.53 (−31.72 to −25.21) | −16.62 (−19.72 to −13.62) |
| Playoffs, pooled P | 28,351 (171) | 14,173.24 | −11.26 (−21.04 to −2.02) | +35.21 (+19.58 to +51.39) | −46.47 (−59.31 to −34.00) | −7.02 (−16.37 to +2.42) |

- **Week-clustered intervals.** They are nearly the same as the game-clustered ones. For example, regular-season `rapm` vs league is −19.08 to −13.48.
- **Team-game RMSE in points (regular season).** `rapm` 10.45, league 10.70, context 11.05, `rapm_context` 10.77. RAPM is best on team-game totals even though context wins per possession. This is the #24 pattern: the context terms help per possession but worsen game totals.
- **RAPM vs league by block.** The delta is negative in all eight regular-season blocks, from −9.1 to −36.5. Against context, it ranges from −17.3 (2021–22 R4) to +26.0 (2022–23 R2).
- **`rapm_context`.** This is the secondary model, scored for information. It beats the context-only baseline in the regular season (−16.6). It ties context in the playoffs.

### Effective weight and penalty scales

Values are means over the eight regular-season blocks, at each candidate's selected penalties. "Ratio" is the penalty divided by the median weighted offensive possessions per observed player, which is the effective shrinkage per typical player.

| Candidate | Rows | Total weight | Kish effective rows | Median weighted offensive possessions | $\lambda_o$ ratio | $\lambda_d$ ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `W1` | 238,554 | 238,554 | 238,554 | 1,600 | 2.54 | 5.12 |
| `W2` | 440,524 | 440,524 | 440,524 | 2,144 | 1.89 | 3.81 |
| `W3` | 623,048 | 623,048 | 623,048 | 2,261 | 1.79 | 3.61 |
| `W5` | 825,773 | 825,773 | 825,773 | 2,486 | 1.62 | 3.25 |
| `H90` | 825,773 | 85,340 | 176,479 | 137 | 18.26 | 37.14 |
| `H180` | 825,773 | 160,517 | 312,697 | 353 | 6.02 | 12.11 |
| `H365` | 825,773 | 292,199 | 529,509 | 781 | 2.63 | 5.31 |
| `H730` | 825,773 | 455,269 | 710,906 | 1,336 | 3.03 | 6.09 |

Short half-lives shrink much harder, because the weights are not renormalized (ADR-0015). The best decays (`H365`, `H730`) land at effective ratios near those of the windows, and score about the same.

`W5` and the decay cap are truncated by the 2018–19 data start. They reach at most about three seasons back for 2021–22 folds and four for 2022–23 folds. `W3` equals `W5` at the 2021–22 R1 cutoff. In the outer seasons `W5` would be complete. It was not selected.

## Coefficient stability (development)

Each candidate is shown at its selected penalties. Correlations are of total (offense + defense) estimates. RMS is the root-mean-square change in points per 100. Exposure bands are by unweighted on-court possessions.

| Candidate | Split-half r (players) | Year-over-year r / RMS (players) | Refit volatility, mean RMS / r | Playoffs added, mean RMS / r | Final-fit total SD |
| --- | --- | --- | --- | --- | ---: |
| `W1` | 0.41 (398) | 0.36 / 1.37 (436) | 0.54 / 0.88 | 0.36 / 0.95 | 1.12 |
| **`W2`** | **0.46 (496)** | **0.76 / 0.96 (628)** | **0.41 / 0.95** | **0.25 / 0.98** | **1.31** |
| `W3` | 0.52 (560) | 0.86 / 0.76 (736) | 0.37 / 0.96 | 0.13 / 1.00 | 1.41 |
| `W5` | 0.56 (692) | 0.95 / 0.46 (885) | 0.25 / 0.98 | 0.08 / 1.00 | 1.46 |
| `H90` | 0.44 (692) | 0.42 / 0.75 (885) | 0.57 / 0.75 | 0.35 / 0.96 | 0.65 |
| `H180` | 0.47 (692) | 0.64 / 0.86 (885) | 0.53 / 0.87 | 0.25 / 0.98 | 0.95 |
| `H365` | 0.50 (692) | 0.81 / 0.81 (885) | 0.47 / 0.93 | 0.19 / 0.99 | 1.24 |
| `H730` | 0.59 (692) | 0.90 / 0.51 (885) | 0.28 / 0.97 | 0.11 / 1.00 | 1.09 |

The columns are defined as follows:
- **Split-half:** two alternating-game halves of the window at 2023-07-01, for players with at least 250 possessions per role in both halves (the #23 rule).
- **Year-over-year:** fits at 2022-07-01 and 2023-07-01.
- **Refit volatility:** consecutive cutoffs within a scored season.
- **Playoffs added:** the fit at the playoff cutoff against the fit at 1 July.

What the table shows:
- **Window length (Inferred).** Longer windows and slower decay give higher split-half reliability (0.41 for `W1` to 0.56 for `W5`) and much smaller refit and year-over-year changes. Most of the year-over-year gain is mechanical overlap. `W1`'s 0.36 is the only correlation between disjoint data, and it measures true persistence plus noise. Predictive accuracy does not follow stability: `W5` and `H730` are the most stable, and they score slightly worse than `W2`.
- **Exposure bands (`W2`).**
  - Split-half r is 0.12 for players under 2,000 on-court possessions, 0.24 for 2,000–5,000, 0.29 for 5,000–10,000 and 0.43 for 10,000 or more.
  - Year-over-year r is 0.59, 0.75, 0.70 and 0.73.
  - Year-over-year RMS change rises with exposure (0.60 to 1.20), because the ridge holds low-exposure players near zero. Across candidates, low-exposure estimates are the least reliable and the most shrunk.
- **Season type (`W2`).** Adding a season's playoffs moves totals by 0.03 to 0.18 RMS in 2021–22 and by 0.27 to 0.46 in 2022–23, rising with exposure. The 2022–23 shift is larger because the 1-July cutoff moves the two-season window. It drops 2020–21 playoff games as well as adding the 2022–23 playoffs. The playoff check scores are in the selection table: every candidate beats the league mean by less in the playoffs than in the regular season (Inferred: playoff rotations and matchups differ, and the sample is small).

## Sensitivity (maintainer requirement)

Each scenario removed rows from fitting and scoring and reran the full selection.

| Scenario | Selected | Δ vs league (scenario rows) | Primary `W2` rank | Rank correlation of candidates | `W2` refit minus `W2` full fit, same rows | Final-fit shift: RMS / r (players) | Baselines selected |
| --- | --- | --- | ---: | ---: | --- | --- | --- |
| Primary | `W2`, 4,000 / 8,000 | −16.24 (−19.25 to −13.20) | 1 | 1 | — | — | league `W1`, context `W1` |
| `exclude_2018_19` | `W2`, 4,000 / 8,000 | −16.24 (−19.25 to −13.20) | 1 | 0.93 | 0.00 (exactly) | 0 / 1 (715) | `W1`, `W1` |
| `exclude_2021_22` | `W2`, 4,000 / 8,000 | −13.54 (−17.29 to −10.10) | 1 | 0.86 (7 feasible) | +1.49 (−0.47 to +3.39) | 0.85 / 0.81 (548) | `H90`, `H180` |
| `exclude_overtime` | `W2`, 4,000 / 8,000 | −16.22 (−19.27 to −13.17) | 1 | 1.00 | +0.01 (−0.11 to +0.12) | 0.05 / 0.999 (715) | `W1`, `W1` |
| `exclude_no_livedata` | `W2`, 4,000 / 8,000 | −14.83 (−17.80 to −11.83) | 1 | 0.85 | +1.40 (+0.68 to +2.13) | 0 / 1 (715) | `W1`, `W1` |

**The selected configuration is the same in every scenario**: `W2` with the same penalties, first in each scenario's ranking.

- **`exclude_2018_19`** changes nothing for `W2`. A 730-day window never reaches 2018–19 from any development cutoff (the earliest cutoff is 2021-10-01), so the `W2` fits are identical. The scenario changes only the longer candidates (`W3`, `W5` and the decays), whose scores move by up to 0.4 units.
- **`exclude_no_livedata`** drops 2018–19 and 2019–20. For `W2` this removes 2019–20 from the 2021–22 folds. Those refits score 1.40 units worse (interval excludes zero). The weaker-verification season adds value rather than harm. The final 2023-07-01 fit is unchanged because its window starts in July 2021.
- **`exclude_2021_22`** removes a scored season and, for every 2022–23 fold, the most recent season of history. `W1` becomes infeasible (an empty window at the 2022-10-01 cutoff). `W2` stays first, and its 2022–23 refits score +1.49 (−0.47 to +3.39) against the full-data fits. The final fit moves the most of any scenario: RMS 0.85, r = 0.81, over 548 players in both fits. The baselines then prefer short decays. The 2022–23 scores (14,072 to 14,077) are not comparable to the primary pool, which also contains 2021–22.
- **`exclude_overtime`** removes 0.6% of possessions. It changes no ranking, and estimates move by 0.05 RMS (r = 0.999).

Interpretation (Inferred): the selection does not depend on the conditionally authorized seasons or on overtime. Within the `W2` reach, the conditional and weaker-verification seasons improve the folds that use them.

### Runtime and memory (development run)

- **Run.** 1,156 s wall, peak resident 3.10 GB (`/usr/bin/time -l`) on the maintainer's Apple-silicon Mac, Python 3.14.3, NumPy 2.5.5, SciPy 1.18.1, DuckDB 2.0.1. The run made 3,970 sparse fits. All converged (LSQR stop code 2), with 4 to 88 iterations (median 33) and a maximum condition estimate of 178.
- **Fits.** Median fit time was 0.24 s. The largest fit (1,066,152 rows, `W5`) took 0.67 s. Fit time totalled 1,077 s.
- **Per scenario.** Primary 353 s, `exclude_2018_19` 234 s, `exclude_2021_22` 105 s, `exclude_overtime` 295 s, `exclude_no_livedata` 165 s.

A representative single multi-season fit is therefore under a second and well under 1 GB of working data. The peak comes from holding seven candidate windows, the design and the fit log in one process.

## Outer validation (Phase 2)

Pending. The configuration is frozen in the [outer-validation addendum](rapm-multiseason-outer-addendum.md) before any 2023–24 or 2024–25 row is read.

## Deviations

1. **Pre-run protocol clarification.** A synthetic end-to-end test showed that `W1` has no fit rows at the 2022–23 opening cutoff under `exclude_2021_22`. The protocol gained a rule: a candidate with an empty window at any scored cutoff is infeasible in that scenario. The rule was committed in `ec4f127`, after the protocol commit `86790ae` and before the development run. It changes only the `exclude_2021_22` scenario, which marks `W1` infeasible.
2. **Split penalties without #77.** #77 is not merged. Separate penalties were selected here with the reference solver's two-penalty interface, using a one-pass coordinate search rather than a full grid.
