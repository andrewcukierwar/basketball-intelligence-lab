# EI refresh cadence against the daily team rating: results (#129)

- **Issue:** [#129](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/129). [Registered protocol](refresh-cadence-protocol.md), SHA-256 `340eaede…69c2aa`.
- **Decision:** [ADR-0038](../DECISIONS.md#adr-0038--refresh-ei-at-least-weekly-on-court-refresh-closes-the-team-level-gap).
- **Evidence class:** **Experimental** development evidence on 2023–25, which #36, #39 and #136 had already examined.
  - #42's 2025–26 result stands as recorded.
  - No 2025–26 data was read, and nothing is compared with EPM.
- **Run:** `issue-129-v1`, from a clean worktree at commit `28246bb`.
  - Runtime 168 s and peak memory 1.95 GiB, on 2,621 scored games.
  - Private outputs are under `data/processed/team_outcomes/issue-129-v1`.

## Verdict

**Both finer cadences close the gap** under the registered criterion (protocol §3).

- **Daily refresh.** It improves EI's pooled 2023–25 regular-season margin RMSE by **−0.142 [−0.191, −0.091]** against block refresh. Its difference from the daily team rating falls from +0.142 to **−0.000 [−0.104, +0.098]**.
- **Weekly refresh.** It gives −0.127 [−0.175, −0.077] against block, and +0.014 [−0.093, +0.116] against the daily team rating.
- **Where the gain comes from.** It is entirely **on-court** refresh. Box refresh of the prior alone (`daily_box`) changes RMSE by +0.000 [−0.029, +0.029].

## Reproduction

Under the #135 as-of ratings, the block cadence reproduced three published values:

- the `issue-36-v1` possession predictions, with gap 0.0;
- the `issue-39-v1` EI margins, with gap 2.3e-6;
- the `issue-39-v1` team margins, with gap 5.0e-7.

This also confirms the #135 inference that the v2 artifact leaves the published #39 margins unchanged to 1e-6 in rating units.

## Game outcomes, frozen #39 calibration (matched)

**Refresh counts per season (2023–24 / 2024–25):** block 5 / 5, weekly 39 / 38, daily and daily_box 205 / 211.

**Pooled 2023–25 regular season:**

| Model | Margin RMSE | Log loss |
| --- | ---: | ---: |
| `ei_block` (#39) | 14.233 | 0.6149 |
| `ei_daily_box` | 14.233 | 0.6148 |
| `ei_weekly` | 14.106 | 0.6089 |
| `ei_daily` | **14.091** | **0.6082** |
| `team_block` | 14.415 | 0.6260 |
| `team_weekly` | 14.147 | 0.6122 |
| `team_daily` (#39 operational) | 14.091 | 0.6097 |

**Contrasts.** Each is model minus comparator, with the game interval and then the week interval. The verdict uses the #39 rule (game interval plus the sign in both seasons).

| Contrast | RMSE Δ | Game CI | Week CI | Log loss Δ (game CI) | RMSE verdict |
| --- | ---: | --- | --- | --- | --- |
| **`weekly_vs_block`** | −0.127 | [−0.175, −0.077] | [−0.195, −0.062] | −0.0059 [−0.0086, −0.0034] | ei_better |
| **`daily_vs_block`** | −0.142 | [−0.191, −0.091] | [−0.211, −0.075] | −0.0067 [−0.0094, −0.0039] | ei_better |
| **`weekly_vs_team_daily`** | +0.014 | [−0.093, +0.116] | [−0.115, +0.148] | −0.0008 [−0.0068, +0.0052] | inconclusive |
| **`daily_vs_team_daily`** | −0.000 | [−0.104, +0.098] | [−0.126, +0.125] | −0.0015 [−0.0074, +0.0041] | inconclusive |
| `box_refresh` (`daily_box − block`) | +0.000 | [−0.029, +0.029] | [−0.030, +0.034] | −0.0001 | inconclusive |
| `on_court_refresh` (`daily − daily_box`) | −0.142 | [−0.183, −0.101] | [−0.201, −0.090] | −0.0066 | ei_better |
| `block_vs_team_daily` (#39 gap) | +0.142 | [+0.018, +0.262] | [−0.021, +0.298] | +0.0052 | ei_worse |
| `daily_box_vs_team_daily` | +0.142 | [+0.020, +0.258] | [−0.009, +0.295] | +0.0051 | ei_worse |
| `block_vs_team_block` (matched cadence) | −0.182 | [−0.303, −0.060] | [−0.303, −0.056] | −0.0111 | ei_better |
| `weekly_vs_team_weekly` (matched cadence) | −0.041 | [−0.149, +0.062] | [−0.168, +0.086] | −0.0032 | inconclusive |
| `team_block_vs_team_daily` | +0.324 | [+0.228, +0.429] | [+0.200, +0.444] | +0.0163 | (team worse) |

**Per season.**

| Contrast | 2023–24 | 2024–25 |
| --- | ---: | ---: |
| Daily minus block | −0.158 | −0.126 |
| Weekly minus block | −0.134 | −0.120 |
| Daily minus team daily | −0.011 | +0.010 |

**Playoffs** (descriptive):

| Contrast | RMSE Δ |
| --- | ---: |
| Daily minus block | −0.028 |
| Weekly minus block | −0.061 |
| Daily minus team daily | +0.127 |
| Block minus team daily | +0.155 |

**Matched cadence.** At matched cadence, EI is better than the team rating at block refresh, and level with it at weekly refresh. The team rating loses more from slow refresh (+0.324) than EI does (+0.142). The #39 gap is therefore a cadence artifact.

## Possession outcomes

Possession MSE on all 2023–25 rows, regular season and playoffs pooled (445,204 possessions):

| Cadence | MSE | Δ vs block (game CI) | Week CI |
| --- | ---: | --- | --- |
| `block` | 14254.33 | — | — |
| `weekly` | 14251.36 | −2.97 [−4.00, −1.91] | [−4.24, −1.79] |
| `daily` | 14251.16 | −3.17 [−4.26, −2.10] | [−4.51, −1.91] |
| `daily_box` | 14253.49 | −0.84 [−1.66, −0.02] | [−1.62, −0.08] |

At possession level, box refresh helps a little. On-court refresh (`daily − daily_box`) adds −2.34 [−3.00, −1.66]. The regular-season gains are larger in 2023–24 (daily −4.17) than in 2024–25 (−2.43).

## Season-aware calibration (strict, 2024–25)

These are #136 post-freeze calibrations per cadence, fit on 2023–24 and scored on 2024–25.

| Cadence | EI slope `b` | Team slope `b` |
| --- | ---: | ---: |
| `block` | 1.097 | 1.000 |
| `weekly` | 1.103 | 1.006 |
| `daily` | 1.110 | 1.029 |
| `daily_box` | 1.101 | 1.029 |

The block EI slope matches #136.

**2024–25 margin RMSE, strict calibration (frozen calibration in parentheses):**

| Model | RMSE |
| --- | --- |
| `ei_block` | 14.148 (14.162) |
| `ei_weekly` | 14.021 (14.042) |
| `ei_daily` | 14.018 (14.036) |
| `team_daily` | 14.019 (14.027) |

**Strict contrasts.**

| Contrast | RMSE Δ | Game CI |
| --- | ---: | --- |
| Daily minus block | −0.130 | [−0.216, −0.050] |
| Weekly minus block | −0.128 | [−0.205, −0.055] |
| Daily minus team daily | −0.001 | [−0.158, +0.162] |

The season-aware calibration improves every model slightly and leaves the cadence conclusions unchanged.

## Coverage and runtime

**Cold minutes.** The mean projected-minute share on cold ratings is:

| Cadence | Cold share |
| --- | ---: |
| Block | 1.6% |
| Weekly | 0.12% |
| Daily and daily_box | 0.0% |

A finer refresh rates newly active players sooner.

**Runtime.** These are the times on this machine. A full EI refresh (window, context, prior and ridge) takes 0.45 to 0.49 s on average, with a maximum of 0.66 s. A box-only refresh takes 0.14 s. A daily season of about 210 refreshes is therefore about 95 s of fitting.

These times include the shared preparation step for every cadence. The per-cadence totals in `results.json` therefore double-count it when cadences share a date, and the 168 s wall clock is the authoritative total.

## Interpretation

- **Cause of the #39 gap.** EI's deficit to the daily team rating in #39 is explained by stale on-court information. It is not explained by the prior or by box refresh.
- **Recommendation.** Refreshing the on-court ridge at least weekly removes it. This supports a daily or weekly cadence for the #43 refresh, with sub-second refit cost.
- **Minutes and calibration.** Both were held fixed, so this isolates cadence. The pregame-minutes heuristic remains the shared limit.

## Limits

These are as registered:

- the evidence is development evidence on previously examined seasons;
- the penalties were tuned at block cadence;
- `daily_box` holds the block context coefficients;
- there is one strict-calibration season;
- there is no availability information;
- no confirmatory claim is made without a validated in-season possession source (#133) or a prospective registration.

All non-primary labels are exploratory and are not corrected for multiplicity.
