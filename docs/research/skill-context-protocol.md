# Frozen protocol: context for game-agnostic and game-optimized skill forecasts (2022–23)

**Status:** Frozen for [issue #33][issue] before any real-data evaluation. This file is committed before the evaluation code runs on private data. Any later change is a deviation and must be recorded in the [results](skill-context-2022-23.md) and handoff, not edited in here.

**Scope.** 2022–23 regular season and playoffs only, from the pinned `issue-5-v2` logs through the #62 loader, the #31 engine and the frozen #32 fits. The build refuses any appearance outside the 2022 season key or on a date on or after 2023-07-01, and never opens a 2023–24 or 2024–25 build (outer validation folds of the [evaluation contract](../validation-strategy.md)) or anything from 2025–26 (confirmatory holdout). No EPM output is read, and no context choice is tuned against EPM.

Labels follow [project plan §2](../PROJECT_PLAN.md#2-non-negotiable-research-rules). EPM names context families for Estimated Skills and a game-agnostic versus game-optimized split but does not publish their forms, covariates or inputs (**Documented** as open, [EPM-U07](epm-uncertainties.md)). Every form below is **Original** and every fitted result **Experimental**. The mode is a retrospective replay, as in [#32](skill-decay-protocol.md).

## Frozen base forecast (reused from #32)

The **game-agnostic** forecast is the #32 model of record, unchanged: for target block `Mk` (and `P`), the clock chosen in the #32 inner folds and the `F_{k-1}` half-life and shrinkage strength `(h, k)` of that clock, read from the private `issue-32-v1` `fits` and `clock_selection` tables. Nothing is refitted. The build reproduces the `issue-32-v1` `pred_model` for every outer row (tolerance `1e-9`) or fails. Folds, targets, exposure weights, the `loss_terms` likelihood, `common` and `cold` row sets and groups are the #32 definitions. Playoffs use the registered pooling convention and are scored apart.

## Pregame context inputs

Every input for a target on played date `t` uses only schedule facts of that game and box evidence from games dated strictly before `t`. The build records, for every row, the latest source date used and fails if any is on or after `t`.

| Input | Definition (per target row and statistic `s`) | Label |
| --- | --- | --- |
| `home` | 1 if the player's team is the home team (team log `home` flag, fixed by the schedule), else 0 | Original |
| `b2b` | 1 if the team's previous game (regular season or playoffs, pooled) was played the day before `t` | Original |
| `rest_days` | `min(d - 1, 4)` with `d` the days since the team's previous game. Unknown for a team's first game, which takes `b2b = 0`, `rest_days = 1` and is counted | Original |
| `opp` | Opponent defensive context, below | Original |
| `team` | Own-team context, below | Original |
| `trend` | League trend, below | Original |
| `age` | Not available. The pinned sources carry no birthdates. Recorded as a missing input, not tested | Missing input |

Rest comes from the schedule alone. It uses team game dates from the team log for games before `t` and nothing from the game itself. It is team rest, not player rest. Player layoffs are the #32 `post_layoff` group.

**Opponent allowed rate.** Over all earlier team-games of the opponent `O`, `N_a` and `D_a` are the summed numerator and exposure (weight units, as in #32) that opposing players produced against `O`. With `m` the #32 `league_to_date` rate for `t`, `K = 10 * D_t / G_t` where `D_t` and `G_t` are the league's summed exposure and team-games before `t`, the shrunk allowed rate is `a = (N_a + K m) / (D_a + K)`. The input is `opp = link(a) - link(m)`, with `link = log` for per-36 rates and `logit` for fractions (rates clipped to `[1e-3, 1 - 1e-3]` for fractions and floored at `1e-3` for per-36 rates). If no earlier league exposure exists the input is 0 and counted. It is not adjusted for the quality of the opponent's opponents, which is a limitation.

**Own-team rate.** The same construction with the player's own team's earlier team-games' own production (all its players, including the target player's earlier games): `team = link(a_team) - link(m)`.

**League trend.** `trend = link(r) - link(m)` with `r` the league rate over played dates in `[t - 28, t)`. When the window holds every earlier date, `trend = 0`.

## Context adjustment (fitted only on earlier blocks)

For one statistic and outer block, with frozen base prediction `b`:

```
eta = link(b) + beta_0 + sum_j beta_j z_j        prediction = link^-1(eta)
```

`z_j` are the selected inputs standardized with the mean and standard deviation of the fit rows (a column with zero spread is dropped). The adjustment is multiplicative for per-36 rates and a logit shift for fractions, which cannot leave `(0, 1)`. The coefficients minimize the #31 likelihood per unit exposure (binomial for fractions, Poisson for per-36) of the fit rows plus `0.5 * 0.001 * sum_j beta_j^2` (the intercept is not penalized), by `scipy.optimize.minimize` L-BFGS-B with analytic gradient, `maxiter=200`, `ftol=1e-12`. The ridge strength, `K`, the 28-day window and the input list are frozen here and are not tuned. The fit rows are the scorable regular-season targets in `M0` through `M_{k-1}`, with their base predictions from the same frozen block-`k` parameters. Outer blocks `M3`, `M4`, `M5` thus use `M0..M2`, `M0..M3` and `M0..M4`, and the playoff block uses `M0..M5`. Playoffs are never fitted on. The base parameters were tuned on the same earlier rows (in sample), so the context fit is conservative for the context terms. No target on or after a block's start date enters its fit.

## Variants

| Variant | Inputs | Role |
| --- | --- | --- |
| `agnostic` | none | the frozen #32 forecast |
| `recal` | intercept only | control for pure recalibration of the base |
| `add_trend`, `add_home`, `add_rest` (`b2b`, `rest_days`), `add_opp`, `add_team` | intercept plus one factor | individual ablation |
| `full` | all five factors | the matchup-specific (game-optimized) forecast |
| `drop_trend`, `drop_home`, `drop_rest`, `drop_opp`, `drop_team` | `full` minus one factor | leave-one-out ablation |

Aging is not a variant because its input is missing.

## Comparisons, groups and uncertainty

- **Primary set.** Regular-season outer blocks M3 to M5 pooled, on the #32 `common` rows (all six #31 baselines defined), per statistic. Deltas are variant minus reference in log loss per unit exposure (primary) and weighted MSE. Negative is better. References are `agnostic` for every variant, `recal` for the add-one variants and `full`, and `full` for the drop-one variants. The matchup-specific versus game-agnostic comparison is `full - agnostic`.
- **Per block.** Point deltas for M3, M4 and M5 separately. Playoffs are a separate scope.
- **Groups** (as in #32): `sparse_career`, `low_minute`, `post_layoff`, history 1–4, 5–19 and 20+, and `rookie_cold` (no covered history, where the agnostic forecast is the league rate, so context deltas there are the cold-start effect). `all` is the primary set.
- **Uncertainty.** Percentile bootstrap, 2,000 replicates, over games (seed `33033`) and, separately, over players (seed `33034`), for the pooled regular outer set and the playoffs. The statistic is the ratio `sum(delta) / sum(weight)`. One count matrix per clustering and scope is shared by all cells. Neither clustering captures serial dependence across a player's games or months fully, and the two are not combined.
- **Retention rule.** A factor is called useful for a statistic only if the `add_factor - agnostic` log-loss interval excludes zero on the negative side under both clusterings, and the point delta is negative in each of M3, M4 and M5. The same factor must also beat `recal` the same way, otherwise the gain is recalibration. A factor is called harmful by the mirror rule. Everything else is inconclusive. There is no multiplicity correction across 13 statistics and 11 variants, so the rule is a screen, not a confirmation.
- **Interpretation rule.** Single-season retrospective evidence. It licenses no claim about 2023–24 or later, and nothing here fixes a default. Outer seasons must be run under this protocol before any context is adopted.

## Validation of cutoffs and cold starts

- Every context input row carries the latest source date used. The run fails if any is on or after the game date, and the manifest counts defaults (unknown rest, no league exposure, no earlier opponent games).
- Synthetic tests check that adding or changing later games cannot move an earlier row's input or prediction, and that rest, back-to-back, opponent allowed rates and the trend use strictly earlier dates only.
- Cold rows (no covered history, or a team's first games) must stay finite and defined under every variant, and are scored as the `rookie_cold` group.

## Missing inputs (recorded, not tested)

Birthdates (aging), pregame injury and availability reports, announced starters, expected minutes or a minutes model, opponent rosters and rest, travel and time-zone distance, betting lines, and any independently timestamped pregame roster feed. The player logs omit DNPs, so a missing row cannot establish absence.

## As-of skill snapshot API

`bil.features.skill_snapshot.skill_snapshot(rows, params, as_of)` returns per player and statistic the shrunk-decay estimate, discounted numerator and exposure, league rate, covered games and prior appearances from appearances dated strictly before `as_of`, for the #62 feature codes (`bil.features.box.FEATURE_CODES`), with the frozen per-statistic `(clock, h, k)`. The build reproduces the `issue-32-v1` snapshots at the four block starts exactly. Context adjustments are not part of the snapshot: the SPM prior (#30) receives the game-agnostic skill. Tests align it with the #62 feature definitions and the `predict` state of a next-day appearance.

## Outputs

Private outputs go to a new directory `issue-33-v1`: `context_inputs` (per-row inputs and latest source dates), `coefficients`, `predictions`, `scores`, `snapshots` and a manifest recording the code commit, the SHA-256 of this protocol, input digests, defaults counts, reconciliation with #32, runtime and peak memory. The evaluation runs once from a clean tree at a committed revision. Committed reports carry aggregates only.

[issue]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/33
