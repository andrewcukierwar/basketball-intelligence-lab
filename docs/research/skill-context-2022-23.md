# Context for game-agnostic and game-optimized skill forecasts: 2022–23 results

**Issue:** [#33][issue]. **Protocol:** [frozen before the run](skill-context-protocol.md) at commit `9642a51` (SHA-256 `7b279184b35e5ace8dc4cc35fa7c49803464f956110ffd75d84119b62ed652e3`, recorded in the manifest). **Run:** one successful evaluation from a clean tree at code commit `9483a40b113282879836c3ad45816de89b33cdd9`, output `data/processed/2022-23/issue-33-v1` (private), `content_id` `e0ed313d9180...`. An earlier launch at commit `b6bb243` aborted at the output-writing step on a schema mismatch (level and delta score rows had different fields) before any table or manifest existed. The fix touched only the output schema, and nothing was read from that attempt. **Evidence class:** Experimental (EPM-U07), retrospective replay of a single season. No EPM output was read. Only 2022–23 appearances were loaded and the build refuses any other season. This page reports aggregates only.

## What was compared

The **game-agnostic** forecast is the frozen [#32](skill-decay-2022-23.md) model of record: the clock, half-life and shrinkage of each statistic and outer block, read from the private `issue-32-v1` fits. The build reproduced all 194,764 outer-block `pred_model` values exactly (0 mismatches) before any context was added. The **matchup-specific** (`full`) forecast moves that prediction on the link scale (log for per-36 rates, logit for fractions) by an intercept plus five standardized, ridge-penalized context terms, fitted only on targets in earlier blocks (`M0..M2`, `M0..M3`, `M0..M4`, `M0..M5` for the three regular outer blocks and the playoffs). The same split, targets, exposure weights, `common` row set and #31 likelihood as #32 are used. See the [protocol](skill-context-protocol.md) for the forms (**Original**; EPM names these context families but publishes no forms, **Documented** as open in EPM-U07).

| Context input | Definition | Result of the pregame-cutoff audit |
| --- | --- | --- |
| `trend` | league rate over the previous 28 days vs the to-date rate | strictly earlier dates |
| `home` | home flag from the schedule | schedule fact |
| `rest` | `b2b` and `rest_days` from the team's earlier game dates | schedule only |
| `opp` | opponent's as-of allowed rate (shrunk, 10 team-games of prior) vs league | strictly earlier dates |
| `team` | own team's as-of rate vs league | strictly earlier dates |
| `age` | not available | **missing input** |

Every one of 27,622 appearances carries the latest source date used, and the run failed on any date on or after the game. The count of violations was 0. Defaults (input set to 0 because nothing earlier exists) hit 45 appearances for each of `opp`, `team` and `trend` (the season's first date), and 329 appearances have unknown rest (each team's first game, taking `b2b = 0`, `rest_days = 1`). All 2,496 coefficient fits converged.

## Game-agnostic versus matchup-specific

Primary set: regular-season outer blocks M3 to M5 pooled, on the #32 `common` rows (7,996 to 14,216 rows per statistic, 684 games). Cells give `full - agnostic` log loss per unit exposure (×10⁻³, negative is better) with the game-clustered 95% bootstrap interval (2,000 replicates, seed 33033), whether the player-clustered interval (seed 33034) also excludes zero, and the change in exposure-weighted MSE as a percentage of the agnostic MSE.

| Statistic | `full` − agnostic, log loss ×10⁻³ (game 95%) | Player CI agrees | MSE change | `add_opp` − agnostic, log loss ×10⁻³ (game 95%) | Player CI agrees | MSE change |
| --- | --- | --- | --- | --- | --- | --- |
| `ast_per_36` | **−2.32** (−3.91, −0.78) | yes | −0.27% | **−2.05** (−3.10, −0.98) | yes | −0.28% |
| `blk_per_36` | **−4.33** (−6.11, −2.58) | yes | −0.88% | **−4.41** (−5.97, −2.88) | yes | −0.86% |
| `dreb_per_36` | −0.39 (−1.63, +0.90) | | −0.02% | **−0.90** (−1.75, −0.03) | no | −0.10% |
| `fg2_pct` | **−0.25** (−0.47, −0.02) | yes | −0.29% | **−0.31** (−0.50, −0.12) | yes | −0.36% |
| `fg3_pct` | −0.07 (−0.24, +0.10) | | −0.06% | −0.00 (−0.05, +0.04) | | −0.00% |
| `fg3_share` | **−0.32** (−0.58, −0.04) | yes | −0.62% | **−0.42** (−0.67, −0.16) | yes | −0.80% |
| `fga_per_36` | **−3.45** (−5.71, −1.24) | yes | −0.62% | **−4.63** (−6.69, −2.63) | yes | −0.80% |
| `ft_pct` | +0.24 (−0.12, +0.60) | | +0.20% | −0.01 (−0.10, +0.07) | | −0.01% |
| `fta_per_36` | **−3.97** (−7.38, −0.63) | yes | −0.46% | **−4.71** (−6.58, −2.78) | yes | −0.47% |
| `oreb_per_36` | **−1.81** (−3.56, −0.01) | no | −0.38% | **−2.14** (−3.57, −0.66) | yes | −0.39% |
| `pf_per_36` | **−1.32** (−2.45, −0.24) | yes | −0.22% | **−2.02** (−3.11, −0.99) | yes | −0.31% |
| `stl_per_36` | **−2.17** (−3.68, −0.63) | yes | −0.24% | **−2.06** (−3.24, −0.80) | yes | −0.23% |
| `tov_per_36` | **−7.43** (−10.61, −4.06) | yes | −0.83% | **−8.21** (−10.64, −5.68) | yes | −1.05% |

The matchup-specific forecast has lower log loss than the agnostic one for 12 of 13 statistics, with game-clustered intervals excluding zero for 10 (9 also under player clustering). Gains are small: MSE falls by 0.02% to 0.88% (median 0.29%), an order of magnitude below the 0.6% to 3.7% that the #32 decay model gained over the #31 baselines. The direction is consistent in all 13 statistics in M3, 12 in M4 and 10 in M5, so the gain shrinks over the season. No interval favors the agnostic forecast. Percentage statistics with sparse attempts (`fg3_pct`, `ft_pct`) show no context effect. **Experimental:** the single-factor opponent model captures about all of the gain for most statistics, as the right-hand columns show.

## Factor ablations

Each factor was added alone to the base (`add_*`, intercept included), compared with the agnostic forecast and with the intercept-only `recal` control, and removed from `full` (`drop_*`). A factor is **retained** for a statistic only under the frozen rule: the log-loss interval excludes zero on the negative side under both clusterings, the point delta is negative in each of M3, M4 and M5, and it passes the same test against `recal`. There is no multiplicity correction (13 statistics, 11 variants), so this is a screen.

| Factor | Statistics where `add_*` beats the agnostic forecast (rule vs agnostic) | Retained after also beating `recal` | Harms or is inconsistent |
| --- | --- | --- | --- |
| `opp` (opponent allowed rates) | 10: `ast`, `blk`, `fg2`, `fg3_share`, `fga`, `fta`, `oreb`, `pf`, `stl`, `tov` | **9** (all those except `pf`, which does not beat `recal` in every block) | none. `dreb` is better under game clustering only |
| `home` | 2: `pf`, `tov` | 0 (`recal` alone explains both) | `fga_per_36` worse (as `recal` is) |
| `rest` (`b2b`, `rest_days`) | 2: `pf`, `tov` | 0 | `dreb`, `fga` worse than agnostic; `fg3_share` worse than `recal` |
| `team` (own-team rate) | 1: `tov` | 0 | `fga` worse |
| `trend` (28-day league trend) | 0 | 0 | `fga` worse; `ast` better under both clusterings but not in every block |
| `age` | not testable: no birthdates | | |

Dropping a factor from `full` makes the log loss significantly worse (both clusterings, every block) for `opp` in 11 of 13 statistics (all except `fg3_pct` and `ft_pct`) and for `home` in `pf`. Dropping `rest` significantly improves `dreb` and `fg3_share`, so rest hurts them inside `full`. Dropping `trend` improves `fga` and `pf` in the pooled intervals but not in every block, and, for `ast`, worsens the pooled loss but not in every block. The intercept-only control `recal` itself improves `pf` (−0.92×10⁻³) and `tov` (−1.35×10⁻³) significantly and worsens `fga` (+0.78×10⁻³). The frozen #32 parameters were tuned on the same earlier rows, so these shifts show level drift in the base between early and later months, not context. Home, rest and team terms are therefore not separable from recalibration in 2022–23.

The fitted opponent coefficients (standardized, `M5` fit) are positive for all 13 statistics, 0.007 to 0.083 on the link scale per standard deviation of the opponent input (largest for `blk_per_36`, `fg3_share` and `tov_per_36`), and are near zero for `fg3_pct` and `ft_pct`. Home coefficients are at most 0.03 in absolute value with mixed signs.

## Groups, cold starts and playoffs

- **Sparse career, low minute, post-layoff** (regular outer, `full` versus agnostic, game-clustered). The `full` forecast has lower point log loss in 7, 10 and 1 of 13 statistics, and its game-clustered interval excludes zero in its favor for 2, 3 and 0 statistics (one sparse-career statistic is significantly worse). Group sizes are 105–457, 1,068–3,356 and 181–573 rows (88–666 games), so these are weak tests. The context terms do not rescue short histories or returns from layoffs.
- **Cold starts.** Rows with no covered history have the league rate as the agnostic forecast, so context changes it directly. The `full` forecast stays finite and defined for all 15–50 such rows per statistic, lowers log loss in only 3 of 13 statistics and has a median MSE change of +0.8%. With 12–43 games per statistic this is inconclusive. `add_opp` lowers the log loss in 6 of 13.
- **Playoffs** (84 games, 850 to 1,726 rows; the context was fitted on regular-season blocks only and applied unchanged). `full` is **worse** than the agnostic forecast for `ast_per_36` (+18.5×10⁻³), `fga_per_36` (+15.4×10⁻³), `pf_per_36` (+12.1×10⁻³) and `stl_per_36` (+27.0×10⁻³), with both clusterings excluding zero, and better for `dreb_per_36` (−6.6×10⁻³) and `fta_per_36` (−15.4×10⁻³). The rest are inconclusive. `add_opp` helps `dreb` and `fta` only. `add_rest` and `add_home` are each worse for `ast`, `fg2` and `pf`, and playoff rest and home patterns differ from the regular season they were fitted on. Regular-season context effects do not carry over to the playoffs here.

## As-of skill snapshot for the SPM prior (#30)

`bil.features.skill_snapshot.skill_snapshot(rows, params, as_of)` returns one row per player and #62 feature code (`FEATURE_CODES`, the 13 statistics in contract order) with the shrunk-decay `estimate` in the contract's own unit (fraction or per 36 minutes), its discounted numerator and exposure, the league rate, covered games and prior appearances, from appearances dated strictly before `as_of` only. `SkillParams(clock, half_life, k)` per statistic come from the #32 fits. It is the game-agnostic skill: context terms are not applied, since the SPM prior should not see game-level inputs. The build reproduced the 26,481 `issue-32-v1` snapshot rows at the four block starts (2023-01-01, 2023-02-01, 2023-03-01 and 2023-04-10; 489, 498, 511 and 539 players) to `1e-9` with 0 mismatches, and wrote them to the private `snapshots` table. Tests check that the codes and offense or defense groups match the #62 definitions, that with no shrinkage and no decay the estimate equals the #62 `aggregate` rate, that rewriting every game on or after `as_of` leaves the result unchanged, and that it equals the #32 prediction state of a game played on the as-of date.

## Missing inputs recorded

Birthdates (so no aging factor), pregame injury and availability reports, announced starters, expected minutes or a minutes model, opponent rosters and opponent rest, travel and time-zone distance, betting lines, and any independently timestamped pregame roster feed. The player logs omit DNPs, so absence cannot be established from them. Team rest is used, not player rest, and home comes from the schedule flag of the pinned team log.

## Limitations

- One season, retrospective, no strict cohort. Nothing here fixes a default or licenses a claim about 2023–24 or later. The outer seasons must be run under this protocol first.
- Opponent allowed rates are not adjusted for the opposing rosters the opponent faced, so they mix opponent quality with schedule strength. They also mix team defense with opponent roster changes. The gain is statistical, not a causal defensive-quality estimate (**Inferred**).
- The base parameters were fitted in sample on the earlier rows, and the `recal` control shows the base drifts for some statistics. Context terms that merely recalibrate are not credited as factors.
- No multiplicity correction. Single-season intervals ignore serial dependence across a player's games, and neither clustering covers it fully.
- Playoff results use regular-season-fitted coefficients on 84 games and show that they do not transfer.
- Expected-minutes, roster and starter inputs were not available, so the "game-optimized" forecast here is a context adjustment of a rate, not a lineup-aware forecast.

## Outputs, runtime and reproducibility

Private tables: `context_inputs` (27,622 appearances), `coefficients` (2,496), `predictions` (194,764 rows with all 13 variants and inputs), `scores` (18,612) and `snapshots` (26,481), plus the manifest (code commit, protocol SHA-256, input digests, defaults counts, reconciliations). The run took 18.5 s wall time (13.2 s evaluation) with 1.05 GB peak resident memory, on Python 3.14.3, NumPy 2.5.5, SciPy 1.18.1 and DuckDB 2.0.1. There is no random component except the two bootstrap seeds.

[issue]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/33
