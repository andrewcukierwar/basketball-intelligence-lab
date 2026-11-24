# Player-game skill histories, exposure denominators and baselines

This document is the contract for [#31][issue], which turns the [box-score features](box-score-feature-contract.md) into player-game targets and strictly earlier baselines. It feeds the Estimated Skills fit in [#32][fit] and the context tests in [#33][context]. Claims are labeled **Original** (a BIL design choice) unless noted. The public EPM methodology specifies none of these definitions ([EPM-U05, EPM-U06](epm-uncertainties.md)). Nothing here reads EPM outputs, and no baseline parameter is tuned.

Only 2022–23 is loaded. Career-to-date therefore equals season-to-date in every row. The build asserts this and fails otherwise. The two diverge only after a second season is appended.

## Observation grain and as-of rule

The grain is the player observation `(game_id, player_id)` from the #62 loader, which keeps its team. For a target on played date `t` (America/New_York), every predictor uses only appearances with a played date strictly before `t`. Same-day games, including a second game by the same player, never reach each other or the league pool. The engine processes one date at a time and emits every row of that date before adding any of them. The target for statistic `s` in player-game `g` is that game's own observed numerator and denominator under the contract table, with rate `numerator * scale / denominator`.

**Original.** History is keyed by season type. A regular-season game sees only earlier regular-season games, and a playoff game sees only earlier playoff games, as in #62. Every player's first playoff game is therefore a no-history row (217 of them). Pooling regular-season history into playoff targets needs a registered convention and is left to #32.

## Rules by statistic

All thirteen features reuse `bil.features.box.FEATURES`. The numerator and opportunity (denominator) come from the contract table.

| Statistic | Numerator | Opportunity (exposure) | Weight in scoring |
| --- | --- | --- | --- |
| `fg2_pct` | `fgm - fg3m` | `fga - fg3a` | two-point attempts |
| `fg3_pct` | `fg3m` | `fg3a` | three-point attempts |
| `ft_pct` | `ftm` | `fta` | free-throw attempts |
| `fg3_share` | `fg3a` | `fga` | field-goal attempts |
| `fga_per_36`, `fta_per_36`, `ast_per_36`, `tov_per_36`, `oreb_per_36`, `dreb_per_36`, `stl_per_36`, `blk_per_36`, `pf_per_36` | matching count | played milliseconds | minutes divided by 36 |

Minutes are the only opportunity for the per-36 counts. They are box exposure, not possessions: the contract keeps the optional `poss` field out, so on-court possession, assistable-make and rebound-opportunity denominators are not available. A possession clock is compared in #32, not built here.

### Target and history statuses

Each `(player-game, statistic)` row has one target status and one history status.

| Target status | Meaning | Scored |
| --- | --- | --- |
| `observed` | both components known and denominator above zero | yes, with weight equal to the exposure |
| `zero_exposure` | both components known and denominator zero (for example no free-throw attempts, or zero minutes) | no. The rate is undefined and carries weight zero. The measured components still enter history |
| `missing_component` | numerator or denominator is null | no. The appearance is skipped for this statistic only |

| History status | Meaning | Baseline prediction |
| --- | --- | --- |
| `no_prior_history` | no earlier appearance of this player in the loaded seasons and season type | none. The league baseline is the only reference |
| `no_covered_history` | earlier appearances exist, none with both components for this statistic | none |
| `zero_exposure_history` | covered earlier appearances sum to a zero denominator | none. The ratio is undefined |
| `has_history` | positive summed denominator | defined for the player baselines |

**Rookie rule (Original convention).** A "rookie" here means no earlier appearance in the loaded data. With one season, veterans in their first 2022–23 game are indistinguishable from true rookies. True rookie status needs a draft or debut registry. Treat the cold cohort as "no prior history in the loaded seasons".

**Missing and zero values.** A valid zero numerator over a positive denominator is an observed zero and is a legitimate target and history value. A missing component is never treated as zero. A zero denominator is a known zero exposure, not missing. The player logs omit DNPs, so a missing row proves nothing about absence.

## Baselines

All are fixed ratio-of-sums forecasters that predict the game's rate for statistic `s`. None is tuned. They are reference points for #32.

| Baseline | History used | Weighting |
| --- | --- | --- |
| `career_to_date` | every earlier same-type appearance, any season | equal exposure weight (ratio of sums) |
| `season_to_date` | earlier same-type appearances in the target game's season | equal exposure weight |
| `last_10` | last 10 earlier appearances with both components known | ratio of sums over those games. Uncovered games take no slot |
| `decay_30d`, `decay_90d` | the career history | numerator and denominator each weighted by `0.5 ** (age_days / half_life)`, with a day clock |
| `league_to_date` | all players' earlier same-type appearances in the same season | equal exposure weight. A reference, and the only forecast for rows with no player history |

Day ages come from played dates, so a layoff or offseason lowers old games' weights automatically. The half-lives are fixed constants, not selections. Possession clocks, shrinkage and any fit belong to #32. A baseline is `null` whenever its summed (weighted) denominator is zero.

## Scoring

Realized targets are scored in chronological order of played date. The scorer rejects out-of-order input. Rows are scored only when the target is `observed`.

- **Weighted MSE.** `sum(w * (prediction - rate)^2) / sum(w)` with `w` the exposure in the table above, in rate units (per attempt or per 36 minutes).
- **Log loss.** Fractions use the binomial negative log-likelihood of makes within attempts. Per-36 rates use the Poisson negative log-likelihood of the count at `rate * minutes / 36`, without the constant `log(n!)` term, so values are comparable across baselines only. Predictions are clipped to `[0.001, 0.999]` for fractions and floored at `0.001` for per-36 rates, which penalizes a zero-history prediction finitely.
- **Cohorts.** The `common` set requires all six baselines to be defined, so the table is a like-for-like comparison. The `cold` set scores `league_to_date` on observed targets with no covered player history.
- **Slices.** `all`, calendar `month` and covered-game `history_games` bucket (1–4, 5–19, 20+) of the player's own history.

## Frozen opportunities and source revisions

`appearance_opportunities` freezes, per appearance, the SHA-256 of the validated source row, the earlier-appearance counts used by the baselines, the New York cutoff, and the strict-cohort count. The manifest records an opportunity digest over those fields, an appearance digest, per-table snapshot IDs bound to the source snapshot digest, the skill and feature versions, the fixed constants, and a `content_id` over the output digests.

- **Retrospective** (the baseline tables) uses the frozen later snapshot with an unrecorded historical-revision gap, as in #62. It is not forecast-origin evidence.
- **Strict** reuses `bil.evaluation.eligibility.resolve_revisions` through `strict_prior_counts`: availability must be known and no later than the cutoff, finalization before it, and the played date earlier. The 2022–23 logs carry only a 2026 capture bound and no finalization instants, so every appearance has zero strict predecessors. The 26,866 appearances with earlier retrospective history are marked `unavailable_historical_strict`, and the 756 first appearances match trivially. No strict baseline is built. If revision evidence appears, state would be rebuilt per cutoff, because strict eligibility need not be monotone across dates.
- **Source revision.** A changed source row changes the appearance digest, opportunity digest, snapshot IDs and content ID (tested). The build verifies the #62 manifest's source snapshot digest and its `appearances.parquet` digest, and requires the loaded appearances to equal that table row for row, using each row's content hash.

The build is gated on an independent DuckDB recomputation from the raw logs: career, season, last-N, both decays and league baselines for all thirteen statistics, every target, every `common`-set headline score, no player-day duplicates, career equal to season while one season is loaded, no strict history, and the #62 appearance match. Any mismatch fails the build and removes the output.

## Results on 2022–23 (retrospective, untuned)

Counts come from `data/processed/2022-23/issue-31-v1` (private; aggregates only here). The build used 27,622 appearances over 1,314 games and produced 359,086 `(player-game, statistic)` rows.

| Cohort coverage | Regular season | Playoffs |
| --- | --- | --- |
| Appearances | 25,894 | 1,728 |
| With earlier same-type history | 25,355 | 1,511 |
| Without (first appearance) | 539 | 217 |
| Players | 539 | 217 |
| Players with any history | 530 | 202 |
| Players only ever without history | 9 | 15 |
| Games | 1,230 | 84 |
| Games where no player has history | 14 | 8 |

Of the 359,086 feature rows, `has_history` plus `observed` target is 308,679 regular and 17,982 playoff. `no_prior_history` rows are 7,007 regular and 2,821 playoff, `zero_exposure_history` rows are 2,549 and 688, and `has_history` with a zero-exposure target are 18,387 and 973.

Weighted MSE on the regular-season `common` cohort (14,073 to 25,353 appearances per statistic). Lower is better, and bold marks the lowest value in each row. Career and season-to-date are identical with one season loaded.

| Statistic | Career/season | Last 10 | Decay 30d | Decay 90d | League |
| --- | --- | --- | --- | --- | --- |
| `ast_per_36` | 6.168 | 6.282 | **6.120** | 6.134 | 10.070 |
| `blk_per_36` | 1.266 | 1.319 | 1.273 | **1.265** | 1.487 |
| `dreb_per_36` | 8.523 | 8.827 | 8.534 | **8.504** | 11.259 |
| `fga_per_36` | 18.333 | 18.733 | **18.188** | 18.232 | 31.074 |
| `fta_per_36` | 10.484 | 10.814 | 10.482 | **10.459** | 13.990 |
| `oreb_per_36` | 3.167 | 3.305 | 3.188 | **3.166** | 4.222 |
| `pf_per_36` | 5.150 | 5.332 | 5.176 | **5.145** | 5.315 |
| `stl_per_36` | 1.878 | 1.959 | 1.890 | 1.877 | **1.817** |
| `tov_per_36` | 3.345 | 3.470 | 3.370 | **3.344** | 3.583 |
| `fg2_pct` | 0.0459 | 0.0487 | 0.0464 | 0.0459 | **0.0448** |
| `fg3_pct` | 0.0577 | 0.0613 | 0.0585 | 0.0578 | **0.0527** |
| `ft_pct` | **0.0502** | 0.0552 | 0.0508 | 0.0503 | 0.0506 |
| `fg3_share` | 0.0248 | 0.0253 | **0.0245** | 0.0246 | 0.0555 |

The league column wins `fg2_pct`, `fg3_pct` and `stl_per_36` and nearly ties `ft_pct`, which shows that unshrunk player-history shooting percentages are noisy at these sample sizes. That is a descriptive result motivating the #32 shrinkage question, not a tuned conclusion. None of these comparisons has a game-clustered uncertainty interval yet, so "wins" means lower point MSE only. Among player baselines, a decay baseline is best on 10 of 13 statistics and career on `fg2_pct`, `fg3_pct` and `ft_pct`. Last 10 is the worst player baseline on every statistic. Differences between career and decay are small (under about 1.5% on every row). For `fg3_pct`, the league baseline has lower MSE than the player baselines in all three history buckets, including 20 or more covered games (0.0516 against 0.0524 for career), and the gap is largest at 1–4 games (0.0558 against 0.0974). The cold cohort (5,831 regular-season rows with no player history, scored with the league baseline) has weighted MSE 0.0546 for `fg2_pct` and 9.39 for `ast_per_36`.

Playoff `common` rows (17,980) favor the league baseline on 7 of 13 statistics (`blk`, `fg2`, `fg3`, `ft`, `pf`, `stl`, `tov`), with only 1,511 appearances, so treat them as descriptive. Log-loss values are in the private `baseline_scores` table and the manifest. Poisson values are not comparable across statistics.

## Limitations and follow-ups

- Unscored observed targets: 1,243 regular-season and 1,153 playoff observed targets fall in neither the `common` nor the `cold` set. Most have zero-exposure history, a last-10 window with zero exposure, or are on the first playoff date. The manifest does not yet record exclusion reasons for them, which the evaluation contract asks for. This is tracked for #32.
- The `strict_rows_with_history` gate must be relaxed once a source with revision evidence exists.

- One season. Career equals season-to-date, and `common` does not yet see season-opening behavior. Append 2023–24 and 2024–25 only as outer validation folds, and never read 2025–26 (confirmatory holdout).
- Role, pace and expected-minutes context are outside this box baseline, and the retrospective gap is unrecorded.
- A true rookie flag, the season-type pooling convention for playoffs, shrinkage and decay fitting go to #32.
- Strict baselines wait for finalization evidence.

[issue]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/31
[fit]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/32
[context]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/33
