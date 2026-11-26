# Team outcomes from frozen ratings and pregame minutes

**Registration:** [#39](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/39), committed before any team outcome is scored.

**Classification:**
- Original BIL design on the [validation contract](../validation-strategy.md) team-and-game row.
- Partial-history methodology replication, retrospective capture bound.

**Evidence type:** a **retrospective rolling-origin** evaluation.
- **Strict historical pregame evidence is unavailable.** No archived pregame availability, roster or receipt proves an origin preceded tip (#55 is blocked).
- **Oracle minutes are a separate, labelled diagnostic.** They never enter the main forecast path.
- **No EPM output is read.** The 2025–26 holdout is not read.

## 1. Cohort and inputs

- **Games:** every official regular-season (`002`) and playoff (`004`) game of 2021–22 through 2024–25 in the pinned NBA.com team logs. Both team rows must have points and dates. Play-in, Cup final and preseason are excluded and counted.
- **Truth:** the final home-minus-away margin, from the team logs' `pts`.
  - Games without exactly one home team are excluded from scoring and counted. These are the ADR-0017 neutral-site games.
  - Their box lines still enter minutes history.
- **Box logs:** player and team logs, pinned as in #30 (`LOG_PINS` 2020–2022) and the #36 addendum (2023, 2024). The 2020–21 logs serve only for opening-week fallbacks.
- **Ratings:** Expected impact v1 snapshots from the private `ratings.csv` of `issue-35-v1` (2021–22 and 2022–23) and `issue-36-v1` (2023–24 and 2024–25). Verify each against its manifest digest:
  - `issue-35-v1`: `db254b8c…e5d1`
  - `issue-36-v1`: `f74fc2a5…a131`
- **Rating at game date `D`:** the latest snapshot with `as_of ≤ D` in that season's run. Its fit rows are strictly before `as_of`.
- **Absent players:** a player absent from the snapshot gets that snapshot's cold rating. This is the prior of a player with no box history and no window rows, or 0 if no such player exists.

## 2. Pregame minutes (main path)

For team `T` and a game on `D`, use only box lines with played date `< D`:

1. **History.** Take `T`'s last 10 games of the current season. If there are none, take `T`'s last 10 games of the previous season.
2. **Candidates.** A candidate is a player with positive minutes for `T` in those games whose most recent earlier appearance, on any team, was for `T`. This is a roster heuristic built only from earlier box lines.
3. **Minutes.** Projected minutes are total minutes in those games divided by the number of games, rescaled so the team sums to 240.

No injury, availability or announced-lineup information is used. A player listed out still projects minutes. This is the registered no-availability baseline.

**Oracle diagnostic.** Use the game's own realized minutes, rescaled to 240. These are reported only in their own section, as `oracle_minutes`.

## 3. Predictions

- **Team net rating** per 100 possessions: `Σ_i (m_i / 48) · (O_i + D_i)`. Positive defense prevents points.
- **Raw input:** `x = (net_home − net_away) · pace / 100`. `pace` is the mean `poss` per team-game over the development-fold regular-season games.

**Models:**

| Name | Margin | Win probability |
| --- | --- | --- |
| `hca` | `a₀`: mean development home margin | `Φ(a₀ / σ₀)` |
| `team_rating` | `a + b·t`, where `t` is the home-minus-away difference from a ridge team-rating regression (below) | `Φ(margin / σ)` |
| `ei` | `a + b·x` with pregame minutes | `Φ(margin / σ)` |
| `ei_oracle_minutes` (diagnostic) | `a + b·x` with realized minutes, using `ei`'s calibration | `Φ(margin / σ)` |

**Team-rating baseline.** This is the contract's "earlier-games opponent-adjusted net rating with a simple schedule-aware update".
- Weighted ridge regression of the final margin on an unpenalized home indicator and ±1 team columns.
- Fit on games played before `D` within 365 days, weight `0.5^(age / h)`, ridge `λ` on team columns. Games without a single home team are left out of this fit.
- `(h, λ)` is chosen from `{30, 60, 120, 240} × {1, 4, 16}` by the development-fold margin RMSE of its uncalibrated predictions. Ties go to the smaller `h`, then the smaller `λ`.
- The home coefficient is not used in `t`.

**Calibration.**
- `(a, b)` per model comes from ordinary least squares of the final margin on the raw input over development-fold regular-season games.
- `σ` is the residual root mean square of that fit.
- These parameters are frozen before any evaluation-fold score.

## 4. Folds, metrics and uncertainty

- **Development folds:** 2021–22 and 2022–23. Calibration and the team-baseline grid are fitted here. Their in-sample scores are descriptive only.
- **Evaluation folds:** 2023–24 and 2024–25. All four seasons have already been scored at possession level, so this remains development evidence for M7 (see the [#36 addendum](expected-impact-outer-addendum.md)).
- **Metrics:** margin MAE and RMSE. Win log loss and Brier score. Calibration in 10 equal-count probability bins, with intercept and slope from a logistic regression of outcome on the logit of the prediction. Win accuracy is descriptive.
- **Reporting splits:** regular season and playoffs separately, and each evaluation season.
- **Uncertainty:** paired deltas of `ei` minus each comparator, using game-resampling and Monday-week-cluster bootstraps (2,000 resamples, seed 39).
- **Primary comparison:** `ei` minus `team_rating` on pooled evaluation regular-season margin RMSE and log loss.
  - `ei_better` on a metric needs the game interval to exclude 0 and the same sign in both seasons.
  - `ei_worse` is the mirror image. Anything else is inconclusive.
- **Oracle-minutes results** are reported separately and adjudicate nothing.

## 5. Coverage, leakage and artifacts

- **Counts reported:** games by status (scored, excluded and why); projected-minute shares on cold-rated players; opening-week previous-season fallbacks; roster-heuristic drops.
- **Synthetic tests.** Poisoning the target game's own box lines, or any later game's, leaves its pregame prediction unchanged. The oracle path is the only one that reads them.
- **Snapshot eligibility.** `as_of ≤ D` is asserted for every rating used.
- **Private artifacts:** frozen per-game predictions with inputs (projected minutes, ratings snapshot IDs and calibration), written before outcomes are joined. Aggregates only in the repository.
- **Freeze for M7.** The minutes rule, the calibration, the team baseline's `(h, λ)` and the metrics are frozen for the joint #42 registration.
