# Frozen protocol: stat-specific Estimated Skills decay and shrinkage (2022–23)

**Status:** Frozen for [issue #32][issue] before any real-data evaluation. This file is committed before the evaluation code runs on private data. Any later change is a deviation and must be recorded in the [results](skill-decay-2022-23.md) and handoff, not edited in here.

**Scope.** 2022–23 regular season and playoffs only, from the pinned `issue-5-v2` logs through the #62 loader and the #31 engine. The build refuses any appearance outside the 2022 season key or on a date on or after 2023-07-01. It never opens a 2023–24 or 2024–25 build (outer validation folds of the [evaluation contract](../validation-strategy.md)) or anything from 2025–26 (confirmatory holdout). No EPM output is read. The mode is a **retrospective replay**: the source has no revision or finalization evidence, so the strict cohort is empty, as recorded in [#31](skill-histories.md#frozen-opportunities-and-source-revisions).

Labels follow [project plan §2](../PROJECT_PLAN.md#2-non-negotiable-research-rules). EPM documents a per-stat exponential game weight `ρ^age`, tuned with Differential Evolution to predict the next game, with days or possessions as the age unit (**Documented**, [EPM-U05, EPM-U06](epm-uncertainties.md)). Everything else here is **Original** unless labeled otherwise, and every fitted result is **Experimental**.

## Targets, history and baselines (reused from #31)

Targets, exposure weights, history statuses, the `loss_terms` likelihood and the six baselines are exactly those of the [#31 contract](skill-histories.md), computed by `bil.features.skill_history.skill_rows`. The build recomputes them in process and must match the private `issue-31-v1` table on every regular-season row, or it fails.

**Playoff pooling convention (Original, registered here).** For this issue, a player's history pools regular-season and earlier playoff appearances on one clock, and the league reference for a playoff target pools all earlier regular-season and playoff dates of the season. It is implemented by passing the #31 engine a stream in which every appearance has season type `regular`, so the baselines for playoff targets are the same #31 forecasters under pooling. Regular-season rows are unaffected because no playoff game precedes them. Parameters are never fitted on playoff targets. Playoffs are scored as a separate, later outer block and reported apart from the regular season.

## Model

For player `p`, statistic `s` and target appearance `t`, with covered earlier appearances `g` (both components known), counts `n_g`, exposures `d_g` in weight units (attempts, or minutes divided by 36) and age `a(g, t)` on clock `c`:

```
N = Σ_g exp(-λ a(g, t)) n_g,   D = Σ_g exp(-λ a(g, t)) d_g,   λ = ln 2 / h
prediction = (N + k m) / (D + k)
```

`m` is the #31 `league_to_date` rate for the target's date (pooled as above). `h` is the half-life in clock units and `k` the shrinkage strength in exposure weight units. This is a gamma-Poisson or beta-binomial posterior mean with an exponentially discounted likelihood (**Original** form; EPM's stabilization is unpublished). With no covered history, or zero covered exposure, the prediction equals `m`, so the cold and rookie forecast is the league reference by construction. A row whose league reference is undefined (the first played date of the season) has no prediction and is excluded with reason `no_league_reference`.

### Clocks

| Clock | Age `a(g, t)` | Label |
| --- | --- | --- |
| `day` | played-date difference in days, `t - g` (at least 1) | Documented unit, Original convention |
| `games` | count of the player's appearances strictly between `g` and `t` (most recent game has age 0) | Original |
| `possessions` | estimated possessions the player was on court for in appearances strictly between `g` and `t` | Documented unit, Inferred estimate |

Every appearance advances the exposure clocks, even one not covered for the statistic. The day clock decays through layoffs, while the exposure clocks do not, which is the contrast the post-layoff group tests.

**Possession estimate (Inferred).** Box logs carry no on-court possessions (the contract excludes `poss`). For each team-game, `FGA + 0.44 FTA - OREB + TOV` summed over that team's player rows. Game possessions are the mean of both teams. A player's possessions are game possessions times the player's played milliseconds divided by one fifth of the team's summed played milliseconds. If a component is missing for either team, the fallback is `100 * minutes / 48`, and the count of fallbacks is recorded. A game's possessions only age games before it, and only targets after it, so the same-game box never reaches its own prediction.

## Loss, bounds, tying and optimizer

- **Loss (frozen).** The #31 `loss_terms` negative log-likelihood summed over scored rows and divided by summed exposure weight: binomial over attempts for `fg2_pct`, `fg3_pct`, `ft_pct` and `fg3_share`; Poisson over 36-minute units for the nine per-36 counts. Clipping is #31's `1e-3`. This is the tuning objective and the primary comparison metric. Exposure-weighted MSE is secondary.
- **Tying.** Each statistic and clock has its own `(h, k)`. Nothing is tied across statistics. Parameters are constant over the season.
- **Parameterization and bounds (frozen).** DE searches `(log10 h, log10 k)`. `log10 k` is in `[-2, 4]` for every statistic. `log10 h` is in `[0, 3.5]` days, `[0, 3]` games and `[1.5, 5]` possessions. The upper ends are effectively no decay within one season. An optimum within 0.01 of a bound is reported as a bound hit.
- **Optimizer (frozen).** `scipy.optimize.differential_evolution`, `strategy="best1bin"`, `popsize=15`, `maxiter=200`, `tol=1e-7`, `mutation=(0.5, 1)`, `recombination=0.7`, `init="latinhypercube"`, `polish=True`, `updating="deferred"`, `vectorized=True`. Seed `32000 + 100 * stat_index + 10 * clock_index + fit_index`, where `stat_index` is the position in `bil.features.box.FEATURES` and `clock_index` is 0, 1, 2 for day, games, possessions.

## Nested chronological folds

Played-date blocks (America/New_York, start included, end excluded):

| Block | Dates | Role |
| --- | --- | --- |
| M0 | 2022-10-18 to 2022-11-01 | tuning only |
| M1 | 2022-11-01 to 2022-12-01 | tuning only |
| M2 | 2022-12-01 to 2023-01-01 | tuning only |
| M3 | 2023-01-01 to 2023-02-01 | outer block 1 |
| M4 | 2023-02-01 to 2023-03-01 | outer block 2 |
| M5 | 2023-03-01 to 2023-04-10 | outer block 3 |
| P | 2023-04-10 to 2023-07-01, playoff games only | outer block 4 (reported separately) |

`F_j` is the fit on regular-season targets in `M0` through `Mj`. History always uses every strictly earlier appearance, but the tuning loss uses only targets in the fit window, so no target on or after a block's start date affects that block's parameters. For outer block `Mk` (and `P` as `k = 6`):

1. **Inner clock selection.** For each clock, score `F_{k-3}` on `M_{k-2}` and `F_{k-2}` on `M_{k-1}`, and pool the two inner losses. The clock with the lowest pooled inner loss is selected for the statistic in this block.
2. **Outer scoring.** Score `F_{k-1}` of every clock on block `k`. The selected-clock forecast is the model of record. The other clocks are reported for the clock comparison.

Fits needed per statistic and clock: `F_0` to `F_5`. Selection never sees an outer block's outcomes.

## Comparisons, groups and uncertainty

- **Primary set.** Regular-season outer blocks M3 to M5 pooled, on the #31 `common` rows (all six baselines and the model defined). Deltas are model minus baseline for each of `career_to_date` (equal to `season_to_date` with one season), `last_10`, `decay_30d`, `decay_90d` and `league_to_date`. Negative is better for the model. Per-block and playoff results are secondary.
- **Groups (pregame-defined).**
  - `rookie_cold`: no covered history for the statistic in the pooled stream. The model equals `league_to_date` here, so the delta is zero by construction and only the league loss is reported. A true rookie flag needs a draft or debut registry, which the pinned sources lack, so "rookie" means no history in the loaded season.
  - `sparse_career`: 1 to 9 earlier covered games for the statistic.
  - `low_minute`: mean played minutes over all earlier appearances below 15.
  - `post_layoff`: 10 or more days since the player's previous appearance.
  - History buckets 1–4, 5–19 and 20+ as in #31.
- **Clock comparison.** For each statistic, outer loss of each clock's `F_{k-1}` on the same rows, with deltas `day - possessions` and `day - games`.
- **Uncertainty.** Game-clustered percentile bootstrap, 2,000 replicates, seed `32032`, resampling the games of the scored set with replacement. The statistic is the ratio `Σ(loss_model - loss_baseline) / Σ weight` over resampled rows. One count matrix per scored set (regular outer, playoffs) is shared across statistics, baselines and groups. Player-level and temporal dependence across games is not captured.
- **Interpretation rule.** A difference is called better or worse only when the 95% interval excludes zero. Results are single-season retrospective evidence and do not license claims about 2023–24 or later.

## Exclusions and outputs

Every observed regular-season or playoff target in the outer blocks gets a reason when it is not in the primary set: `no_league_reference`, `rookie_cold`, `zero_exposure_history`, `last_10_zero_exposure` (or another undefined baseline). The build also classifies the 2,396 observed #31 targets that fall in neither its `common` nor `cold` set, from the `issue-31-v1` table.

Private outputs go to a new directory: fits (seed, window, cutoff, parameters, objective, evaluations, bound hits), clock selections, outer predictions, scores with intervals, exclusion counts, date-specific skill snapshots at each outer block's start (2023-01-01, 2023-02-01, 2023-03-01, 2023-04-10) with the parameters in force for that block, and a manifest recording the code commit, input digests, runtime and peak memory. The evaluation runs once from a clean tree at a committed revision. Committed reports carry aggregates only.

[issue]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/32
