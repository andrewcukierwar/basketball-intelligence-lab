# Stat-specific skill decay and shrinkage: 2022–23 results

**Issue:** [#32][issue]. **Protocol:** [frozen before the run](skill-decay-protocol.md) at commit `4e25451`. **Run:** one evaluation from a clean tree at code commit `33fd3d09edc8abbc3a01e69fad3f2714188985f8`, output `data/processed/2022-23/issue-32-v1` (private), `content_id` `5dc36c1874aa...`. **Evidence class:** Experimental, retrospective replay of a single season. No EPM output was read. Only 2022–23 appearances were loaded, and the build refuses any other season. This page reports aggregates only.

## What was fitted

Per statistic and clock, `prediction = (N + k m) / (D + k)`: exponentially discounted earlier counts `N` and exposures `D`, shrunk toward the #31 league-to-date rate `m` with strength `k` in exposure units (attempts, or 36-minute units). Half-life `h` and `k` were fitted by Differential Evolution on the #31 likelihood, with frozen bounds and seeds. The day, games and estimated-possession clocks were compared, and the clock for each statistic and outer block was chosen on two earlier inner blocks. See the [protocol](skill-decay-protocol.md) for the model, folds and rules (**Original** form; EPM documents only the per-stat exponential weighting, DE and the day or possession ages, **Documented**).

**Gates passed.** Rerunning the #31 engine on the pooled stream reproduced all 336,622 regular-season `(player-game, statistic)` rows of the `issue-31-v1` build exactly (0 mismatches). No team-game needed the possession fallback. All 234 fits (13 statistics, 3 clocks, fits `F0` to `F5`) reported DE convergence.

## Selected parameters

Clock chosen in inner folds for outer blocks M3 (January), M4 (February), M5 (March to April 9) and P (playoffs), then the `F5` fit (all regular-season targets) of each clock as half-life / `k`. Half-lives are in days, the player's games, or estimated possessions. `(bound)` marks a half-life at the upper bound, meaning no decay within the season.

| Statistic | Clock by block (M3, M4, M5, P) | `F5`: day | `F5`: games | `F5`: possessions |
| --- | --- | --- | --- | --- |
| `ast_per_36` | games, possessions, possessions, day | 33.6 / 0.69 | 11.5 / 0.74 | 631 / 0.77 |
| `blk_per_36` | possessions, games, games, day | 108 / 2.36 | 38.0 / 2.39 | 2,391 / 2.47 |
| `dreb_per_36` | possessions, games, possessions, possessions | 57.5 / 1.25 | 19.8 / 1.30 | 1,081 / 1.33 |
| `fg2_pct` | day, possessions, possessions, day | 601 / 59.9 | 231 / 60.1 | 6,074 / 58.9 |
| `fg3_pct` | possessions, day, games, games | (bound) / 302 | (bound) / 300 | (bound) / 303 |
| `fg3_share` | possessions, possessions, games, games | 31.6 / 2.15 | 10.3 / 2.30 | 556 / 2.44 |
| `fga_per_36` | games, possessions, possessions, games | 30.4 / 0.56 | 10.5 / 0.61 | 579 / 0.63 |
| `ft_pct` | games, day, possessions, possessions | 251 / 24.1 | 97.8 / 24.4 | 5,129 / 24.5 |
| `fta_per_36` | games, possessions, possessions, possessions | 61.9 / 1.34 | 20.1 / 1.36 | 1,056 / 1.38 |
| `oreb_per_36` | possessions, possessions, day, day | 177 / 1.36 | 56.3 / 1.38 | 3,044 / 1.40 |
| `pf_per_36` | games, games, games, games | 93.4 / 2.79 | 29.6 / 2.84 | 1,727 / 2.93 |
| `stl_per_36` | games, possessions, possessions, games | 130 / 8.04 | 45.0 / 8.07 | 2,416 / 8.19 |
| `tov_per_36` | possessions, games, possessions, possessions | 88.6 / 2.83 | 32.6 / 2.88 | 1,781 / 2.93 |

Shrinkage strength is the most stable parameter. Across fits `F2` to `F5` its largest-to-smallest ratio is at most 1.27 for 11 statistics, 1.36 for `fg3_share` and 1.82 for `fg3_pct`. The three-point percentage is shrunk with about 300 to 550 attempts of league prior, two-point percentage with about 55 to 60, and free-throw percentage with about 24. Per-36 counts take 0.6 to 8 units of 36 minutes. Half-lives vary much more between fits and clocks, which means the loss surface is flat along the decay axis.

## Comparison with the #31 baselines

Primary set: regular-season outer blocks M3 to M5 pooled, on rows where every #31 baseline is defined (7,996 to 14,216 rows per statistic over 684 games). Each cell gives the change in exposure-weighted MSE as a percentage of the baseline's MSE, with a game-clustered 95% bootstrap interval (2,000 replicates, seed 32032). Bold means the interval excludes zero. The playoff block (850 to 1,726 rows, 84 games) pools regular-season history under the registered convention.

| Statistic | Regular vs decay 90d | Regular vs league | Playoffs vs decay 90d | Playoffs vs league |
| --- | --- | --- | --- | --- |
| `ast_per_36` | **−1.4%** (−2.0, −0.9) | **−42.1%** (−44.6, −39.7) | **−1.8%** (−3.3, −0.1) | **−36.6%** (−43.9, −29.2) |
| `blk_per_36` | **−1.0%** (−1.7, −0.4) | **−21.2%** (−23.8, −18.8) | −0.5% (−1.3, +0.2) | **−17.2%** (−23.4, −11.0) |
| `dreb_per_36` | **−1.5%** (−2.0, −1.0) | **−30.7%** (−32.5, −28.9) | **−0.9%** (−1.9, −0.0) | **−34.4%** (−40.2, −28.3) |
| `fg2_pct` | **−2.9%** (−3.7, −2.2) | **−5.3%** (−6.1, −4.5) | −0.4% (−1.4, +0.5) | **−2.9%** (−5.4, −0.3) |
| `fg3_pct` | **−3.5%** (−4.6, −2.6) | **−0.6%** (−0.8, −0.4) | **−2.1%** (−3.3, −0.9) | +0.3% (−0.7, +1.3) |
| `fg3_share` | **−1.8%** (−2.3, −1.3) | **−59.9%** (−61.7, −58.1) | **−2.1%** (−3.7, −0.5) | **−62.0%** (−67.8, −56.4) |
| `fga_per_36` | **−2.4%** (−3.2, −1.7) | **−42.4%** (−44.8, −40.2) | −1.4% (−3.1, +0.4) | **−41.7%** (−47.2, −36.2) |
| `ft_pct` | **−3.7%** (−5.0, −2.5) | **−10.6%** (−12.0, −9.1) | −0.9% (−2.6, +0.8) | **−13.0%** (−18.1, −8.0) |
| `fta_per_36` | **−1.5%** (−2.9, −0.6) | **−30.0%** (−32.4, −27.7) | **−2.1%** (−3.3, −0.9) | **−25.3%** (−32.8, −17.9) |
| `oreb_per_36` | **−1.4%** (−2.3, −0.7) | **−29.3%** (−31.5, −27.1) | +0.0% (−0.7, +0.7) | **−30.6%** (−37.3, −24.4) |
| `pf_per_36` | **−2.6%** (−3.7, −1.8) | **−10.8%** (−11.8, −9.7) | −0.2% (−1.0, +0.6) | **−9.3%** (−11.8, −6.8) |
| `stl_per_36` | **−2.3%** (−3.1, −1.6) | **−4.8%** (−5.5, −4.0) | **−1.0%** (−1.8, −0.1) | **−3.0%** (−5.3, −0.7) |
| `tov_per_36` | **−1.9%** (−3.0, −1.0) | **−13.9%** (−15.1, −12.7) | +0.1% (−0.5, +0.6) | **−18.0%** (−21.6, −14.2) |

On the primary log-loss metric, the model beats every #31 baseline (career, last 10, 30- and 90-day decay and league) on all 13 statistics, with intervals that exclude zero. It also has a lower point loss than each baseline in each of the three regular-season outer blocks separately. Against the strongest player baseline, the MSE gain is modest: 0.6% to 3.7% depending on the statistic and baseline. It is largest for shooting percentages, where the #31 player baselines lost to the league reference. The model now beats the league reference on those too, although for `fg3_pct` only by 0.6%. On the playoff log loss, the model beats `last_10` on 13 statistics, the league on 12, career on 8, the 30-day decay on 6 and the 90-day decay on 3. No interval favors a baseline.

### Groups (regular season, MSE change vs baseline)

| Statistic | Sparse vs decay 90d | Sparse vs league | Low-minute vs decay 90d | Low-minute vs league | Post-layoff vs decay 90d | Post-layoff vs league |
| --- | --- | --- | --- | --- | --- | --- |
| `ast_per_36` | **−18.6%** | **−23.9%** | **−4.8%** | **−22.0%** | −2.3% | **−29.7%** |
| `blk_per_36` | **−14.3%** | −3.1% | **−2.7%** | **−11.9%** | −2.0% | **−13.1%** |
| `dreb_per_36` | **−26.2%** | −5.7% | **−5.0%** | **−16.6%** | **−8.8%** | **−20.9%** |
| `fg2_pct` | **−40.6%** | +0.1% | **−8.9%** | **−4.2%** | **−13.1%** | −1.1% |
| `fg3_pct` | **−42.1%** | −0.0% | **−11.4%** | −0.2% | **−14.0%** | −0.1% |
| `fg3_share` | **−17.1%** | **−37.2%** | **−3.7%** | **−53.3%** | −3.9% | **−50.2%** |
| `fga_per_36` | **−28.9%** | **−12.9%** | **−5.9%** | **−25.1%** | **−13.1%** | **−33.2%** |
| `ft_pct` | **−54.3%** | +1.0% | **−10.4%** | **−9.9%** | −4.8% | **−9.3%** |
| `fta_per_36` | **−32.5%** | **−7.9%** | **−6.2%** | **−13.1%** | −2.4% | **−25.9%** |
| `oreb_per_36` | **−27.2%** | **−10.4%** | **−3.6%** | **−22.2%** | **−8.0%** | **−21.4%** |
| `pf_per_36` | **−29.3%** | **−4.9%** | **−6.5%** | **−6.9%** | **−5.1%** | **−9.8%** |
| `stl_per_36` | **−19.8%** | **−2.5%** | **−6.3%** | **−2.6%** | −6.4% | **−2.5%** |
| `tov_per_36` | **−33.7%** | −2.5% | **−7.1%** | **−4.6%** | **−6.7%** | **−8.7%** |

Group sizes (rows per statistic, games): sparse career (1 to 9 earlier covered games) 105–457 rows over 88–291 games; low-minute (earlier mean under 15 minutes) 1,068–3,356 over 494–666; post-layoff (10 or more days since the previous appearance) 181–573 over 145–314. All intervals are in the private `scores` table. In sparse histories, the model always beats the player baselines and never loses to the league reference. For sparse shooting percentages, it effectively equals the league reference. After a layoff, the 90-day decay difference is within the interval for 6 of 13 statistics.

**Rookie or cold group.** With no covered history the model returns the league rate, so its loss equals the league baseline's. Measured differences are below `3e-14`, which is floating-point noise. Bootstrap intervals that technically exclude zero in that group are artifacts of that noise, not findings. Regular-season outer blocks hold 15 to 50 such rows per statistic (12 to 43 games). True rookie status is not available: the pinned sources have no draft or debut registry, so this group means no history in the loaded season.

## Clock comparison

Over the pooled regular outer blocks (`common/all`), the day clock minus the possession clock and the day clock minus the games clock, in log loss per unit exposure, are within the 95% interval for 12 and 11 of 13 statistics. The exception is `fta_per_36`, where the day clock is worse than both possessions (+0.0035, interval +0.0021 to +0.0050) and games (+0.0018, +0.0009 to +0.0027), and `pf_per_36`, where it is worse than games (+0.0005, +0.0002 to +0.0008). The `fta_per_36` gap widens after layoffs and in low-minute players. In the playoffs, the day clock is better than both exposure clocks for `fga_per_36` and better than games for `fg3_pct`, and worse than games for `stl_per_36`. These are single-block findings over 84 games.

Inner-fold clock choice is unstable. Across the 39 regular-season (block, statistic) choices, possessions was chosen 21 times, games 14 and day 4. Only `pf_per_36` kept the same clock in all three regular blocks. The median spread of inner losses across clocks is `2e-4`. **Inferred:** with one season and the shrinkage term present, the data barely separate the clocks, except that a pure day clock underperforms for free-throw rate. The choice of clock per statistic remains open (EPM-U06) until the outer seasons are run. The inner-fold choice also costs accuracy for some statistics compared with a single fixed clock. For `ast_per_36`, the model's log loss is +0.00124 worse than the games clock (game-clustered 95% interval +0.00054 to +0.00194). For `tov_per_36`, the model's MSE is significantly worse than the possessions clock under player clustering. A fixed or tied clock may be preferable (independent review, **Original**).

## Failure cases and cautions

- **Bound hits.** 33 of 234 fits put the half-life at its upper bound (no decay): 19 of the 39 `F0` fits (two weeks of targets), and then 6, 3, 2, 0 and 3 for `F1` to `F5`. `fg3_pct` hits the bound for all three clocks in `F5`. Within one season, the best three-point model is the shrunk season-to-date rate. The upper bound is effectively "no decay", so this is a boundary solution, not a failed fit.
- **Flat decay surface.** Half-lives for the same statistic vary up to several-fold between consecutive fits (for example `tov_per_36` possessions from 58,132 in `F2` to 1,781 in `F5`), while losses barely change. Report half-lives with that uncertainty. They are not stable skill-aging constants.
- **Playoffs.** With 84 games, the model is no better than the 90-day decay for 10 of 13 statistics (intervals include zero) and has a higher point MSE than the best baseline for `fg3_pct` (league, +0.3%), `fga_per_36` (30-day, +0.3%), `oreb_per_36` and `tov_per_36` (90-day, under +0.1%). Playoff groups with 1–4 or 5–19 earlier games have 1 to 50 rows over at most 35 games. Their single- or few-cluster intervals are degenerate, so the apparent losses there are not evidence.
- **Log-loss clipping.** The #31 likelihood clips a zero rate prediction at `1e-3`, so sparse-history player baselines often take very large Poisson penalties. Log-loss deltas in the sparse and short-history groups are therefore dominated by those zero-rate cases. The MSE table above is the cleaner group comparison.
- **Dependence.** The bootstrap resamples games. It does not capture dependence of one player's rows across games or across months, so intervals are likely too narrow, especially for statistics dominated by a few high-minute players. The independent review reran the pooled regular-season comparisons with a player-clustered bootstrap (2,000 replicates). Every model-versus-baseline interval still excludes zero on both log loss and MSE for all 13 statistics. The sparse-career, post-layoff, low-minute and playoff group results were not rechecked under player clustering, and some groups span only 88–145 games. Treat their bolded cells as game-clustered only.

## Exclusions

Every outer-block `(target, statistic)` row has a recorded reason (private `exclusions` table). Regular season: 173,304 primary rows, 579 cold rows (scored against league only), 11,403 zero-exposure targets (unscorable), 108 with zero-exposure history and 90 whose last-10 window has zero exposure. Playoffs: 20,649 primary, 21 cold, 1,781 zero-exposure targets and 13 with a zero last-10 window. No outer-block row lacks a league reference.

**#31 unscored targets.** The 2,396 observed #31 targets outside its `common` and `cold` sets break down as follows. Regular season (1,243): 545 on the first date with no history and no league reference, 584 with zero-exposure history, 114 with a zero last-10 window. Playoffs (1,153): 973 on first playoff dates with no history and no league reference (the season-type keying), 178 with zero-exposure history, 2 with a zero last-10 window. Under this issue's pooling convention, every playoff target has a league reference and nearly all have player history.

## Outputs, runtime and reproducibility

Private tables: `fits` (seed, window, cutoff, parameters, objective, generations, bound hits), `clock_selection`, `predictions` (194,764 outer rows), `scores`, `exclusions` and `snapshots`. The snapshots hold date-specific skill estimates at 2023-01-01, 2023-02-01, 2023-03-01 and 2023-04-10 (489 to 539 players, 6,357 to 7,007 rows each), with the parameters in force for the following block. The manifest records inputs, frozen settings, seeds, the #31 reconciliation and runtime. The run took 109 seconds wall time (manifest: 109.1 s) (99 s fitting, 5 s scoring), with 1.10 GB peak resident memory, on Python 3.14.3, NumPy 2.5.5, SciPy 1.18.1 and DuckDB 2.0.1 (the local `uv` environment; CI uses Python 3.12). Seeds follow `32000 + 100 × stat_index + 10 × clock_index + fit_index`. Synthetic tests check seed reproducibility, and the real run was executed once.

## Limitations

- One season, retrospective. The strict cohort is empty for this source. None of this is forecast-origin evidence, and nothing here selects defaults for 2023–24 or later. The outer validation seasons (2023–24, 2024–25) must be run under this protocol before any choice is fixed. The 2025–26 holdout stays untouched.
- Career equals season-to-date with one season, so the model's decay is mostly tested within a season. The offseason gap, where day and exposure clocks differ most, is not exercised.
- Possessions are a box-score estimate (**Inferred**), not on-court possession counts.
- No context (opponent, pace, role, home) and no expected-minutes model. Targets condition on realized exposure, as in #31.

[issue]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/32
