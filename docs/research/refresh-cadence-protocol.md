# EI refresh cadence against the daily team rating: registered protocol (#129)

- **Issue:** [#129](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/129)
- **Status:** Registered before any scored run of `bil.models.refresh_cadence`. The registration is the last commit that changes this file before the run.
- **Pre-registration plumbing check.** It used a reduced plan: block cutoffs for every cadence plus 15 daily cutoffs per season. It confirmed the reproduction gates in §4: possession gap 0.0, EI margin 2.3e-6 and team margin 5e-7. It also confirmed that the post-freeze machinery runs. The block-cadence post-freeze EI slope was 1.097, as in #136. No evaluation metric, delta or interval was computed.
- **Evidence class:** **Original** design. Results are **Experimental** development evidence.
  - 2023–24 and 2024–25 were already examined by #36, #39 and #136, and are reused as development evidence.
  - #42's 2025–26 result stands as recorded. No 2025–26 data is read and nothing is compared with EPM.
  - Any confirmatory claim needs a separately eligible holdout or prospective registration.

## 1. Question

#39 found EI's regular-season margin RMSE worse than the daily ridge team rating by +0.142 on 2023–25. EI refreshes five times a season, while the team rating refits every game day. This protocol asks whether a finer EI refresh closes that gap when everything else is held fixed. It also asks how much of any change comes from box refresh of the prior and how much from on-court refresh of the deviation.

## 2. Matched design

Everything except the refresh cadence is the frozen path:

- **EI model.** #36 EI: `W2` window, context offset, offense and defense penalties 8,000/8,000, the locked `final_contiguous_fit.json` SPM, and #36 rows and box-log pins. Ratings use the #135 as-of artifact construction (explicit cold priors).
- **Team outcomes.** #39 inputs: pregame minutes (the last 10 earlier team games and the roster heuristic), pace, cohort, games, and the team-rating configuration (half-life 60, ridge 4). These are read from the pinned `issue-39-v1` run.
- **Matched calibration.** The #39 frozen calibration (`a`, `b`, `σ` per source), applied unchanged to every cadence of that source. Minutes and calibration are therefore identical across cadences.

**EI cadences** in each season `S` ∈ {2023, 2024}. These are registered in advance, and no variant is selected:

| Cadence | Refresh dates `C` | Each refresh |
| --- | --- | --- |
| `block` | #36 cutoffs: 1 Oct, 1 Dec, 1 Feb, 1 Apr, first playoff day | Full #36 refit |
| `weekly` | 1 Oct and every Monday through the season's last game | Full refit: window, context, prior, deviation |
| `daily` | 1 Oct and every game day | Full refit |
| `daily_box` | Same as `daily` | The SPM prior from box logs before `C`. Deviation, context coefficients and intercept are held at the latest `block` fit on or before `C` |

- **Box versus on-court refresh.** `daily_box − block` isolates box refresh. `daily − daily_box` isolates on-court refresh.
- **Game-day rating.** A game on day `D` uses the latest refresh with `C ≤ D`. Every refit reads only rows and box lines strictly before `C`.
- **Possession scoring.** Each possession of `S` is scored by the refresh covering its date.

**Team-rating cadences:**

- **`team_daily`.** This is the #39 operational baseline and refits every game day.
- **`team_weekly` and `team_block`.** These refit at the weekly and block dates. They are the matched-cadence comparators.

## 3. Comparisons and decision rule

The metrics, bootstrap and verdict rule follow #39:

- **Metrics.** Margin RMSE and MAE, win log loss, Brier score, and calibration.
- **Uncertainty.** Paired deltas `model − comparator`, with game-resampling and Monday-week-cluster bootstraps (2,000 resamples, seed 39).
- **Verdict.** `ei_better` needs the pooled regular-season game interval below 0 and a negative delta in both seasons. `ei_worse` is the mirror case. Anything else is `inconclusive`.

| Contrast | Model − comparator | Role |
| --- | --- | --- |
| `weekly_vs_block`, `daily_vs_block` | `ei_weekly`/`ei_daily` − `ei_block` | **Primary**: cadence effect |
| `weekly_vs_team_daily`, `daily_vs_team_daily` | `ei_weekly`/`ei_daily` − `team_daily` | **Primary**: remaining gap |
| `box_refresh`, `on_court_refresh` | `ei_daily_box` − `ei_block`; `ei_daily` − `ei_daily_box` | Decomposition |
| `block_vs_team_daily`, `daily_box_vs_team_daily` | − `team_daily` | Reference: the #39 gap |
| `block_vs_team_block`, `weekly_vs_team_weekly` | Matched-cadence | Secondary |
| `team_block_vs_team_daily` | Team cadence effect | Secondary |

**Gap criterion.** A finer cadence **closes the gap** if both of these hold:

1. its `vs_block` RMSE verdict is `ei_better`;
2. its `vs_team_daily` RMSE verdict is not `ei_worse`.

Otherwise the frozen block-cadence baseline is retained and the negative result is reported.

**Other contrasts.** All other contrasts, the log-loss verdicts and all slices are exploratory and are not corrected for multiplicity.

**Dependence sensitivity.** The week-cluster interval of every contrast is reported as `below_zero`, `includes_zero` or `above_zero`, next to the game-interval verdict.

**Possession outcomes.** Possession MSE per cadence on all 2023–25 rows, pooled and by season and role. Each finer cadence is compared with `block`, and `daily` with `daily_box`, using `paired_delta` with game and week clusters.

**Season-aware calibration (separate comparison).** This uses the #136 post-freeze construction for each cadence:

- **Fit.** Examples are 2023–24 regular-season games with that cadence's raw inputs. The fit cutoff is 2024-07-01.
- **Parents.** New parents `ei:issue-129-v1-<cadence>` and `team_rating:issue-129-v1-<cadence>`, with outcomes through 2023-06-30. These are the #35 penalty and #39 team-configuration selections.
- **Loading.** Calibrations are loaded through `load_calibration`. `daily_box` pairs with `team_daily`.
- **Scoring.** 2024–25 only, beside the frozen-calibration scores of the same season. This part is descriptive.

**Coverage and runtime.** The report includes:

- the mean cold-minute share per cadence;
- refresh counts;
- seconds per refresh (mean, maximum, total) and peak memory, for #43.

## 4. Reproduction gates and leakage checks

The run stops before scoring unless the `block` cadence reproduces three published values:

- the `issue-36-v1` possession predictions, to 1e-6;
- the `issue-39-v1` EI margins, to 1e-4;
- the `team_daily` margins of `issue-39-v1`, to 1e-4.

The margin tolerance covers six-decimal rounding in the published CSV and the #135 artifact change. Every refit refuses a scored game inside its own window. Per-game predictions are written before outcomes are scored.

## 5. Limits

- **Minutes.** The pregame-minutes heuristic is unchanged and has no availability information. Cadence cannot fix minutes error.
- **Penalties.** They were selected at block cadence on 2021–23. Finer cadences are not re-tuned.
- **`daily_box` context.** It holds the block context coefficients, so context drift is attributed to on-court refresh.
- **Strict calibration.** It has one fit season, and scores only 2024–25.
- **Confirmatory claims.** 2025–26 in-season on-court replay needs a validated possession source (#133), so no confirmatory claim is made here.
